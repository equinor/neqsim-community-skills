"""Open-data adapter: Sodir facility and pipeline rows to inventory items (status and verification kept honest).

Sodir (NLOD 2.0) lists facilities, pipelines and their phase but **not** free slots or spare lines. Slots are therefore
returned as ``estimated`` (nominal slots minus connected wells) and never ``documented``; pipelines in service are
``in_use``, pipelines with a non-service phase are ``abandoned`` or ``unknown``, so nothing is called spare from open data.
"""
from __future__ import annotations

from .inventory import normalize_item

_KIND_BY_FACILITY = (("TEMPLATE", "template"), ("MANIFOLD", "manifold"), ("PLEM", "plem"), ("PLET", "plet"), ("RISER", "riser_slot"))
_SERVICE_BY_MEDIUM = {"OIL": "oil", "GAS": "gas", "CONDENSATE": "oil", "OIL/GAS": "multiphase", "MULTIPHASE": "multiphase", "WATER": "water_injection",
                      "NGL": "oil", "LPG": "oil", "CO2": "gas_injection", "METHANOL": "meg", "MEG": "meg", "CHEMICAL": "chemical"}


def _status_from_phase(phase):
    p = str(phase or "").upper()
    if p == "IN SERVICE":
        return "in_use"
    if p in ("SHUT DOWN", "OUT OF USE", "DISUSED"):
        return "abandoned"
    if p in ("PLANNED", "APPROVED", "UNDER CONSTRUCTION", "PDO"):
        return "planned"
    return "unknown"


def items_from_sodir(facilities=(), pipelines=(), wells_per_facility=None, nominal_slots=None, as_of_year=None):
    """Convert raw Sodir rows (dicts with ``fcl*`` / ``ppl*`` attributes) to normalized inventory items.

    Args:
        facilities: Sodir facility rows (fclName, fclKind, fclPhase, fclWaterDepth, fclStartupDate, fclDesignLifetime).
        pipelines: Sodir pipeline rows (pplName, pplMedium, pplDimension, fclNameFrom, fclNameTo, pplCurrentPhase).
        wells_per_facility: optional ``{facility name: connected wells}``.
        nominal_slots: optional ``{facility name: nominal slot count}`` (from a document; otherwise slots stay unknown).
    """
    wells_per_facility = wells_per_facility or {}
    nominal_slots = nominal_slots or {}
    items = []
    for row in facilities:
        kind_text = str(row.get("fclKind") or "").upper()
        kind = next((k for needle, k in _KIND_BY_FACILITY if needle in kind_text), None)
        if kind is None:
            continue
        name = row.get("fclName")
        total = nominal_slots.get(name)
        used = wells_per_facility.get(name)
        free = (total - used) if total is not None and used is not None else None
        start = str(row.get("fclStartupDate") or "")[:4]
        items.append(normalize_item({
            "id": name, "name": name, "kind": kind, "status": _status_from_phase(row.get("fclPhase")), "service": "unknown",
            "water_depth_m": row.get("fclWaterDepth"), "install_year": int(start) if start.isdigit() else None,
            "design_life_years": row.get("fclDesignLifetime"), "total_slots": total, "free_slots": free,
            "verification": "estimated" if free is not None else "unknown", "source": "Sodir facility %s" % name,
            "notes": "slot numbers are not published by Sodir; count is nominal minus connected wells" if free is not None else "slot data not in open data"}, as_of_year))
    for row in pipelines:
        medium = str(row.get("pplMedium") or "").upper()
        items.append(normalize_item({
            "id": row.get("pplName"), "name": row.get("pplName"), "kind": "pipeline", "status": _status_from_phase(row.get("pplCurrentPhase")),
            "service": _SERVICE_BY_MEDIUM.get(medium, "unknown"), "size_in": row.get("pplDimension"),
            "connects": [x for x in (row.get("fclNameFrom"), row.get("fclNameTo")) if x], "verification": "documented",
            "source": "Sodir pipeline %s" % row.get("pplName")}, as_of_year))
    return items
