"""Analysis helpers for the public NCS reference dataset.

Deterministic, dependency-free functions for screening-level analysis of
Norwegian Continental Shelf production and resources built on the public seed
snapshot or on an ingested annual-production series. These are transparent
public calculations intended to orient a study; quantitative production
forecasting must use validated NeqSim reservoir/process workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .dataset import AnnualProduction, NcsField


@dataclass(frozen=True)
class ResourceRemaining:
    total_billion_sm3_oe: float
    produced_billion_sm3_oe: float
    remaining_billion_sm3_oe: float
    remaining_fraction: float
    reserve_to_production_years: float | None


def resource_remaining(
    *,
    total_billion_sm3_oe: float,
    produced_fraction: float,
    latest_annual_oe_mill_sm3: float | None = None,
) -> ResourceRemaining:
    """Compute remaining NCS resources from the resource-accounting split.

    ``produced_fraction`` is the produced/sold/delivered share (0-1). When a
    latest annual production rate (million Sm3 o.e./year) is supplied, a simple
    reserves-to-production (R/P) horizon in years is also returned. This is a
    static screening ratio, not a forecast.
    """
    _require_positive("total_billion_sm3_oe", total_billion_sm3_oe)
    _require_fraction("produced_fraction", produced_fraction)
    produced = total_billion_sm3_oe * produced_fraction
    remaining = total_billion_sm3_oe - produced
    remaining_fraction = 1.0 - produced_fraction
    rp_years: float | None = None
    if latest_annual_oe_mill_sm3 is not None:
        _require_positive("latest_annual_oe_mill_sm3", latest_annual_oe_mill_sm3)
        # remaining is in billion Sm3 o.e.; rate in million Sm3 o.e./year
        rp_years = round((remaining * 1000.0) / latest_annual_oe_mill_sm3, 2)
    return ResourceRemaining(
        total_billion_sm3_oe=round(total_billion_sm3_oe, 4),
        produced_billion_sm3_oe=round(produced, 4),
        remaining_billion_sm3_oe=round(remaining, 4),
        remaining_fraction=round(remaining_fraction, 4),
        reserve_to_production_years=rp_years,
    )


@dataclass(frozen=True)
class ProductionShare:
    year: int
    oe_mill_sm3: float
    oil_share: float | None
    gas_share: float | None
    ngl_share: float | None
    condensate_share: float | None


def production_share(record: AnnualProduction) -> ProductionShare:
    """Return the oil/gas/NGL/condensate share of total o.e. for one year.

    Shares are only computed for the components that are populated in the
    record; missing components return ``None``. Gas is converted to o.e. using
    the NCS convention (billion Sm3 gas = million Sm3 o.e.).
    """
    total = record.oe_mill_sm3
    _require_positive("oe_mill_sm3", total)

    def share(value: float | None, *, scale: float = 1.0) -> float | None:
        if value is None:
            return None
        return round((value * scale) / total, 4)

    return ProductionShare(
        year=record.year,
        oe_mill_sm3=round(total, 4),
        oil_share=share(record.oil_mill_sm3),
        gas_share=share(record.gas_bill_sm3),
        ngl_share=share(record.ngl_mill_sm3_oe),
        condensate_share=share(record.condensate_mill_sm3),
    )


@dataclass(frozen=True)
class ProductionTrend:
    first_year: int
    last_year: int
    first_oe_mill_sm3: float
    last_oe_mill_sm3: float
    total_change_pct: float
    cagr_pct: float | None
    direction: str


def production_trend(series: Sequence[AnnualProduction]) -> ProductionTrend:
    """Compute a first-to-last trend and CAGR over an annual o.e. series.

    ``series`` must contain at least two years. Returns the total percentage
    change, the compound annual growth rate (percent per year), and a
    ``rising`` / ``falling`` / ``flat`` direction label. This is a descriptive
    statistic over historical data, not a forecast.
    """
    if len(series) < 2:
        raise ValueError("production_trend needs at least two years")
    ordered = sorted(series, key=lambda r: r.year)
    first, last = ordered[0], ordered[-1]
    if first.oe_mill_sm3 <= 0:
        raise ValueError("first-year production must be positive")
    span = last.year - first.year
    total_change = (last.oe_mill_sm3 / first.oe_mill_sm3) - 1.0
    cagr: float | None = None
    if span > 0:
        cagr = ((last.oe_mill_sm3 / first.oe_mill_sm3) ** (1.0 / span)) - 1.0
    if total_change > 0.01:
        direction = "rising"
    elif total_change < -0.01:
        direction = "falling"
    else:
        direction = "flat"
    return ProductionTrend(
        first_year=first.year,
        last_year=last.year,
        first_oe_mill_sm3=round(first.oe_mill_sm3, 4),
        last_oe_mill_sm3=round(last.oe_mill_sm3, 4),
        total_change_pct=round(total_change * 100.0, 3),
        cagr_pct=None if cagr is None else round(cagr * 100.0, 3),
        direction=direction,
    )


def aggregate_field_counts(fields: Sequence[NcsField]) -> dict[str, dict[str, int]]:
    """Group a list of field records into counts by area, product, and status."""
    by_area: dict[str, int] = {}
    by_product: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for record in fields:
        by_area[record.sea_area] = by_area.get(record.sea_area, 0) + 1
        by_product[record.main_product] = by_product.get(record.main_product, 0) + 1
        by_status[record.status] = by_status.get(record.status, 0) + 1
    return {
        "by_sea_area": dict(sorted(by_area.items())),
        "by_main_product": dict(sorted(by_product.items())),
        "by_status": dict(sorted(by_status.items())),
    }


def fields_started_by_decade(fields: Sequence[NcsField]) -> dict[int, int]:
    """Count fields by their production-start decade (e.g. 1970, 1980, ...)."""
    decades: dict[int, int] = {}
    for record in fields:
        decade = (record.production_start_year // 10) * 10
        decades[decade] = decades.get(decade, 0) + 1
    return dict(sorted(decades.items()))


def rank_fields_by_remaining(
    fields: Sequence[NcsField], *, top: int | None = None
) -> list[NcsField]:
    """Rank fields by remaining oil-equivalent reserves (descending).

    Fields without a populated ``remaining_oe_mill_sm3`` (i.e. not yet ingested
    from the official reserves export) are excluded. Pass ``top`` to limit the
    number returned.
    """
    ranked = sorted(
        (f for f in fields if f.remaining_oe_mill_sm3 is not None),
        key=lambda f: f.remaining_oe_mill_sm3,  # type: ignore[arg-type,return-value]
        reverse=True,
    )
    return ranked if top is None else ranked[: max(0, int(top))]


def remaining_reserves_by_area(fields: Sequence[NcsField]) -> dict[str, float]:
    """Sum remaining oil-equivalent reserves by sea area (populated fields only)."""
    totals: dict[str, float] = {}
    for record in fields:
        if record.remaining_oe_mill_sm3 is None:
            continue
        totals[record.sea_area] = round(
            totals.get(record.sea_area, 0.0) + record.remaining_oe_mill_sm3, 4
        )
    return dict(sorted(totals.items()))


def _require_positive(name: str, value: float) -> None:
    if value is None or value <= 0.0:
        raise ValueError(f"{name} must be positive")


def _require_fraction(name: str, value: float) -> None:
    if value is None or not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be between 0 and 1")
