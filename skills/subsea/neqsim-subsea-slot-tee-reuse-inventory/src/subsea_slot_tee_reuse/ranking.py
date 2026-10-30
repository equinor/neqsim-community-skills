"""Rank reuse of existing subsea capacity (free slots, tees/hubs, spare or repurposable lines) against a new-build tie-back.

Screening only: distance, capacity, hydraulics (single-phase Darcy), flow-assurance compatibility, remaining life
(:mod:`lifetime`) and a relative cost index are scored 0-100 with fixed, stated weights. A reuse option never removes
the need for host ullage, flow-assurance and integrity studies; ``needs`` lists what must be confirmed.
"""
from __future__ import annotations

import math

from .inventory import LINE_KINDS, normalize_item
from .lifetime import lifetime_check

WEIGHTS = {"distance": 25.0, "capacity": 20.0, "hydraulics": 20.0, "compatibility": 15.0, "lifetime": 10.0, "cost": 10.0}
LIFETIME_SCORE = {"ok": 1.0, "monitor": 0.85, "life-extend": 0.6, "refurbish": 0.35, "replace": 0.1, "data-gap": 0.4}
TORTUOSITY = 1.15
SLOT_KINDS = ("template", "manifold", "hub", "tee", "riser_slot", "j_tube", "plet", "plem")
REUSE_COST_PER_KM = 0.25  # relative to a new flowline (1.0 per km): spools, flushing, testing, tie-in tools
SLOT_TIE_IN_KM = 0.3  # kilometre-equivalent of one jumper/spool tie-in
LINE_TIE_IN_KM = 0.5
ACTION_COST_FACTOR = {"ok": 0.0, "monitor": 0.0, "life-extend": 0.1, "refurbish": 0.4, "replace": 1.0, "data-gap": 0.2}
DENSITY = {"oil": 800.0, "water_injection": 1030.0, "produced_water": 1030.0, "gas": 150.0, "gas_lift": 150.0, "gas_injection": 150.0,
           "multiphase": 400.0, "meg": 1050.0, "chemical": 1000.0, "hydraulic": 900.0}
STD_DENSITY = {"Sm3/d": 850.0, "MSm3/d": 0.8e6, "m3/d": 1000.0, "kg/s": None}  # kg per unit per day (None: already kg/s)

_COMPAT = {
    "multiphase": {"multiphase": 1.0, "oil": 1.0, "gas": 0.5, "water_injection": 0.3, "gas_lift": 0.4, "gas_injection": 0.4},
    "oil": {"oil": 1.0, "multiphase": 0.9, "gas": 0.4, "water_injection": 0.3, "gas_lift": 0.3, "gas_injection": 0.3},
    "gas": {"gas": 1.0, "gas_injection": 0.8, "gas_lift": 0.7, "multiphase": 0.6, "oil": 0.4, "water_injection": 0.2},
    "gas_lift": {"gas_lift": 1.0, "gas_injection": 0.9, "gas": 0.8, "multiphase": 0.3, "oil": 0.2, "water_injection": 0.2},
    "gas_injection": {"gas_injection": 1.0, "gas": 0.9, "gas_lift": 0.9, "multiphase": 0.3, "water_injection": 0.2},
    "water_injection": {"water_injection": 1.0, "produced_water": 0.9, "oil": 0.3, "gas": 0.2},
    "meg": {"meg": 1.0, "chemical": 0.6},
}


def haversine_km(a, b):
    """Great-circle distance in km between two ``{"lat","lon"}`` dicts."""
    r = 6371.0088
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _mass_rate_kg_s(rate, density_hint=None):
    value, unit = float(rate["value"]), rate.get("unit", "Sm3/d")
    if unit == "kg/s":
        return value
    per_day = STD_DENSITY.get(unit)
    if per_day is None:
        raise ValueError("unsupported rate unit %s" % unit)
    return value * per_day / 86400.0


def screening_dp_bar(service, rate, size_in, length_km, density=None, friction=0.015):
    """Single-phase Darcy-Weisbach pressure drop in bar (screening; multiphase uses a mixture density guess)."""
    if not size_in or not length_km:
        return None
    rho = density or DENSITY.get(service, 600.0)
    d = size_in * 0.0254 * 0.9
    area = math.pi * d * d / 4.0
    m = _mass_rate_kg_s(rate)
    v = m / (rho * area)
    dp = friction * (length_km * 1000.0 / d) * rho * v * v / 2.0
    return dp / 1e5


