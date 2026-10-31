"""Alternatives, sensitivities and deliverability profile.

All numbers are deliverability/injectivity based. Recovery, plateau length and project value are NOT inferred; costs
enter only when the basis supplies them (with currency and source) and are carried unchanged to the scorecard.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from .basis import CASES, PRODUCER_TYPES, case_value, rng
from .registers import get_path

DEFAULT_CRITERIA = ["deliverability", "erosion_margin", "loading_margin", "energy_demand", "cost", "uncertainty_spread", "intervention_access"]


def default_alternatives(basis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Alternatives to compare when the basis supplies none: tubing size x lift strategy (producers) or tubing size (injectors)."""
    wtype = get_path(basis, "well.type")
    d0 = float(get_path(basis, "completion.tubing.id_m"))
    sizes = sorted({round(d0 * f, 4) for f in (0.85, 1.0, 1.2)})
    alts = []
    for d in sizes:
        alts.append({"id": "T{:.0f}".format(d * 1000), "label": "tubing ID {:.0f} mm".format(d * 1000), "overrides": {"tubing_id_m": d}})
    if wtype in PRODUCER_TYPES:
        alts.append({"id": "T{:.0f}-GL".format(d0 * 1000), "label": "tubing ID {:.0f} mm + gas lift 100 kSm3/d".format(d0 * 1000),
                     "overrides": {"tubing_id_m": d0, "lift_gas_sm3d": 1.0e5}, "lift": "gas_lift"})
    return alts


def evaluate_alternatives(model: Any, basis: Dict[str, Any], alternatives: Optional[List[Dict[str, Any]]] = None, cases: Sequence[str] = CASES, producer: bool = True) -> List[Dict[str, Any]]:
    """Run each alternative through the chain for each outcome case and collect comparable metrics."""
    alts = alternatives or get_path(basis, "alternatives") or default_alternatives(basis)
    results = []
    for alt in alts:
        per_case = {}
        for c in cases:
            r = model.operating_point(c, alt.get("overrides"), detail=(c == "base")) if producer else model.operating_point(c, alt.get("overrides"))
            per_case[c] = r
        base = per_case["base"]
        row: Dict[str, Any] = {"id": alt["id"], "label": alt.get("label", alt["id"]), "overrides": alt.get("overrides", {}), "cost": alt.get("cost"), "qualitative": alt.get("qualitative", {}),
                               "lift": alt.get("lift", "none")}
        if producer:
            tub = base.get("tubing", {})
            row.update({"q_op": {c: per_case[c].get("q_op") for c in cases}, "target_met": {c: per_case[c]["target_met"] for c in cases}, "target": base["target_rate"],
                        "surplus_at_target_bar": {c: per_case[c]["surplus_at_target_bar"] for c in cases}, "erosional_ratio": tub.get("erosional_ratio_max"),
                        "turner_min": tub.get("turner_min"), "loading_risk": tub.get("loading_risk"), "lift_gas_sm3d": (alt.get("overrides") or {}).get("lift_gas_sm3d", 0.0),
                        "status": {c: per_case[c]["status"] for c in cases}})
            margins = {"drawdown surplus at target (base)": base["surplus_at_target_bar"] / max(base["params"]["pressure_bara"] * 0.1, 1.0),
                       "erosional margin (1 - ratio)": (1.0 - tub["erosional_ratio_max"]) if tub.get("erosional_ratio_max") is not None else None}
            row["binding_constraint"] = min((k for k, v in margins.items() if v is not None), key=lambda k: margins[k])
        else:
            row.update({"whp_required": {c: per_case[c].get("whp_required_bara") for c in cases}, "power_kw": {c: per_case[c].get("power_kw") for c in cases},
                        "fracture_margin_bar": {c: per_case[c].get("fracture_margin_bar") for c in cases}, "status": {c: per_case[c]["status"] for c in cases}, "target": base["rate"]})
            m = {"fracture margin": base.get("fracture_margin_bar")}
            row["binding_constraint"] = "fracture margin" if m["fracture margin"] is not None else "feasibility"
        results.append(row)
    return results


