"""Shared building blocks of the reservoir-well-facility chain (fluids, case parameters, thermal, back pressure).

Cases are *outcome* cases: ``low`` is the pessimistic deliverability/injectivity outcome, ``high`` the
optimistic one. Parameters where a higher number is worse (skin, water cut, host pressure, GOR) are therefore
taken from the ``high`` end of their range in the ``low`` case.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .basis import CASES, case_value, rng
from .registers import get_path
from .runtime import ensure_runtime, jclass

SC_MOLAR_VOLUME_SM3_PER_KMOL = 23.645
WATER_MW_KG_PER_MOL = 0.018015
WATER_SC_DENSITY = 999.0
HIGHER_IS_WORSE = {"skin", "water_cut", "host_pressure_bara", "gor", "wgr"}
_OPPOSITE = {"low": "high", "base": "base", "high": "low"}


class ModelUnavailable(RuntimeError):
    """Raised when a calculation needs NeqSim classes that are not available at run time."""


def require(*names: str) -> None:
    """Raise :class:`ModelUnavailable` with an explicit reason when any named class is missing."""
    st = ensure_runtime()
    missing = [n for n in names if not st.has(n)]
    if missing:
        raise ModelUnavailable("NeqSim classes not available: {} ({})".format(", ".join(missing), st.reason or "runtime not started"))


def pick(value: Any, case: str, parameter: str) -> float:
    """Return the value of a range for an outcome case, flipping the end for worse-when-higher parameters."""
    use = _OPPOSITE[case] if parameter in HIGHER_IS_WORSE else case
    return case_value(value, use)


def case_params(basis: Dict[str, Any], case: str) -> Dict[str, Any]:
    """Resolve the scalar parameters of one outcome case from the basis."""
    g = lambda p: get_path(basis, p)  # noqa: E731
    out: Dict[str, Any] = {"case": case}
    out["pressure_bara"] = pick(g("reservoir.pressure_bara"), case, "pressure_bara")
    out["temperature_C"] = float(g("reservoir.temperature_C"))
    out["k_md"] = pick(g("reservoir.permeability_md"), case, "k")
    out["h_m"] = pick(g("reservoir.thickness_m"), case, "h")
    out["skin"] = pick(g("reservoir.skin"), case, "skin")
    out["re_m"] = float(g("reservoir.drainage_radius_m") or 400.0)
    out["rw_m"] = float(g("reservoir.wellbore_radius_m") or 0.108)
    out["water_cut"] = pick(g("reservoir.water_cut") if g("reservoir.water_cut") is not None else 0.0, case, "water_cut")
    out["wgr_sm3_per_msm3"] = pick(g("reservoir.wgr_sm3_per_msm3") if g("reservoir.wgr_sm3_per_msm3") is not None else 0.0, case, "wgr")
    out["host_pressure_bara"] = pick(g("facility.host_pressure_bara"), case, "host_pressure_bara")
    out["rate"] = case_value(g("targets.rate"), "base")
    out["rate_low"], out["rate_high"] = case_value(g("targets.rate"), "low"), case_value(g("targets.rate"), "high")
    return out


def effective_tubing_depths(basis: Dict[str, Any]) -> Dict[str, float]:
    """Return tubing MD/TVD below the tree (seabed for subsea wells) and the inclination equivalent."""
    md = float(get_path(basis, "trajectory.md_m"))
    tvd = float(get_path(basis, "trajectory.tvd_m"))
    if get_path(basis, "reservoir.datum_tvd_m"):
        tvd = float(get_path(basis, "reservoir.datum_tvd_m"))
    env = get_path(basis, "well.environment")
    rkb = float(get_path(basis, "datums.reference_elevation_msl_m") or 0.0)
    wd = float(get_path(basis, "datums.water_depth_m") or 0.0)
    offset = (wd + rkb) if env == "subsea" else 0.0
    tub_tvd, tub_md = tvd - offset, md - offset
    incl = math.degrees(math.acos(max(-1.0, min(1.0, tub_tvd / tub_md)))) if tub_md > 0 and tub_tvd > 0 else 0.0
    return {"tvd_m": tub_tvd, "md_m": tub_md, "inclination_deg": incl, "offset_m": offset}


def surface_temperature_C(basis: Dict[str, Any]) -> float:
    """Tree temperature reference: seabed temperature (subsea) or ambient surface temperature."""
    env = get_path(basis, "well.environment")
    if env == "subsea":
        v = get_path(basis, "environment.seabed_temperature_C")
        return 4.0 if v is None else float(v)
    v = get_path(basis, "environment.surface_temperature_C")
    return 10.0 if v is None else float(v)


CPA_LIBRARY_NAMES = ("nitrogen", "CO2", "H2S", "methane", "ethane", "propane", "i-butane", "n-butane", "i-pentane", "n-pentane", "n-hexane")


def e300_path(basis: Dict[str, Any]) -> Optional[str]:
    """Resolve ``fluid.e300_file`` (absolute, or relative to ``fluid.e300_base_dir``); ``None`` when the basis uses ``fluid.components`` only."""
    f = get_path(basis, "fluid.e300_file")
    if not f:
        return None
    p = Path(str(f))
    base = get_path(basis, "fluid.e300_base_dir")
    if not p.is_absolute() and base:
        p = Path(str(base)) / p
    return str(p)


def read_e300_fluid(path: str, water_moles_per_mole: float = 0.0):
    """Read an Eclipse E300 characterised fluid (EOS, pseudo-components and binary parameters from the file); optionally add free water with the reader's kij."""
    import jpype

    reader = jpype.JClass("neqsim.thermo.util.readwrite.EclipseFluidReadWrite")
    f = reader.read(str(path), True) if water_moles_per_mole > 0 else reader.read(str(path))
    if water_moles_per_mole > 0:
        f.addComponent("water", float(water_moles_per_mole))
    return f


