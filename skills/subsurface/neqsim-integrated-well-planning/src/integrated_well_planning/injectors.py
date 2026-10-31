"""Injector chain: injectivity -> tubing -> wellhead pressure -> pump/compressor duty, with fracture margin.

Water injectors use NeqSim ``InjectionWellHydraulics`` (matrix operating point, thermal fracture-pressure reduction).
Gas injectors use a radial pseudo-pressure injectivity with NeqSim Z and viscosity, the same hydraulics class for the
tubing column and a NeqSim isentropic compression duty. Intentional-fracture injection is NOT modelled (ledger L26).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from .basis import INJECTOR_TYPES
from .model_chain import (case_params, effective_tubing_depths, gas_injectivity_coefficient, build_fluid, require, reservoir_properties, standard_factors,
                          surface_temperature_C, thermal_model, SC_MOLAR_VOLUME_SM3_PER_KMOL)
from .registers import get_path
from .runtime import jclass

WATER_DENSITY = 999.0


def _bisect(f, lo: float, hi: float, tol: float = 0.02, maxit: int = 40) -> Optional[float]:
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(maxit):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) < 1e-4:
            return mid
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


class InjectorModel:
    """Reservoir-well-facility model of one injector."""

    def __init__(self, basis: Dict[str, Any], segments: int = 10) -> None:
        self.wtype = get_path(basis, "well.type")
        if self.wtype not in INJECTOR_TYPES:
            raise ValueError("InjectorModel needs an injector well.type, got {}".format(self.wtype))
        require("InjectionWellHydraulics", "WellboreThermalModel", "ThermodynamicOperations")
        self.basis = basis
        self.segments = segments
        self.gas = self.wtype == "gas_injector"
        self.depths = effective_tubing_depths(basis)
        self.tubing_id_m = float(get_path(basis, "completion.tubing.id_m"))
        self.roughness_m = float(get_path(basis, "completion.tubing.roughness_m") or 4.5e-5)
        self.std = standard_factors(basis) if self.gas else {}

    def params(self, case: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Resolve case parameters (injectivity improves with the ``high`` case)."""
        p = case_params(self.basis, case)
        p["injection_temperature_C"] = float(get_path(self.basis, "reservoir.injection_temperature_C") or 15.0)
        p["fracture_gradient"] = float(get_path(self.basis, "reservoir.fracture_gradient_bar_per_m"))
        p["tubing_id_m"] = self.tubing_id_m
        p.update({k: v for k, v in (overrides or {}).items() if v is not None})
        return p

    def mass_rate(self, p: Dict[str, Any], q: float) -> float:
        """Mass rate (kg/s) from the target volume rate (m3/d water or Sm3/d gas)."""
        if self.gas:
            return q * self.std["kg_per_sm3_gas_equivalent"] / 86400.0
        return q * WATER_DENSITY / 86400.0

    def _fluid(self, p: Dict[str, Any]):
        return build_fluid(self.basis, p["injection_temperature_C"], 100.0)

    def _hydraulics(self, p: Dict[str, Any], mass: float):
        fluid = self._fluid(p)
        tm = thermal_model(self.basis, mass, p["temperature_C"], direction="INJECTION", inlet_temperature_C=p["injection_temperature_C"])
        h = jclass("InjectionWellHydraulics")(fluid)
        h.setMassFlowRate(float(mass)).setTubing(float(p["tubing_id_m"]), self.roughness_m)
        h.setStraightWell(self.depths["md_m"], self.depths["inclination_deg"], self.segments).setThermalModel(tm)
        rock = get_path(self.basis, "reservoir.rock") or {}
        t_bottom = p["temperature_C"]
        h.setFractureData(p["fracture_gradient"], t_bottom, float(rock.get("alpha_per_K", 1.0e-5)), float(rock.get("E_GPa", 5.0)), float(rock.get("nu", 0.25)))
        if not self.gas:
            h.setReservoir(p["pressure_bara"], p["k_md"], p["h_m"], p["re_m"], p["rw_m"], p["skin"])
            h.setReservoirViscosity(float(get_path(self.basis, "reservoir.reservoir_viscosity_pa_s") or 6.0e-4))
        return h, tm

    def required_bhp(self, p: Dict[str, Any], q: float, h=None) -> Dict[str, float]:
        """Bottom-hole pressure needed to inject ``q`` into the matrix."""
        if not self.gas:
            mass = self.mass_rate(p, q)
            h = h or self._hydraulics(p, mass)[0]
            f = lambda bhp: float(h.matrixMassRateKgPerS(bhp)) - mass  # noqa: E731
            bhp = _bisect(f, p["pressure_bara"], p["pressure_bara"] + 800.0, tol=1e-3)
            return {"bhp_bara": bhp if bhp is not None else float("nan"), "method": "InjectionWellHydraulics.matrixMassRateKgPerS (bisection)"}
        t_k = p["temperature_C"] + 273.15
        pres = p["pressure_bara"]
        bhp = pres * 1.1
        for _ in range(3):
            pm = 0.5 * (bhp + pres)
            props = reservoir_properties(self.basis, pm, p["temperature_C"])
            c = gas_injectivity_coefficient(p["k_md"], p["h_m"], props["viscosity_cp"], props["z"], t_k, p["re_m"], p["rw_m"], p["skin"])
            bhp = math.sqrt(pres ** 2 + q / c)
        return {"bhp_bara": bhp, "method": "radial gas pseudo-steady, (pbh^2 - pres^2), NeqSim Z and viscosity at mean pressure", "injectivity_c": c, "z": props["z"],
                "viscosity_cp": props["viscosity_cp"]}

    def whp_for_bhp(self, p: Dict[str, Any], mass: float, bhp: float):
        """Wellhead pressure that gives ``bhp`` at the tubing shoe plus the hydraulics result at that point."""
        h, tm = self._hydraulics(p, mass)
        f = lambda whp: float(h.calculateFromWellhead(float(whp)).getBottomholePressureBara()) - bhp  # noqa: E731
        whp = _bisect(f, 1.5, max(bhp + 100.0, 50.0), tol=0.01)
        if whp is None:
            return None, None, h, tm
        return whp, h.calculateFromWellhead(float(whp)), h, tm

    def operating_point(self, case: str, overrides: Optional[Dict[str, Any]] = None, rate: Optional[float] = None) -> Dict[str, Any]:
        """Required wellhead pressure, fracture margin, temperatures and surface duty for a rate."""
        p = self.params(case, overrides)
        q = float(rate if rate is not None else p["rate"])
        mass = self.mass_rate(p, q)
        bh = self.required_bhp(p, q)
        out: Dict[str, Any] = {"case": case, "rate": q, "mass_kg_s": mass, "kind": "gas_injector" if self.gas else "water_injector", "bhp_required_bara": bh["bhp_bara"],
                               "injectivity_method": bh["method"], "warnings": [], "params": {k: v for k, v in p.items() if isinstance(v, (int, float, str))}}
        if not (bh["bhp_bara"] == bh["bhp_bara"]):
            out.update({"status": "NOT_FEASIBLE", "whp_required_bara": None})
            out["warnings"].append("matrix injectivity cannot deliver the rate within 800 bar above reservoir pressure")
            return out
        whp, res, h, tm = self.whp_for_bhp(p, mass, bh["bhp_bara"])
        if whp is None:
            out.update({"status": "NOT_FEASIBLE", "whp_required_bara": None})
            out["warnings"].append("no wellhead pressure within the solver bracket reaches the required bottom-hole pressure")
            return out
        t_bh = float(res.getTemperatureK()[-1]) - 273.15
        frac = float(h.getEffectiveFracturePressureBara(t_bh + 273.15)) if hasattr(h, "getEffectiveFracturePressureBara") else float(res.getFracturePressureBara())
        out.update({
            "status": "OK", "whp_required_bara": whp, "bhp_bara": float(res.getBottomholePressureBara()), "gravity_gain_bar": float(res.getGravityGainBar()),
            "friction_loss_bar": float(res.getFrictionLossBar()), "bottomhole_temperature_C": t_bh, "wellhead_temperature_C": float(res.getTemperatureK()[0]) - 273.15,
            "effective_fracture_pressure_bara": frac, "fracture_margin_bar": frac - float(res.getBottomholePressureBara()), "two_phase": bool(res.isTwoPhase()),
            "density_top_kg_m3": float(res.getDensityKgPerM3()[0]), "density_bottom_kg_m3": float(res.getDensityKgPerM3()[-1]),
            "profile": {"tvd_m": np.linspace(0.0, self.depths["tvd_m"], len(list(res.getTemperatureK()))).tolist(), "temperature_C": [float(x) - 273.15 for x in res.getTemperatureK()],
                        "tvd_density_m": np.linspace(0.0, self.depths["tvd_m"], len(list(res.getDensityKgPerM3()))).tolist(), "density_kg_m3": [float(x) for x in res.getDensityKgPerM3()]},
        })
        if out["fracture_margin_bar"] < 0:
            out["warnings"].append("bottom-hole pressure exceeds the effective fracture pressure: matrix basis invalid, intentional-fracture injection needs a specialist model")
        if bh.get("z"):
            out["gas_z"], out["gas_viscosity_cp"] = bh["z"], bh["viscosity_cp"]
        supply = float(get_path(self.basis, "facility.supply_pressure_bara") or get_path(self.basis, "facility.host_pressure_bara") or 1.0)
        if self.gas:
            eta = float(get_path(self.basis, "facility.compressor_efficiency") or 0.75)
            t_s = float(get_path(self.basis, "facility.host_temperature_C") or 35.0)
            out["surface_duty"] = {"type": "compression", **compression_duty(self.basis, mass, supply, t_s, whp, eta)}
            out["power_kw"] = out["surface_duty"]["power_kw"]
        else:
            eta = float(get_path(self.basis, "facility.pump_efficiency") or 0.7)
            qm3s = q / 86400.0
            out["surface_duty"] = {"type": "pump", "suction_bara": supply, "discharge_bara": whp, "efficiency": eta, "power_kw": max(0.0, qm3s * (whp - supply) * 1e5 / eta / 1000.0),
                                   "method": "hydraulic power = Q dP / eta (efficiency is an input)"}
            out["power_kw"] = out["surface_duty"]["power_kw"]
        return out

    def injectivity_curve(self, case: str, whps: List[float]) -> List[Dict[str, float]]:
        """Matrix rate versus wellhead pressure (water injectors: NeqSim operating point; gas: bisection on rate)."""
        rows = []
        p = self.params(case)
        for whp in whps:
            if not self.gas:
                mass_guess = self.mass_rate(p, p["rate"])
                h, _ = self._hydraulics(p, mass_guess)
                op = h.findOperatingPoint(float(whp))
                rows.append({"whp_bara": float(whp), "rate_m3d": float(op.getMassRateKgPerS()) * 86400.0 / WATER_DENSITY, "bhp_bara": float(op.getBottomholePressureBara()),
                             "fracture_limited": bool(op.isFractureLimited()), "capped_rate_m3d": float(op.getCappedMassRateKgPerS()) * 86400.0 / WATER_DENSITY})
            else:
                qs = np.linspace(0.05 * p["rate"], 3.0 * p["rate"], 12)
                best = None
                for q in qs:
                    mass = self.mass_rate(p, float(q))
                    bh = self.required_bhp(p, float(q))["bhp_bara"]
                    h, _ = self._hydraulics(p, mass)
                    bhp_at = float(h.calculateFromWellhead(float(whp)).getBottomholePressureBara())
                    if bh <= bhp_at:
                        best = float(q)
                rows.append({"whp_bara": float(whp), "rate_sm3d": best or 0.0})
        return rows

    def sweep_tubing(self, case: str, ids_m: List[float]) -> List[Dict[str, Any]]:
        """Required wellhead pressure and power for a list of tubing inner diameters."""
        rows = []
        for d in ids_m:
            r = self.operating_point(case, {"tubing_id_m": d})
            rows.append({"tubing_id_m": d, "whp_required_bara": r.get("whp_required_bara"), "power_kw": r.get("power_kw"), "fracture_margin_bar": r.get("fracture_margin_bar"),
                         "status": r["status"]})
        return rows


