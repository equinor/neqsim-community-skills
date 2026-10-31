"""Life-cycle load cases, tubular utilisation, annular pressure build-up and tubing movement.

Design factors, material ratings beyond the API formula ratings, annulus pressure limits and test pressures are NEVER
defaulted: they come from ``basis.design_factors`` / ``basis.limits`` with a source, otherwise the row is
``NEEDS_REVIEW`` and only the utilisation (load / formula rating) is reported. Tubular ratings use the API TR 5C3 formulas
of the required drilling/casing module ``well_design_study``; they are formula ratings, not manufacturer datasheet ratings.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .model_chain import effective_tubing_depths, build_fluid, require, surface_temperature_C
from .registers import get_path
from .runtime import ensure_runtime, jclass

G = 9.80665
IN = 0.0254
PPF_TO_KG_M = 1.48816


def drilling_module():
    """Return the ``well_design_study`` module or None when the required drilling/casing module is not installed."""
    try:
        import well_design_study as wds  # type: ignore

        return wds
    except ImportError:
        return None


def pipe_dimensions(od_in: float, weight_ppf: Optional[float] = None, wall_in: Optional[float] = None) -> Dict[str, float]:
    """OD, wall and ID in inches (wall from weight with the plain-end formula when needed)."""
    if wall_in is None:
        if weight_ppf is None:
            raise ValueError("need wall_in or weight_ppf")
        # 10.69 (OD - t) t = w  ->  t^2 - OD t + w/10.69 = 0
        disc = od_in ** 2 - 4.0 * weight_ppf / 10.69
        wall_in = (od_in - math.sqrt(max(disc, 0.0))) / 2.0
    return {"od_in": od_in, "wall_in": wall_in, "id_in": od_in - 2.0 * wall_in}


def tubular_ratings(od_in: float, wall_in: float, grade: str, temperature_c: float = 20.0) -> Dict[str, Any]:
    """Burst, collapse (bar) and body yield (kN) from API TR 5C3 formulas; ``available=False`` without the casing module."""
    wds = drilling_module()
    if wds is None or grade not in wds.GRADES:
        return {"available": False, "reason": "well_design_study module or grade '{}' not available".format(grade)}
    yp = wds.casing_design.yield_psi(wds.GRADES[grade], temperature_c)
    return {"available": True, "burst_bar": wds.burst_rating_psi(od_in, wall_in, yp) * 0.0689475729, "collapse_bar": wds.collapse_rating_psi(od_in, wall_in, yp) * 0.0689475729,
            "yield_kn": wds.body_yield_kn(od_in, wall_in, yp), "yield_psi": yp, "source": "API TR 5C3 formulas via well_design_study (formula rating, not a datasheet rating)",
            "temperature_C": temperature_c}


def shut_in_wellhead_pressure(basis: Dict[str, Any], reservoir_pressure_bara: float) -> Dict[str, float]:
    """Shut-in tubing head pressure from the reservoir fluid column (density iterated with a NeqSim flash, 3 passes)."""
    require("ThermodynamicOperations")
    tvd = effective_tubing_depths(basis)["tvd_m"]
    tres = float(get_path(basis, "reservoir.temperature_C"))
    ts = surface_temperature_C(basis)
    p_top = max(1.0, reservoir_pressure_bara * 0.6)
    rho = 0.0
    for _ in range(3):
        pm = 0.5 * (p_top + reservoir_pressure_bara)
        f = build_fluid(basis, 0.5 * (tres + ts), pm)
        jclass("ThermodynamicOperations")(f).TPflash()
        f.initProperties()
        rho = float(f.getDensity("kg/m3"))
        p_top = max(1.01325, reservoir_pressure_bara - rho * G * tvd / 1e5)
    return {"whp_bara": p_top, "column_density_kg_m3": rho, "method": "single-density column from NeqSim flash at mean P and T (screening)"}


def annulus_geometry(basis: Dict[str, Any]) -> Dict[str, float]:
    """Annulus A geometry (m) from tubing and production casing definitions."""
    tub = get_path(basis, "completion.tubing")
    prod = [c for c in get_path(basis, "completion.casing") if "production" in c["name"].lower()][-1]
    td = pipe_dimensions(tub["od_in"], tub.get("weight_ppf"), tub.get("wall_in"))
    cd = pipe_dimensions(prod["od_in"], prod.get("weight_ppf"), prod.get("wall_in"))
    return {"tub_od_m": td["od_in"] * IN, "tub_id_m": td["id_in"] * IN, "csg_id_m": cd["id_in"] * IN, "csg_od_m": cd["od_in"] * IN}


def thermal_dT_mean(tm, depth_tvd_m: float, n: int = 30) -> float:
    """Mean temperature change of the annulus: flowing profile minus undisturbed geotherm."""
    zs = [depth_tvd_m * (i + 0.5) / n for i in range(n)]
    return sum((tm.temperatureAt(z) - tm.getFormationTemperatureK(z)) for z in zs) / n


def annular_pressure_build_up(basis: Dict[str, Any], tm, packer_tvd_m: float) -> Dict[str, Any]:
    """APB in annulus A for the flowing (or injecting) thermal profile; uses NeqSim ``AnnularPressureBuildup``."""
    require("AnnularPressureBuildup", "SystemSrkCPAstatoil")
    geo = annulus_geometry(basis)
    d_t = thermal_dT_mean(tm, packer_tvd_m)
    apb = jclass("AnnularPressureBuildup")()
    apb.setAnnulusLength(float(packer_tvd_m)).setGeometry(geo["tub_od_m"], geo["tub_id_m"], geo["csg_id_m"], geo["csg_od_m"]).setTemperatureChange(float(d_t))
    apb.setInitialPressure(float(get_path(basis, "completion.annulus_a.initial_pressure_bara") or 1.01325 + 0.1 * packer_tvd_m * 0.1))
    water = jclass("SystemSrkCPAstatoil")(310.0, 100.0)
    water.addComponent("water", 1.0)
    water.setMixingRule(10)
    t_mean_k = 273.15 + surface_temperature_C(basis) + 0.5 * (float(get_path(basis, "reservoir.temperature_C")) - surface_temperature_C(basis))
    alpha, kappa = apb.setFluidFromThermoSystem(water, 10.0 + 0.1 * packer_tvd_m * 0.1, float(t_mean_k))
    r = apb.calculate()
    return {"delta_pressure_bar": float(r.getDeltaPressureBar()), "final_pressure_bara": float(r.getFinalPressureBara()), "rigid_limit_bar": float(r.getRigidLimitBar()),
            "compliance_m3_per_bar": float(r.getComplianceM3PerBar()), "delta_t_mean_K": float(d_t), "alpha_per_K": float(alpha), "kappa_per_bar": float(kappa),
            "annulus_volume_m3": float(r.getAnnulusVolumeM3()), "method": "AnnularPressureBuildup (closed form, free-standing outer string, water-based annulus fluid assumed)",
            "assumptions": ["water-based packer fluid (CPA water properties)", "free-standing outer string (no cement/formation compliance)", "no bleeding"]}


def tubing_movement(basis: Dict[str, Any], tm, state: str, d_pi_packer: float, d_po_packer: float, packer_tvd_m: float, packer_mode: str = "FREE") -> Dict[str, Any]:
    """Tubing length change / packer force for one state with ``TubingMovementCalculator`` (vertical, no friction)."""
    require("TubingMovementCalculator")
    tub = get_path(basis, "completion.tubing")
    td = pipe_dimensions(tub["od_in"], tub.get("weight_ppf"), tub.get("wall_in"))
    geo = annulus_geometry(basis)
    d_t = thermal_dT_mean(tm, packer_tvd_m)
    calc = jclass("TubingMovementCalculator")()
    calc.setLength(float(packer_tvd_m)).setGeometry(td["od_in"] * IN, td["id_in"] * IN, td["id_in"] * IN * 1.05, geo["csg_id_m"])
    Mode = jclass("neqsim.process.fielddevelopment.wellplanning.TubingMovementCalculator$PackerMode")
    calc.setPackerMode(getattr(Mode, packer_mode), 0.0)
    calc.setFluidDensities(800.0, 1030.0)
    calc.setLoadChange(float(d_pi_packer), float(d_po_packer), float(d_pi_packer) * 0.6, float(d_po_packer) * 0.6, float(d_t))
    r = calc.calculate()
    return {"state": state, "packer_mode": packer_mode, "free_movement_m": float(r.getFreeDeltaLM()), "piston_m": float(r.getPistonDeltaLM()), "balloon_m": float(r.getBalloonDeltaLM()),
            "temperature_m": float(r.getTemperatureDeltaLM()), "buckling_m": float(r.getBucklingDeltaLM()), "axial_force_change_kn": float(r.getAxialForceChangeN()) / 1e3,
            "sinusoidal_buckled": bool(r.isSinusoidalBuckled()), "helical_buckled": bool(r.isHelicalBuckled()), "delta_t_mean_K": float(d_t),
            "method": "TubingMovementCalculator (closed form; vertical, uniform, no friction/bending; mean pressure changes taken as 60 % of packer values)"}


def build_load_cases(basis: Dict[str, Any], producer: Optional[Dict[str, Any]] = None, injector: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Life-cycle load cases from the model results: production/injection, shut-in, evacuation (and supplied test pressure)."""
    tvd = effective_tubing_depths(basis)["tvd_m"]
    pack_tvd = tvd * float(get_path(basis, "completion.packer_md_m") or tvd) / float(get_path(basis, "trajectory.md_m"))
    ann_fluid = float(get_path(basis, "completion.annulus_a.fluid_density_kg_m3") or 1030.0)
    annulus_hydro = ann_fluid * G * pack_tvd / 1e5
    cases: List[Dict[str, Any]] = []
    pres = float(get_path(basis, "reservoir.pressure_bara") if not isinstance(get_path(basis, "reservoir.pressure_bara"), dict) else get_path(basis, "reservoir.pressure_bara")["high"])
    if producer:
        bh = producer.get("bottomhole", {})
        wh = producer.get("wellhead", {})
        cases.append({"state": "production", "pi_top_bara": wh.get("pressure_bara"), "pi_packer_bara": _interp_profile(producer, pack_tvd), "po_packer_bara": 1.01325 + annulus_hydro,
                      "temperature_top_C": wh.get("temperature_C"), "source": "producer base-case traverse; annulus = packer-fluid hydrostatic (density {} kg/m3 ASSUMED)".format(ann_fluid)})
        si = shut_in_wellhead_pressure(basis, pres)
        cases.append({"state": "shut_in", "pi_top_bara": si["whp_bara"], "pi_packer_bara": si["whp_bara"] + si["column_density_kg_m3"] * G * pack_tvd / 1e5, "po_packer_bara": 1.01325 + annulus_hydro,
                      "temperature_top_C": surface_temperature_C(basis), "source": "shut-in column at the high reservoir pressure ({})".format(si["method"])})
    if injector and injector.get("whp_required_bara"):
        cases.append({"state": "injection", "pi_top_bara": injector["whp_required_bara"], "pi_packer_bara": injector["whp_required_bara"] + (injector["bhp_bara"] - injector["whp_required_bara"]) * pack_tvd / tvd,
                      "po_packer_bara": 1.01325 + annulus_hydro, "temperature_top_C": injector.get("wellhead_temperature_C"), "source": "injector base-case operating point"})
    cases.append({"state": "evacuated_tubing", "pi_top_bara": 1.01325, "pi_packer_bara": 1.01325, "po_packer_bara": 1.01325 + annulus_hydro, "temperature_top_C": surface_temperature_C(basis),
                  "source": "collapse check: tubing emptied, annulus at packer-fluid hydrostatic"})
    tp = get_path(basis, "integrity.test_pressure_bara")
    if tp:
        cases.append({"state": "pressure_test", "pi_top_bara": float(tp), "pi_packer_bara": float(tp) + 0.08 * pack_tvd, "po_packer_bara": 1.01325 + annulus_hydro, "temperature_top_C": surface_temperature_C(basis),
                      "source": "supplied test pressure (integrity.test_pressure_bara)"})
    return cases


