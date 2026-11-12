"""Screening statistics: investigation counts per structure-year with exact Poisson (Garwood) intervals."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence

from .parse import Investigation, Structure

CAVEATS = (
    "Numerator is BSEE accident investigations on the US Outer Continental Shelf, not all incidents or all "
    "hydrocarbon releases; the rate is a lower-bound screening index.",
    "Investigations are not linked to a structure here (only lease/area/block); events on pipelines, vessels or "
    "drilling units are in the numerator while the denominator counts platform structures only.",
    "Reporting thresholds and practice changed over 1995 to date; compare periods, do not extrapolate one rate.",
    "Gulf of Mexico regime and equipment mix differ from the Norwegian shelf; use as an open order-of-magnitude "
    "cross-check, never as the basis of a SIL, QRA or design frequency without review.",
)


@dataclass
class RateEstimate:
    """Investigation rate per structure-year with an exact Poisson interval."""

    labels: List[str]
    period: str
    count: int
    structure_years: float
    rate_per_structure_year: Optional[float]
    lower: Optional[float]
    upper: Optional[float]
    confidence: float
    filters: Dict[str, object] = field(default_factory=dict)
    caveats: Sequence[str] = CAVEATS

    def to_dict(self) -> dict:
        """Return a JSON-ready dict."""
        data = dict(self.__dict__)
        data["caveats"] = list(self.caveats)
        return data


def _poisson_cdf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0
    term = math.exp(-lam)
    total = term
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(total, 1.0)


def _bisect(func, low: float, high: float) -> float:
    for _ in range(200):
        mid = 0.5 * (low + high)
        if func(mid) > 0:
            high = mid
        else:
            low = mid
    return 0.5 * (low + high)


def poisson_interval(count: int, confidence: float = 0.90) -> tuple:
    """Exact two-sided (Garwood) confidence interval for a Poisson mean given an observed ``count``."""
    if count < 0 or not 0.0 < confidence < 1.0:
        raise ValueError("count must be >= 0 and confidence in (0, 1)")
    alpha = 1.0 - confidence
    upper_bound = max(10.0, 4.0 * count + 20.0)
    lower = 0.0 if count == 0 else _bisect(lambda lam: (1.0 - _poisson_cdf(count - 1, lam)) - alpha / 2.0, 0.0, upper_bound)
    upper = _bisect(lambda lam: alpha / 2.0 - _poisson_cdf(count, lam), 0.0, upper_bound)
    return lower, upper


def structure_years(
    structures: Iterable[Structure],
    start: date,
    end: date,
    *,
    major_only: bool = False,
    manned_only: bool = False,
    areas: Optional[Iterable[str]] = None,
) -> float:
    """Sum installed time (years) of the structures inside ``[start, end]``; blank removal date means still installed."""
    wanted = {a.upper() for a in areas} if areas else None
    total_days = 0
    for s in structures:
        if (major_only and not s.major) or (manned_only and not s.manned_24h) or (wanted and s.area.upper() not in wanted):
            continue
        first = max(s.installed, start)
        last = min(s.removed or end, end)
        if last >= first:
            total_days += (last - first).days + 1
    return total_days / 365.25


def label_counts(investigations: Iterable[Investigation], start_year: int, end_year: int) -> List[tuple]:
    """Return ``(label, count)`` for single labels in the period, most frequent first."""
    counter: Counter = Counter()
    for item in investigations:
        if start_year <= item.occurred.year <= end_year:
            counter.update(set(item.labels))
    return counter.most_common()


def annual_counts(investigations: Iterable[Investigation], labels: Iterable[str]) -> Dict[int, int]:
    """Investigations per year that carry any of ``labels`` (case-insensitive)."""
    wanted = {l.lower() for l in labels}
    counter: Counter = Counter()
    for item in investigations:
        if wanted & {l.lower() for l in item.labels}:
            counter[item.occurred.year] += 1
    return dict(sorted(counter.items()))


def estimate_rate(
    investigations: Iterable[Investigation],
    structures: Iterable[Structure],
    labels: Iterable[str],
    start_year: int,
    end_year: int,
    *,
    major_only: bool = False,
    manned_only: bool = False,
    areas: Optional[Iterable[str]] = None,
    confidence: float = 0.90,
) -> RateEstimate:
    """Count investigations carrying any of ``labels`` and divide by structure-years for the same filters.

    ``areas`` filters both numerator (investigation area) and denominator (structure area), for example
    ``["GC", "MC"]`` for deepwater Gulf blocks. A zero exposure yields ``None`` rates rather than a division error.
    """
    label_list = list(labels)
    wanted = {l.lower() for l in label_list}
    areas_set = {a.upper() for a in areas} if areas else None
    count = sum(
        1
        for item in investigations
        if start_year <= item.occurred.year <= end_year
        and wanted & {l.lower() for l in item.labels}
        and (areas_set is None or item.area.upper() in areas_set)
    )
    exposure = structure_years(structures, date(start_year, 1, 1), date(end_year, 12, 31),
                               major_only=major_only, manned_only=manned_only, areas=areas)
    lower, upper = poisson_interval(count, confidence)
    if exposure <= 0:
        return RateEstimate(label_list, f"{start_year}-{end_year}", count, exposure, None, None, None, confidence)
    return RateEstimate(
        label_list, f"{start_year}-{end_year}", count, exposure, count / exposure, lower / exposure, upper / exposure,
        confidence,
        {"major_only": major_only, "manned_only": manned_only, "areas": sorted(areas_set) if areas_set else None},
    )