def _line_capacity_kg_s(service, size_in):
    """Erosional-velocity (API RP 14E, C=100) mass-rate limit of a line, kg/s."""
    if not size_in:
        return None
    rho = DENSITY.get(service, 600.0)
    rho_lb_ft3 = rho * 0.062428
    v_ft_s = 100.0 / math.sqrt(rho_lb_ft3)
    v = v_ft_s * 0.3048
    d = size_in * 0.0254 * 0.9
    return rho * v * math.pi * d * d / 4.0


def _compat(need, item_service, item, target):
    flags = []
    base = _COMPAT.get(need, {}).get(item_service)
    if base is None:
        base = 1.0 if need == item_service else 0.4
        if item_service == "unknown":
            flags.append("service of the reused item unknown")
        elif need != item_service:
            flags.append("service change %s -> %s not in the compatibility table: check materials, coating, inhibitors" % (item_service, need))
    elif need != item_service and base < 1.0:
        flags.append("service conversion %s -> %s (compatibility %.1f): check materials, internal coating/cladding, flow regime, inhibition" % (item_service, need, base))
    rating, design = item.get("pressure_rating_bar"), target.get("design_pressure_bar")
    if rating and design and rating < design:
        base *= 0.3
        flags.append("pressure rating %.0f bar below design pressure %.0f bar" % (rating, design))
    fluid = target.get("fluid") or {}
    if fluid.get("wax") and item.get("insulated") is False:
        base *= 0.7
        flags.append("waxy fluid in an uninsulated line: cooldown/WAT check")
    if fluid.get("hydrate_prone") and not item.get("inhibitor_available", True):
        base *= 0.7
        flags.append("hydrate-prone fluid and no inhibitor supply on the reused path")
    if fluid.get("h2s_ppm", 0) and item.get("sour_service") is False:
        base *= 0.5
        flags.append("sour fluid: line not qualified for sour service")
    return max(0.0, min(1.0, base)), flags