def _soreide_density_g_cm3(mw_g_mol: float) -> float:
    """Soreide (1989) specific gravity of a petroleum fraction from its molar mass (screening estimate for a lumped plus fraction)."""
    return 0.2855 + 0.27 * (max(mw_g_mol, 70.0) - 66.0) ** 0.13


def lump_to_cpa_fluid(source, temperature_C: float, pressure_bara: float, water_mole_fraction: float, plus_name: str = "C7+"):
    """CPA (mixing rule 10) fluid for hydrate/water work from a characterised source fluid.

    Library components are copied by name; every other (pseudo) component is lumped into one TBP fraction with the mole-weighted molar
    mass and a Soreide density estimate (a model choice to record in the assumptions). Water is added in ``water_mole_fraction`` moles per
    mole of hydrocarbon feed.
    """
    require("SystemSrkCPAstatoil")
    f = jclass("SystemSrkCPAstatoil")(273.15 + temperature_C, pressure_bara)
    total = float(source.getTotalNumberOfMoles()) or 1.0
    n_plus, m_plus = 0.0, 0.0
    for i in range(source.getNumberOfComponents()):
        c = source.getComponent(i)
        name, mm = str(c.getComponentName()), float(c.getMolarMass())
        z = float(c.getNumberOfmoles()) / total
        if name in CPA_LIBRARY_NAMES:
            f.addComponent(name, z)
        elif name.lower() != "water":
            n_plus += z
            m_plus += z * mm
    if n_plus > 0:
        mw = m_plus / n_plus
        f.addTBPfraction(plus_name, n_plus, mw, _soreide_density_g_cm3(mw * 1000.0))
    if water_mole_fraction > 0:
        f.addComponent("water", float(water_mole_fraction))
    f.setMixingRule(10)
    f.setMultiPhaseCheck(True)
    return f


def build_fluid(basis: Dict[str, Any], temperature_C: float, pressure_bara: float, water_moles_per_mole: float = 0.0, extra: Optional[Dict[str, float]] = None,
                eos: Optional[str] = None, e300_file: Optional[str] = None):
    """Create a NeqSim fluid from ``fluid.components`` or an E300 file (clone-safe, mixing rule always set).

    Args:
        basis: planning basis.
        temperature_C: temperature in Celsius.
        pressure_bara: absolute pressure.
        water_moles_per_mole: moles of water added per mole of hydrocarbon feed (classic mixing rule, no mutual
            solubility: a hydraulics-only treatment; use a CPA basis for water-content and hydrate work).
        extra: additional component moles per mole of feed (for example lift gas).
        eos: override of ``fluid.eos`` (SRK, PR or CPA).
        e300_file: E300 file overriding ``fluid.e300_file`` (for example a low/high yield variant); the EOS then comes from the file.
    """
    require("SystemSrkEos")
    path = e300_file or e300_path(basis)
    if path:
        f = read_e300_fluid(path, water_moles_per_mole)
        f.setTemperature(273.15 + temperature_C)
        f.setPressure(pressure_bara)
        for name, moles in (extra or {}).items():
            f.addComponent(name, moles)
        return f
    eos = (eos or get_path(basis, "fluid.eos") or "SRK").upper()
    comps = get_path(basis, "fluid.components")
    use_cpa = eos == "CPA" or any(c["name"].lower() == "water" for c in comps)
    if use_cpa:
        require("SystemSrkCPAstatoil")
        f = jclass("SystemSrkCPAstatoil")(273.15 + temperature_C, pressure_bara)
    elif eos == "PR":
        f = jclass("SystemPrEos")(273.15 + temperature_C, pressure_bara)
    else:
        f = jclass("SystemSrkEos")(273.15 + temperature_C, pressure_bara)
    for c in comps:
        f.addComponent(c["name"], float(c["mole_fraction"]))
    if water_moles_per_mole > 0 and not any(c["name"].lower() == "water" for c in comps):
        f.addComponent("water", water_moles_per_mole)
    for name, moles in (extra or {}).items():
        f.addComponent(name, moles)
    f.setMixingRule(10 if use_cpa else "classic")
    return f


