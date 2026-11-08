"""Limit catalogue, loader and gap register for the placement screening.

The screening never invents a limit. This module makes the limits explicit and auditable: a catalogue of every limit key the checks use
(what it limits, its unit and direction), a loader that validates a supplied limits file (each limit needs a unit and a basis, and an
approved or supplied limit also needs a source such as a standard, clause or design-basis item), and a gap register that lists which limits
are still open so the report can name the document or decision that closes each one.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Mapping, Optional, Union

from .placement import APPROVED_BASES, Limit

BASES = ("APPROVED", "SUPPLIED", "ASSUMED", "NONE")

# key -> description, unit, direction of the check, check ids that use it, and what normally closes it
LIMIT_CATALOG: Dict[str, dict] = {
    "zone_clearance_m": {"description": "Smallest distance to an active hard exclusion zone", "unit": "m", "operator": ">=", "checks": ["ZONE"],
                         "closed_by": "authority or safety-zone rules for the area"},
    "structure_clearance_m": {"description": "Smallest distance to an existing structure or the host", "unit": "m", "operator": ">=", "checks": ["STRUCT"],
                              "closed_by": "operator requirement or project design basis (installation and intervention access)"},
    "line_clearance_m": {"description": "Smallest distance to an existing line or cable", "unit": "m", "operator": ">=", "checks": ["LINE", "PARALLEL"],
                         "closed_by": "a recorded risk assessment, or the owner's requirement for the line"},
    "max_slope_deg": {"description": "Largest seabed slope in the footprint or along the route", "unit": "deg", "operator": "<=", "checks": ["SLOPE"],
                      "closed_by": "foundation and levelling-system capability for structures, route-stability and installation limits for lines"},
    "min_water_depth_m": {"description": "Smallest water depth of the supported system envelope", "unit": "m", "operator": ">=", "checks": ["DEPTH_MIN"],
                          "closed_by": "the standard system catalogue or vendor envelope"},
    "max_water_depth_m": {"description": "Largest water depth of the supported system envelope", "unit": "m", "operator": "<=", "checks": ["DEPTH"],
                          "closed_by": "the standard system catalogue or vendor envelope"},
    "max_fishing_intensity": {"description": "Largest accepted fishing intensity (user-defined measure)", "unit": "-", "operator": "<=", "checks": ["FISHING"],
                              "closed_by": "the fishing-impact assessment and protection philosophy"},
    "max_horizontal_reach_m": {"description": "Largest horizontal reach from the site to a well target", "unit": "m", "operator": "<=", "checks": ["REACH"],
                               "closed_by": "the well-planning feasibility study"},
    "max_erd_ratio": {"description": "Largest horizontal-reach to TVD ratio", "unit": "-", "operator": "<=", "checks": ["ERD"],
                      "closed_by": "the well-planning feasibility study (torque, drag, hole cleaning, casing)"},
    "max_stepout_m": {"description": "Largest distance from the site to the host", "unit": "m", "operator": "<=", "checks": ["STEPOUT"],
                      "closed_by": "the standard system catalogue, flow-assurance and control-system reach"},
    "max_route_length_m": {"description": "Longest accepted route", "unit": "m", "operator": "<=", "checks": ["LENGTH"],
                           "closed_by": "hydraulic, thermal and cost screening"},
    "max_crossings": {"description": "Largest number of crossings with existing lines", "unit": "-", "operator": "<=", "checks": ["XCOUNT"],
                      "closed_by": "project design basis and the owners of the crossed lines"},
    "min_crossing_angle_deg": {"description": "Smallest accepted crossing angle", "unit": "deg", "operator": ">=", "checks": ["XANGLE"],
                               "closed_by": "the crossing design basis agreed with the owner of the crossed line"},
    "min_straight_end_m": {"description": "Shortest straight length at each end of a route (before a structure or tie-in)", "unit": "m", "operator": ">=",
                           "checks": ["STRAIGHT_START", "STRAIGHT_END"], "closed_by": "tie-in and installation requirements for the connection"},
}


def limits_template() -> dict:
    """An empty limits document: every limit key with its description, unit and direction, no value and basis NONE."""
    return {"schema": "placement_limits.v1", "limits": {k: {"value": None, "unit": v["unit"], "source": "", "basis": "NONE", "description": v["description"],
                                                            "operator": v["operator"]} for k, v in LIMIT_CATALOG.items()}}


def write_limits_template(path: Union[str, os.PathLike]) -> str:
    """Write :func:`limits_template` as JSON and return the path, to be filled by the design basis owner."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(limits_template(), handle, indent=2)
    return str(path)


