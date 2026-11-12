"""Score a model against ThermoML data points."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional

from .parser import DataPoint

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
WARN_FACTOR = 2.0


@dataclass(frozen=True)
class PointResult:
    """Model value against one measured point."""

    point: DataPoint
    model_value: float
    deviation_pct: Optional[float]
    within_uncertainty: Optional[bool]


@dataclass
class ComparisonSummary:
    """Aggregate statistics of a model-versus-experiment comparison."""

    property_name: str
    unit: str
    n_points: int
    n_skipped: int
    aad_pct: Optional[float]
    bias_pct: Optional[float]
    max_abs_pct: Optional[float]
    fraction_within_uncertainty: Optional[float]
    tolerance_pct: float
    status: str
    doi: str = ""
    results: List[PointResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-ready dict without the per-point objects."""
        data = {k: v for k, v in self.__dict__.items() if k != "results"}
        data["rows"] = [
            {
                "T_K": r.point.temperature_k,
                "P_bara": r.point.pressure_bara,
                "x": r.point.mole_fractions,
                "experiment": r.point.value,
                "uncertainty": r.point.uncertainty,
                "model": r.model_value,
                "deviation_pct": r.deviation_pct,
            }
            for r in self.results
        ]
        return data


def compare_points(
    points: Iterable[DataPoint],
    model: Callable[[DataPoint], float],
    tolerance_pct: float = 2.0,
) -> ComparisonSummary:
    """Evaluate ``model(point)`` at every point and summarise the deviation.

    ``model`` receives the full point (state, composition, property) and returns the model value in the point's
    unit. Points whose model call raises ``ValueError`` or returns a non-finite value are skipped, so a failed flash
    never silently counts as agreement. Status is PASS when AAD <= tolerance, WARN up to twice the tolerance, else FAIL
    (also FAIL when no point could be evaluated).
    """
    results: List[PointResult] = []
    skipped = 0
    first: Optional[DataPoint] = None
    for point in points:
        first = first or point
        try:
            value = float(model(point))
        except ValueError:
            skipped += 1
            continue
        if not math.isfinite(value):
            skipped += 1
            continue
        deviation = None if point.value == 0 else 100.0 * (value - point.value) / abs(point.value)
        within = None if point.uncertainty is None else abs(value - point.value) <= point.uncertainty
        results.append(PointResult(point, value, deviation, within))
    deviations = [r.deviation_pct for r in results if r.deviation_pct is not None]
    judged = [r.within_uncertainty for r in results if r.within_uncertainty is not None]
    aad = sum(abs(d) for d in deviations) / len(deviations) if deviations else None
    if aad is None:
        status = STATUS_FAIL
    elif aad <= tolerance_pct:
        status = STATUS_PASS
    elif aad <= WARN_FACTOR * tolerance_pct:
        status = STATUS_WARN
    else:
        status = STATUS_FAIL
    return ComparisonSummary(
        property_name=first.property_name if first else "",
        unit=first.unit if first else "",
        n_points=len(results),
        n_skipped=skipped,
        aad_pct=aad,
        bias_pct=sum(deviations) / len(deviations) if deviations else None,
        max_abs_pct=max(abs(d) for d in deviations) if deviations else None,
        fraction_within_uncertainty=sum(judged) / len(judged) if judged else None,
        tolerance_pct=tolerance_pct,
        status=status,
        doi=first.doi if first else "",
        results=results,
    )
