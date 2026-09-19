"""Match a split factor, generate fluid cases, and blend compositions.

All functions are public, deterministic, and dependency-free.

- :func:`match_split_factor` finds the split / characterization factor that best
  reproduces a measured target, using a robust golden-section 1-D search over a
  caller-supplied forward model. The forward model is injected so this helper has
  no dependency on any particular EOS; in practice it wraps the community
  ``pseudocomponent-split-characterization`` gamma split or a NeqSim
  characterization call.
- :func:`generate_fluid_cases` builds a set of representative or synthetic fluids
  from a common reference by applying a range of factors.
- :func:`blend_compositions` combines several well/fluid compositions into a
  field composition by molar-rate weighting (production allocation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class MatchResult:
    """Result of a split-factor match.

    :ivar factor: the split / characterization factor that minimizes the objective.
    :ivar objective: the objective value at ``factor``.
    :ivar iterations: number of golden-section iterations performed.
    :ivar converged: whether the search interval shrank below the tolerance.
    """

    factor: float
    objective: float
    iterations: int
    converged: bool


def match_split_factor(
    objective: Callable[[float], float],
    low: float,
    high: float,
    tol: float = 1.0e-4,
    max_iter: int = 100,
) -> MatchResult:
    """Find the split factor that minimizes a scalar objective by golden section.

    Typical objective: the sum of squared relative residuals between measured PVT
    or separator quantities (saturation pressure, GOR, stock-tank-oil density) and
    the values a forward model predicts for a given split factor.

    :param objective: callable mapping a candidate factor to a non-negative scalar
        (lower is better). Must be finite over ``[low, high]``.
    :param low: lower bound of the factor search interval.
    :param high: upper bound of the factor search interval, must exceed ``low``.
    :param tol: absolute tolerance on the factor interval width. Default 1e-4.
    :param max_iter: maximum number of iterations. Default 100.
    :returns: a :class:`MatchResult` with the best factor and objective.
    :raises ValueError: if ``high <= low`` or ``tol`` is not positive.
    """
    if not high > low:
        raise ValueError("high must be greater than low")
    if tol <= 0.0 or not math.isfinite(tol):
        raise ValueError("tol must be a positive finite number")

    inv_phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = low, high
    c = b - inv_phi * (b - a)
    d = a + inv_phi * (b - a)
    fc = float(objective(c))
    fd = float(objective(d))
    iterations = 0
    converged = False
    for iterations in range(1, max_iter + 1):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - inv_phi * (b - a)
            fc = float(objective(c))
        else:
            a, c, fc = c, d, fd
            d = a + inv_phi * (b - a)
            fd = float(objective(d))
        if abs(b - a) < tol:
            converged = True
            break
    factor = (a + b) / 2.0
    return MatchResult(
        factor=factor,
        objective=float(objective(factor)),
        iterations=iterations,
        converged=converged,
    )


def generate_fluid_cases(
    factors: Sequence[float],
    builder: Callable[[float], Mapping[str, float]],
) -> List[Dict[str, float]]:
    """Generate representative fluid cases by applying a range of split factors.

    :param factors: split / characterization factors to apply (for example
        low/base/high, or a scan across a field's fluid variability).
    :param builder: callable mapping a factor to a component-to-mole-fraction
        mapping (for example a reference fluid re-split with that factor).
    :returns: a list of composition dictionaries, one per factor.
    :raises ValueError: if ``factors`` is empty.
    """
    if not list(factors):
        raise ValueError("factors must contain at least one value")
    return [dict(builder(factor)) for factor in factors]


@dataclass(frozen=True)
class BlendResult:
    """Result of a molar-rate-weighted composition blend.

    :ivar composition: the blended (field) composition, normalized to sum to 1.
    :ivar total_molar_rate: the sum of the supplied molar rates.
    :ivar weights: the normalized molar-rate weight of each input stream.
    """

    composition: Dict[str, float]
    total_molar_rate: float
    weights: Tuple[float, ...]


def blend_compositions(
    weighted_compositions: Sequence[Tuple[float, Mapping[str, float]]],
) -> BlendResult:
    """Blend several compositions into one by molar-rate allocation.

    Use this to combine per-well or per-fluid compositions into a single field
    composition when the molar rates (or a rate proxy) of each stream are known.

    :param weighted_compositions: a sequence of ``(molar_rate, composition)``
        pairs. Each composition maps component names to mole fractions. Molar
        rates must be non-negative and not all zero.
    :returns: a :class:`BlendResult` with the normalized blended composition.
    :raises ValueError: if the input is empty, a rate is negative, or the total
        rate is zero.
    """
    pairs = list(weighted_compositions)
    if not pairs:
        raise ValueError("weighted_compositions must contain at least one stream")
    total_rate = 0.0
    for rate, _ in pairs:
        if rate < 0.0 or not math.isfinite(rate):
            raise ValueError("molar rates must be non-negative and finite")
        total_rate += rate
    if total_rate <= 0.0:
        raise ValueError("total molar rate must be positive")

    moles: Dict[str, float] = {}
    for rate, composition in pairs:
        comp_sum = sum(composition.values())
        if comp_sum <= 0.0:
            raise ValueError("each composition must have a positive sum")
        for name, fraction in composition.items():
            moles[name] = moles.get(name, 0.0) + rate * fraction / comp_sum

    total_moles = sum(moles.values())
    composition = {name: value / total_moles for name, value in moles.items()}
    weights = tuple(rate / total_rate for rate, _ in pairs)
    return BlendResult(
        composition=composition,
        total_molar_rate=total_rate,
        weights=weights,
    )
