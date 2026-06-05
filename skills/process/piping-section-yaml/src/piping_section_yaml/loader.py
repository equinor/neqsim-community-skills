from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any


# Equivalent-length L/D ratios (Crane Technical Paper No. 410, turbulent, full open).
# L/D = equivalent pipe length expressed as a multiple of the pipe inner diameter.
FITTING_LD: dict[str, float] = {
    "elbow_90": 20.0,        # 90 deg long-radius elbow
    "elbow_90_LR": 20.0,     # 90 deg long-radius elbow (explicit)
    "elbow_90_short": 30.0,  # 90 deg short-radius elbow
    "elbow_45": 16.0,        # 45 deg elbow
    "tee_run": 20.0,         # tee, flow through run
    "tee_branch": 60.0,      # tee, flow through branch
    "ball_valve": 3.0,       # ball valve, full bore, full open
    "gate_valve": 8.0,       # gate valve, full open
    "check_valve": 50.0,     # swing check valve
    "reducer": 0.0,          # gradual reducer, negligible
}

DEFAULT_WALL_ROUGHNESS_M = 4.6e-5  # commercial carbon steel

_EQUIPMENT_TYPES = (
    "three_phase_separator",
    "gas_scrubber",
    "cooler",
    "valve",
    "tuning_valve",
)


@dataclass(frozen=True)
class PipingSection:
    """Parsed piping section topology."""

    section_id: str
    description: str
    nodes: dict[str, dict[str, Any]]
    segments: tuple[dict[str, Any], ...]
    equipment: tuple[dict[str, Any], ...]
    flow_path: tuple[dict[str, Any], ...]