def compression_duty(basis: Dict[str, Any], mass_kg_s: float, p_suction: float, t_suction_c: float, p_discharge: float, eta: float) -> Dict[str, float]:
    """Isentropic compression duty (NeqSim PS flash) for the injection gas; efficiency is an input."""
    f = build_fluid(basis, t_suction_c, p_suction)
    ops = jclass("ThermodynamicOperations")(f)
    ops.TPflash()
    f.initProperties()
    h1 = float(f.getEnthalpy("kJ/kg"))
    s1 = float(f.getEntropy())
    g = f.clone()
    g.setPressure(float(p_discharge))
    jclass("ThermodynamicOperations")(g).PSflash(s1)
    g.initProperties()
    dh_s = float(g.getEnthalpy("kJ/kg")) - h1
    power = mass_kg_s * dh_s / max(eta, 0.05)
    return {"suction_bara": p_suction, "discharge_bara": p_discharge, "pressure_ratio": p_discharge / p_suction, "isentropic_head_kj_per_kg": dh_s, "efficiency": eta,
            "power_kw": power, "discharge_temperature_C": float(g.getTemperature()) - 273.15 + (dh_s / max(eta, 0.05) - dh_s) / max(float(f.getCp("kJ/kgK")), 0.1),
            "method": "isentropic enthalpy rise from NeqSim PS flash / efficiency; discharge temperature estimated with suction Cp (screening)"}
