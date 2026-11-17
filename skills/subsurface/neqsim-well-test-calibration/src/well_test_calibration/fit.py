"""Damped Gauss-Newton fit of a few model parameters with Gaussian priors and an identifiability check."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np


@dataclass
class FitResult:
    theta: list[float]
    objective: list[
        float
    ]  # sum of squared weighted residuals per iteration (incl. prior terms)
    singular_values: list[float]  # of the data Jacobian (prior rows excluded)
    identifiable: bool
    n_data: int
    notes: list[str] = field(default_factory=list)


def fit_with_priors(
    residual_fn: Callable[[np.ndarray], np.ndarray],
    prior: Sequence[float],
    prior_std: Sequence[float],
    bounds: Sequence[Sequence[float]],
    steps: Sequence[float] = None,
    iters: int = 4,
    min_singular: float = 0.3,
) -> FitResult:
    """Fit ``theta`` so that ``residual_fn(theta)`` (data residuals already divided by their measurement std) is small,
    pulled towards ``prior`` with standard deviations ``prior_std``.

    Each model evaluation can be an expensive simulation (a NeqSim tubing run), so the Jacobian is by forward
    differences with ``steps`` and only a few damped iterations are taken. ``identifiable`` is False when a singular
    value of the data Jacobian is below ``min_singular`` (the data cannot separate the parameters; the prior decides).
    """
    prior = np.asarray(prior, dtype=float)
    sd = np.asarray(prior_std, dtype=float)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    steps = np.asarray(
        steps if steps is not None else 0.1 * np.maximum(np.abs(prior), 1.0),
        dtype=float,
    )

    def full(th):
        return np.concatenate(
            [np.asarray(residual_fn(th), dtype=float), (th - prior) / sd]
        )

    th = prior.copy()
    r = full(th)
    hist = [float(r @ r)]
    jac = None
    notes = []
    for _ in range(iters):
        jac = np.zeros((len(r), len(th)))
        for j in range(len(th)):
            tp = th.copy()
            tp[j] += steps[j]
            jac[:, j] = (full(tp) - r) / steps[j]
        step = np.linalg.lstsq(jac, -r, rcond=None)[0]
        for a in (1.0, 0.5, 0.25):
            cand = np.clip(th + a * step, lo, hi)
            rc = full(cand)
            if rc @ rc < r @ r:
                th, r = cand, rc
                break
        else:
            notes.append("no descent step found; stopped")
            break
        hist.append(float(r @ r))
        if hist[-2] - hist[-1] < 0.01 * hist[-2]:
            break
    n_data = len(r) - len(th)
    sv = (
        np.linalg.svd(jac[:n_data], compute_uv=False)
        if jac is not None and n_data > 0
        else np.array([])
    )
    ident = bool(len(sv) == len(th) and sv.min() > min_singular)
    if not ident:
        notes.append(
            "parameters not separately identifiable from these data; result leans on the prior"
        )
    return FitResult(
        [float(x) for x in th], hist, [float(s) for s in sv], ident, int(n_data), notes
    )