def scorecard(rows: List[Dict[str, Any]], weights: Optional[Dict[str, float]] = None, producer: bool = True) -> Dict[str, Any]:
    """Normalised 0-1 criterion scores (1 = best) and a weighted total; weights default to equal and are labelled ASSUMED."""
    crit = list(DEFAULT_CRITERIA) if producer else ["feasibility", "wellhead_pressure", "energy_demand", "fracture_margin", "cost", "uncertainty_spread", "intervention_access"]
    weights_used = dict(weights or {c: 1.0 for c in crit})
    weights_source = "supplied" if weights else "ASSUMED equal weights"
    raw: Dict[str, Dict[str, Optional[float]]] = {c: {} for c in crit}
    for r in rows:
        i = r["id"]
        if producer:
            qb = (r["q_op"]["base"] or 0.0) / r["target"]
            raw["deliverability"][i] = qb
            raw["erosion_margin"][i] = (1.0 - r["erosional_ratio"]) if r.get("erosional_ratio") is not None else None
            raw["loading_margin"][i] = (r["turner_min"] - 1.0) if r.get("turner_min") is not None else None
            raw["energy_demand"][i] = -(r.get("lift_gas_sm3d") or 0.0)
            spread = ((r["q_op"]["high"] or 0.0) - (r["q_op"]["low"] or 0.0)) / r["target"]
            raw["uncertainty_spread"][i] = -spread
        else:
            raw["feasibility"][i] = 1.0 if r["status"]["base"] == "OK" else 0.0
            raw["wellhead_pressure"][i] = -(r["whp_required"]["base"] or 1e6)
            raw["energy_demand"][i] = -(r["power_kw"]["base"] or 1e9)
            raw["fracture_margin"][i] = r["fracture_margin_bar"]["base"]
            w_hi, w_lo = r["whp_required"]["high"], r["whp_required"]["low"]
            raw["uncertainty_spread"][i] = -abs((w_lo or 0.0) - (w_hi or 0.0))
        cost = (r.get("cost") or {}).get("capex")
        raw["cost"][i] = -float(cost) if cost is not None else None
        iq = (r.get("qualitative") or {}).get("intervention_access")
        raw["intervention_access"][i] = float(iq) if iq is not None else None
    return score_raw([r["id"] for r in rows], crit, raw, weights_used, weights_source)


def score_raw(ids: Sequence[str], crit: Sequence[str], raw: Dict[str, Dict[str, Optional[float]]], weights_used: Dict[str, float], weights_source: str = "ASSUMED equal weights") -> Dict[str, Any]:
    """Normalise raw criterion values (higher = better, ``None`` = no data) to 0-1 per criterion and compute the weighted total per alternative.

    Criteria without data for any alternative are excluded from the total (not scored zero). Use this directly for study-specific criteria.
    """
    scores: Dict[str, Dict[str, Optional[float]]] = {}
    for c in crit:
        vals = [v for v in raw[c].values() if v is not None]
        scores[c] = {}
        for i, v in raw[c].items():
            if v is None:
                scores[c][i] = None
            elif max(vals) - min(vals) < 1e-12:
                scores[c][i] = 1.0
            else:
                scores[c][i] = (v - min(vals)) / (max(vals) - min(vals))
    totals = {}
    for i in ids:
        num = sum(weights_used.get(c, 1.0) * scores[c][i] for c in crit if scores[c].get(i) is not None)
        den = sum(weights_used.get(c, 1.0) for c in crit if scores[c].get(i) is not None)
        totals[i] = num / den if den else 0.0
    missing = [c for c in crit if all(scores[c].get(i) is None for i in ids)]
    return {"criteria": list(crit), "scores": scores, "raw": raw, "weights": weights_used, "weights_source": weights_source, "totals": totals, "criteria_without_data": missing,
            "note": "scores are relative to the alternatives compared; criteria without data are excluded from the weighted total, not scored zero"}


