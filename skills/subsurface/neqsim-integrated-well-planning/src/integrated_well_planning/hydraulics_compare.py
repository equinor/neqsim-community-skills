"""Comparison of tubing hydraulic methods at one rate and wellhead pressure.

Implemented methods: the NeqSim drift-flux traverse (reference of the chain, with the Ramey temperature profile) and the NeqSim pipe correlations
Beggs-Brill, Gray, Hagedorn-Brown and Mukherjee-Brill run isothermally at the mean tubing temperature of the drift-flux profile, so that the
differences come from the hydraulic correlation and not from the temperature model. None of the methods is field-calibrated; the spread is a
model-uncertainty indicator, not a confidence interval.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .model_chain import build_fluid, require
from .runtime import jclass

PIPE_METHODS = {
    "beggs_brill": ("PipeBeggsAndBrills", "Beggs and Brill (1973)"),
    "gray": ("PipeGray", "Gray (wet-gas correlation)"),
    "hagedorn_brown": ("PipeHagedornBrown", "Hagedorn and Brown"),
    "mukherjee_brill": ("PipeMukherjeeAndBrill", "Mukherjee and Brill"),
}


def _pipe_dp_bar(model: Any, method_class: str, mass_kg_s: float, water_moles: float, t_mean_c: float, p_in_bara: float, p: Dict[str, Any]) -> Optional[float]:
    """Pressure drop (bar) of one isothermal upward pipe run from ``p_in_bara``; ``None`` when the correlation cannot run."""
    import jpype

    Stream = jpype.JClass("neqsim.process.equipment.stream.Stream")
    fl = build_fluid(model.basis, t_mean_c, p_in_bara, water_moles_per_mole=water_moles)
    if water_moles > 0:
        fl.setMultiPhaseCheck(True)
    s = Stream("tubing-in", fl)
    s.setFlowRate(float(mass_kg_s), "kg/sec")
    s.setTemperature(float(t_mean_c), "C")
    s.setPressure(float(p_in_bara), "bara")
    s.run()
    cls = jpype.JClass("neqsim.process.equipment.pipeline.{}".format(method_class))
    pipe = cls("tubing", s)
    pipe.setLength(float(model.depths["md_m"]))
    pipe.setDiameter(float(p["tubing_id_m"]))
    pipe.setElevation(float(model.depths["tvd_m"]))
    pipe.setPipeWallRoughness(float(model.roughness_m))
    pipe.setNumberOfIncrements(20)
    if method_class == "PipeBeggsAndBrills":
        mode = jpype.JClass("neqsim.process.equipment.pipeline.PipeBeggsAndBrills$HeatTransferMode").ISOTHERMAL
        pipe.setHeatTransferMode(mode)
    try:
        pipe.run()
    except Exception:  # noqa: BLE001 - a correlation outside its domain is reported as unavailable
        return None
    return float(p_in_bara - pipe.getOutletStream().getPressure("bara"))


def compare_methods(model: Any, case: str, q: float, whp_bara: float, overrides: Optional[Dict[str, Any]] = None,
                    methods: Sequence[str] = tuple(PIPE_METHODS)) -> List[Dict[str, Any]]:
    """Bottom-hole pressure required for rate ``q`` at wellhead pressure ``whp_bara`` by each hydraulic method.

    Returns one row per method with the BHP, the difference to the drift-flux reference and the drift-flux flow regime/loading indicators for the reference row.
    """
    require("DriftFluxWellboreHydraulics")
    res, extra = model.traverse(case, q, whp_bara, overrides)
    p = extra["params"]
    mass = extra["mass"]
    t_nodes = [float(t) - 273.15 for t in res.getSegmentTemperatureK()]
    t_mean = sum(t_nodes) / len(t_nodes)
    bhp_ref = float(res.getBottomholePressureBara())
    rows = [{"method": "drift_flux", "label": "NeqSim drift-flux traverse (chain reference, Ramey temperature)", "bhp_bara": bhp_ref, "delta_vs_reference_bar": 0.0,
             "regime": str(res.getRegimeCounts()), "erosional_ratio": float(res.getMaxErosionalRatio()), "mean_temperature_C": t_mean}]
    wm = 0.0
    if mass["water"] > 0:
        wm = (mass["water"] / 0.018015) / (mass["hydrocarbon"] / model.std["mw_kg_per_mol"])
    for key in methods:
        cls, label = PIPE_METHODS[key]
        p_in = bhp_ref
        dp = None
        for _ in range(4):
            dp = _pipe_dp_bar(model, cls, mass["total"], wm, t_mean, p_in, p)
            if dp is None:
                break
            new_in = whp_bara + dp
            if abs(new_in - p_in) < 0.3:
                p_in = new_in
                break
            p_in = new_in
        rows.append({"method": key, "label": label + " (isothermal at the drift-flux mean temperature)", "bhp_bara": None if dp is None else p_in,
                     "delta_vs_reference_bar": None if dp is None else p_in - bhp_ref, "regime": "n/a", "erosional_ratio": None, "mean_temperature_C": t_mean})
    return rows
