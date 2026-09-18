"""Weighted multi-target regression of a characterization factor.

All functions are public, deterministic, and dependency-free. The forward model
is injected: it maps a candidate factor to a mapping of predicted quantities
keyed by target name. This mirrors FluidMagic's regression, which fits EOS/
characterization parameters to measured PVT experiment values with per-target
weights, and NeqSim's characterization plus PVT-simulation workflow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class RegressionTarget:
    """A single measured regression target.

    :ivar name: identifier that the forward model uses for this quantity (for
        example ``"saturation_pressure"``, ``"gor"``, ``"sto_density"``).
    :ivar measured: measured value (in the forward model's units).
    :ivar weight: relative weight (higher = higher priority). Default 1.0.
    """

    name: str
    measured: float
    weight: float = 1.0


def weighted_ssr(
    predicted: Mapping[str, float],
    targets: Sequence[RegressionTarget],
) -> float:
    """Return the weighted sum of squared relative residuals.

    Each residual is ``(predicted - measured) / measured`` so quantities with
    different magnitudes and units contribute comparably. Missing predictions or
    zero measured values raise, so silent mismatches are avoided.

    :param predicted: mapping of target name to predicted value.
    :param targets: measured targets with weights.
    :returns: the weighted sum of squared relative residuals (non-negative).
    :raises ValueError: if a target is missing from ``predicted``, a measured
        value is zero, or a weight is negative.
    """
    total = 0.0
    for target in targets:
        if target.weight < 0.0 or not math.isfinite(target.weight):
            raise ValueError(f"weight for {target.name} must be non-negative and finite")
        if target.name not in predicted:
            raise ValueError(f"predicted value for target '{target.name}' is missing")
        if target.measured == 0.0:
            raise ValueError(f"measured value for target '{target.name}' must be non-zero")
        rel = (float(predicted[target.name]) - target.measured) / target.measured
        total += target.weight * rel * rel
    return total


@dataclass(frozen=True)
class RegressionResult:
    """Result of a characterization-factor regression.

    :ivar factor: the fitted split / characterization factor.
    :ivar objective: the weighted sum of squared relative residuals at ``factor``.
    :ivar residuals: per-target relative residual at ``factor``.
    :ivar predicted: per-target predicted value at ``factor``.
    :ivar iterations: number of golden-section iterations performed.
    :ivar converged: whether the search interval shrank below the tolerance.
    """

    factor: float
    objective: float
    residuals: Dict[str, float]
    predicted: Dict[str, float]
    iterations: int
    converged: bool


def regress_characterization_factor(
    forward_model: Callable[[float], Mapping[str, float]],
    targets: Sequence[RegressionTarget],
    low: float,
    high: float,
    tol: float = 1.0e-4,
    max_iter: int = 100,
) -> RegressionResult:
    """Regress one characterization factor against weighted PVT/separator targets.

    Uses a robust golden-section 1-D search over ``[low, high]`` — no gradients,
    suitable for the noisy forward models produced by flash/PVT calculations.

    :param forward_model: callable mapping a candidate factor to a mapping of
        predicted quantities keyed by target name (for example a NeqSim
        characterization + saturation-pressure/GOR/density evaluation).
    :param targets: measured targets with weights.
    :param low: lower bound of the factor search interval.
    :param high: upper bound of the factor search interval, must exceed ``low``.
    :param tol: absolute tolerance on the factor interval width. Default 1e-4.
    :param max_iter: maximum number of iterations. Default 100.
    :returns: a :class:`RegressionResult` with the fitted factor and residuals.
    :raises ValueError: if ``high <= low``, ``tol`` is not positive, or ``targets``
        is empty.
    """
    if not high > low:
        raise ValueError("high must be greater than low")
    if tol <= 0.0 or not math.isfinite(tol):
        raise ValueError("tol must be a positive finite number")
    if not list(targets):
        raise ValueError("at least one regression target is required")

    def objective(factor: float) -> float:
        return weighted_ssr(forward_model(factor), targets)

    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = low, high
    c = b - inv_phi * (b - a)
    d = a + inv_phi * (b - a)
    fc = objective(c)
    fd = objective(d)
    iterations = 0
    converged = False
    for iterations in range(1, max_iter + 1):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - inv_phi * (b - a)
            fc = objective(c)
        else:
            a, c, fc = c, d, fd
            d = a + inv_phi * (b - a)
            fd = objective(d)
        if abs(b - a) < tol:
            converged = True
            break

    factor = (a + b) / 2.0
    predicted = {name: float(value) for name, value in forward_model(factor).items()}
    residuals = {
        target.name: (predicted[target.name] - target.measured) / target.measured
        for target in targets
    }
    return RegressionResult(
        factor=factor,
        objective=weighted_ssr(predicted, targets),
        residuals=residuals,
        predicted={target.name: predicted[target.name] for target in targets},
        iterations=iterations,
        converged=converged,
    )
