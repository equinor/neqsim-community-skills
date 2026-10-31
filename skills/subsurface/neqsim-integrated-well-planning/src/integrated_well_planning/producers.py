"""Producer chain: IPR -> tubing VLP -> wellhead -> flowline -> host, with nodal solve and sensitivities.

Oil producers use a Darcy productivity index (Standing composite IPR, Vogel below the bubble point). Gas and
gas-condensate producers use the NeqSim GasCondensateInflowModel. Tubing outflow is the NeqSim drift-flux
traverse with a Ramey thermal profile. Every number carries the label of the ledger row it comes from.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .basis import PRODUCER_TYPES
from .model_chain import (ModelUnavailable, build_fluid, case_params, effective_tubing_depths, flowline_back_pressure, darcy_oil_pi_sm3d_per_bar,
                          require, reservoir_properties, standard_factors, thermal_model, water_moles_for_cut, SC_MOLAR_VOLUME_SM3_PER_KMOL, WATER_SC_DENSITY, WATER_MW_KG_PER_MOL)
from .nodal import NodalResult, composite_oil_ipr, solve_nodal, surplus_at
from .registers import get_path
from .runtime import jclass

LIFT_GAS_MOLES_PER_SM3 = 1000.0 / SC_MOLAR_VOLUME_SM3_PER_KMOL


class ProducerModel:
    """Reservoir-well-facility model of one producer."""

    def __init__(self, basis: Dict[str, Any], segments: int = 10, n_scan: int = 12) -> None:
        wtype = get_path(basis, "well.type")
        if wtype not in PRODUCER_TYPES:
            raise ValueError("ProducerModel needs a producer well.type, got {}".format(wtype))
        require("DriftFluxWellboreHydraulics", "WellboreThermalModel", "ThermodynamicOperations")
        self.basis = basis
        self.wtype = wtype
        self.segments = segments
        self.n_scan = n_scan
        self.depths = effective_tubing_depths(basis)
        self.std = standard_factors(basis)
        self.gas_well = wtype in ("gas_producer", "gas_condensate_producer")
        self._ipr_cache: Dict[str, Any] = {}
        self._fl_cache: Dict[str, Any] = {}
        self._vlp_cache: Dict[str, Tuple[float, Any]] = {}
        self.tubing_id_m = float(get_path(basis, "completion.tubing.id_m"))
        self.roughness_m = float(get_path(basis, "completion.tubing.roughness_m") or 4.5e-5)
        self.lift_gas_default = float(get_path(basis, "completion.lift.gas_rate_sm3d") or 0.0)

    # ------------------------------------------------------------------ parameters
    def params(self, case: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Case parameters with optional overrides (tubing_id_m, host_pressure_bara, water_cut, pressure_bara, skin, k_md, lift_gas_sm3d)."""
        p = case_params(self.basis, case)
        p.update({k: v for k, v in (overrides or {}).items() if v is not None})
        p.setdefault("tubing_id_m", self.tubing_id_m)
        p.setdefault("lift_gas_sm3d", self.lift_gas_default)
        return p

    @staticmethod
    def _key(p: Dict[str, Any], *names: str) -> str:
        return "|".join("{}={:.6g}".format(n, float(p.get(n, 0.0))) for n in names)

    def mass_flow(self, p: Dict[str, Any], q: float) -> Dict[str, float]:
        """Mass rates (kg/s) for a stock-tank oil or wellstream-gas-equivalent rate ``q`` (Sm3/d)."""
        if self.gas_well:
            hc = q * self.std["kg_per_sm3_gas_equivalent"] / 86400.0
            water = q * float(p.get("wgr_sm3_per_msm3", 0.0)) * 1.0e-6 * WATER_SC_DENSITY / 86400.0
        else:
            hc = q * self.std["kg_per_sm3_stock_tank_liquid"] / 86400.0
            wc = p.get("water_cut", 0.0)
            water = q * WATER_SC_DENSITY * wc / (1.0 - wc) / 86400.0 if wc > 0 else 0.0
        lift_mol_s = p.get("lift_gas_sm3d", 0.0) * LIFT_GAS_MOLES_PER_SM3 / 86400.0
        lift_mass = lift_mol_s * 0.016043
        return {"hydrocarbon": hc, "water": water, "lift": lift_mass, "total": hc + water + lift_mass, "lift_mol_s": lift_mol_s}

    # ------------------------------------------------------------------ inflow
    def ipr(self, case: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return inflow callables for the case: ``pwf(q)``, ``rate(pwf)``, ``aof`` and metadata."""
        p = self.params(case, overrides)
        key = case + self._key(p, "pressure_bara", "skin", "k_md", "h_m", "water_cut")
        if key in self._ipr_cache:
            return self._ipr_cache[key]
        props = reservoir_properties(self.basis, p["pressure_bara"], p["temperature_C"])
        if not self.gas_well:
            rho = props["density_kg_m3"]
            res_per_sm3 = self.std["kg_per_sm3_stock_tank_liquid"] / rho
            pi = darcy_oil_pi_sm3d_per_bar(p["k_md"], p["h_m"], props["viscosity_cp"], p["re_m"], p["rw_m"], p["skin"], res_per_sm3)
            pi_override = get_path(self.basis, "reservoir.productivity_index_sm3d_per_bar")
            pi_source = "Darcy pseudo-steady radial (NeqSim viscosity and volume factor)"
            if pi_override:
                pi = float(pi_override)
                pi_source = "supplied productivity index (reservoir.productivity_index_sm3d_per_bar)"
            pb = props.get("bubble_point_bara", float("nan"))
            c = composite_oil_ipr(p["pressure_bara"], pb if pb == pb else 0.0, pi)
            out = {"kind": "oil_composite", "pwf": c["pwf"], "rate": c["rate"], "aof": c["aof"], "pi_sm3d_per_bar": pi, "bubble_point_bara": pb,
                   "source": pi_source, "viscosity_cp": props["viscosity_cp"], "res_density": rho, "params": p}
        else:
            require("GasCondensateInflowModel")
            GC = jclass("GasCondensateInflowModel")
            fl = build_fluid(self.basis, p["temperature_C"], p["pressure_bara"])
            m = GC(fl, p["temperature_C"]).setReservoirPressure(p["pressure_bara"]).setFormation(p["k_md"], p["h_m"]).setGeometry(p["re_m"], p["rw_m"], p["skin"])
            rp = get_path(self.basis, "reservoir.relperm") or {}
            m.setRelativePermeability(rp.get("swc", 0.2), rp.get("soc", 0.1), rp.get("krg_max", 1.0), rp.get("kro_max", 1.0), rp.get("ng", 3.0), rp.get("no", 3.0))
            phi = get_path(self.basis, "reservoir.porosity")
            beta = None
            if phi:
                beta = float(m.useGeertsmaBeta(float(phi)))
            dew = float(m.getDewPointPressureBara())
            pts = int(get_path(self.basis, "reservoir.ipr_points") or 16)
            rows = sorted({(round(float(r[0]), 6), float(r[1])) for r in m.generateIpr(pts)}, key=lambda x: -x[0])
            pw = np.array([p["pressure_bara"]] + [r[0] for r in rows if r[0] < p["pressure_bara"]])
            qs = np.maximum.accumulate(np.array([0.0] + [r[1] for r in rows if r[0] < p["pressure_bara"]]))
            keep = np.concatenate([[True], np.diff(qs) > 1e-9])
            qs, pw = qs[keep], pw[keep]

            def pwf(q: float, qs=qs, pw=pw) -> float:
                return float(np.interp(q, qs, pw, left=pw[0], right=0.0))

            def rate(pwf_bar: float, qs=qs, pw=pw) -> float:
                return float(np.interp(pwf_bar, pw[::-1], qs[::-1]))

            out = {"kind": "gas_condensate_model", "pwf": pwf, "rate": rate, "aof": float(qs[-1]), "dew_point_bara": dew, "forchheimer_beta_1_per_m": beta,
                   "source": "GasCondensateInflowModel (molar pseudo-pressure, banking screening)", "table": {"q": qs.tolist(), "pwf": pw.tolist()},
                   "model": m, "params": p, "non_darcy": bool(beta), "relperm_assumed": not bool(rp)}
        self._ipr_cache[key] = out
        return out

    # ------------------------------------------------------------------ outflow
    def _thermal(self, p: Dict[str, Any], mass: float):
        return thermal_model(self.basis, mass, p["temperature_C"])

    def traverse(self, case: str, q: float, whp_bara: float, overrides: Optional[Dict[str, Any]] = None, from_bottomhole: bool = False):
        """Run the drift-flux traverse at rate ``q``; returns the Java Result and extras.

        By default the pressure given is the wellhead pressure and the result is the bottom-hole pressure (VLP). With ``from_bottomhole=True`` the
        pressure given is the flowing bottom-hole pressure and the result carries the wellhead pressure the well can deliver.
        """
        p = self.params(case, overrides)
        mflow = self.mass_flow(p, q)
        if self.gas_well:
            wm = (mflow["water"] / WATER_MW_KG_PER_MOL) / (mflow["hydrocarbon"] / self.std["mw_kg_per_mol"]) if mflow["water"] > 0 else 0.0
        else:
            wm = water_moles_for_cut(self.basis, p.get("water_cut", 0.0))
        extra = None
        if mflow["lift_mol_s"] > 0:
            hc_mol_s = mflow["hydrocarbon"] / self.std["mw_kg_per_mol"]
            extra = {"methane": mflow["lift_mol_s"] / hc_mol_s}
        fluid = build_fluid(self.basis, 60.0, whp_bara, water_moles_per_mole=wm, extra=extra)
        tm = self._thermal(p, mflow["total"])
        h = jclass("DriftFluxWellboreHydraulics")(fluid).setMassFlowRate(float(mflow["total"])).setTubing(float(p["tubing_id_m"]), self.roughness_m)
        h.setStraightWell(self.depths["md_m"], self.depths["inclination_deg"], self.segments).setThermalModel(tm)
        if wm > 0:
            h.setMultiPhaseCheck(True)
        res = h.calculateFromBottomhole(float(whp_bara)) if from_bottomhole else h.calculateFromWellhead(float(whp_bara))
        return res, {"mass": mflow, "thermal": tm, "fluid": fluid, "params": p, "wellhead_temperature_C": tm.temperatureAt(0.0) - 273.15}

    def available_whp(self, case: str, q: float, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Wellhead pressure the well can deliver at rate ``q``: IPR gives the flowing bottom-hole pressure, the tubing traverse gives the wellhead pressure.

        The difference to the required wellhead pressure (host boundary + minimum choke drop) is the choke drop the subsea choke has to absorb at that rate.
        """
        ipr = self.ipr(case, overrides)
        if q >= ipr["aof"]:
            return {"q": q, "feasible": False, "reason": "rate above the inflow limit"}
        pwf = float(ipr["pwf"](q))
        try:
            res, extra = self.traverse(case, q, pwf, overrides, from_bottomhole=True)
        except Exception as exc:  # noqa: BLE001 - the Java traverse throws when the column cannot lift the fluid to the surface
            return {"q": q, "feasible": False, "pwf_bara": pwf, "reason": "tubing traverse failed: {}".format(str(exc)[:140])}
        req = self.back_pressure(case, q, overrides)
        whp = float(res.getWellheadPressureBara())
        return {"q": q, "feasible": True, "pwf_bara": pwf, "whp_available_bara": whp, "whp_required_bara": req["wellhead_pressure_bara"], "choke_dp_bar": whp - req["wellhead_pressure_bara"],
                "wellhead_temperature_C": extra["wellhead_temperature_C"], "erosional_ratio": _f(res.getMaxErosionalRatio()), "turner_ratio": _f(res.getMinTurnerRatio()),
                "loading_risk": bool(res.isLiquidLoadingRisk()), "regimes": str(res.getRegimeCounts()), "hydrostatic_dp_bar": float(res.getHydrostaticDropBar()),
                "friction_dp_bar": float(res.getFrictionDropBar()), "mass_flow_kg_s": extra["mass"]["total"], "tubing_id_m": extra["params"]["tubing_id_m"]}

    def back_pressure(self, case: str, q: float, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        """Wellhead pressure needed to deliver ``q`` to the host (flowline dP interpolated from a 5-point table)."""
        p = self.params(case, overrides)
        fl = get_path(self.basis, "facility.flowline") or {}
        choke = float(get_path(self.basis, "facility.choke_dp_bar") or 0.0)
        bt = get_path(self.basis, "facility.boundary_table")
        if bt:
            scale = float(bt.get("q_scale", 1.0))
            ref = float(bt.get("reference_host_pressure_bara", p["host_pressure_bara"]))
            manifold = float(np.interp(q * scale, bt["q_sm3d"], bt["p_bara"])) + (p["host_pressure_bara"] - ref)
            return {"wellhead_pressure_bara": manifold + choke, "flowline_dp_bar": manifold - p["host_pressure_bara"], "choke_dp_bar": choke,
                    "method": "supplied boundary table (manifold pressure versus rate from an upstream flowline study) shifted by the host-pressure change + choke drop"}
        if not fl or not fl.get("length_m"):
            return {"wellhead_pressure_bara": p["host_pressure_bara"] + choke, "flowline_dp_bar": 0.0, "choke_dp_bar": choke}
        key = case + self._key(p, "host_pressure_bara", "water_cut", "lift_gas_sm3d")
        tab = self._fl_cache.get(key)
        if tab is None:
            q_hi = max(self.ipr(case, overrides)["aof"] * 0.85, 1.0)
            grid = np.linspace(q_hi / 5.0, q_hi, 5)
            dps = []
            for qq in grid:
                mflow = self.mass_flow(p, float(qq))
                tm = self._thermal(p, mflow["total"])
                wm = water_moles_for_cut(self.basis, p.get("water_cut", 0.0)) if not self.gas_well else 0.0
                tmpl = build_fluid(self.basis, 40.0, p["host_pressure_bara"] + 5.0, water_moles_per_mole=wm)
                r = flowline_back_pressure(self.basis, tmpl, mflow["total"], p["host_pressure_bara"], tm.temperatureAt(0.0) - 273.15)
                dps.append(r["flowline_dp_bar"])
            tab = (grid, np.array(dps))
            self._fl_cache[key] = tab
        dp = float(np.interp(q, tab[0], tab[1]))
        return {"wellhead_pressure_bara": p["host_pressure_bara"] + dp + choke, "flowline_dp_bar": dp, "choke_dp_bar": choke}

    def vlp_bhp(self, case: str, q: float, overrides: Optional[Dict[str, Any]] = None) -> float:
        """Bottom-hole pressure required to deliver ``q`` against the host back pressure."""
        p = self.params(case, overrides)
        key = case + self._key(p, "tubing_id_m", "host_pressure_bara", "water_cut", "lift_gas_sm3d", "wgr_sm3_per_msm3") + "|q={:.5g}".format(q)
        if key in self._vlp_cache:
            return self._vlp_cache[key][0]
        whp = self.back_pressure(case, q, overrides)["wellhead_pressure_bara"]
        res, _ = self.traverse(case, q, whp, overrides)
        bhp = float(res.getBottomholePressureBara())
        self._vlp_cache[key] = (bhp, None)
        return bhp

    # ------------------------------------------------------------------ nodal
    def operating_point(self, case: str, overrides: Optional[Dict[str, Any]] = None, detail: bool = True) -> Dict[str, Any]:
        """Solve the nodal intersection and report the operating point, target check and tubing diagnostics."""
        p = self.params(case, overrides)
        ipr = self.ipr(case, overrides)
        q_max = ipr["aof"] * 0.85
        q_min = max(q_max * 0.04, 1.0)
        nodal = solve_nodal(ipr["pwf"], lambda q: self.vlp_bhp(case, q, overrides), q_min, q_max, n_scan=self.n_scan)
        target = p["rate"]
        out: Dict[str, Any] = {"case": case, "params": {k: v for k, v in p.items() if isinstance(v, (int, float, str))}, "ipr_kind": ipr["kind"], "ipr_source": ipr["source"],
                               "pi_sm3d_per_bar": ipr.get("pi_sm3d_per_bar"), "bubble_point_bara": ipr.get("bubble_point_bara"), "dew_point_bara": ipr.get("dew_point_bara"),
                               "target_rate": target, "nodal": nodal.to_dict(), "status": nodal.status, "warnings": []}
        s_tgt = float(ipr["pwf"](target)) - self.vlp_bhp(case, target, overrides) if target <= ipr["aof"] else -1.0e3
        out["surplus_at_target_bar"] = s_tgt
        out["target_met"] = bool(s_tgt >= 0.0)
        op = nodal.operating_point
        q_diag = target if out["target_met"] or op is None else op.rate
        if op is not None:
            out.update({"q_op": op.rate, "bhp_op": op.bhp_bara, "drawdown_bar": p["pressure_bara"] - op.bhp_bara})
        else:
            out.update({"q_op": 0.0, "bhp_op": None, "drawdown_bar": None})
            out["warnings"].append("no stable intersection: the well does not flow naturally against this back pressure (artificial lift or lower back pressure needed)")
        if out["status"] == "UNSTABLE_ONLY":
            out["warnings"].append("only an unstable intersection exists (VLP loading branch)")
        if detail and q_diag > 0:
            whp = self.back_pressure(case, q_diag, overrides)
            throttled = bool(get_path(self.basis, "facility.throttle_surplus_across_choke")) and out["target_met"] and q_diag < ipr["aof"]
            if throttled:
                # the well delivers the target with surplus pressure: the choke absorbs it, so the real tree conditions follow from the bottom-hole pressure
                res, extra = self.traverse(case, q_diag, float(ipr["pwf"](q_diag)), overrides, from_bottomhole=True)
                whp = {"wellhead_pressure_bara": float(res.getWellheadPressureBara()), "flowline_dp_bar": whp["flowline_dp_bar"],
                       "choke_dp_bar": float(res.getWellheadPressureBara()) - whp["wellhead_pressure_bara"] + whp["choke_dp_bar"]}
            else:
                res, extra = self.traverse(case, q_diag, whp["wellhead_pressure_bara"], overrides)
            out["diagnostic_rate"] = q_diag
            out["diagnostic_basis"] = "throttled at the choke: wellhead pressure from the inflow (bottom-hole) side" if throttled else "wellhead pressure at the minimum required back pressure (choke open)"
            out["wellhead"] = {"pressure_bara": whp["wellhead_pressure_bara"], "temperature_C": extra["wellhead_temperature_C"], "flowline_dp_bar": whp["flowline_dp_bar"],
                               "choke_dp_bar": whp["choke_dp_bar"]}
            out["bottomhole"] = {"pressure_bara": float(res.getBottomholePressureBara()), "temperature_C": p["temperature_C"]}
            out["profile"] = profile_from_result(res, extra, self.depths, self.segments)
            out["tubing"] = {"turner_min": _f(res.getMinTurnerRatio()), "loading_risk": bool(res.isLiquidLoadingRisk()), "erosional_ratio_max": _f(res.getMaxErosionalRatio()),
                             "regime_counts": str(res.getRegimeCounts()), "hydrostatic_dp_bar": float(res.getHydrostaticDropBar()), "friction_dp_bar": float(res.getFrictionDropBar()),
                             "warnings": [str(w) for w in res.getWarnings()]}
            out["mass_flow_kg_s"] = extra["mass"]["total"]
        return out

    # ------------------------------------------------------------------ sweeps
    def sweep(self, case: str, parameter: str, values: List[float]) -> List[Dict[str, Any]]:
        """Operating point for a list of values of one override parameter (tubing_id_m, host_pressure_bara, water_cut, pressure_bara, skin, lift_gas_sm3d)."""
        rows = []
        for v in values:
            r = self.operating_point(case, {parameter: v}, detail=False)
            rows.append({"value": v, "q_op": r.get("q_op"), "bhp_op": r.get("bhp_op"), "status": r["status"], "target_met": r["target_met"],
                         "surplus_at_target_bar": r["surplus_at_target_bar"]})
        return rows

    def nodal_family(self, case: str, parameter: str, values: List[float], n_points: int = 14) -> Dict[str, Any]:
        """IPR plus a family of VLP curves for one override parameter (for the nodal chart)."""
        ipr = self.ipr(case)
        p = self.params(case)
        q_max = min(ipr["aof"] * 0.85, 3.5 * p["rate_high"])
        qs = np.linspace(max(q_max * 0.04, 1.0), q_max, n_points)
        fam = {}
        for v in values:
            fam[v] = [self.vlp_bhp(case, float(q), {parameter: v}) for q in qs]
        return {"q": qs.tolist(), "ipr_pwf": [float(ipr["pwf"](q)) for q in qs], "families": {str(k): v for k, v in fam.items()}, "parameter": parameter}


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def profile_from_result(res: Any, extra: Dict[str, Any], depths: Dict[str, float], n: int) -> Dict[str, Any]:
    """Convert a drift-flux Result into depth-aligned arrays (index 0 = wellhead)."""
    tvd = depths["tvd_m"]
    node_z = np.linspace(0.0, tvd, n + 1)
    mid_z = 0.5 * (node_z[:-1] + node_z[1:])
    return {
        "node_tvd_m": node_z.tolist(),
        "pressure_bara": [float(x) for x in res.getPressureBara()],
        "tvd_m": mid_z.tolist(),
        "temperature_C": [float(x) - 273.15 for x in res.getSegmentTemperatureK()],
        "liquid_holdup": [float(x) for x in res.getLiquidHoldup()],
        "void_fraction": [float(x) for x in res.getVoidFraction()],
        "vsg_m_s": [float(x) for x in res.getSuperficialGasVelocity()],
        "vsl_m_s": [float(x) for x in res.getSuperficialLiquidVelocity()],
        "mixture_density": [float(x) for x in res.getMixtureDensity()],
        "turner_ratio": [(_f(x)) for x in res.getTurnerRatio()],
        "regime": [str(x) for x in res.getFlowRegime()],
    }