def pareto_front(points: Dict[str, Sequence[float]], maximise: Sequence[bool]) -> List[str]:
    """Non-dominated ids for points given as {id: (x, y, ...)} with a per-axis maximise flag."""
    ids = list(points)
    front = []
    for a in ids:
        dominated = False
        for b in ids:
            if a == b:
                continue
            better_or_eq = all((pb >= pa) if mx else (pb <= pa) for pa, pb, mx in zip(points[a], points[b], maximise))
            strictly = any((pb > pa) if mx else (pb < pa) for pa, pb, mx in zip(points[a], points[b], maximise))
            if better_or_eq and strictly:
                dominated = True
                break
        if not dominated:
            front.append(a)
    return front


def tornado(model: Any, basis: Dict[str, Any], producer: bool = True, parameters: Optional[List[str]] = None) -> Dict[str, Any]:
    """One-at-a-time sensitivity: swing of the base-case metric when each parameter moves to its low/high value.

    Metric: stock-tank/standard rate at the stable operating point (producers) or required wellhead pressure (injectors).
    """
    base_cfg = {"pressure_bara": "reservoir.pressure_bara", "k_md": "reservoir.permeability_md", "skin": "reservoir.skin", "water_cut": "reservoir.water_cut",
                "host_pressure_bara": "facility.host_pressure_bara", "h_m": "reservoir.thickness_m"}
    params = parameters or [p for p in base_cfg if get_path(basis, base_cfg[p]) is not None and isinstance(get_path(basis, base_cfg[p]), dict)]
    metric = (lambda r: r.get("q_op")) if producer else (lambda r: r.get("whp_required_bara"))
    ref = metric(model.operating_point("base", detail=False) if producer else model.operating_point("base"))
    rows = []
    for p in params:
        lo, ba, hi = rng(get_path(basis, base_cfg[p]))
        vals = {}
        for tag, v in (("low_value", lo), ("high_value", hi)):
            r = model.operating_point("base", {p: v}, detail=False) if producer else model.operating_point("base", {p: v})
            vals[tag] = metric(r)
        rows.append({"parameter": p, "range": [lo, ba, hi], "metric_at_low_value": vals["low_value"], "metric_at_high_value": vals["high_value"], "swing": abs((vals["high_value"] or 0.0) - (vals["low_value"] or 0.0))})
    rows.sort(key=lambda r: -r["swing"])
    return {"metric": "q_op [Sm3/d]" if producer else "required WHP [bara]", "reference": ref, "rows": rows}


def sensitivity_grid(model: Any, case: str, x_param: str, x_vals: List[float], y_param: str, y_vals: List[float]) -> Dict[str, Any]:
    """Two-parameter grid of operating rate (producer) for a heat map."""
    z = []
    for y in y_vals:
        z.append([model.operating_point(case, {x_param: x, y_param: y}, detail=False).get("q_op") for x in x_vals])
    return {"x_param": x_param, "x": x_vals, "y_param": y_param, "y": y_vals, "q_op": z}


def deliverability_profile(model: Any, basis: Dict[str, Any], years: Sequence[float], cases: Sequence[str] = CASES) -> Dict[str, Any]:
    """Deliverability (plateau capacity) versus time with linear depletion. NOT a production forecast and not a recovery estimate."""
    dep = float(get_path(basis, "reservoir.depletion_bar_per_year") or 0.0)
    out: Dict[str, Any] = {"years": list(years), "cases": {}, "target": None, "note": "deliverability at depleted reservoir pressure with constant other inputs; not a production forecast, no recovery inferred"}
    for c in cases:
        p0 = model.params(c)["pressure_bara"]
        qs = []
        for y in years:
            p_y = p0 - dep * y
            if p_y <= max(1.5 * model.params(c)["host_pressure_bara"], 5.0):
                qs.append(0.0)  # reservoir pressure at or below the host back pressure: no natural deliverability
                continue
            r = model.operating_point(c, {"pressure_bara": p_y}, detail=False)
            qs.append(r.get("q_op"))
        out["cases"][c] = qs
    out["target"] = model.params("base")["rate"]
    return out