def _interp_profile(producer: Dict[str, Any], z_tvd: float) -> float:
    prof = producer.get("profile") or {}
    if not prof:
        return float("nan")
    import numpy as np

    return float(np.interp(z_tvd, prof["node_tvd_m"], prof["pressure_bara"]))


def evaluate_tubing(basis: Dict[str, Any], load_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Utilisation of the tubing against formula ratings, and design-factor status against supplied factors only."""
    tub = get_path(basis, "completion.tubing")
    dims = pipe_dimensions(tub["od_in"], tub.get("weight_ppf"), tub.get("wall_in"))
    rat = tubular_ratings(dims["od_in"], dims["wall_in"], tub.get("grade", ""), 20.0)
    factors = get_path(basis, "design_factors") or {}
    rows = []
    for lc in load_cases:
        pi = lc.get("pi_top_bara")
        po_top = 1.01325
        burst_load = (pi - po_top) if pi is not None else None
        pi_p, po_p = lc.get("pi_packer_bara"), lc.get("po_packer_bara")
        collapse_load = (po_p - pi_p) if (pi_p is not None and po_p is not None and pi_p == pi_p) else None
        row = {"state": lc["state"], "burst_load_bar": burst_load, "collapse_load_bar": collapse_load, "load_source": lc["source"], "rating_available": rat["available"]}
        if rat["available"]:
            row.update({"burst_rating_bar": rat["burst_bar"], "collapse_rating_bar": rat["collapse_bar"], "rating_source": rat["source"]})
            row["burst_utilisation"] = (burst_load / rat["burst_bar"]) if burst_load is not None and burst_load > 0 else 0.0
            row["collapse_utilisation"] = (collapse_load / rat["collapse_bar"]) if collapse_load is not None and collapse_load > 0 else 0.0
            for key, util in (("burst", row["burst_utilisation"]), ("collapse", row["collapse_utilisation"])):
                df_req = (factors.get(key) or {}).get("value")
                if df_req and util > 0:
                    df = 1.0 / util
                    row[key + "_design_factor"] = df
                    row[key + "_required_factor"] = df_req
                    row[key + "_status"] = "PASS" if df >= df_req else "FAIL"
                    row[key + "_factor_source"] = (factors.get(key) or {}).get("source", "")
                else:
                    row[key + "_status"] = "NEEDS_REVIEW (no supplied design factor)" if util > 0 else "NOT_LOADED"
        else:
            row["burst_status"] = row["collapse_status"] = "NOT_ASSESSED (ratings unavailable: {})".format(rat.get("reason", ""))
        rows.append(row)
    return rows


def evaluate_integrity(basis: Dict[str, Any], producer: Optional[Dict[str, Any]] = None, injector: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Full screening integrity block for the base case (load cases, tubing, APB, movement)."""
    out: Dict[str, Any] = {"status": "SCREENING", "notes": ["formula ratings only; design factors are used only when supplied with a source",
                                                          "not a substitute for specialist well-load software (ISO 13679 load-case matrix not performed)"]}
    load_cases = build_load_cases(basis, producer, injector)
    out["load_cases"] = load_cases
    out["tubing"] = evaluate_tubing(basis, load_cases)
    res = producer or injector
    depths = effective_tubing_depths(basis)
    pack_tvd = depths["tvd_m"] * float(get_path(basis, "completion.packer_md_m") or depths["tvd_m"]) / float(get_path(basis, "trajectory.md_m"))
    pack_tvd = min(pack_tvd, depths["tvd_m"])
    try:
        from .model_chain import thermal_model

        if producer:
            mass = producer.get("mass_flow_kg_s", 5.0)
            tm = thermal_model(basis, mass, float(get_path(basis, "reservoir.temperature_C")))
            direction = "production"
        else:
            mass = injector["mass_kg_s"]
            tm = thermal_model(basis, mass, float(get_path(basis, "reservoir.temperature_C")), direction="INJECTION",
                               inlet_temperature_C=float(get_path(basis, "reservoir.injection_temperature_C") or 15.0))
            direction = "injection"
        out["apb"] = annular_pressure_build_up(basis, tm, pack_tvd)
        lc_by = {c["state"]: c for c in load_cases}
        main = lc_by.get("production") or lc_by.get("injection")
        base_state = lc_by.get("shut_in")
        d_pi = (main["pi_packer_bara"] - (base_state["pi_packer_bara"] if base_state else 1.01325 + 0.1 * 1000.0 * G * pack_tvd / 1e5))
        out["tubing_movement"] = [tubing_movement(basis, tm, direction, d_pi, 0.0, pack_tvd, "FREE"), tubing_movement(basis, tm, direction, d_pi, 0.0, pack_tvd, "FIXED")]
    except Exception as exc:  # noqa: BLE001 - keep the rest of the integrity block when a Java class is missing
        out["apb_error"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
    return out