def _flash(fluid) -> None:
    jclass("ThermodynamicOperations")(fluid).TPflash()
    fluid.initProperties()


def standard_factors(basis: Dict[str, Any]) -> Dict[str, float]:
    """Stock-tank/standard-condition factors of the dry (water-free) reservoir fluid.

    Uses a single TP flash at 15 C and 1.01325 bara (no separator train) and an ideal-gas standard molar
    volume of 23.645 Sm3/kmol. Returns kg wellstream per Sm3 stock-tank liquid, GOR (Sm3/Sm3), CGR, Mw, and the
    liquid/gas standard volumes per mole of feed.
    """
    require("SystemSrkEos", "ThermodynamicOperations")
    f = build_fluid(basis, 15.0, 1.01325)
    _flash(f)
    mw = f.getMolarMass()  # kg/mol
    liquid_vol = gas_vol = 0.0
    n_phases = f.getNumberOfPhases()
    for i in range(n_phases):
        ph = f.getPhase(i)
        t = str(ph.getType())
        beta = ph.getBeta()
        if t in ("GAS",):
            gas_vol += beta * SC_MOLAR_VOLUME_SM3_PER_KMOL / 1000.0
        elif t in ("OIL", "LIQUID"):
            liquid_vol += beta * ph.getMolarMass() / ph.getDensity("kg/m3")
        elif t in ("AQUEOUS",):
            liquid_vol += 0.0
    out = {
        "mw_kg_per_mol": mw,
        "stock_tank_liquid_m3_per_mol": liquid_vol,
        "gas_sm3_per_mol": gas_vol if n_phases > 1 or gas_vol > 0 else SC_MOLAR_VOLUME_SM3_PER_KMOL / 1000.0,
        "kg_per_sm3_gas_equivalent": mw / (SC_MOLAR_VOLUME_SM3_PER_KMOL / 1000.0),
    }
    if liquid_vol > 0:
        out["kg_per_sm3_stock_tank_liquid"] = mw / liquid_vol
        out["gor_sm3_per_sm3"] = out["gas_sm3_per_mol"] / liquid_vol
        out["cgr_sm3_per_msm3"] = liquid_vol / (SC_MOLAR_VOLUME_SM3_PER_KMOL / 1000.0) * 1.0e6
    return out


def reservoir_properties(basis: Dict[str, Any], pressure_bara: float, temperature_C: float) -> Dict[str, float]:
    """Density, viscosity (cP) and bubble point (bara) of the dry reservoir fluid."""
    require("SystemSrkEos", "ThermodynamicOperations")
    f = build_fluid(basis, temperature_C, pressure_bara)
    _flash(f)
    out = {
        "density_kg_m3": f.getDensity("kg/m3"),
        "viscosity_cp": f.getViscosity("cP"),
        "z": f.getZ(),
        "phases": float(f.getNumberOfPhases()),
    }
    try:
        g = build_fluid(basis, temperature_C, pressure_bara)
        jclass("ThermodynamicOperations")(g).bubblePointPressureFlash(False)
        out["bubble_point_bara"] = g.getPressure()
    except Exception:  # noqa: BLE001
        out["bubble_point_bara"] = float("nan")
    return out


def water_moles_for_cut(basis: Dict[str, Any], water_cut: float) -> float:
    """Moles of water per mole of hydrocarbon feed for a stock-tank water cut."""
    if water_cut <= 0:
        return 0.0
    std = standard_factors(basis)
    vol_oil = std.get("stock_tank_liquid_m3_per_mol", 0.0)
    if vol_oil <= 0:
        return 0.0
    vol_w = water_cut / (1.0 - water_cut) * vol_oil
    return vol_w * WATER_SC_DENSITY / WATER_MW_KG_PER_MOL


def thermal_model(basis: Dict[str, Any], mass_kg_s: float, bottom_temperature_C: float, direction: str = "PRODUCTION", inlet_temperature_C: Optional[float] = None,
                  flowing_days: float = 30.0):
    """Create a WellboreThermalModel for the effective tubing depth."""
    require("WellboreThermalModel")
    depths = effective_tubing_depths(basis)
    ts = surface_temperature_C(basis)
    tres = float(get_path(basis, "reservoir.temperature_C"))
    grad = max(1e-4, (tres - ts) / max(depths["tvd_m"], 1.0))
    FlowDir = jclass("neqsim.process.fielddevelopment.wellplanning.WellboreThermalModel$FlowDirection")
    tm = jclass("WellboreThermalModel")()
    tm.setFlowDirection(getattr(FlowDir, direction))
    tm.setSurfaceTemperatureC(ts).setGeothermalGradient(grad).setTotalDepth(depths["tvd_m"]).setMassFlowRate(max(mass_kg_s, 0.05))
    tm.setInletTemperatureC(bottom_temperature_C if inlet_temperature_C is None else inlet_temperature_C)
    u = get_path(basis, "completion.overall_u_w_m2k")
    if u:
        tm.setOverallHeatTransferCoefficient(float(u))
    tm.setFlowingTimeDays(flowing_days)
    return tm


