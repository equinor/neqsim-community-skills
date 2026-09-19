"""Normalise heterogeneous engineering inputs into a traceable FEM design basis.

A finite-element model is only as good as the geometry, the material assignment
and the boundary conditions behind it. In a real workflow those numbers arrive
from several places at once - a P&ID, a tag register such as STID, a mechanical
datasheet, an insulation specification, a coating report, an inspection report,
historian data, or an engineer's estimate. They overlap, they disagree, and some
are missing.

This module merges those sources by precedence, records where every accepted value
came from, flags conflicts, and reports what is still missing before a mesh is
generated. The model kind drives which fields are required, so the same code serves
an insulated flowline, a vessel wall, a wellbore-to-formation stack and a porous
block.

It is deliberately close in shape to the design basis in the CFD-coupling skill,
because the two are normally assembled from the same documents in the same task -
but the required fields differ: CFD needs a flow area, FEM needs a layer build-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

# Highest authority first. A value from an earlier source wins a conflict.
SOURCE_PRECEDENCE: tuple[str, ...] = (
    "measurement",
    "mechanical_datasheet",
    "material_certificate",
    "insulation_specification",
    "process_datasheet",
    "vendor",
    "stid",
    "inspection_report",
    "plant_data",
    "pid",
    "estimate",
    "assumption",
)

_CONFIDENCE_BY_SOURCE: dict[str, str] = {
    "measurement": "high",
    "mechanical_datasheet": "high",
    "material_certificate": "high",
    "insulation_specification": "high",
    "process_datasheet": "high",
    "vendor": "high",
    "stid": "medium",
    "inspection_report": "medium",
    "plant_data": "medium",
    "pid": "medium",
    "estimate": "low",
    "assumption": "low",
}

# Geometry and material build-up a finite-element model needs, by model kind.
MODEL_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "insulated_pipe": (
        "inside_diameter_m",
        "wall_thickness_m",
        "wall_material",
        "insulation_thickness_m",
        "insulation_material",
    ),
    "pipe_wall": ("inside_diameter_m", "wall_thickness_m", "wall_material"),
    "buried_pipeline": (
        "inside_diameter_m",
        "wall_thickness_m",
        "wall_material",
        "insulation_thickness_m",
        "insulation_material",
        "burial_depth_m",
        "soil_material",
    ),
    "vessel_wall": ("inside_diameter_m", "wall_thickness_m", "wall_material"),
    "plate": ("thickness_m", "wall_material"),
    "nozzle": (
        "inside_diameter_m",
        "wall_thickness_m",
        "wall_material",
        "shell_inside_diameter_m",
        "shell_thickness_m",
    ),
    "wellbore": (
        "inside_diameter_m",
        "wall_thickness_m",
        "wall_material",
        "cement_thickness_m",
        "cement_material",
        "formation_radius_m",
        "formation_material",
    ),
    "porous_block": ("length_m", "height_m", "porosity", "tortuosity", "rock_material"),
}

# Thermal boundary data every conduction model needs regardless of model kind.
THERMAL_REQUIREMENTS: tuple[str, ...] = (
    "internal_temperature_c",
    "external_temperature_c",
    "external_film_coefficient_w_per_m2k",
)

# Additional fields a thermal-stress evaluation needs on top of the thermal ones.
STRESS_REQUIREMENTS: tuple[str, ...] = (
    "design_pressure_bara",
    "restraint_condition",
)

_UNIT_HINTS: tuple[tuple[str, str], ...] = (
    ("_temperature_c", "degC"),
    ("temperature_c", "degC"),
    ("_thickness_m", "m"),
    ("_diameter_m", "m"),
    ("_radius_m", "m"),
    ("_depth_m", "m"),
    ("_length_m", "m"),
    ("length_m", "m"),
    ("height_m", "m"),
    ("_bara", "bara"),
    ("_w_per_m2k", "W/m2.K"),
    ("_w_per_mk", "W/m.K"),
    ("_kg_per_h", "kg/h"),
    ("_m2_per_s", "m2/s"),
)


@dataclass(frozen=True)
class FieldRecord:
    """One accepted design-basis value and where it came from."""

    field: str
    value: Any
    unit: str
    source: str
    confidence: str
    reference: str


@dataclass(frozen=True)
class FieldConflict:
    """Two sources disagreed about the same field beyond tolerance."""

    field: str
    accepted_value: Any
    accepted_source: str
    rejected_value: Any
    rejected_source: str
    relative_difference: float


@dataclass(frozen=True)
class FemDesignBasis:
    """A merged, traceable set of inputs sufficient (or not) to build a FEM model."""

    tag: str
    model_kind: str
    values: Mapping[str, Any]
    records: tuple[FieldRecord, ...]
    conflicts: tuple[FieldConflict, ...]
    missing_fields: tuple[str, ...]
    ready_for_meshing: bool
    assumptions: tuple[str, ...]

    def value(self, field: str, default: Any = None) -> Any:
        """Return an accepted value, or ``default`` when the field is missing."""
        return self.values.get(field, default)

    def source_of(self, field: str) -> str | None:
        """Return the source that supplied ``field``, or ``None``."""
        for record in self.records:
            if record.field == field:
                return record.source
        return None

    def traceability_rows(self) -> tuple[dict[str, Any], ...]:
        """Return rows suitable for a report traceability table."""
        return tuple(
            {
                "field": record.field,
                "value": record.value,
                "unit": record.unit,
                "source": record.source,
                "confidence": record.confidence,
                "reference": record.reference,
            }
            for record in self.records
        )


def required_fields(model_kind: str, *, include_stress: bool = False) -> tuple[str, ...]:
    """Return the fields a finite-element model of this kind needs.

    Raises ``ValueError`` for an unknown model kind so an agent is forced to
    classify the component rather than silently meshing an under-specified model.
    """
    key = (model_kind or "").strip().lower()
    if key not in MODEL_REQUIREMENTS:
        known = ", ".join(sorted(MODEL_REQUIREMENTS))
        raise ValueError(f"unknown model_kind '{model_kind}'; known kinds: {known}")
    fields = MODEL_REQUIREMENTS[key] + THERMAL_REQUIREMENTS
    if include_stress:
        fields += STRESS_REQUIREMENTS
    return fields


def build_design_basis(
    *,
    tag: str,
    model_kind: str,
    sources: Sequence[Mapping[str, Any]],
    units: Mapping[str, str] | None = None,
    include_stress: bool = False,
    extra_required: Sequence[str] = (),
    conflict_tolerance: float = 0.02,
) -> FemDesignBasis:
    """Merge partial inputs from several sources into one traceable design basis.

    Each entry of ``sources`` is a mapping with a ``source`` key drawn from
    :data:`SOURCE_PRECEDENCE`, an optional ``reference`` string (document number,
    STID tag, historian tag), and a ``values`` mapping of field name to value.
    Values that are ``None`` are ignored, so a partially populated document
    extraction can be passed in as-is.
    """
    if not tag or not tag.strip():
        raise ValueError("tag must be a non-empty equipment or line identifier")
    if not 0.0 < conflict_tolerance < 1.0:
        raise ValueError("conflict_tolerance must be a fraction between 0 and 1")

    needed = tuple(
        dict.fromkeys(
            required_fields(model_kind, include_stress=include_stress) + tuple(extra_required)
        )
    )
    unit_map = dict(units or {})

    ranked = sorted(sources, key=_precedence_index)
    accepted: dict[str, FieldRecord] = {}
    conflicts: list[FieldConflict] = []

    for entry in ranked:
        source = _validated_source(entry)
        reference = str(entry.get("reference", "")).strip() or "not recorded"
        values = entry.get("values") or {}
        if not isinstance(values, Mapping):
            raise ValueError(f"source '{source}' must provide a mapping under 'values'")

        for field, raw in values.items():
            if raw is None:
                continue
            existing = accepted.get(field)
            if existing is None:
                accepted[field] = FieldRecord(
                    field=field,
                    value=raw,
                    unit=unit_map.get(field, _infer_unit(field)),
                    source=source,
                    confidence=_CONFIDENCE_BY_SOURCE[source],
                    reference=reference,
                )
                continue

            difference = _relative_difference(existing.value, raw)
            if difference is not None and difference > conflict_tolerance:
                conflicts.append(
                    FieldConflict(
                        field=field,
                        accepted_value=existing.value,
                        accepted_source=existing.source,
                        rejected_value=raw,
                        rejected_source=source,
                        relative_difference=round(difference, 4),
                    )
                )

    missing = tuple(field for field in needed if field not in accepted)
    records = tuple(sorted(accepted.values(), key=lambda record: record.field))

    assumptions = [
        "Values are merged by source precedence; a lower-ranked source never "
        "overwrites a higher-ranked one, it only raises a conflict.",
        "An as-built insulation thickness is not the specified thickness. Where an "
        "inspection report exists it outranks the specification for the as-is case.",
        "A photograph or sketch is not dimensional authority unless it carries a "
        "calibrated scale reference and has been corrected for perspective.",
    ]
    if conflicts:
        assumptions.append(
            f"{len(conflicts)} field conflict(s) exceed the "
            f"{100.0 * conflict_tolerance:.0f} % tolerance and must be resolved by an "
            "engineer before the result is used."
        )
    if missing:
        assumptions.append(
            "Missing fields must be retrieved or explicitly assumed; do not invent a "
            "layer thickness or a material grade to make a mesh close."
        )

    return FemDesignBasis(
        tag=tag.strip(),
        model_kind=(model_kind or "").strip().lower(),
        values={record.field: record.value for record in records},
        records=records,
        conflicts=tuple(conflicts),
        missing_fields=missing,
        ready_for_meshing=not missing and not conflicts,
        assumptions=tuple(assumptions),
    )


def _precedence_index(entry: Mapping[str, Any]) -> int:
    return SOURCE_PRECEDENCE.index(_validated_source(entry))


def _validated_source(entry: Mapping[str, Any]) -> str:
    source = str(entry.get("source", "")).strip().lower()
    if source not in SOURCE_PRECEDENCE:
        known = ", ".join(SOURCE_PRECEDENCE)
        raise ValueError(f"unknown source '{source}'; known sources: {known}")
    return source


def _relative_difference(first: Any, second: Any) -> float | None:
    """Relative difference between two numeric values, or ``None`` if not numeric."""
    try:
        left = float(first)
        right = float(second)
    except (TypeError, ValueError):
        # Non-numeric fields such as a material grade: any difference is a conflict.
        return None if str(first) == str(second) else 1.0
    if not (isfinite(left) and isfinite(right)):
        return None
    scale = max(abs(left), abs(right))
    if scale == 0.0:
        return 0.0
    return abs(left - right) / scale


def _infer_unit(field: str) -> str:
    for suffix, unit in _UNIT_HINTS:
        if field.endswith(suffix):
            return unit
    return "-"
