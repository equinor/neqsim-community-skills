"""Flow-assurance and life-cycle assessments connected to the well model.

Implemented: hydrate temperature and margin along the well (NeqSim CPA via ``WellChemicalTreatment``), inhibitor dose and
injection basis, shut-in cooldown time to the hydrate line (``WellboreThermalModel``), liquid-loading (Turner) and erosional
ratios (drift-flux result), wax margin only when a laboratory WAT is supplied, CO2/H2S partial pressures for the materials
engineer. NOT performed: scale, MIC, asphaltene, sand (see ``ledger``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from .model_chain import build_fluid, e300_path, lump_to_cpa_fluid, require, surface_temperature_C, thermal_model
from .registers import get_path
from .runtime import jclass


def _wet_fluid(basis: Dict[str, Any], p_bara: float, t_c: float):
    water = float(get_path(basis, "fluid.free_water_for_hydrate.water_mole_fraction") or 0.02)
    require("SystemSrkCPAstatoil")
    if e300_path(basis):
        return lump_to_cpa_fluid(build_fluid(basis, t_c, p_bara), t_c, p_bara, water)
    f = jclass("SystemSrkCPAstatoil")(273.15 + t_c, p_bara)
    for c in get_path(basis, "fluid.components"):
        f.addComponent(c["name"], float(c["mole_fraction"]))
    if not any(c["name"].lower() == "water" for c in get_path(basis, "fluid.components")):
        f.addComponent("water", water)
    f.setMixingRule(10)
    return f


def hydrate_assessment(basis: Dict[str, Any], producer: Dict[str, Any]) -> Dict[str, Any]:
    """Hydrate temperature along the flowing profile, wellhead margin, shut-in cooldown and MEG/methanol dose."""
    require("WellChemicalTreatment", "WellboreThermalModel")
    prof = producer.get("profile")
    wh = producer.get("wellhead", {})
    if not prof or not wh:
        return {"status": "NOT_PERFORMED", "reason": "no producer profile available"}
    water_rate = float(get_path(basis, "flow_assurance.water_rate_kg_per_h") or 1000.0)
    WCT = jclass("WellChemicalTreatment")
    Inh = jclass("neqsim.process.fielddevelopment.wellplanning.WellChemicalTreatment$HydrateInhibitor")
    fl = _wet_fluid(basis, wh["pressure_bara"], wh["temperature_C"])
    t = WCT(fl)
    t.setInhibitor(Inh.MEG, 0.9).setSubcoolingMargin(float(get_path(basis, "flow_assurance.subcooling_margin_K") or 3.0)).setWaterRate(water_rate)
    p_nodes = prof["pressure_bara"]
    z_nodes = prof["node_tvd_m"]
    thyd = []
    z_prof, p_prof, t_prof = [], [], []
    stride = max(1, len(prof["tvd_m"]) // 6)
    for i in range(0, len(prof["tvd_m"]), stride):
        p_here = 0.5 * (p_nodes[i] + p_nodes[i + 1])
        thyd.append(float(t.hydrateTemperatureC(float(p_here), 0.0)))
        z_prof.append(prof["tvd_m"][i])
        p_prof.append(p_here)
        t_prof.append(prof["temperature_C"][i])
    margin = [tp - th for tp, th in zip(t_prof, thyd)]
    si_p = float(get_path(basis, "reservoir.pressure_bara") if not isinstance(get_path(basis, "reservoir.pressure_bara"), dict) else get_path(basis, "reservoir.pressure_bara")["base"])
    si_whp = max(1.0, producer.get("shut_in_whp_bara") or wh["pressure_bara"])
    amb = surface_temperature_C(basis)
    t.addStation("wellhead flowing", float(wh["pressure_bara"]), float(wh["temperature_C"]))
    t.addStation("tree shut-in (cooled)", float(si_whp), float(amb))
    res = t.evaluate()
    stations = [{"name": str(s.getName()), "pressure_bara": float(s.getPressureBara()), "temperature_C": float(s.getTemperatureC()), "hydrate_T0_C": float(s.getUninhibitedHydrateTemperatureC()),
                 "required_weight_fraction": float(s.getRequiredWeightFraction())} for s in res.getStations()]
    cool = None
    try:
        tm = thermal_model(basis, producer.get("mass_flow_kg_s", 5.0), float(get_path(basis, "reservoir.temperature_C")))
        t_hyd_si = float(t.hydrateTemperatureC(float(si_whp), 0.0))
        tw0 = float(wh["temperature_C"]) + 273.15
        hours = float(tm.timeToReachTemperatureHours(0.0, tw0, t_hyd_si + 273.15))
        cool = {"hydrate_temperature_C": t_hyd_si, "time_to_hydrate_line_hours": hours if hours < 1e6 else None, "method": "lumped exponential shut-in cooldown at the wellhead (WellboreThermalModel)"}
    except Exception as exc:  # noqa: BLE001
        cool = {"error": str(exc)[:120]}
    return {"status": "SCREENING", "profile": {"tvd_m": z_prof, "pressure_bara": p_prof, "temperature_C": t_prof, "hydrate_T_C": thyd, "margin_K": margin},
            "wellhead_margin_K": margin[0], "min_margin_K": float(min(margin)), "wellhead_hydrate_T_C": thyd[0], "inhibitor": {
                "type": "MEG", "lean_weight_fraction": 0.9, "governing_station": str(res.getGoverningStation()), "required_weight_fraction": float(res.getGoverningWeightFraction()),
                "lean_solution_kg_per_h": float(res.getLeanSolutionKgPerHour()), "lean_solution_m3_per_h": float(res.getLeanSolutionM3PerHour()), "stations": stations,
                "water_rate_kg_per_h_assumed": water_rate}, "shut_in_cooldown": cool, "basis_note": "free water assumed at {} mole fraction of the wellstream (ASSUMED); CPA hydrate model, not laboratory calibrated".format(
                    get_path(basis, "fluid.free_water_for_hydrate.water_mole_fraction") or 0.02)}


def wax_assessment(basis: Dict[str, Any], producer: Dict[str, Any]) -> Dict[str, Any]:
    """Wax margin from a supplied laboratory wax appearance temperature; otherwise NOT_PERFORMED with the consequence."""
    wat = get_path(basis, "fluid.wax_appearance_temperature_C")
    prof = producer.get("profile")
    if wat is None or not prof:
        return {"status": "NOT_PERFORMED", "reason": "no laboratory wax appearance temperature supplied",
                "consequence": "wax deposition risk in the upper tubing and flowline cannot be excluded; measure WAT and pour point"}
    tmin = min(prof["temperature_C"])
    return {"status": "SCREENING", "wat_C": float(wat), "min_flowing_temperature_C": float(tmin), "margin_K": float(tmin) - float(wat)}


def loading_and_erosion(producer: Dict[str, Any], gas_well: bool) -> Dict[str, Any]:
    """Liquid-loading (Turner) and erosional ratios from the drift-flux tubing result."""
    tub = producer.get("tubing", {})
    out = {"erosional_ratio_max": tub.get("erosional_ratio_max"), "erosional_basis": "API RP 14E ratio from the drift-flux mixture velocity (C-factor input)"}
    if gas_well:
        out.update({"turner_min": tub.get("turner_min"), "liquid_loading_risk_at_diagnostic_rate": tub.get("loading_risk"),
                    "loading_basis": "Turner critical-velocity ratio from the drift-flux result (ratio < 1 means gas velocity below critical)"})
    else:
        out["turner_min"] = None
        out["loading_note"] = "Turner liquid-loading ratio is a gas-well criterion and is not applied to an oil producer; check slugging with a transient model (ledger L21)"
    return out


def unloading_curve(model, case: str, n: int = 8) -> Optional[Dict[str, Any]]:
    """Minimum stable rate from the VLP minimum: below ``q_min_stable`` the outflow curve slopes down (loading branch)."""
    try:
        r = model.operating_point(case, detail=False)
        return {"q_min_stable": r["nodal"].get("outflow_min_rate"), "status": r["status"]}
    except Exception:  # noqa: BLE001
        return None


def contaminants_screening(basis: Dict[str, Any], whp: Optional[float], bhp: Optional[float]) -> Dict[str, Any]:
    """CO2/H2S partial pressures at the wellhead and bottom hole for the materials engineer (no acceptance limits applied)."""
    co2 = float(get_path(basis, "fluid.contaminants.co2_mol_frac") or 0.0)
    h2s_ppm = float(get_path(basis, "fluid.contaminants.h2s_ppm") or 0.0)
    out: Dict[str, Any] = {"co2_mol_frac": co2, "h2s_ppm": h2s_ppm}
    if whp and bhp:
        out.update({"pco2_wellhead_bar": co2 * whp, "pco2_bottomhole_bar": co2 * bhp, "ph2s_wellhead_bar": h2s_ppm * 1e-6 * whp, "ph2s_bottomhole_bar": h2s_ppm * 1e-6 * bhp})
    out["status"] = "NEEDS_REVIEW" if (co2 > 0 or h2s_ppm > 0) else "NOT_APPLICABLE (no CO2/H2S stated)"
    out["note"] = "sour-service and CO2-corrosion acceptance is a materials-engineering decision against the verified ISO 15156 / NORSOK M-506 editions; no limits applied here"
    return out


def scale_assessment(basis: Dict[str, Any]) -> Dict[str, Any]:
    """Scale/compatibility: NOT_PERFORMED unless a water analysis is supplied (then route to the scale-screening skill)."""
    if get_path(basis, "fluid.water_chemistry"):
        return {"status": "EXTERNAL_TOOL_REQUIRED", "reason": "water analysis supplied: run neqsim-produced-water-scale-screening / BrineMixingScaleEvaluator and attach the result"}
    return {"status": "NOT_PERFORMED", "reason": "no water chemistry supplied", "consequence": "scale and injection-water compatibility unknown; laboratory brine compatibility test required"}


def assess_flow_assurance(basis: Dict[str, Any], producer: Optional[Dict[str, Any]], injector: Optional[Dict[str, Any]], gas_well: bool) -> Dict[str, Any]:
    """Run every flow-assurance assessment that applies and collect the labelled results."""
    out: Dict[str, Any] = {}
    if producer:
        try:
            out["hydrate"] = hydrate_assessment(basis, producer)
        except Exception as exc:  # noqa: BLE001
            out["hydrate"] = {"status": "NOT_PERFORMED", "reason": "{}: {}".format(type(exc).__name__, str(exc)[:140])}
        out["wax"] = wax_assessment(basis, producer)
        out["loading_erosion"] = loading_and_erosion(producer, gas_well)
        wh, bh = producer.get("wellhead", {}), producer.get("bottomhole", {})
        out["contaminants"] = contaminants_screening(basis, wh.get("pressure_bara"), bh.get("pressure_bara"))
    if injector:
        out["injection_temperature"] = {"wellhead_C": injector.get("wellhead_temperature_C"), "bottomhole_C": injector.get("bottomhole_temperature_C"),
                                        "note": "cold injection reduces the effective fracture pressure (thermal stress, full-cooling upper bound) and loads tubing in tension"}
        out["two_phase_injection"] = {"two_phase": injector.get("two_phase")}
    out["scale"] = scale_assessment(basis)
    out["transient"] = {"status": "EXTERNAL_TOOL_REQUIRED", "reason": "start-up, unloading, slugging and restart need a transient simulator; steady-state results are not transient validation"}
    return out
