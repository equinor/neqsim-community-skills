"""Turn an optimiser result into decisions: bottlenecks, ullage, tie-ins, uplift."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


def bottlenecks(result: Dict[str, Any], top: int = 15) -> List[Dict[str, Any]]:
    """Capacity elements ranked by discounted shadow value over the horizon.

    Shadow price = extra MNOK per year from one more MSm3/d (gas) or Sm3/d
    (liquid) of capacity in that element, holding everything else fixed.
    """
    rate, base = result["discount_rate"], result["base_year"]
    agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"pv_mnok_per_unit": 0.0, "years": [], "max": 0.0})
    for yr in result["years"]:
        df = 1.0 / (1.0 + rate) ** (yr["year"] - base)
        for element, value in yr["shadow_price_mnok_per_unit_yr"].items():
            if value <= 1e-6:
                continue
            a = agg[element]
            a["pv_mnok_per_unit"] += value * df
            a["years"].append(yr["year"])
            a["max"] = max(a["max"], value)
    ranked = [{"element": k, "binding_years": v["years"], "pv_mnok_per_unit_capacity": round(v["pv_mnok_per_unit"], 2),
               "max_shadow_mnok_per_unit_yr": round(v["max"], 3)} for k, v in agg.items()]
    ranked.sort(key=lambda r: -r["pv_mnok_per_unit_capacity"])
    return ranked[:top]


def ullage_timeline(result: Dict[str, Any], elements: Optional[List[str]] = None) -> Dict[str, Dict[int, float]]:
    """Spare capacity per element and year (capacity - optimised flow), in element units."""
    out: Dict[str, Dict[int, float]] = defaultdict(dict)
    for yr in result["years"]:
        for element, util in yr["utilization"].items():
            if elements and element not in elements:
                continue
            flow = yr["element_flow"].get(element, 0.0)
            cap = flow / util if util else None
            if cap:
                out[element][yr["year"]] = round(cap - flow, 3)
    return dict(out)


def curtailment(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Entities that could produce more than the network lets them (by year)."""
    rows = []
    for yr in result["years"]:
        for ent, cur in yr["curtailed"].items():
            if cur["gas_msm3d"] > 1e-3 or cur["liquid_sm3d"] > 1:
                rows.append({"year": yr["year"], "entity": ent, **cur})
    rows.sort(key=lambda r: (r["year"], -r["gas_msm3d"]))
    return rows


def tiein_ranking(result: Dict[str, Any], *, gas_price: float, liquid_price: float) -> List[Dict[str, Any]]:
    """Discoveries ranked by discounted gross revenue actually accepted by the network."""
    rate, base = result["discount_rate"], result["base_year"]
    value: Dict[str, float] = defaultdict(float)
    volumes: Dict[str, Dict[str, float]] = defaultdict(lambda: {"gas_gsm3": 0.0, "liquid_msm3": 0.0})
    first_year: Dict[str, int] = {}
    for yr in result["years"]:
        df = 1.0 / (1.0 + rate) ** (yr["year"] - base)
        for ent, prod in yr["produced"].items():
            if not ent.startswith("DSC_"):
                continue
            gas, liq = prod["gas_msm3d"], prod["liquid_sm3d"]
            value[ent] += (gas * gas_price * 365.0 + liq * liquid_price * 365.0 / 1.0e6) * df
            volumes[ent]["gas_gsm3"] += gas * 365.0 / 1000.0
            volumes[ent]["liquid_msm3"] += liq * 365.0 / 1.0e6
            first_year.setdefault(ent, yr["year"])
    rows = []
    for ent, pv in value.items():
        host = result.get("tiebacks", {}).get(ent) or {}
        supply = result.get("supply", {}).get(ent, {})
        rows.append({"discovery": ent, "host": host.get("name"), "host_field": host.get("field_id"),
                     "distance_km": host.get("distance_km"), "first_year": first_year.get(ent),
                     "status": supply.get("method", {}).get("status"), "rc": supply.get("method", {}).get("rc"),
                     "pv_gross_revenue_mnok": round(pv, 1),
                     "gas_gsm3": round(volumes[ent]["gas_gsm3"], 3), "liquid_msm3": round(volumes[ent]["liquid_msm3"], 3)})
    rows.sort(key=lambda r: -r["pv_gross_revenue_mnok"])
    return rows


def stranded_discoveries(result: Dict[str, Any]) -> List[str]:
    """Discoveries with supply but no host within the tie-back radius (need standalone or longer tie-back)."""
    seen = set()
    for yr in result["years"]:
        seen.update(e for e in yr["unconnected"] if e.startswith("DSC_"))
    return sorted(seen)


def production_uplift(optimizer: Any, result: Dict[str, Any], year: int, top: int = 15) -> List[Dict[str, Any]]:
    """Extra rate each producing field could ship in ``year``.

    Uplift = min(route headroom, demonstrated capability gap). Route headroom
    is the smallest spare capacity along the field's best path given every
    other field's optimised flow. The capability gap is the field's historical
    peak rate minus its planned rate, a screening proxy for what wells and
    facilities have shown they can deliver. The result says where on the NCS
    more can be produced and whether the network or the field sets the limit.
    """
    yr = next(y for y in result["years"] if y["year"] == year)
    prices = optimizer.scenario["prices"]
    rows = []
    for ent, produced in yr["produced"].items():
        if ent.startswith("DSC_"):
            continue
        prof = optimizer.profiles.get(ent)
        for medium in ("gas", "liquid"):
            paths = optimizer.paths(ent, medium)
            if not paths or prof is None:
                continue
            series = prof.gas_msm3d if medium == "gas" else prof.liquid_sm3d
            history = [v for y, v in series.items() if y < result["base_year"]]
            current = produced["gas_msm3d"] if medium == "gas" else produced["liquid_sm3d"]
            capability_gap = max(max(history, default=0.0) - current, 0.0)
            if capability_gap <= 1e-6 or current <= 0:
                continue
            caps = optimizer.capacities(year, medium)
            best, limiting = 0.0, None
            for p in paths:
                spare, lim = float("inf"), None
                for e in p.arcs + p.nodes:
                    if e in caps:
                        s = caps[e] - yr["element_flow"].get(e, 0.0)
                        if s < spare:
                            spare, lim = s, e
                if spare > best:
                    best, limiting = spare, lim
            uplift = min(best, capability_gap)
            if uplift <= 1e-6:
                continue
            unit_value = prices["gas_nok_per_sm3"] * 365.0 if medium == "gas" else prices["liquid_nok_per_sm3"] * 365.0 / 1e6
            rows.append({"entity": ent, "medium": medium, "year": year, "current": round(current, 3),
                         "uplift": round(uplift, 3), "unit": "MSm3/d" if medium == "gas" else "Sm3/d",
                         "route_headroom": None if best == float("inf") else round(best, 3),
                         "capability_gap": round(capability_gap, 3),
                         "limited_by": "field capability (historical peak)" if capability_gap <= best else limiting,
                         "value_of_uplift_mnok_yr": round(uplift * unit_value, 1)})
    rows.sort(key=lambda r: -r["value_of_uplift_mnok_yr"])
    return rows[:top]
