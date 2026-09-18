"""Compare a model value against an independent reference value.

The comparison is deliberately strict about two things a hand-written benchmark
cell usually gets wrong:

1. **Independence.** The reference must outrank the model basis, otherwise the
   comparison is a consistency check and is reported as ``INFO``, not ``PASS``.
2. **Resolution.** A deviation smaller than the reference's own stated
   uncertainty cannot be claimed as agreement to that precision, so the result
   records whether it sits inside the reference uncertainty band.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from .reference_data import ReferencePoint

#: Default acceptance tolerance in percent, by property.
DEFAULT_TOLERANCE_PCT: Dict[str, float] = {
    "critical_temperature": 1.0,
    "critical_pressure": 2.0,
    "critical_density": 5.0,
    "triple_point_temperature": 0.5,
    "triple_point_pressure": 5.0,
    "normal_boiling_point": 1.0,
    "sublimation_temperature": 1.0,
    "density": 2.0,
    "molar_density": 2.0,
    "enthalpy": 2.0,
    "entropy": 2.0,
    "cp": 3.0,
    "cv": 3.0,
    "speed_of_sound": 2.0,
    "compressibility_factor": 1.0,
    "viscosity": 10.0,
    "thermal_conductivity": 10.0,
    "molar_mass": 0.1,
    "acentric_factor": 5.0,
}

#: Fallback tolerance when the property is not in the table.
FALLBACK_TOLERANCE_PCT = 5.0

#: A deviation up to ``WARN_FACTOR`` times the tolerance is WARN, beyond it FAIL.
WARN_FACTOR = 2.0

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_INFO = "INFO"


def default_tolerance_pct(property_name: str) -> float:
    """Acceptance tolerance for a property, in percent."""
    return DEFAULT_TOLERANCE_PCT.get(property_name, FALLBACK_TOLERANCE_PCT)


@dataclass(frozen=True)
class BenchmarkResult:
    """Outcome of one model-vs-reference comparison."""

    name: str
    property_name: str
    unit: str
    model_label: str
    model_value: float
    reference_value: float
    deviation: float
    deviation_pct: Optional[float]
    tolerance_pct: float
    status: str
    source_key: str
    citation: str
    state: Dict[str, float] = field(default_factory=dict)
    within_source_uncertainty: Optional[bool] = None
    independent: bool = True
    note: str = ""

    @property
    def passed(self) -> bool:
        """True only for an unambiguous PASS."""
        return self.status == STATUS_PASS

    def description(self) -> str:
        """One-line description used as the report table caption."""
        parts = [self.property_name.replace("_", " ")]
        if self.state:
            parts.append(
                "at "
                + ", ".join(
                    "{}={:g}".format(k, v) for k, v in sorted(self.state.items())
                )
            )
        parts.append("vs {}".format(self.source_key))
        return " ".join(parts)

    def to_dict(self) -> Dict[str, object]:
        """Serialisable form used by the ``benchmark_validation`` block."""
        payload: Dict[str, object] = {
            "description": self.description(),
            "reference": self.source_key,
            "status": self.status,
            "property": self.property_name,
            "unit": self.unit,
            "{}_value".format(self.model_label.lower()): self.model_value,
            "reference_value": self.reference_value,
            "deviation": self.deviation,
            "tolerance_pct": self.tolerance_pct,
            "citation": self.citation,
        }
        if self.deviation_pct is not None:
            payload["deviation_pct"] = self.deviation_pct
        if self.within_source_uncertainty is not None:
            payload["within_source_uncertainty"] = self.within_source_uncertainty
        if not self.independent:
            payload["independent"] = False
        if self.note:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True)
class BenchmarkCase:
    """A model value queued for comparison against a reference point."""

    name: str
    model_value: float
    reference: ReferencePoint
    tolerance_pct: Optional[float] = None
    model_label: str = "neqsim"
    model_tier: str = "correlation"
    informational: bool = False
    note: str = ""


def compare(
    name: str,
    model_value: float,
    reference: ReferencePoint,
    tolerance_pct: Optional[float] = None,
    model_label: str = "neqsim",
    model_tier: str = "correlation",
    informational: bool = False,
    note: str = "",
) -> BenchmarkResult:
    """Compare one model value against one reference point."""
    tolerance = (
        tolerance_pct
        if tolerance_pct is not None
        else default_tolerance_pct(reference.property_name)
    )
    deviation = model_value - reference.value
    if reference.value == 0.0:
        deviation_pct = None
    else:
        deviation_pct = 100.0 * deviation / abs(reference.value)

    independent = reference.source.is_independent_of(model_tier)

    if informational or deviation_pct is None or not independent:
        status = STATUS_INFO
    elif abs(deviation_pct) <= tolerance:
        status = STATUS_PASS
    elif abs(deviation_pct) <= WARN_FACTOR * tolerance:
        status = STATUS_WARN
    else:
        status = STATUS_FAIL

    source_uncertainty = reference.effective_uncertainty_pct()
    within_uncertainty: Optional[bool] = None
    if deviation_pct is not None and source_uncertainty is not None:
        within_uncertainty = abs(deviation_pct) <= source_uncertainty

    notes: List[str] = []
    if note:
        notes.append(note)
    if not independent:
        notes.append(
            "reference tier '{}' does not outrank model tier '{}' — consistency "
            "check only, not a benchmark".format(reference.source.tier, model_tier)
        )
    if reference.note:
        notes.append(reference.note)

    return BenchmarkResult(
        name=name,
        property_name=reference.property_name,
        unit=reference.unit,
        model_label=model_label,
        model_value=model_value,
        reference_value=reference.value,
        deviation=deviation,
        deviation_pct=deviation_pct,
        tolerance_pct=tolerance,
        status=status,
        source_key=reference.source_key,
        citation=reference.citation,
        state=dict(reference.state),
        within_source_uncertainty=within_uncertainty,
        independent=independent,
        note="; ".join(notes),
    )


def compare_many(cases: Iterable[BenchmarkCase]) -> List[BenchmarkResult]:
    """Compare a batch of cases, preserving order."""
    return [
        compare(
            case.name,
            case.model_value,
            case.reference,
            tolerance_pct=case.tolerance_pct,
            model_label=case.model_label,
            model_tier=case.model_tier,
            informational=case.informational,
            note=case.note,
        )
        for case in cases
    ]