def _score_option(opt, baseline_km, baseline_cost, target, as_of_year):
    need = target.get("service", "multiphase")
    rate = target.get("rate")
    flags, needs = list(opt.get("flags", [])), list(opt.get("needs", []))
    comp, cflags = _compat(need, opt.get("service", "unknown"), opt.get("item", {}), target)
    flags += cflags
    # distance
    new_km = opt["new_km"]
    s_dist = 0.5 if new_km is None else max(0.0, min(1.0, 1.0 - new_km / max(baseline_km, 1e-6)))
    if new_km is None:
        flags.append("position unknown: distance not scored")
    # hydraulics
    dp, arrival, s_hyd = None, None, 0.4
    if rate and opt.get("size_in"):
        total_dp = screening_dp_bar(need if need != "gas_lift" else "gas_lift", rate, opt["size_in"], (new_km or 0) + opt.get("reused_km", 0.0),
                                    density=DENSITY.get(opt.get("service")) or None)
        if total_dp is not None:
            dp = round(total_dp, 2)
            src_p = target.get("source_pressure_bar")
            if src_p is not None:
                arrival = round(src_p - dp, 1)
                need_p = target.get("arrival_pressure_min_bar", 0.0)
                margin = arrival - need_p
                s_hyd = 0.0 if margin < 0 else min(1.0, 0.5 + margin / 40.0)
                if margin < 0:
                    flags.append("arrival pressure %.1f bar below the %.1f bar needed" % (arrival, need_p))
            else:
                s_hyd = max(0.0, 1.0 - dp / 60.0)
    elif rate:
        flags.append("size unknown: hydraulics not scored")
    # capacity
    s_cap, cap_ok = 0.5, None
    if rate and opt.get("kind") in LINE_KINDS and opt.get("size_in"):
        cap_kg_s = _line_capacity_kg_s(opt.get("service", "oil"), opt["size_in"])
        m = _mass_rate_kg_s(rate)
        if cap_kg_s:
            ratio = cap_kg_s / m
            cap_ok = ratio >= 1.0
            s_cap = 0.0 if ratio < 1.0 else min(1.0, 0.6 + 0.2 * (ratio - 1.0))
            if not cap_ok:
                flags.append("line capacity (erosional limit) %.1f kg/s below the rate %.1f kg/s" % (cap_kg_s, m))
    elif opt["option_type"] in ("slot", "hub"):
        needs.append("host ullage / inlet capacity for the added rate (slots do not carry capacity)")
    # lifetime
    life = opt.get("lifetime") or {"action": "ok", "basis": "new equipment"}
    s_life = LIFETIME_SCORE.get(life["action"], 0.4)
    # cost
    cost = (new_km or 0.0) + opt.get("reused_km", 0.0) * REUSE_COST_PER_KM + opt.get("tie_in_km", 0.0)
    cost += opt.get("reused_km", 0.0) * ACTION_COST_FACTOR.get(life["action"], 0.2)
    s_cost = max(0.0, min(1.0, 1.0 - cost / max(baseline_cost, 1e-6) + 0.0))
    comps = {"distance": s_dist, "capacity": s_cap, "hydraulics": s_hyd, "compatibility": comp, "lifetime": s_life, "cost": s_cost}
    score = sum(WEIGHTS[k] * v for k, v in comps.items())
    ver = opt.get("verification", "unknown")
    if ver in ("estimated", "unknown") and opt["option_type"] != "new_build":
        flags.append("availability is %s: confirm with the owner before presenting as free" % ver)
        score -= 5.0
    return {
        "id": opt["id"], "name": opt.get("name", opt["id"]), "option_type": opt["option_type"], "score": round(max(score, 0.0), 1),
        "components": {k: round(v, 2) for k, v in comps.items()}, "new_km": None if new_km is None else round(new_km, 1),
        "reused_km": round(opt.get("reused_km", 0.0), 1), "cost_index": round(cost, 2), "cost_class": "AACE class 5 (screening, relative to new-build = %.1f)" % baseline_cost,
        "dp_bar": dp, "arrival_pressure_bar": arrival, "capacity_ok": cap_ok, "lifetime": life, "flags": flags, "needs": needs,
        "verification": ver, "source": opt.get("source"),
    }