def _read(source: Union[str, os.PathLike, Mapping]) -> Mapping:
    if isinstance(source, Mapping):
        return source
    with open(source, "r", encoding="utf-8") as handle:
        text = handle.read()
    if str(source).lower().endswith((".yaml", ".yml")):
        import yaml  # optional dependency, only needed for YAML limit files

        return yaml.safe_load(text)
    return json.loads(text)


def load_limits(source: Union[str, os.PathLike, Mapping]) -> Dict[str, Limit]:
    """Validate and load a limits document (dict, JSON or YAML file) into ``{key: Limit}``.

    Rules: keys must be in :data:`LIMIT_CATALOG`; a value is a finite number or null; the unit must match the catalogue; ``basis`` is one of
    APPROVED, SUPPLIED, ASSUMED, NONE; an APPROVED or SUPPLIED limit needs a value and a source (standard and clause, or design-basis item).
    A limit without a value is loaded as basis NONE. Raises ``ValueError`` listing every problem.
    """
    data = _read(source)
    limits = data.get("limits", data) if isinstance(data, Mapping) else None
    if not isinstance(limits, Mapping):
        raise ValueError("the limits document must be a mapping (optionally under a 'limits' key)")
    problems: List[str] = []
    out: Dict[str, Limit] = {}
    for key, rec in limits.items():
        if key == "schema":
            continue
        if key not in LIMIT_CATALOG:
            problems.append("unknown limit key %r" % key)
            continue
        if not isinstance(rec, Mapping):
            problems.append("%s: entry must be a mapping with value, unit, source and basis" % key)
            continue
        value = rec.get("value")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or abs(value) == float("inf")):
            problems.append("%s: value must be a finite number or null" % key)
            continue
        unit = rec.get("unit", LIMIT_CATALOG[key]["unit"])
        if unit != LIMIT_CATALOG[key]["unit"]:
            problems.append("%s: unit %r does not match %r" % (key, unit, LIMIT_CATALOG[key]["unit"]))
        basis = rec.get("basis", "NONE" if value is None else "ASSUMED")
        if basis not in BASES:
            problems.append("%s: basis must be one of %s" % (key, ", ".join(BASES)))
            continue
        source_text = str(rec.get("source", "") or "")
        if basis in APPROVED_BASES and (value is None or not source_text):
            problems.append("%s: an %s limit needs a value and a source" % (key, basis))
            continue
        out[key] = Limit(None if value is None else float(value), unit, source_text, "NONE" if value is None else basis)
    if problems:
        raise ValueError("invalid limits document: " + "; ".join(problems))
    return out


def limits_gap_register(limits: Mapping[str, Limit], keys: Optional[Iterable[str]] = None) -> List[dict]:
    """One row per catalogue limit: ``CLOSED`` when approved or supplied with a source, otherwise ``OPEN`` with what closes it.

    Use it in every report so an ASSUMED screening value is listed as a gap, never read as a requirement.
    """
    rows = []
    for key in (list(keys) if keys is not None else list(LIMIT_CATALOG)):
        spec = LIMIT_CATALOG[key]
        lim: Optional[Limit] = limits.get(key)
        closed = lim is not None and lim.approved
        rows.append({"key": key, "description": spec["description"], "unit": spec["unit"], "operator": spec["operator"], "checks": spec["checks"],
                     "status": "CLOSED" if closed else "OPEN", "basis": "NONE" if lim is None else lim.basis,
                     "value": None if lim is None else lim.value, "source": "" if lim is None else lim.source,
                     "closed_by": "" if closed else spec["closed_by"]})
    return rows