def _require_finite(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")


def _require_positive(name: str, value: float) -> None:
    _require_finite(name, value)
    if float(value) <= 0.0:
        raise ValueError(f"{name} must be positive")


def fittings_equivalent_length(
    fittings: list[dict[str, Any]], inner_diameter_m: float
) -> float:
    """Return the extra equivalent pipe length (m) contributed by fittings.

    Uses the Crane TP-410 L/D ratios in ``FITTING_LD``. Unknown fitting types
    contribute zero length.
    """
    _require_positive("inner_diameter_m", inner_diameter_m)
    extra = 0.0
    for fitting in fittings:
        ld = FITTING_LD.get(fitting.get("type", ""), 0.0)
        count = fitting.get("count", 1)
        _require_finite("fitting count", count)
        if count < 0:
            raise ValueError("fitting count must be non-negative")
        extra += ld * float(inner_diameter_m) * float(count)
    return extra


def _walk(items: list[dict[str, Any]], nodes, segments, equipment) -> None:
    for item in items:
        kind = item.get("type")
        if kind == "node":
            node_id = item["id"]
            nodes[node_id] = {k: v for k, v in item.items() if k not in ("type", "id")}
        elif kind == "segment":
            segments.append({k: v for k, v in item.items() if k != "type"})
        elif kind == "equipment":
            equipment.append({k: v for k, v in item.items() if k != "type"})
        elif kind == "parallel":
            for branch in item.get("branches", []):
                _walk(branch, nodes, segments, equipment)


def load_section(data: dict[str, Any]) -> PipingSection:
    """Parse a section mapping into a :class:`PipingSection`.

    Validates the schema first; raises ``ValueError`` on problems.
    """
    validate_section(data)
    nodes: dict[str, dict[str, Any]] = {}
    segments: list[dict[str, Any]] = []
    equipment: list[dict[str, Any]] = []
    _walk(data["flow_path"], nodes, segments, equipment)
    return PipingSection(
        section_id=data["section_id"],
        description=data.get("description", ""),
        nodes=nodes,
        segments=tuple(segments),
        equipment=tuple(equipment),
        flow_path=tuple(data["flow_path"]),
    )


def validate_section(data: dict[str, Any]) -> None:
    """Validate a section mapping. Raises ``ValueError`` listing all problems."""
    problems: list[str] = []

    if not isinstance(data, dict):
        raise ValueError("section data must be a mapping")
    if not data.get("section_id"):
        problems.append("missing required key 'section_id'")
    flow_path = data.get("flow_path")
    if not isinstance(flow_path, list) or not flow_path:
        problems.append("'flow_path' must be a non-empty list")
        if problems:
            raise ValueError("; ".join(problems))

    def _check(items: list[dict[str, Any]], path: str) -> None:
        for i, item in enumerate(items):
            loc = f"{path}[{i}]"
            kind = item.get("type")
            if kind == "node":
                if not item.get("id"):
                    problems.append(f"{loc} node missing 'id'")
            elif kind == "segment":
                if not item.get("id"):
                    problems.append(f"{loc} segment missing 'id'")
                for key in ("length_m", "inner_diameter_m"):
                    value = item.get(key)
                    if not isinstance(value, (int, float)) or value <= 0:
                        problems.append(f"{loc} segment '{key}' must be positive")
                for fitting in item.get("fittings", []):
                    if fitting.get("type") not in FITTING_LD:
                        problems.append(
                            f"{loc} unknown fitting type '{fitting.get('type')}'"
                        )
            elif kind == "equipment":
                if not item.get("id"):
                    problems.append(f"{loc} equipment missing 'id'")
                if item.get("equipment_type") not in _EQUIPMENT_TYPES:
                    problems.append(
                        f"{loc} unknown equipment_type '{item.get('equipment_type')}'"
                    )
            elif kind == "parallel":
                branches = item.get("branches")
                if not isinstance(branches, list) or not branches:
                    problems.append(f"{loc} parallel must have non-empty 'branches'")
                else:
                    for j, branch in enumerate(branches):
                        if not isinstance(branch, list) or not branch:
                            problems.append(f"{loc}.branches[{j}] must be a non-empty list")
                        else:
                            _check(branch, f"{loc}.branches[{j}]")
            else:
                problems.append(f"{loc} unknown item type '{kind}'")

    _check(flow_path, "flow_path")
    if problems:
        raise ValueError("; ".join(problems))


def total_length(section: PipingSection) -> float:
    """Sum of physical segment lengths (m), excluding fitting equivalents."""
    return sum(float(seg["length_m"]) for seg in section.segments)


def total_elevation(section: PipingSection) -> float:
    """Net elevation change (m) across all segments (positive = upward)."""
    return sum(float(seg.get("elevation_m", 0.0)) for seg in section.segments)


def inspect_section(section: PipingSection) -> list[dict[str, Any]]:
    """Return an ordered, flattened description of every flow_path item."""
    rows: list[dict[str, Any]] = []

    def _walk_inspect(items: list[dict[str, Any]], depth: int) -> None:
        for item in items:
            kind = item.get("type")
            if kind == "parallel":
                rows.append({"kind": "parallel_start", "depth": depth,
                             "branches": len(item.get("branches", []))})
                for branch in item.get("branches", []):
                    _walk_inspect(branch, depth + 1)
                rows.append({"kind": "parallel_end", "depth": depth})
            elif kind == "segment":
                diameter = float(item["inner_diameter_m"])
                extra = fittings_equivalent_length(item.get("fittings", []), diameter)
                rows.append({
                    "kind": "segment", "id": item.get("id"), "depth": depth,
                    "length_m": float(item["length_m"]),
                    "inner_diameter_m": diameter,
                    "elevation_m": float(item.get("elevation_m", 0.0)),
                    "fitting_equiv_length_m": round(extra, 4),
                })
            else:
                rows.append({"kind": kind, "id": item.get("id"), "depth": depth})

    _walk_inspect(list(section.flow_path), 0)
    return rows


def load_yaml_file(path: str) -> dict[str, Any]:
    """Load a YAML section file into a mapping. Requires PyYAML."""
    import yaml  # local import keeps the core importable without PyYAML

    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
