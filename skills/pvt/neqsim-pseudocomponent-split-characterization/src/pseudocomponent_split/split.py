"""Whitson gamma split, lumping split factor, and delumping reconstruction.

All functions are public, deterministic, and dependency-free. They implement
well-published correlations (Whitson gamma distribution for the C7+ plus
fraction, and a simple normalized lumping/delumping split factor) so the outputs
can be reproduced and reviewed. They are screening-level helpers; use the
rigorous ``neqsim.thermo.characterization`` Java classes for design-grade work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple


# ---------------------------------------------------------------------------
# Regularized lower incomplete gamma function P(a, x) (Numerical Recipes gser/gcf)
# ---------------------------------------------------------------------------
def _gamma_p(a: float, x: float) -> float:
    """Return the regularized lower incomplete gamma function P(a, x).

    :param a: shape parameter, must be positive.
    :param x: upper integration limit, must be non-negative (``inf`` allowed).
    :returns: P(a, x) in the closed interval [0, 1].
    :raises ValueError: if ``a`` is not positive or ``x`` is negative.
    """
    if a <= 0.0 or not math.isfinite(a):
        raise ValueError("shape parameter a must be a positive finite number")
    if x < 0.0:
        raise ValueError("x must be non-negative")
    if math.isinf(x):
        return 1.0
    if x == 0.0:
        return 0.0
    if x < a + 1.0:
        # Series representation.
        ap = a
        total = 1.0 / a
        term = total
        for _ in range(1000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1.0e-14:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # Continued fraction representation for Q(a, x) = 1 - P(a, x).
    tiny = 1.0e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1.0e-14:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


@dataclass(frozen=True)
class GammaSplitResult:
    """Result of a Whitson gamma molar split of a plus fraction.

    :ivar mole_fractions: mole fraction of each pseudocomponent (sums to ``z_plus``).
    :ivar molar_masses: average molar mass (g/mol) of each pseudocomponent.
    :ivar boundaries: molar-mass boundaries (g/mol) used for the split.
    :ivar alpha: gamma shape factor used.
    :ivar eta: minimum molar mass (g/mol) used.
    """

    mole_fractions: Tuple[float, ...]
    molar_masses: Tuple[float, ...]
    boundaries: Tuple[float, ...]
    alpha: float
    eta: float


def gamma_mole_split(
    z_plus: float,
    m_plus: float,
    boundaries: Sequence[float],
    alpha: float = 1.0,
    eta: float = 90.0,
) -> GammaSplitResult:
    """Split a plus fraction into pseudocomponents with a Whitson gamma distribution.

    The three-parameter gamma distribution controls the heavy-end molar
    distribution. ``alpha`` is the split/characterization factor: ``alpha = 1``
    gives an exponential (Pedersen-like) distribution, higher ``alpha`` narrows
    the distribution, lower ``alpha`` produces a heavier tail.

    :param z_plus: total mole fraction of the plus fraction (0, 1].
    :param m_plus: average molar mass of the plus fraction (g/mol), > ``eta``.
    :param boundaries: increasing molar-mass boundaries (g/mol); ``n+1`` values
        produce ``n`` pseudocomponents. The last boundary may be ``math.inf``.
    :param alpha: gamma shape (split) factor, > 0. Default 1.0.
    :param eta: minimum molar mass (g/mol) of the distribution, >= 0. Default 90.
    :returns: a :class:`GammaSplitResult` with per-pseudocomponent mole fractions
        and average molar masses.
    :raises ValueError: if inputs are out of range or fewer than two boundaries
        are supplied.
    """
    if not 0.0 < z_plus <= 1.0:
        raise ValueError("z_plus must be in the interval (0, 1]")
    if alpha <= 0.0 or not math.isfinite(alpha):
        raise ValueError("alpha must be a positive finite number")
    if eta < 0.0:
        raise ValueError("eta must be non-negative")
    if m_plus <= eta:
        raise ValueError("m_plus must be greater than eta")
    bounds = list(boundaries)
    if len(bounds) < 2:
        raise ValueError("boundaries must contain at least two values")
    for lower, upper in zip(bounds, bounds[1:]):
        if not (upper > lower):
            raise ValueError("boundaries must be strictly increasing")

    beta = (m_plus - eta) / alpha
    ys = [math.inf if math.isinf(b) else max(b - eta, 0.0) / beta for b in bounds]
    p_alpha = [_gamma_p(alpha, y) for y in ys]
    p_alpha1 = [_gamma_p(alpha + 1.0, y) for y in ys]

    raw = [p_alpha[i + 1] - p_alpha[i] for i in range(len(bounds) - 1)]
    total = sum(raw)
    if total <= 0.0:
        raise ValueError("gamma split produced no mass; check boundaries and eta")

    fractions: List[float] = []
    masses: List[float] = []
    for i in range(len(bounds) - 1):
        frac = z_plus * raw[i] / total
        fractions.append(frac)
        d_alpha = p_alpha[i + 1] - p_alpha[i]
        if d_alpha > 0.0:
            mass = eta + beta * alpha * (p_alpha1[i + 1] - p_alpha1[i]) / d_alpha
        else:
            mass = eta
        masses.append(mass)

    return GammaSplitResult(
        mole_fractions=tuple(fractions),
        molar_masses=tuple(masses),
        boundaries=tuple(bounds),
        alpha=alpha,
        eta=eta,
    )


# ---------------------------------------------------------------------------
# Lumping split factor and delumping
# ---------------------------------------------------------------------------
LumpingScheme = Sequence[Sequence[int]]
"""A lumping scheme: for each lump, the indices of the detailed components it contains."""


@dataclass(frozen=True)
class SplitFactorResult:
    """Per-component split factors for a lumping scheme.

    :ivar split_factors: for each detailed component index, the fraction of its
        lump total that it represents (each lump's factors sum to 1).
    :ivar lump_totals: total mole fraction of each lump.
    """

    split_factors: Tuple[float, ...]
    lump_totals: Tuple[float, ...]


def _validate_scheme(n_components: int, lumping_scheme: LumpingScheme) -> None:
    seen = set()
    for lump in lumping_scheme:
        if not lump:
            raise ValueError("each lump must contain at least one component index")
        for idx in lump:
            if not 0 <= idx < n_components:
                raise ValueError(f"component index {idx} out of range")
            if idx in seen:
                raise ValueError(f"component index {idx} appears in more than one lump")
            seen.add(idx)


def calculate_split_factor(
    full_composition: Sequence[float],
    lumping_scheme: LumpingScheme,
) -> SplitFactorResult:
    """Compute the delumping split factor from a detailed reference composition.

    For each lump, the split factor of a detailed component is its mole fraction
    divided by the lump total. This mirrors FluidMagic's
    ``EOSConverter.calculate_split_factor`` and lets a lumped composition be
    reconstructed (delumped) back to detailed components using the reference
    fluid's internal distribution.

    :param full_composition: detailed component mole fractions (any positive
        basis; need not sum to one).
    :param lumping_scheme: for each lump, the indices of the detailed components
        it contains. Indices must be unique across lumps and in range.
    :returns: a :class:`SplitFactorResult` with per-component split factors and
        per-lump totals.
    :raises ValueError: if the scheme references invalid or duplicated indices,
        or a lump total is non-positive.
    """
    values = list(full_composition)
    _validate_scheme(len(values), lumping_scheme)
    split_factors = [0.0] * len(values)
    lump_totals: List[float] = []
    for lump in lumping_scheme:
        total = sum(values[idx] for idx in lump)
        if total <= 0.0:
            raise ValueError("lump total must be positive to compute a split factor")
        lump_totals.append(total)
        for idx in lump:
            split_factors[idx] = values[idx] / total
    return SplitFactorResult(
        split_factors=tuple(split_factors),
        lump_totals=tuple(lump_totals),
    )


def delump_composition(
    lumped_composition: Sequence[float],
    split_factors: Sequence[float],
    lumping_scheme: LumpingScheme,
) -> Tuple[float, ...]:
    """Reconstruct a detailed composition from a lumped one and a split factor.

    :param lumped_composition: mole fraction of each lump (same order as
        ``lumping_scheme``).
    :param split_factors: per detailed-component split factors from
        :func:`calculate_split_factor`.
    :param lumping_scheme: for each lump, the indices of the detailed components
        it contains.
    :returns: the detailed component mole fractions.
    :raises ValueError: if the lumped composition length does not match the
        scheme.
    """
    lumped = list(lumped_composition)
    if len(lumped) != len(list(lumping_scheme)):
        raise ValueError("lumped_composition length must match the lumping scheme")
    full = [0.0] * len(split_factors)
    for lump, lump_value in zip(lumping_scheme, lumped):
        for idx in lump:
            full[idx] = lump_value * split_factors[idx]
    return tuple(full)