def flowline_back_pressure(basis: Dict[str, Any], fluid_template, mass_kg_s: float, host_pressure_bara: float, wellhead_temperature_C: float) -> Dict[str, float]:
    """Wellhead pressure needed to deliver ``mass_kg_s`` to the host boundary.

    Uses the NeqSim Beggs and Brill pipe on the supplied flowline description plus a supplied choke/valve
    pressure drop. Without a flowline description the host pressure plus the choke drop is returned.
    """
    fl = get_path(basis, "facility.flowline") or {}
    choke = float(get_path(basis, "facility.choke_dp_bar") or 0.0)
    if not fl or not fl.get("length_m"):
        return {"wellhead_pressure_bara": host_pressure_bara + choke, "flowline_dp_bar": 0.0, "choke_dp_bar": choke, "method": "host pressure + choke only"}
    require("PipeBeggsAndBrills")
    import jpype

    Stream = jpype.JClass("neqsim.process.equipment.stream.Stream")
    p_in = host_pressure_bara + 5.0
    dp = 0.0
    for _ in range(4):
        f = fluid_template.clone()
        f.setTemperature(273.15 + wellhead_temperature_C)
        f.setPressure(p_in)
        s = Stream("flowline-in", f)
        s.setFlowRate(float(mass_kg_s), "kg/sec")
        s.setTemperature(wellhead_temperature_C, "C")
        s.setPressure(p_in, "bara")
        s.run()
        pipe = jclass("PipeBeggsAndBrills")("flowline", s)
        pipe.setLength(float(fl["length_m"]))
        pipe.setDiameter(float(fl.get("id_m", 0.2)))
        pipe.setElevation(float(fl.get("elevation_change_m", 0.0)))
        pipe.setPipeWallRoughness(float(fl.get("roughness_m", 4.5e-5)))
        pipe.setNumberOfIncrements(int(fl.get("increments", 10)))
        pipe.setConstantSurfaceTemperature(float(fl.get("ambient_temperature_C", surface_temperature_C(basis))), "C")
        try:
            pipe.run()
        except Exception as exc:  # noqa: BLE001 - hydraulic domain errors mean the line cannot pass this rate
            return {"wellhead_pressure_bara": 4.0 * host_pressure_bara + choke, "flowline_dp_bar": 3.0 * host_pressure_bara, "choke_dp_bar": choke,
                    "method": "FLOWLINE_CANNOT_PASS_RATE (penalty applied): {}".format(str(exc)[:80])}
        p_out = float(pipe.getOutletStream().getPressure("bara"))
        dp = p_in - p_out
        new_in = host_pressure_bara + dp
        if abs(new_in - p_in) < 0.05:
            p_in = new_in
            break
        p_in = new_in
    return {"wellhead_pressure_bara": p_in + choke, "flowline_dp_bar": dp, "choke_dp_bar": choke,
            "method": "PipeBeggsAndBrills (fixed-point on inlet pressure) + supplied choke drop"}


def darcy_oil_pi_sm3d_per_bar(k_md: float, h_m: float, mu_cp: float, re_m: float, rw_m: float, skin: float, reservoir_m3_per_sm3: float) -> float:
    """Productivity index of a vertical well in pseudo-steady state (Sm3/d per bar, stock-tank basis)."""
    k = k_md * 9.869233e-16
    pi_m3s_per_pa = 2.0 * math.pi * k * h_m / (mu_cp * 1e-3 * (math.log(re_m / rw_m) - 0.75 + skin))
    return pi_m3s_per_pa * 1.0e5 * 86400.0 / reservoir_m3_per_sm3


def gas_injectivity_coefficient(k_md: float, h_m: float, mu_cp: float, z: float, t_k: float, re_m: float, rw_m: float, skin: float) -> float:
    """C in q_sc[Sm3/d] = C (pbh^2 - pres^2) with pressures in bar (radial, Darcy, pseudo-steady)."""
    k = k_md * 9.869233e-16
    t_sc, p_sc = 288.15, 101325.0
    c = math.pi * k * h_m * t_sc / (mu_cp * 1e-3 * z * t_k * p_sc * (math.log(re_m / rw_m) - 0.75 + skin))
    return c * (1.0e5 ** 2) * 86400.0