def rank_reuse_options(inv, target, as_of_year=None, top=10):
    """Rank slots, tees/hubs and reusable lines against a new-build tie-back for one target.

    Args:
        inv: inventory dict (see :mod:`inventory`).
        target: dict with ``position {lat, lon}``, ``host_position`` (for the new-build baseline), ``service`` (oil, gas,
            multiphase, gas_lift, water_injection, meg), ``rate {value, unit}``, ``source_pressure_bar``,
            ``arrival_pressure_min_bar``, ``design_pressure_bar``, ``horizon_end_year``, optional ``fluid`` flags, ``flowline_size_in``.
        as_of_year: assessment year (default current year).
        top: number of options returned (new-build is always included).

    Returns:
        list of option dicts sorted by score, each with ``rank`` and ``advantage_vs_new_build`` (score points).
    """
    from datetime import date

    year = as_of_year or target.get("as_of_year") or date.today().year
    horizon = target.get("horizon_end_year", year + 25)
    pos = target.get("position")
    size = target.get("flowline_size_in", 8.0)
    host = target.get("host_position")
    baseline_km = TORTUOSITY * haversine_km(pos, host) if pos and host else None
    baseline_km_eff = baseline_km if baseline_km else 20.0
    baseline_cost = baseline_km_eff
    items = [normalize_item(i, year) for i in inv.get("items", [])]
    options = [{"id": "new-build", "name": "New-build flowline to host", "option_type": "new_build", "service": target.get("service", "multiphase"),
                "new_km": baseline_km_eff, "reused_km": 0.0, "size_in": size, "kind": "flowline", "verification": "documented", "tie_in_km": 0.0,
                "needs": ["new flowline route survey, host tie-in point and ullage"], "lifetime": {"action": "ok", "basis": "new equipment, design life covers the horizon"},
                "source": "baseline"}]
    for it in items:
        if it["status"] in ("abandoned",) and it["kind"] not in LINE_KINDS:
            continue
        if it["kind"] in SLOT_KINDS and (it["free_slots"] or 0) > 0 and it["status"] != "planned":
            ipos = it.get("position")
            dist = TORTUOSITY * haversine_km(pos, ipos) if pos and ipos else None
            life = lifetime_check(it, horizon, year)
            otype = "hub" if it["kind"] in ("hub", "tee", "plet", "plem") else "slot"
            options.append({"id": it["id"], "name": it["name"], "option_type": otype, "service": target.get("service", "multiphase"), "new_km": dist, "reused_km": 0.0, "size_in": size,
                            "kind": it["kind"], "verification": it["verification"], "tie_in_km": SLOT_TIE_IN_KM, "lifetime": life, "item": it,
                            "needs": ["well/flowline connection hardware and slot availability documented by the owner"], "source": it["source"]})
        elif it["kind"] in LINE_KINDS and (it["status"] in ("spare", "abandoned") or it.get("repurpose_option")):
            ipos = it.get("position") or it.get("start_position")
            dist = TORTUOSITY * haversine_km(pos, ipos) if pos and ipos else None
            life = lifetime_check(it, horizon, year)
            flags = []
            if it["status"] == "in_use":
                flags.append("line is in use: re-purposing needs the owner's agreement and a replacement for its current service")
            options.append({"id": it["id"], "name": it["name"], "option_type": "reuse_line", "service": it["service"], "new_km": dist, "reused_km": it["length_km"] or 0.0,
                            "size_in": it["size_in"] or size, "kind": it["kind"], "verification": it["verification"], "tie_in_km": LINE_TIE_IN_KM, "lifetime": life,
                            "item": it, "flags": flags, "needs": ["pigging/inspection, flushing and pressure test of the reused line", "tie-in spools at both ends"],
                            "source": it["source"]})
    scored = [_score_option(o, baseline_km_eff, baseline_cost, target, year) for o in options]
    scored.sort(key=lambda r: -r["score"])
    base_score = next(r["score"] for r in scored if r["id"] == "new-build")
    for i, r in enumerate(scored, 1):
        r["rank"] = i
        r["advantage_vs_new_build"] = round(r["score"] - base_score, 1)
    keep = scored[:top]
    if not any(r["id"] == "new-build" for r in keep):
        keep.append(next(r for r in scored if r["id"] == "new-build"))
    return keep


def handoff(ranking, target, consumer, n=3):
    """Hand-off dict for ``export-tie-in-concept``, ``surf-design-study``, ``tie-in-screening`` or ``area-development``."""
    reuse = [r for r in ranking if r["option_type"] != "new_build"][:n]
    base = next((r for r in ranking if r["option_type"] == "new_build"), None)
    out = {"schema": "neqsim.subsea_reuse_handoff.v1", "consumer": consumer, "target": target.get("name"), "human_review_required": True,
           "basis": "screening, relative cost index (new-build = %.1f)" % (base["cost_index"] if base else 0.0)}
    if consumer == "export-tie-in-concept":
        out["candidate_landing_points"] = [{"id": r["id"], "type": r["option_type"], "new_km": r["new_km"], "score": r["score"], "verification": r["verification"]} for r in reuse]
    elif consumer == "surf-design-study":
        out["reused_equipment"] = [{"id": r["id"], "type": r["option_type"], "reused_km": r["reused_km"], "new_km": r["new_km"], "lifetime_action": r["lifetime"]["action"],
                                    "service_flags": [f for f in r["flags"] if "service" in f or "rating" in f]} for r in reuse]
        out["new_build_km"] = base["new_km"] if base else None
    elif consumer == "tie-in-screening":
        out["flow_assurance_flags"] = {r["id"]: r["flags"] for r in reuse}
        out["arrival_pressure_bar"] = {r["id"]: r["arrival_pressure_bar"] for r in reuse}
    elif consumer == "area-development":
        out["options"] = [{"id": r["id"], "type": r["option_type"], "cost_index": r["cost_index"], "cost_class": r["cost_class"], "lifetime_action": r["lifetime"]["action"],
                           "needs": r["needs"], "advantage_vs_new_build": r["advantage_vs_new_build"]} for r in reuse]
        out["new_build_cost_index"] = base["cost_index"] if base else None
    else:
        raise ValueError("unknown consumer %s" % consumer)
    return out
