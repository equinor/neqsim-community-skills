"""Normalize heterogeneous engineering inputs into a traceable CFD design basis.

A CFD case is only as good as the geometry and process data behind it. In a real
workflow those numbers arrive from several places at once - a P&ID, a tag register
such as STID, a mechanical datasheet, a process datasheet, historian data, or an
engineer's estimate. They overlap, they disagree, and some are missing.

This module merges those sources by precedence, records where every accepted value
came from, flags conflicts, and reports what is still missing before a mesh is
generated. It is deliberately generic: the component kind drives which fields are
required, so the same code serves a pipe, a bend, a vessel or a tube bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

# Highest authority first. A value from an earlier source wins a conflict.
SOURCE_PRECEDENCE: tuple[str, ...] = (
    "measurement",
    "mechanical_datasheet",
    "process_datasheet",
    "vendor",
    "stid",
    "plant_data",
    "pid",
    "estimate",
    "assumption",
)

_CONFIDENCE_BY_SOURCE: dict[str, str] = {
    "measurement": "high",
    "mechanical_datasheet": "high",
    "process_datasheet": "high",
    "vendor": "high",
    "stid": "medium",
    "plant_data": "medium",
    "pid": "medium",
    "estimate": "low",
    "assumption": "low",
}

# Geometry a CFD model needs, by the component class read off the P&ID.
GEOMETRY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "pipe": ("inside_diameter_m", "length_m"),
    "bend": ("inside_diameter_m", "bend_radius_m", "bend_angle_deg"),
    "tee": ("inside_diameter_m", "branch_inside_diameter_m", "length_m"),
    "reducer": ("inside_diameter_m", "outlet_inside_diameter_m", "length_m"),
    "orifice": ("inside_diameter_m", "bore_diameter_m", "length_m"),
    "valve": ("inside_diameter_m", "bore_diameter_m", "length_m"),
    "vessel": ("inside_diameter_m", "tangent_length_m", "inlet_nozzle_diameter_m"),
    "separator": ("inside_diameter_m", "tangent_length_m", "inlet_nozzle_diameter_m"),
    "manifold": ("header_inside_diameter_m", "branch_inside_diameter_m", "length_m"),
    "tube_bundle": ("tube_inside_diameter_m", "tube_length_m", "tube_count"),
    "channel": ("height_m", "width_m", "length_m"),
}

# Process data a CFD model needs regardless of the component class.
PROCESS_REQUIREMENTS: tuple[str, ...] = (
    "temperature_c",
    "pressure_bara",
    "mass_flow_kg_per_h",
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
class CfdDesignBasis:
    """A merged, traceable set of inputs sufficient (or not) to build a CFD case."""

    tag: str
    component_kind: str
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


def required_fields(component_kind: str) -> tuple[str, ...]:
    """Return the geometry and process fields a CFD case of this kind needs.

    Raises ``ValueError`` for an unknown component kind so an agent is forced to
    classify the component rather than silently meshing an under-specified case.
    """
    key = (component_kind or "").strip().lower()
    if key not in GEOMETRY_REQUIREMENTS:
        known = ", ".join(sorted(GEOMETRY_REQUIREMENTS))
        raise ValueError(f"unknown component_kind '{component_kind}'; known kinds: {known}")
    return GEOMETRY_REQUIREMENTS[key] + PROCESS_REQUIREMENTS


def build_design_basis(
    *,
    tag: str,
    component_kind: str,
    sources: Sequence[Mapping[str, Any]],
    units: Mapping[str, str] | None = None,
    extra_required: Sequence[str] = (),
    conflict_tolerance: float = 0.02,
) -> CfdDesignBasis:
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

    needed = tuple(dict.fromkeys(required_fields(component_kind) + tuple(extra_required)))
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
        "A photograph or sketch is not dimensional authority unless it carries a "
        "calibrated scale reference and has been corrected for perspective.",
    ]
    if conflicts:
        assumptions.append(
            f"{len(conflicts)} field conflict(s) exceed the {100.0 * conflict_tolerance:.0f} % "
            "tolerance and must be resolved by an engineer before the result is used."
        )
    if missing:
        assumptions.append(
            "Missing fields must be retrieved or explicitly assumed; do not invent "
            "geometry to make a mesh close."
        )

    return CfdDesignBasis(
        tag=tag.strip(),
        component_kind=(component_kind or "").strip().lower(),
        values={record.field: record.value for record in records},
        records=records,
        conflicts=tuple(conflicts),
        missing_fields=missing,
        ready_for_meshing=not missing and not conflicts,
        assumptions=tuple(assumptions),
    )


def _validated_source(entry: Mapping[str, Any]) -> str:
    source = str(entry.get("source", "")).strip().lower()
    if source not in _CONFIDENCE_BY_SOURCE:
        known = ", ".join(SOURCE_PRECEDENCE)
        raise ValueError(f"unknown source '{entry.get('source')}'; known sources: {known}")
    return source


def _precedence_index(entry: Mapping[str, Any]) -> int:
    return SOURCE_PRECEDENCE.index(_validated_source(entry))


def _relative_difference(first: Any, second: Any) -> float | None:
    """Return the relative difference of two numbers, or ``None`` if not comparable."""
    try:
        left = float(first)
        right = float(second)
    except (TypeError, ValueError):
        return None if first == second else 1.0
    if not (isfinite(left) and isfinite(right)):
        return None
    scale = max(abs(left), abs(right))
    if scale == 0.0:
        return 0.0
    return abs(left - right) / scale


def _infer_unit(field: str) -> str:
    for suffix, unit in (
        ("_m", "m"),
        ("_m2", "m2"),
        ("_c", "degC"),
        ("_bara", "bara"),
        ("_deg", "deg"),
        ("_kg_per_h", "kg/h"),
        ("_kg_per_s", "kg/s"),
        ("_m3_per_h", "m3/h"),
        ("_count", "-"),
    ):
        if field.endswith(suffix):
            return unit
    return "-"
