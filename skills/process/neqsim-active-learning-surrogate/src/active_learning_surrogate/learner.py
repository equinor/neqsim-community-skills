"""Active-learning surrogate of an expensive simulation.

The learner starts from a small Latin-hypercube design, fits one Gaussian
process per output and then asks the simulator for one new point at a time,
chosen where the surrogate is least certain about what matters:

``global``
    The candidate with the largest predictive standard deviation (summed over
    outputs, each scaled by its spread). Stops when every output's
    leave-one-out Q2 reaches ``1 - tolerance``.

``limit_state``
    Learns where one output crosses a threshold (a capacity limit, a
    specification). Uses the AK-MCS learning function of Echard et al. (2011),
    ``U = |mean - threshold| / std``, and stops when every candidate has
    ``U >= u_stop`` - the sign of ``output - threshold`` is then known with
    at least ``Phi(u_stop)`` confidence everywhere in the candidate pool.

Failed simulations (an exception or a non-finite output) are recorded and
their neighbourhood is excluded from later picks, so a flowsheet that does not
converge in one corner does not stall the study.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import erf

from .gp import GaussianProcess

Model = Callable[[dict[str, float]], Mapping[str, float]]


class SurrogateError(RuntimeError):
    """Raised for invalid set-up or an unusable result."""


@dataclass(frozen=True)
class Parameter:
    """An input of the simulation with its range.

    Attributes:
        name: Input name passed to the model.
        low: Lower bound in engineering units.
        high: Upper bound in engineering units.
        log: Sample and model on a log scale (for inputs spanning decades).
    """

    name: str
    low: float
    high: float
    log: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise SurrogateError("parameter needs a name")
        if not (math.isfinite(self.low) and math.isfinite(self.high)):
            raise SurrogateError(f"{self.name}: bounds must be finite")
        if not self.high > self.low:
            raise SurrogateError(f"{self.name}: high must exceed low")
        if self.log and self.low <= 0:
            raise SurrogateError(f"{self.name}: log scale needs low > 0")

    def to_unit(self, value: float) -> float:
        """Engineering value to the unit interval."""
        if self.log:
            return (math.log(value) - math.log(self.low)) / (
                math.log(self.high) - math.log(self.low)
            )
        return (value - self.low) / (self.high - self.low)

    def from_unit(self, u: float) -> float:
        """Unit-interval coordinate to an engineering value."""
        if self.log:
            return math.exp(
                math.log(self.low) + u * (math.log(self.high) - math.log(self.low))
            )
        return self.low + u * (self.high - self.low)


def latin_hypercube(n: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    """``n`` stratified points in the ``dim``-dimensional unit cube."""
    if n < 1 or dim < 1:
        raise SurrogateError("n and dim must be >= 1")
    points = (rng.random((n, dim)) + np.arange(n)[:, None]) / n
    for column in range(dim):
        points[:, column] = rng.permutation(points[:, column])
    return points


@dataclass
class IterationRecord:
    """Learning-curve entry after each new evaluation."""

    evaluations: int
    failures: int
    q2: dict[str, float]
    min_u: float | None
    elapsed_s: float


@dataclass
class Surrogate:
    """A fitted multi-output surrogate in engineering units."""

    parameters: list[Parameter]
    outputs: list[str]
    models: dict[str, GaussianProcess]
    threshold: tuple[str, float] | None = None

    def _unit(self, values: Mapping[str, float] | Sequence[Mapping[str, float]]):
        rows = [values] if isinstance(values, Mapping) else list(values)
        try:
            return np.array(
                [
                    [p.to_unit(float(row[p.name])) for p in self.parameters]
                    for row in rows
                ]
            )
        except KeyError as exc:
            raise SurrogateError(f"missing input {exc}") from exc

    def predict(
        self, values: Mapping[str, float] | Sequence[Mapping[str, float]]
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """Mean and standard deviation per output for one or many input sets."""
        unit = self._unit(values)
        return {name: self.models[name].predict(unit) for name in self.outputs}

    def predict_mean(self, values: Mapping[str, float]) -> dict[str, float]:
        """Mean prediction for one input set, as plain floats."""
        return {
            name: float(mean[0]) for name, (mean, _) in self.predict(values).items()
        }

    def extrapolating(self, values: Mapping[str, float]) -> list[str]:
        """Names of inputs outside the trained range."""
        return [
            p.name
            for p in self.parameters
            if not 0.0 <= p.to_unit(float(values[p.name])) <= 1.0
        ]

    def as_model(self, output: str) -> Callable[[dict[str, float]], float]:
        """A ``dict -> float`` callable, e.g. for ``UncertaintyStudy(model=...)``."""
        if output not in self.models:
            raise SurrogateError(f"unknown output {output!r}")

        def model(values: dict[str, float]) -> float:
            return float(self.models[output].predict(self._unit(values))[0][0])

        return model

    def exceedance_probability(
        self,
        samples: Sequence[Mapping[str, float]],
        output: str | None = None,
        threshold: float | None = None,
    ) -> float:
        """Fraction of ``samples`` whose predicted output exceeds the threshold.

        Each sample contributes ``Phi((mean - threshold) / std)``, so surrogate
        uncertainty near the boundary is carried into the probability.
        """
        if output is None or threshold is None:
            if self.threshold is None:
                raise SurrogateError("give output and threshold")
            output, threshold = self.threshold
        mean, std = self.models[output].predict(self._unit(samples))
        z = (mean - threshold) / np.maximum(std, 1e-300)
        return float(np.mean(0.5 * (1.0 + erf(z / math.sqrt(2.0)))))

    def to_json(self, path: str | Path | None = None) -> str:
        """Serialise to JSON (and write ``path`` when given)."""
        payload = {
            "format": "neqsim-active-learning-surrogate/1",
            "kernel": "matern52-ard",
            "parameters": [asdict(p) for p in self.parameters],
            "outputs": self.outputs,
            "threshold": list(self.threshold) if self.threshold else None,
            "models": {name: gp.state() for name, gp in self.models.items()},
        }
        text = json.dumps(payload)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    @classmethod
    def from_json(cls, text_or_path: str | Path) -> Surrogate:
        """Load a surrogate written by :meth:`to_json`."""
        text = str(text_or_path)
        if not text.lstrip().startswith("{"):
            text = Path(text_or_path).read_text(encoding="utf-8")
        payload = json.loads(text)
        if payload.get("format") != "neqsim-active-learning-surrogate/1":
            raise SurrogateError("not a neqsim-active-learning-surrogate file")
        threshold = payload.get("threshold")
        return cls(
            parameters=[Parameter(**p) for p in payload["parameters"]],
            outputs=list(payload["outputs"]),
            models={
                name: GaussianProcess.from_state(state)
                for name, state in payload["models"].items()
            },
            threshold=(threshold[0], float(threshold[1])) if threshold else None,
        )


@dataclass
class LearningResult:
    """Outcome of :meth:`ActiveLearner.run`."""

    surrogate: Surrogate
    converged: bool
    stop_reason: str
    evaluations: int
    failures: int
    history: list[IterationRecord]
    samples: list[dict[str, float]]
    responses: list[dict[str, float]]
    failed_samples: list[dict[str, float]]
    model_time_s: float
    mode: str

    def summary(self) -> dict[str, Any]:
        """Compact JSON-safe summary for reports."""
        last = self.history[-1] if self.history else None
        return {
            "calculation_basis": "neqsim-java surrogate",
            "mode": self.mode,
            "converged": self.converged,
            "stop_reason": self.stop_reason,
            "evaluations": self.evaluations,
            "failures": self.failures,
            "model_time_s": round(self.model_time_s, 3),
            "q2": last.q2 if last else {},
            "min_u": last.min_u if last else None,
            "threshold": (
                list(self.surrogate.threshold) if self.surrogate.threshold else None
            ),
        }


@dataclass
class ActiveLearner:
    """Build a surrogate of ``model`` with as few evaluations as possible.

    Attributes:
        model: ``dict[name, value] -> mapping[output, value]``. Wrap the NeqSim
            flowsheet here; raise or return NaN on non-convergence.
        parameters: Inputs and their ranges.
        outputs: Output names to learn.
        mode: ``"global"`` or ``"limit_state"``.
        limit_output: Output whose threshold crossing is learned
            (``limit_state`` only).
        threshold: Threshold value in the output's units.
        tolerance: ``global`` stop when every output has Q2 >= 1 - tolerance.
        u_stop: ``limit_state`` stop when min U over the pool >= u_stop.
        initial_samples: Size of the starting design (default 2*d + 2, min 6).
        max_evaluations: Hard budget of model calls, failures included.
        pool_size: Candidate points the next sample is chosen from.
        patience: Consecutive iterations the stop criterion must hold.
        seed: Random seed (designs and pool are reproducible).
    """

    model: Model
    parameters: Sequence[Parameter]
    outputs: Sequence[str]
    mode: str = "global"
    limit_output: str | None = None
    threshold: float | None = None
    tolerance: float = 0.01
    u_stop: float = 2.0
    initial_samples: int | None = None
    max_evaluations: int = 60
    pool_size: int = 3000
    patience: int = 2
    seed: int = 42
    callback: Callable[[IterationRecord], None] | None = None
    _gps: dict[str, GaussianProcess] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.parameters = list(self.parameters)
        self.outputs = list(self.outputs)
        if not self.parameters:
            raise SurrogateError("give at least one parameter")
        if not self.outputs:
            raise SurrogateError("give at least one output")
        names = [p.name for p in self.parameters]
        if len(set(names)) != len(names):
            raise SurrogateError("parameter names must be unique")
        if self.mode not in ("global", "limit_state"):
            raise SurrogateError("mode must be 'global' or 'limit_state'")
        if self.mode == "limit_state" and (
            self.limit_output not in self.outputs or self.threshold is None
        ):
            raise SurrogateError(
                "limit_state needs limit_output (one of outputs) and threshold"
            )
        if not 0 < self.tolerance < 1:
            raise SurrogateError("tolerance must be within 0-1")
        if self.u_stop <= 0:
            raise SurrogateError("u_stop must be > 0")
        dim = len(self.parameters)
        if self.initial_samples is None:
            self.initial_samples = max(2 * dim + 2, 6)
        if self.initial_samples < 3:
            raise SurrogateError("initial_samples must be >= 3")
        if self.max_evaluations < self.initial_samples:
            raise SurrogateError("max_evaluations must be >= initial_samples")
        if self.pool_size < 100:
            raise SurrogateError("pool_size must be >= 100")

    # ----------------------------------------------------------------------
    def _values(self, unit_point: np.ndarray) -> dict[str, float]:
        return {
            p.name: p.from_unit(float(u)) for p, u in zip(self.parameters, unit_point)
        }

    def _call(self, values: dict[str, float]) -> dict[str, float] | None:
        try:
            raw = self.model(dict(values))
            response = {name: float(raw[name]) for name in self.outputs}
        except Exception:  # noqa: BLE001 - any simulator failure counts
            return None
        if not all(math.isfinite(v) for v in response.values()):
            return None
        return response

    def _fit(self, x: np.ndarray, y: dict[str, list[float]], optimise: bool) -> None:
        for i, name in enumerate(self.outputs):
            gp = self._gps.get(name) or GaussianProcess(seed=self.seed + i)
            gp.fit(x, np.array(y[name]), optimise=optimise)
            self._gps[name] = gp

    def run(self) -> LearningResult:
        """Run the learning loop until converged or out of budget."""
        self._gps = {}
        rng = np.random.default_rng(self.seed)
        dim = len(self.parameters)
        pool = latin_hypercube(self.pool_size, dim, rng)
        exclusion = 0.05 * math.sqrt(dim)

        x_ok: list[np.ndarray] = []
        y_ok: dict[str, list[float]] = {name: [] for name in self.outputs}
        samples, responses, failed = [], [], []
        x_failed: list[np.ndarray] = []
        history: list[IterationRecord] = []
        model_time = 0.0
        start = time.perf_counter()
        evaluations = 0

        def evaluate(point: np.ndarray) -> None:
            nonlocal model_time, evaluations
            values = self._values(point)
            t0 = time.perf_counter()
            response = self._call(values)
            model_time += time.perf_counter() - t0
            evaluations += 1
            if response is None:
                failed.append(values)
                x_failed.append(point)
                return
            x_ok.append(point)
            samples.append(values)
            responses.append(response)
            for name in self.outputs:
                y_ok[name].append(response[name])

        for point in latin_hypercube(self.initial_samples, dim, rng):
            evaluate(point)

        streak = 0
        converged, reason = False, "budget exhausted"
        while True:
            if len(x_ok) < 3:
                if evaluations >= self.max_evaluations:
                    raise SurrogateError(
                        f"only {len(x_ok)} of {evaluations} evaluations succeeded"
                    )
                evaluate(rng.random(dim))
                continue
            x = np.array(x_ok)
            optimise = len(x_ok) <= 40 or len(x_ok) % 5 == 0 or not self._gps
            self._fit(x, y_ok, optimise)
            q2 = {name: self._gps[name].loo_q2() for name in self.outputs}

            # Candidates away from failures.
            candidates = pool
            if x_failed:
                dist = np.min(
                    np.linalg.norm(pool[:, None, :] - np.array(x_failed)[None], axis=2),
                    axis=1,
                )
                candidates = pool[dist > exclusion]
                if len(candidates) == 0:
                    candidates = pool

            min_u = None
            if self.mode == "limit_state":
                mean, std = self._gps[self.limit_output].predict(candidates)
                u = np.abs(mean - self.threshold) / np.maximum(std, 1e-300)
                best = int(np.argmin(u))
                min_u = float(u[best])
                satisfied = min_u >= self.u_stop
            else:
                score = np.zeros(len(candidates))
                for name in self.outputs:
                    _, std = self._gps[name].predict(candidates)
                    spread = float(np.std(y_ok[name])) or 1.0
                    score += std / spread
                best = int(np.argmax(score))
                satisfied = min(q2.values()) >= 1.0 - self.tolerance

            record = IterationRecord(
                evaluations=evaluations,
                failures=len(failed),
                q2={k: round(v, 6) for k, v in q2.items()},
                min_u=None if min_u is None else round(min_u, 4),
                elapsed_s=round(time.perf_counter() - start, 3),
            )
            history.append(record)
            if self.callback:
                self.callback(record)

            streak = streak + 1 if satisfied else 0
            if streak >= self.patience:
                converged = True
                reason = (
                    f"min U >= {self.u_stop}"
                    if self.mode == "limit_state"
                    else f"Q2 >= {1.0 - self.tolerance:g} for all outputs"
                )
                break
            if evaluations >= self.max_evaluations:
                break
            chosen = candidates[best]
            pool = pool[~np.all(pool == chosen, axis=1)]
            evaluate(chosen)

        surrogate = Surrogate(
            parameters=list(self.parameters),
            outputs=list(self.outputs),
            models=dict(self._gps),
            threshold=(
                (self.limit_output, float(self.threshold))
                if self.mode == "limit_state"
                else None
            ),
        )
        return LearningResult(
            surrogate=surrogate,
            converged=converged,
            stop_reason=reason,
            evaluations=evaluations,
            failures=len(failed),
            history=history,
            samples=samples,
            responses=responses,
            failed_samples=failed,
            model_time_s=model_time,
            mode=self.mode,
        )


@dataclass
class ValidationReport:
    """Surrogate against fresh model evaluations."""

    points: int
    failures: int
    rmse: dict[str, float]
    max_abs_error: dict[str, float]
    normalised_rmse: dict[str, float]
    coverage_2sigma: dict[str, float]
    classification_agreement: float | None = None


def validate(
    surrogate: Surrogate, model: Model, n: int = 20, seed: int = 7
) -> ValidationReport:
    """Check a surrogate against ``n`` new Latin-hypercube model runs.

    ``coverage_2sigma`` should be near 0.95; much lower means the surrogate is
    over-confident. ``classification_agreement`` is the share of points where
    surrogate and model agree on the side of the threshold.
    """
    if n < 2:
        raise SurrogateError("n must be >= 2")
    rng = np.random.default_rng(seed)
    points = latin_hypercube(n, len(surrogate.parameters), rng)
    errors: dict[str, list[float]] = {name: [] for name in surrogate.outputs}
    inside: dict[str, list[bool]] = {name: [] for name in surrogate.outputs}
    truth: dict[str, list[float]] = {name: [] for name in surrogate.outputs}
    agree: list[bool] = []
    failures = 0
    for point in points:
        values = {
            p.name: p.from_unit(float(u)) for p, u in zip(surrogate.parameters, point)
        }
        try:
            raw = model(dict(values))
            actual = {name: float(raw[name]) for name in surrogate.outputs}
        except Exception:  # noqa: BLE001
            failures += 1
            continue
        if not all(math.isfinite(v) for v in actual.values()):
            failures += 1
            continue
        predicted = surrogate.predict(values)
        for name in surrogate.outputs:
            mean, std = float(predicted[name][0][0]), float(predicted[name][1][0])
            errors[name].append(mean - actual[name])
            inside[name].append(abs(mean - actual[name]) <= 2.0 * std)
            truth[name].append(actual[name])
        if surrogate.threshold:
            out, limit = surrogate.threshold
            agree.append((float(predicted[out][0][0]) > limit) == (actual[out] > limit))
    if not any(errors.values()):
        raise SurrogateError("every validation run failed")
    rmse = {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in errors.items()}
    return ValidationReport(
        points=n,
        failures=failures,
        rmse=rmse,
        max_abs_error={k: float(np.max(np.abs(v))) for k, v in errors.items()},
        normalised_rmse={
            k: rmse[k] / (float(np.std(truth[k])) or 1.0) for k in surrogate.outputs
        },
        coverage_2sigma={k: float(np.mean(v)) for k, v in inside.items()},
        classification_agreement=float(np.mean(agree)) if agree else None,
    )
