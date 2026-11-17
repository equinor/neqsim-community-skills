"""Slot occupancy screening: group existing wellbores by surface location before reusing a slot."""

from __future__ import annotations

import math
from collections.abc import Iterable

ACTIVE = {
    "producing",
    "injecting",
    "online",
    "operating",
    "operational",
    "active",
    "suspended",
    "drilling",
}
PLANNED = {"planning", "planned", "reserved"}


def group_by_surface(wellbores: Iterable[dict], tol_m: float = 1.0) -> list[dict]:
    """Cluster wellbores whose surface (E, N) lie within ``tol_m`` into slots.

    Each input dict needs ``name``, ``easting``, ``northing``; optional ``status``, ``parent`` and ``slot``.
    Returns one record per slot with its wellbores and an ``occupied`` flag (any active bore).
    """
    slots: list[dict] = []
    for w in wellbores:
        e, n = float(w["easting"]), float(w["northing"])
        hit = next(
            (
                s
                for s in slots
                if math.hypot(s["easting"] - e, s["northing"] - n) <= tol_m
            ),
            None,
        )
        if hit is None:
            hit = {"slot": w.get("slot"), "easting": e, "northing": n, "wellbores": []}
            slots.append(hit)
        if hit["slot"] is None and w.get("slot") is not None:
            hit["slot"] = w["slot"]
        hit["wellbores"].append({k: w.get(k) for k in ("name", "status", "parent")})
    for s in slots:
        statuses = {str(b.get("status") or "").lower() for b in s["wellbores"]}
        s["occupied"] = bool(statuses & ACTIVE)
        s["reserved"] = bool(statuses & PLANNED)
        s["statuses"] = sorted(x for x in statuses if x)
    return slots


def check_slot(
    slots: list[dict],
    slot: str | None = None,
    easting: float | None = None,
    northing: float | None = None,
    tol_m: float = 1.0,
) -> dict:
    """Is the chosen slot free, or does a plan from it have to be a slot-recovery sidetrack?"""
    match = None
    for s in slots:
        if (
            slot is not None
            and s.get("slot") is not None
            and str(s["slot"]) == str(slot)
        ):
            match = s
            break
        if (
            easting is not None
            and northing is not None
            and math.hypot(s["easting"] - easting, s["northing"] - northing) <= tol_m
        ):
            match = s
            break
    if match is None:
        return {
            "status": "FREE",
            "message": "no existing wellbore found at this slot (confirm against the template register)",
        }
    if match["occupied"]:
        return {
            "status": "OCCUPIED",
            "slot": match,
            "message": "slot holds an active wellbore: choose a free slot or plan a sidetrack from an abandoned bore",
        }
    if match.get("reserved"):
        return {
            "status": "RESERVED",
            "slot": match,
            "message": "slot already carries a planned wellbore: coordinate with that plan before reusing the slot",
        }
    return {
        "status": "RECOVERABLE",
        "slot": match,
        "message": "slot holds only closed/abandoned bores: plan as a slot-recovery sidetrack, tie in to the parent survey",
    }
