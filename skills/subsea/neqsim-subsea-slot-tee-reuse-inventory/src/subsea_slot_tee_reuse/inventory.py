"""Inventory model: items, status, verification level, free-slot and reusable-line tables, validation.

An inventory is a JSON object ``{"schema": "neqsim.subsea_infrastructure_inventory.v1", "host": ..., "as_of": ..., "items": [...]}``.
Every item carries a ``status`` (in_use, spare, abandoned, planned, unknown), a ``verification`` level (documented,
measured, estimated, unknown) and a ``source``. A spare slot or line is only *evidence of availability*; hydraulic and
host capacity, flow-assurance compatibility and remaining life are checked separately (see :mod:`ranking`).
"""
from __future__ import annotations

import json
import os
from datetime import date

INVENTORY_SCHEMA = "neqsim.subsea_infrastructure_inventory.v1"

KINDS = (
    "host", "template", "manifold", "slot", "tee", "hub", "plet", "plem", "well",
    "pipeline", "flowline", "riser", "j_tube", "riser_slot", "umbilical", "umbilical_core", "spool",
    "gas_lift_line", "injection_line", "meg_line", "chemical_line", "cable",
)
LINE_KINDS = ("pipeline", "flowline", "riser", "gas_lift_line", "injection_line", "meg_line", "chemical_line", "umbilical_core", "spool")
STATUSES = ("in_use", "spare", "abandoned", "planned", "unknown")
SERVICES = (
    "oil", "gas", "multiphase", "water_injection", "gas_injection", "gas_lift", "meg", "chemical", "hydraulic",
    "power", "control", "produced_water", "unknown",
)
VERIFICATION = ("measured", "documented", "estimated", "unknown")
CONDITIONS = ("good", "fair", "poor", "unknown")


def _num(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_item(raw, as_of_year=None):
    """Return a copy of ``raw`` with defaults, numeric coercion and ``remaining_life_years`` derived when possible."""
    year = as_of_year or date.today().year
    it = dict(raw)
    it.setdefault("id", it.get("name") or "item")
    it.setdefault("name", it["id"])
    it["kind"] = str(it.get("kind", "pipeline")).lower()
    it["status"] = str(it.get("status", "unknown")).lower()
    it["service"] = str(it.get("service", "unknown")).lower()
    it["verification"] = str(it.get("verification", "unknown")).lower()
    it["condition"] = str(it.get("condition", "unknown")).lower()
    for key in ("size_in", "pressure_rating_bar", "length_km", "free_slots", "total_slots", "install_year", "design_life_years",
                "remaining_life_years", "water_depth_m"):
        it[key] = _num(it.get(key))
    if it["remaining_life_years"] is None and it["install_year"] is not None and it["design_life_years"] is not None:
        it["remaining_life_years"] = round(it["install_year"] + it["design_life_years"] - year, 1)
    it.setdefault("source", "unspecified")
    it.setdefault("connects", [])
    it.setdefault("notes", "")
    return it


def validate_inventory(inv, as_of_year=None):
    """Check an inventory dict; returns a list of ``{"level": "error"|"warning", "item", "message"}``."""
    issues = []

    def add(level, item, msg):
        issues.append({"level": level, "item": item, "message": msg})

    if inv.get("schema") != INVENTORY_SCHEMA:
        add("error", None, "schema must be %s" % INVENTORY_SCHEMA)
    ids = set()
    items = [normalize_item(i, as_of_year) for i in inv.get("items", [])]
    if not items:
        add("error", None, "inventory has no items")
    for it in items:
        iid = it["id"]
        if iid in ids:
            add("error", iid, "duplicate id")
        ids.add(iid)
        for key, allowed in (("kind", KINDS), ("status", STATUSES), ("service", SERVICES), ("verification", VERIFICATION), ("condition", CONDITIONS)):
            if it[key] not in allowed:
                add("error", iid, "%s '%s' not in %s" % (key, it[key], list(allowed)))
        if it["kind"] in ("template", "manifold", "hub", "host", "riser_slot", "j_tube"):
            tot, free = it["total_slots"], it["free_slots"]
            if tot is not None and free is not None and free > tot:
                add("error", iid, "free_slots %.0f exceeds total_slots %.0f" % (free, tot))
            if free is not None and free > 0 and it["verification"] in ("estimated", "unknown"):
                add("warning", iid, "free slots are %s, not documented: do not present them as free" % it["verification"])
        if it["status"] in ("spare", "abandoned") and it["verification"] == "unknown":
            add("warning", iid, "%s claimed without any documentation" % it["status"])
        if it["kind"] in LINE_KINDS and it["status"] != "planned":
            if it["size_in"] is None:
                add("warning", iid, "line without size_in: hydraulic screening impossible")
            if it["length_km"] is None:
                add("warning", iid, "line without length_km")
            if it["remaining_life_years"] is None:
                add("warning", iid, "no remaining life or install year/design life: lifetime action cannot be set")
        for ref in it["connects"]:
            if ref not in {i.get("id", i.get("name")) for i in inv.get("items", [])}:
                add("warning", iid, "connects to unknown id '%s'" % ref)
    return issues


def free_slot_table(inv, as_of_year=None):
    """Per template/manifold/hub/riser-slot: total, free, in use and the verification tier of the count."""
    rows = []
    for it in (normalize_item(i, as_of_year) for i in inv.get("items", [])):
        if it["kind"] not in ("template", "manifold", "hub", "host", "riser_slot", "j_tube", "tee"):
            continue
        tot, free = it["total_slots"], it["free_slots"]
        rows.append({
            "id": it["id"], "name": it["name"], "kind": it["kind"], "status": it["status"],
            "total_slots": tot, "free_slots": free, "in_use_slots": (tot - free) if tot is not None and free is not None else None,
            "verification": it["verification"], "hub_type": it.get("hub_type"), "source": it["source"],
            "usable_as_free": bool(free and free > 0 and it["verification"] in ("documented", "measured")),
        })
    return rows


def reusable_lines(inv, as_of_year=None, statuses=("spare", "abandoned", "in_use"), include_in_use=False):
    """Lines that could be reused: spare, abandoned, or (``include_in_use``) in-use lines with a repurposing option."""
    out = []
    for it in (normalize_item(i, as_of_year) for i in inv.get("items", [])):
        if it["kind"] not in LINE_KINDS or it["status"] not in statuses:
            continue
        if it["status"] == "in_use" and not (include_in_use or it.get("repurpose_option")):
            continue
        out.append(it)
    return out


def summarize(inv, as_of_year=None):
    """Counts by kind and status, free slots by verification tier, spare line kilometres by service."""
    items = [normalize_item(i, as_of_year) for i in inv.get("items", [])]
    by_status, by_kind = {}, {}
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    tiers = {}
    for row in free_slot_table(inv, as_of_year):
        if row["free_slots"]:
            tiers[row["verification"]] = tiers.get(row["verification"], 0) + int(row["free_slots"])
    spare_km = {}
    for it in reusable_lines(inv, as_of_year, statuses=("spare", "abandoned")):
        if it["length_km"]:
            spare_km[it["service"]] = round(spare_km.get(it["service"], 0.0) + it["length_km"], 2)
    return {"host": inv.get("host"), "items": len(items), "by_status": by_status, "by_kind": by_kind, "free_slots_by_verification": tiers,
            "spare_line_km_by_service": spare_km, "issues": len(validate_inventory(inv, as_of_year))}


def load(path):
    """Read an inventory JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def schema_path():
    """Path of the bundled JSON schema file."""
    return os.path.join(os.path.dirname(__file__), "data", "subsea_infrastructure_inventory.schema.json")
