"""Reading the result of a PSC bid screen: Swanson-weighted EMV and what you need to believe.

All helpers wrap :class:`PscBidModel`. Volumes are scales on the P50 production
profile, so the P90 case is ``p90 / p50`` and the P10 case ``p10 / p50``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .model import PscBidModel, PscBidResult

SWANSON_WEIGHTS = (0.3, 0.4, 0.3)


def swanson_cases(volume_p90: float, volume_p50: float, volume_p10: float,
                  weights: Sequence[float] = SWANSON_WEIGHTS) -> tuple[list, list]:
    """Volume scales and weights (P90, P50, P10 with 0.3/0.4/0.3) for ``PscBidModel.evaluate``."""
    if min(volume_p90, volume_p50, volume_p10) <= 0.0:
        raise ValueError("volumes must be positive")
    if not volume_p90 <= volume_p50 <= volume_p10:
        raise ValueError("expected P90 <= P50 <= P10 volumes (low, mid, high)")
    return [volume_p90 / volume_p50, 1.0, volume_p10 / volume_p50], list(weights)


def swanson_emv(model: PscBidModel, production_mmbbl: Sequence[float], capex_musd: Sequence[float],
                opex_musd: Sequence[float], volumes_p90_p50_p10: Sequence[float],
                weights: Sequence[float] = SWANSON_WEIGHTS, **evaluate_kwargs) -> PscBidResult:
    """Evaluate the bid with Swanson-weighted volume cases; ``production_mmbbl`` is the P50 profile.

    CAPEX and OPEX do not scale with volume, so the low case carries a thinner margin.
    """
    scales, w = swanson_cases(*volumes_p90_p50_p10, weights=weights)
    return model.evaluate(production_mmbbl, capex_musd, opex_musd, volume_scales=scales,
                          volume_weights=w, **evaluate_kwargs)


@dataclass
class Belief:
    """What must be true for EMV to reach zero, plus the zero-NPV markers of the development."""

    emv_musd: float
    pv_development_given_discovery_musd: float
    pv_pre_discovery_cost_musd: float
    break_even_chance_of_discovery: float
    chance_attainable: bool
    p50_volume_scale_for_zero_emv: float | None
    p50_volume_mmbbl_for_zero_emv: float | None


def _bisect(f: Callable[[float], float], lo: float, hi: float, iterations: int = 60) -> float | None:
    """Root of an increasing ``f`` on [lo, hi]; ``lo`` if already positive, ``None`` if never positive."""
    if f(lo) >= 0.0:
        return lo
    if f(hi) < 0.0:
        return None
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if f(mid) >= 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def what_you_need_to_believe(model: PscBidModel, production_mmbbl: Sequence[float],
                             capex_musd: Sequence[float], opex_musd: Sequence[float],
                             volumes_p90_p50_p10: Sequence[float] | None = None,
                             weights: Sequence[float] = SWANSON_WEIGHTS,
                             max_volume_scale: float = 100.0, **evaluate_kwargs) -> Belief:
    """Break-even chance of discovery and the P50 volume (scale) at which EMV is zero.

    EMV = pre + Pg * development, so ``Pg* = -pre / development`` (above 1 means no
    chance of discovery can pay for the bid). The volume break-even scales every
    volume case by one factor at the stated ``chance_of_discovery``.
    """
    if volumes_p90_p50_p10 is not None:
        scales, w = swanson_cases(*volumes_p90_p50_p10, weights=weights)
    else:
        scales, w = [1.0], [1.0]

    def run(multiplier: float = 1.0) -> PscBidResult:
        return model.evaluate(production_mmbbl, capex_musd, opex_musd,
                              volume_scales=[s * multiplier for s in scales], volume_weights=w, **evaluate_kwargs)

    base = run()
    dev, pre = base.pv_development_given_discovery_musd, base.pv_pre_discovery_cost_musd
    pg_star = float("inf") if dev <= 0.0 else max(0.0, -pre / dev)
    multiplier = _bisect(lambda m: run(m).emv_musd, 0.01, max_volume_scale)
    p50_total = float(sum(production_mmbbl))
    return Belief(
        emv_musd=base.emv_musd,
        pv_development_given_discovery_musd=dev,
        pv_pre_discovery_cost_musd=pre,
        break_even_chance_of_discovery=pg_star,
        chance_attainable=pg_star <= 1.0,
        p50_volume_scale_for_zero_emv=multiplier,
        p50_volume_mmbbl_for_zero_emv=None if multiplier is None else multiplier * p50_total,
    )


def minimum_economic_volume(model: PscBidModel, production_mmbbl: Sequence[float],
                            capex_musd: Sequence[float], opex_musd: Sequence[float],
                            max_volume_scale: float = 100.0, **evaluate_kwargs) -> float | None:
    """Recoverable volume (MMbbl, 100 %, P50 profile scaled) where development NPV given discovery is zero."""
    def dev(m: float) -> float:
        return model.evaluate(production_mmbbl, capex_musd, opex_musd, volume_scales=[m],
                              volume_weights=[1.0], **evaluate_kwargs).pv_development_given_discovery_musd

    multiplier = _bisect(dev, 0.01, max_volume_scale)
    return None if multiplier is None else multiplier * float(sum(production_mmbbl))


def breakeven_oil_price(model: PscBidModel, production_mmbbl: Sequence[float],
                        capex_musd: Sequence[float], opex_musd: Sequence[float],
                        low: float = 5.0, high: float = 300.0, **evaluate_kwargs) -> float | None:
    """Realised oil price at which development NPV given discovery is zero (Brent follows via the model's discount)."""
    original = model.oil_price

    def dev(price: float) -> float:
        model.oil_price = price
        return model.evaluate(production_mmbbl, capex_musd, opex_musd,
                              **evaluate_kwargs).pv_development_given_discovery_musd

    try:
        return _bisect(dev, low, high)
    finally:
        model.oil_price = original


def find_crossover(npv_a: Callable[[float], float], npv_b: Callable[[float], float],
                   low: float, high: float, iterations: int = 60) -> float | None:
    """Volume where concept A and B have equal NPV (for example tie-back versus stand-alone).

    Pass callables that build each concept's cash flows at a given volume (MMbbl) and
    return development NPV. Returns ``None`` when the difference does not change sign.
    """
    def diff(v: float) -> float:
        return npv_a(v) - npv_b(v)

    d_lo, d_hi = diff(low), diff(high)
    if d_lo == 0.0:
        return low
    if d_lo * d_hi > 0.0:
        return None
    lo, hi = low, high
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if diff(mid) * d_lo > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
