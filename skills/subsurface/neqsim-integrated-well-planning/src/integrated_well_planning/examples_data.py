"""Synthetic, textbook-style planning bases used by the examples, templates and tests.

Nothing here is field data. Every value is a demonstration assumption (``study.synthetic: true``) and the
provenance map marks it ASSUMED. The four cases cover an oil producer (platform), a gas-condensate producer
(subsea), a water injector (onshore) and a gas injector (platform).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

OIL = [("methane", 0.35), ("ethane", 0.05), ("propane", 0.04), ("n-butane", 0.03), ("n-hexane", 0.08), ("n-decane", 0.45)]
GC = [("methane", 0.75), ("ethane", 0.08), ("propane", 0.05), ("n-butane", 0.03), ("n-hexane", 0.04), ("n-octane", 0.03), ("nC10", 0.02)]
LEAN_GAS = [("methane", 0.95), ("ethane", 0.05)]
WATER = [("water", 1.0)]

_SYN = "synthetic demonstration assumption (no field data)"


def _prov(paths: List[str], cls: str = "ASSUMED", source: str = _SYN) -> Dict[str, Dict[str, Any]]:
    return {p: {"class": cls, "source": source, "synthetic": True} for p in paths}


def _casing(env: str) -> List[Dict[str, Any]]:
    base = [
        {"name": "Conductor", "od_in": 30.0, "hole_in": 36.0, "top_md_m": 0.0, "shoe_md_m": 120.0, "shoe_tvd_m": 120.0, "grade": "X-52", "cement_top_md_m": 0.0},
        {"name": "Surface casing", "od_in": 13.375, "hole_in": 17.5, "top_md_m": 0.0, "shoe_md_m": 800.0, "shoe_tvd_m": 800.0, "grade": "L80", "weight_ppf": 68.0, "cement_top_md_m": 0.0},
        {"name": "Production casing", "od_in": 9.625, "hole_in": 12.25, "top_md_m": 0.0, "shoe_md_m": 2300.0, "shoe_tvd_m": 2300.0, "grade": "L80", "weight_ppf": 47.0,
         "cement_top_md_m": 1600.0},
    ]
    return base


def _formations(tvd: float, contact: bool = True) -> List[Dict[str, Any]]:
    f = [
        {"name": "Overburden shale", "top_tvd_m": 0.0},
        {"name": "Caprock", "top_tvd_m": round(tvd * 0.88)},
        {"name": "Reservoir", "top_tvd_m": round(tvd * 0.96), "base_tvd_m": round(tvd * 1.01)},
    ]
    if contact:
        f.append({"name": "Fluid contact (synthetic)", "top_tvd_m": round(tvd * 1.0), "kind": "contact"})
    return f


def _pressure_window(tvd: float, pres: float) -> List[Dict[str, float]]:
    pts = []
    for frac in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0):
        z = tvd * frac
        pts.append({"tvd_m": z, "pore_bara": 1.01 + 0.0981 * 1.03 * z * (0.97 if frac < 1 else 1.0) if frac < 1 else pres,
                    "frac_bara": 1.01 + 0.0981 * 1.65 * z, "mud_bara": 1.01 + 0.0981 * (1.12 + 0.12 * frac) * z})
    return pts


def _survey(md: float, tvd: float, kop: float = 600.0, inc: float = 0.0) -> Dict[str, Any]:
    return {"kop_md_m": kop, "build_rate_deg_per_30m": 2.0, "hold_inclination_deg": inc, "azimuth_deg": 90.0}


def oil_producer_platform() -> Dict[str, Any]:
    md = tvd = 2500.0
    b = {
        "schema": "iwp_planning_basis.v1",
        "study": {"id": "IWP-DEMO-A", "title": "Oil producer, platform well (synthetic demonstration)", "maturity": "selection", "revision": "A", "author": "neqsim-community",
                  "date": "2026-10-31", "currency": "USD", "synthetic": True, "purpose": "Size tubing and wellhead back pressure for a 1500 Sm3/d oil producer"},
        "well": {"id": "A-1", "type": "oil_producer", "environment": "platform", "name": "Synthetic oil producer"},
        "datums": {"reference": "RKB", "reference_elevation_msl_m": 25.0, "water_depth_m": 0.0, "coordinate_system": "synthetic local grid", "pressure_reference": "bara (absolute)",
                   "standard_conditions": {"temperature_C": 15.0, "pressure_bara": 1.01325}},
        "environment": {"surface_temperature_C": 8.0},
        "targets": {"rate": {"kind": "oil_sm3d", "low": 1200.0, "base": 1500.0, "high": 1800.0}, "plateau_years": 3.0},
        "trajectory": {"md_m": md, "tvd_m": tvd, "survey": _survey(md, tvd, 600.0, 0.0), "max_dls_deg_per_30m": 3.0},
        "reservoir": {"pressure_bara": {"low": 235.0, "base": 250.0, "high": 262.0}, "temperature_C": 90.0, "permeability_md": {"low": 90.0, "base": 150.0, "high": 220.0},
                      "thickness_m": 25.0, "skin": {"low": 0.0, "base": 2.0, "high": 8.0}, "drainage_radius_m": 400.0, "wellbore_radius_m": 0.108,
                      "water_cut": {"low": 0.0, "base": 0.2, "high": 0.5}, "depletion_bar_per_year": 6.0, "datum_tvd_m": tvd, "fracture_gradient_bar_per_m": 0.17},
        "fluid": {"eos": "SRK", "components": [{"name": n, "mole_fraction": z, "origin": "synthetic"} for n, z in OIL], "pvt_measurements": [], "water_chemistry": None,
                  "contaminants": {"co2_mol_frac": 0.0, "h2s_ppm": 0.0}, "wax_appearance_temperature_C": None},
        "completion": {"tubing": {"od_in": 5.5, "id_m": 0.1, "roughness_m": 4.5e-5, "grade": "L80", "weight_ppf": 17.0, "wall_in": 0.304, "shoe_md_m": 2270.0}, "casing": _casing("platform"),
                       "packer_md_m": 2250.0, "sssv_md_m": 150.0, "perforations": [{"top_md_m": 2400.0, "base_md_m": 2460.0}],
                       "lift": {"type": "none", "gas_rate_sm3d": 0.0, "mandrels_md_m": [900.0, 1500.0, 2000.0]}, "tree": "conventional surface tree", "wellhead_rating_bar": 345.0,
                       "formations": _formations(tvd), "overall_u_w_m2k": 5.0},
        "facility": {"host_pressure_bara": {"low": 22.0, "base": 25.0, "high": 30.0}, "host_temperature_C": 40.0, "choke_dp_bar": 0.0,
                     "flowline": {"length_m": 300.0, "id_m": 0.15, "elevation_change_m": 0.0, "roughness_m": 4.5e-5},
                     "max_oil_sm3d": 5000.0, "max_gas_msm3d": 2.0, "max_liquid_m3d": 6000.0, "fluid_quality": {"max_water_cut": 0.6}},
        "operations": {"life_years": 15, "intervention_strategy": "rig-less wireline intervention; rig workover for tubing replacement", "abandonment": "permanent abandonment per applicable regulation (requirement to be identified)"},
        "drilling": {"hazards": ["shallow gas (synthetic placeholder)"], "pressure_window": _pressure_window(tvd, 250.0), "rig": "jack-up (synthetic)"},
        "standards": {"jurisdiction": "TO_BE_IDENTIFIED"},
        "design_factors": {},
        "limits": [
            {"parameter": "erosional_ratio", "condition": "production, all cases", "max": 1.0, "unit": "-", "source": "API RP 14E ratio definition (ratio = velocity / erosional velocity); C-factor is an operator choice",
             "limit_basis": "ASSUMED", "margin_note": "C-factor 100 assumed (synthetic)"},
            {"parameter": "wellhead_pressure_bara", "condition": "shut-in", "max": 345.0, "unit": "bara", "source": "synthetic tree rating placeholder (to be replaced by equipment datasheet)", "limit_basis": "SYNTHETIC"},
        ],
        "provenance": {},
    }
    b["provenance"] = _prov(["reservoir.pressure_bara", "reservoir.temperature_C", "reservoir.permeability_md", "reservoir.thickness_m", "reservoir.skin", "reservoir.drainage_radius_m",
                             "reservoir.water_cut", "fluid.components", "completion.tubing.id_m", "facility.host_pressure_bara", "targets.rate", "trajectory.md_m", "trajectory.tvd_m",
                             "datums.reference_elevation_msl_m"])
    return b


def gas_condensate_producer_subsea() -> Dict[str, Any]:
    md, tvd = 3500.0, 3252.0
    b = oil_producer_platform()
    b["study"].update({"id": "IWP-DEMO-B", "title": "Gas-condensate producer, subsea tie-back well (synthetic demonstration)", "purpose": "Tubing and flowline back-pressure screening for a subsea gas-condensate well"})
    b["well"].update({"id": "B-1", "type": "gas_condensate_producer", "environment": "subsea", "name": "Synthetic subsea gas-condensate producer"})
    b["datums"].update({"water_depth_m": 350.0})
    b["environment"] = {"seabed_temperature_C": 4.0}
    b["targets"] = {"rate": {"kind": "gas_sm3d", "low": 0.8e6, "base": 1.2e6, "high": 1.6e6}, "plateau_years": 4.0}
    b["trajectory"] = {"md_m": md, "tvd_m": tvd, "survey": _survey(md, tvd, 1100.0, 28.0), "max_dls_deg_per_30m": 3.0}
    b["reservoir"] = {"pressure_bara": {"low": 400.0, "base": 450.0, "high": 470.0}, "temperature_C": 110.0, "permeability_md": {"low": 12.0, "base": 20.0, "high": 30.0},
                      "thickness_m": 40.0, "skin": {"low": 0.0, "base": 3.0, "high": 10.0}, "drainage_radius_m": 500.0, "wellbore_radius_m": 0.108, "porosity": 0.15,
                      "relperm": {"swc": 0.2, "soc": 0.1, "krg_max": 1.0, "kro_max": 1.0, "ng": 3.0, "no": 3.0}, "datum_tvd_m": tvd, "ipr_points": 14, "fracture_gradient_bar_per_m": 0.17,
                      "depletion_bar_per_year": 15.0, "water_cut": 0.0}
    b["fluid"]["components"] = [{"name": n, "mole_fraction": z, "origin": "synthetic"} for n, z in GC]
    b["completion"].update({"tubing": {"od_in": 5.5, "id_m": 0.124, "roughness_m": 4.5e-5, "grade": "13Cr-L80", "weight_ppf": 17.0, "wall_in": 0.304, "shoe_md_m": 3300.0},
                            "packer_md_m": 3280.0, "sssv_md_m": 650.0, "perforations": [{"top_md_m": 3440.0, "base_md_m": 3480.0}], "tree": "vertical subsea tree (synthetic)",
                            "lift": {"type": "none", "gas_rate_sm3d": 0.0}, "wellhead_rating_bar": 690.0, "formations": _formations(tvd)})
    b["completion"]["casing"] = [
        {"name": "Conductor", "od_in": 30.0, "hole_in": 36.0, "top_md_m": 375.0, "shoe_md_m": 500.0, "shoe_tvd_m": 500.0, "grade": "X-52", "cement_top_md_m": 375.0},
        {"name": "Surface casing", "od_in": 13.375, "hole_in": 17.5, "top_md_m": 375.0, "shoe_md_m": 1400.0, "shoe_tvd_m": 1394.0, "grade": "L80", "weight_ppf": 68.0, "cement_top_md_m": 375.0},
        {"name": "Production casing", "od_in": 9.625, "hole_in": 12.25, "top_md_m": 375.0, "shoe_md_m": 3300.0, "shoe_tvd_m": 3075.0, "grade": "L80", "weight_ppf": 53.5, "cement_top_md_m": 2500.0},
    ]
    b["facility"].update({"host_pressure_bara": {"low": 80.0, "base": 90.0, "high": 100.0}, "host_temperature_C": 30.0,
                          "flowline": {"length_m": 8000.0, "id_m": 0.2, "elevation_change_m": 60.0, "roughness_m": 4.5e-5, "ambient_temperature_C": 4.0}, "choke_dp_bar": 0.0,
                          "max_gas_msm3d": 6.0})
    b["fluid"]["water_chemistry"] = None
    b["operations"]["life_years"] = 20
    b["operations"]["intervention_strategy"] = "light well intervention vessel (synthetic assumption)"
    b["drilling"]["pressure_window"] = _pressure_window(tvd, 450.0)
    b["drilling"]["rig"] = "semi-submersible (synthetic)"
    b["limits"] = [
        {"parameter": "erosional_ratio", "condition": "production, all cases", "max": 1.0, "unit": "-", "source": "API RP 14E ratio definition; C-factor 100 assumed", "limit_basis": "ASSUMED"},
        {"parameter": "hydrate_margin_K", "condition": "production, wellhead", "min": 3.0, "unit": "K", "source": "synthetic subcooling margin for demonstration (operator value to be supplied)", "limit_basis": "SYNTHETIC"},
        {"parameter": "wellhead_pressure_bara", "condition": "shut-in", "max": 690.0, "unit": "bara", "source": "synthetic tree rating placeholder", "limit_basis": "SYNTHETIC"},
    ]
    b["fluid"]["water_chemistry"] = None
    b["fluid"]["free_water_for_hydrate"] = {"water_mole_fraction": 0.02}
    b["provenance"] = _prov(["reservoir.pressure_bara", "reservoir.temperature_C", "reservoir.permeability_md", "reservoir.thickness_m", "reservoir.skin", "reservoir.drainage_radius_m",
                             "fluid.components", "completion.tubing.id_m", "facility.host_pressure_bara", "targets.rate", "trajectory.md_m", "trajectory.tvd_m", "datums.reference_elevation_msl_m"])
    return b


def water_injector_onshore() -> Dict[str, Any]:
    md = tvd = 2000.0
    b = oil_producer_platform()
    b["study"].update({"id": "IWP-DEMO-C", "title": "Water injector, onshore well (synthetic demonstration)", "purpose": "Required wellhead pressure, fracture margin and pump duty for a water injector"})
    b["well"].update({"id": "C-1", "type": "water_injector", "environment": "onshore", "name": "Synthetic onshore water injector"})
    b["datums"].update({"reference_elevation_msl_m": 5.0, "water_depth_m": 0.0})
    b["environment"] = {"surface_temperature_C": 5.0}
    b["targets"] = {"rate": {"kind": "water_m3d", "low": 900.0, "base": 1300.0, "high": 1700.0}, "injection_basis": "matrix"}
    b["trajectory"] = {"md_m": md, "tvd_m": tvd, "survey": _survey(md, tvd, 500.0, 0.0), "max_dls_deg_per_30m": 3.0}
    b["reservoir"] = {"pressure_bara": {"low": 190.0, "base": 200.0, "high": 210.0}, "temperature_C": 75.0, "permeability_md": {"low": 120.0, "base": 300.0, "high": 450.0},
                      "thickness_m": 30.0, "skin": {"low": 0.0, "base": 2.0, "high": 6.0}, "drainage_radius_m": 300.0, "wellbore_radius_m": 0.108, "datum_tvd_m": tvd,
                      "fracture_gradient_bar_per_m": 0.17, "injection_temperature_C": 15.0, "rock": {"alpha_per_K": 1.0e-5, "E_GPa": 5.0, "nu": 0.25}, "reservoir_viscosity_pa_s": 6.0e-4}
    b["fluid"] = {"eos": "CPA", "components": [{"name": "water", "mole_fraction": 1.0, "origin": "synthetic injection water"}], "pvt_measurements": [], "water_chemistry": None,
                  "contaminants": {"co2_mol_frac": 0.0, "h2s_ppm": 0.0}}
    b["completion"].update({"tubing": {"od_in": 5.5, "id_m": 0.124, "roughness_m": 4.5e-5, "grade": "L80", "weight_ppf": 17.0, "wall_in": 0.304, "shoe_md_m": 1770.0},
                            "packer_md_m": 1750.0, "sssv_md_m": 100.0, "perforations": [{"top_md_m": 1900.0, "base_md_m": 1940.0}], "lift": {"type": "none"}, "tree": "conventional injection tree",
                            "wellhead_rating_bar": 345.0, "formations": _formations(tvd, contact=False)})
    b["completion"]["casing"] = _casing("onshore")[:3]
    b["completion"]["casing"][2].update({"shoe_md_m": 1800.0, "shoe_tvd_m": 1800.0, "cement_top_md_m": 1200.0})
    b["facility"] = {"host_pressure_bara": 150.0, "host_pressure_note": "injection water supply (pump discharge) pressure available at the wellhead manifold",
                     "supply_pressure_bara": 5.0, "pump_efficiency": 0.7, "max_injection_pressure_bara": 180.0, "max_pump_power_kw": 1500.0,
                     "host_temperature_C": 15.0, "flowline": {}, "choke_dp_bar": 0.0}
    b["drilling"]["pressure_window"] = _pressure_window(tvd, 200.0)
    b["drilling"]["rig"] = "land rig (synthetic)"
    b["operations"]["life_years"] = 25
    b["operations"]["intervention_strategy"] = "wireline; coiled tubing for stimulation"
    b["limits"] = [
        {"parameter": "wellhead_injection_pressure_bara", "condition": "injection, all cases", "max": 180.0, "unit": "bara", "source": "synthetic wellhead/flowline rating placeholder", "limit_basis": "SYNTHETIC"},
        {"parameter": "fracture_margin_bar", "condition": "injection, matrix basis", "min": 0.0, "unit": "bar", "source": "definition: bottom-hole pressure below effective fracture pressure (matrix basis)", "limit_basis": "ASSUMED"},
        {"parameter": "pump_power_kw", "condition": "injection", "max": 1500.0, "unit": "kW", "source": "synthetic facility power allocation", "limit_basis": "SYNTHETIC"},
    ]
    b["provenance"] = _prov(["reservoir.pressure_bara", "reservoir.temperature_C", "reservoir.permeability_md", "reservoir.thickness_m", "reservoir.skin", "reservoir.drainage_radius_m",
                             "reservoir.fracture_gradient_bar_per_m", "fluid.components", "completion.tubing.id_m", "facility.host_pressure_bara", "targets.rate", "trajectory.md_m",
                             "trajectory.tvd_m", "datums.reference_elevation_msl_m"])
    b["provenance"]["facility.host_pressure_bara"]["note"] = "supply pressure available at the injection manifold"
    return b


def gas_injector_platform() -> Dict[str, Any]:
    md = tvd = 3000.0
    b = water_injector_onshore()
    b["study"].update({"id": "IWP-DEMO-D", "title": "Gas injector, platform well (synthetic demonstration)", "purpose": "Required wellhead pressure and compression duty for a gas injector"})
    b["well"].update({"id": "D-1", "type": "gas_injector", "environment": "platform", "name": "Synthetic platform gas injector"})
    b["datums"].update({"reference_elevation_msl_m": 25.0})
    b["environment"] = {"surface_temperature_C": 20.0}
    b["targets"] = {"rate": {"kind": "gas_inj_sm3d", "low": 0.6e6, "base": 1.0e6, "high": 1.4e6}, "injection_basis": "matrix"}
    b["trajectory"] = {"md_m": md, "tvd_m": tvd, "survey": _survey(md, tvd, 700.0, 0.0), "max_dls_deg_per_30m": 3.0}
    b["reservoir"] = {"pressure_bara": {"low": 280.0, "base": 300.0, "high": 320.0}, "temperature_C": 100.0, "permeability_md": {"low": 60.0, "base": 100.0, "high": 160.0},
                      "thickness_m": 30.0, "skin": {"low": 0.0, "base": 3.0, "high": 10.0}, "drainage_radius_m": 500.0, "wellbore_radius_m": 0.108, "datum_tvd_m": tvd,
                      "fracture_gradient_bar_per_m": 0.17, "injection_temperature_C": 40.0, "rock": {"alpha_per_K": 1.0e-5, "E_GPa": 5.0, "nu": 0.25}}
    b["fluid"] = {"eos": "SRK", "components": [{"name": n, "mole_fraction": z, "origin": "synthetic lean gas"} for n, z in LEAN_GAS], "pvt_measurements": [], "water_chemistry": None,
                  "contaminants": {"co2_mol_frac": 0.0, "h2s_ppm": 0.0}}
    b["completion"]["tubing"].update({"id_m": 0.15, "od_in": 7.0, "wall_in": 0.317, "weight_ppf": 26.0, "shoe_md_m": 2850.0})
    b["completion"].update({"packer_md_m": 2830.0, "perforations": [{"top_md_m": 2950.0, "base_md_m": 2990.0}], "formations": _formations(tvd, contact=False)})
    b["completion"]["casing"] = _casing("platform")
    b["completion"]["casing"][2].update({"shoe_md_m": 3050.0, "shoe_tvd_m": 3050.0, "cement_top_md_m": 2200.0, "od_in": 9.625})
    b["facility"] = {"host_pressure_bara": 70.0, "host_pressure_note": "compressor suction (export gas header) pressure", "supply_pressure_bara": 70.0, "compressor_efficiency": 0.75,
                     "max_injection_pressure_bara": 400.0, "max_compression_power_kw": 8000.0, "host_temperature_C": 35.0, "flowline": {}, "choke_dp_bar": 0.0}
    b["drilling"]["pressure_window"] = _pressure_window(tvd, 300.0)
    b["drilling"]["rig"] = "platform drilling rig (synthetic)"
    b["limits"] = [
        {"parameter": "wellhead_injection_pressure_bara", "condition": "injection, all cases", "max": 400.0, "unit": "bara", "source": "synthetic tree/flowline rating placeholder", "limit_basis": "SYNTHETIC"},
        {"parameter": "fracture_margin_bar", "condition": "injection, matrix basis", "min": 0.0, "unit": "bar", "source": "definition: bottom-hole pressure below effective fracture pressure", "limit_basis": "ASSUMED"},
        {"parameter": "compression_power_kw", "condition": "injection", "max": 8000.0, "unit": "kW", "source": "synthetic facility power allocation", "limit_basis": "SYNTHETIC"},
    ]
    b["provenance"] = _prov(["reservoir.pressure_bara", "reservoir.temperature_C", "reservoir.permeability_md", "reservoir.thickness_m", "reservoir.skin", "reservoir.drainage_radius_m",
                             "reservoir.fracture_gradient_bar_per_m", "fluid.components", "completion.tubing.id_m", "facility.host_pressure_bara", "targets.rate", "trajectory.md_m",
                             "trajectory.tvd_m", "datums.reference_elevation_msl_m"])
    return b


CASES: Dict[str, Dict[str, Any]] = {}
BUILDERS = {
    "oil_producer:platform": oil_producer_platform,
    "gas_condensate_producer:subsea": gas_condensate_producer_subsea,
    "water_injector:onshore": water_injector_onshore,
    "gas_injector:platform": gas_injector_platform,
}
CASE_NAMES = {"oil_producer": "oil_producer_platform", "gas_condensate_producer": "gas_condensate_producer_subsea", "water_injector": "water_injector_onshore",
              "gas_injector": "gas_injector_platform"}


def generic(well_type: str, environment: str) -> Dict[str, Any]:
    """Return the closest synthetic template with the requested well type and environment applied."""
    key = {"oil_producer": "oil_producer:platform", "gas_producer": "gas_condensate_producer:subsea", "gas_condensate_producer": "gas_condensate_producer:subsea",
           "water_injector": "water_injector:onshore", "gas_injector": "gas_injector:platform"}[well_type]
    b = BUILDERS[key]()
    b["well"]["type"] = well_type
    b["well"]["environment"] = environment
    if environment == "subsea" and not b["datums"].get("water_depth_m"):
        b["datums"]["water_depth_m"] = 300.0
        b["environment"] = {"seabed_temperature_C": 4.0}
    if environment != "subsea":
        b["datums"]["water_depth_m"] = 0.0
        b["environment"].setdefault("surface_temperature_C", 10.0)
    return b


def all_cases() -> Dict[str, Dict[str, Any]]:
    """Return the four worked cases keyed by file stem."""
    return {CASE_NAMES[k.split(":")[0]]: copy.deepcopy(f()) for k, f in BUILDERS.items()}


CASES.update({k: f() for k, f in BUILDERS.items()})
