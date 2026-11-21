"""Small Gaussian-process regressor for deterministic simulators.

Matern 5/2 kernel with one length scale per input (ARD), inputs in the unit
cube, output standardised, a small nugget for solver noise. Hyperparameters
maximise the log marginal likelihood (L-BFGS-B with restarts). Closed-form
leave-one-out residuals give the Q2 accuracy measure without refitting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import cho_factor, cho_solve, solve_triangular
from scipy.optimize import minimize

LOG_LENGTH_BOUNDS = (math.log(0.02), math.log(20.0))
LOG_SIGNAL_BOUNDS = (math.log(0.05), math.log(20.0))
LOG_NOISE_BOUNDS = (math.log(1e-10), math.log(1e-1))
SQRT5 = math.sqrt(5.0)


class GPError(RuntimeError):
    """Raised for an unusable training set or a failed factorisation."""


def matern52(x1: np.ndarray, x2: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Matern 5/2 correlation between two point sets (unit signal variance)."""
    diff = (x1[:, None, :] - x2[None, :, :]) / lengths
    r = np.sqrt(np.maximum(np.sum(diff * diff, axis=-1), 0.0))
    return (1.0 + SQRT5 * r + 5.0 / 3.0 * r * r) * np.exp(-SQRT5 * r)


@dataclass
class GaussianProcess:
    """Gaussian-process regression of one scalar output.

    Fit with :meth:`fit`; inputs must already be scaled to ``[0, 1]``.
    """

    restarts: int = 4
    seed: int = 0
    log_params: np.ndarray | None = None
    _x: np.ndarray = field(default=None, init=False, repr=False)
    _y: np.ndarray = field(default=None, init=False, repr=False)
    _y_mean: float = field(default=0.0, init=False, repr=False)
    _y_std: float = field(default=1.0, init=False, repr=False)
    _chol: tuple = field(default=None, init=False, repr=False)
    _alpha: np.ndarray = field(default=None, init=False, repr=False)

    # -- hyperparameters ----------------------------------------------------
    def _unpack(self, theta: np.ndarray) -> tuple[np.ndarray, float, float]:
        dim = self._x.shape[1]
        return np.exp(theta[:dim]), math.exp(theta[dim]), math.exp(theta[dim + 1])

    def _covariance(self, theta: np.ndarray) -> np.ndarray:
        lengths, signal, noise = self._unpack(theta)
        k = signal * matern52(self._x, self._x, lengths)
        k[np.diag_indices_from(k)] += noise + 1e-10 * signal
        return k

    def _neg_log_likelihood(self, theta: np.ndarray) -> float:
        try:
            factor = cho_factor(self._covariance(theta), lower=True)
        except np.linalg.LinAlgError:
            return 1e25
        alpha = cho_solve(factor, self._y)
        return float(
            0.5 * self._y @ alpha
            + np.sum(np.log(np.diag(factor[0])))
            + 0.5 * len(self._y) * math.log(2 * math.pi)
        )

    def _bounds(self) -> list[tuple[float, float]]:
        dim = self._x.shape[1]
        return [LOG_LENGTH_BOUNDS] * dim + [LOG_SIGNAL_BOUNDS, LOG_NOISE_BOUNDS]

    # -- public API ---------------------------------------------------------
    def fit(
        self, x: np.ndarray, y: np.ndarray, optimise: bool = True
    ) -> GaussianProcess:
        """Fit to ``x`` (n x d, unit cube) and ``y`` (n,).

        Args:
            x: Training inputs scaled to ``[0, 1]``.
            y: Training outputs.
            optimise: Re-optimise hyperparameters; otherwise reuse the last.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        if x.ndim != 2 or len(x) != len(y):
            raise GPError("x must be n x d and y must have n values")
        if len(y) < 3:
            raise GPError("need at least 3 training points")
        if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
            raise GPError("training data must be finite")
        self._x = x
        self._y_mean = float(np.mean(y))
        spread = float(np.std(y))
        self._y_std = spread if spread > 1e-12 * max(1.0, abs(self._y_mean)) else 1.0
        self._y = (y - self._y_mean) / self._y_std

        dim = x.shape[1]
        if self.log_params is None or len(self.log_params) != dim + 2:
            self.log_params = np.array([math.log(0.3)] * dim + [0.0, math.log(1e-6)])
            optimise = True
        if optimise:
            rng = np.random.default_rng(self.seed + len(y))
            bounds = self._bounds()
            starts = [self.log_params] + [
                np.array([rng.uniform(lo, hi) for lo, hi in bounds])
                for _ in range(self.restarts)
            ]
            best = (self._neg_log_likelihood(self.log_params), self.log_params)
            for start in starts:
                result = minimize(
                    self._neg_log_likelihood,
                    start,
                    method="L-BFGS-B",
                    bounds=bounds,
                )
                if result.fun < best[0]:
                    best = (float(result.fun), np.asarray(result.x))
            self.log_params = best[1]
        try:
            self._chol = cho_factor(self._covariance(self.log_params), lower=True)
        except np.linalg.LinAlgError as exc:
            raise GPError("covariance matrix is not positive definite") from exc
        self._alpha = cho_solve(self._chol, self._y)
        return self

    @property
    def fitted(self) -> bool:
        """True after a successful :meth:`fit`."""
        return self._alpha is not None

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posterior mean and standard deviation at ``x`` (unit cube)."""
        if not self.fitted:
            raise GPError("fit the model first")
        x = np.atleast_2d(np.asarray(x, dtype=float))
        lengths, signal, _ = self._unpack(self.log_params)
        k_star = signal * matern52(x, self._x, lengths)
        mean = k_star @ self._alpha
        v = solve_triangular(self._chol[0], k_star.T, lower=True)
        var = np.maximum(signal - np.sum(v * v, axis=0), 1e-14)
        return (
            mean * self._y_std + self._y_mean,
            np.sqrt(var) * self._y_std,
        )

    def loo_q2(self) -> float:
        """Leave-one-out Q2 (1 is perfect, 0 is no better than the mean)."""
        if not self.fitted:
            raise GPError("fit the model first")
        k_inv = cho_solve(self._chol, np.eye(len(self._y)))
        residuals = self._alpha / np.diag(k_inv)
        total = float(np.sum((self._y - np.mean(self._y)) ** 2))
        if total <= 0:
            return 1.0
        return 1.0 - float(np.sum(residuals**2)) / total

    def length_scales(self) -> np.ndarray:
        """Fitted ARD length scales in unit-cube coordinates."""
        if self.log_params is None:
            raise GPError("fit the model first")
        return np.exp(self.log_params[: len(self.log_params) - 2])

    def state(self) -> dict:
        """Serialisable state (training data plus hyperparameters)."""
        if not self.fitted:
            raise GPError("fit the model first")
        return {
            "x": self._x.tolist(),
            "y": (self._y * self._y_std + self._y_mean).tolist(),
            "log_params": self.log_params.tolist(),
        }

    @classmethod
    def from_state(cls, state: dict) -> GaussianProcess:
        """Rebuild a fitted model from :meth:`state` without re-optimising."""
        gp = cls(log_params=np.asarray(state["log_params"], dtype=float))
        return gp.fit(np.asarray(state["x"]), np.asarray(state["y"]), optimise=False)
