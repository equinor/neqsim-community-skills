"""Screening hydraulics, thermal decay and DNV-ST-F101 wall thickness for a dry-oil export pipeline.

Everything here is analytical and dependency free so an agent can use it without a JVM. Results are
screening indicators: for a design basis re-run the chosen case in NeqSim ``PipeBeggsAndBrills`` with the
real fluid and the surveyed profile, and let qualified pipeline engineering review the wall thickness.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

G = 9.80665
RHO_SEAWATER = 1025.0
E_MOD_MPA = 207000.0
POISSON = 0.3

NPS_OD_M: dict[int, float] = {
    4: 0.1143, 6: 0.1683, 8: 0.2191, 10: 0.2731, 12: 0.3239, 14: 0.3556, 16: 0.4064, 18: 0.4572, 20: 0.5080,
    24: 0.6096,
}
STANDARD_WT_MM: Sequence[float] = (4.8, 5.6, 6.4, 7.1, 7.9, 8.7, 9.5, 10.3, 11.1, 12.7, 14.3, 15.9, 17.5, 19.1,
                                   22.2, 25.4)


@dataclass
class OilProperties:
    """Dry, stabilised crude properties needed for the screening.

    Attributes:
        std_density_kg_m3: density at 15 C and 1.01325 bara.
        viscosity_cp_inlet: dynamic viscosity at the inlet temperature in cP.
        viscosity_cp_sea: dynamic viscosity at the sea temperature in cP.
        cp_j_kgk: specific heat capacity.
        thermal_expansion_per_k: volumetric expansion coefficient used for density versus temperature.
    """

    std_density_kg_m3: float
    viscosity_cp_inlet: float
    viscosity_cp_sea: float
    cp_j_kgk: float = 2100.0
    thermal_expansion_per_k: float = 4.3e-4


@dataclass
class PipelineDesignBasis:
    """Design basis of the screening. All values are assumptions until replaced by project data."""

    length_m: float
    t_inlet_c: float = 50.0
    t_sea_c: float = 8.0
    arrival_pressure_barg: float = 10.0
    design_pressure_barg: float = 50.0
    corrosion_allowance_mm: float = 3.0
    roughness_mm: float = 0.045
    net_elevation_m: float = 0.0
    max_water_depth_m: float = 120.0
    riser_height_m: float = 140.0
    smys_mpa: float = 450.0
    smts_mpa: float = 535.0
    safety_class_factor: float = 1.138
    material_factor: float = 1.15
    fabrication_tolerance: float = 0.125
    alpha_u: float = 0.96
    alpha_fab: float = 0.93
    d_over_t_limit: float = 35.0
    operating_fraction_of_design: float = 0.9
    v_max_ms: float = 3.0
    v_min_ms: float = 0.3
    pump_efficiency: float = 0.70
    h_inner_w_m2k: float = 150.0
    h_outer_w_m2k: float = 300.0
    k_steel: float = 45.0
    coating_thickness_m: float = 0.003
    coating_k: float = 0.22
    insulation_thickness_m: float = 0.0
    insulation_k: float = 0.17
    standard_wt_mm: Sequence[float] = field(default_factory=lambda: tuple(STANDARD_WT_MM))


def overall_u(d_i: float, t_wall: float, basis: PipelineDesignBasis) -> float:
    """Overall heat-transfer coefficient referred to the inside area in W/(m2 K)."""
    r = d_i / 2.0
    layers = [(t_wall, basis.k_steel), (basis.coating_thickness_m, basis.coating_k)]
    if basis.insulation_thickness_m > 0:
        layers.append((basis.insulation_thickness_m, basis.insulation_k))
    res = 1.0 / basis.h_inner_w_m2k
    r_k = r
    for t, k in layers:
        res += r * math.log((r_k + t) / r_k) / k
        r_k += t
    res += r / (r_k * basis.h_outer_w_m2k)
    return 1.0 / res


def friction_factor(reynolds: float, rel_roughness: float) -> float:
    """Darcy friction factor: laminar 64/Re, Haaland above Re 4000, linear blend in between."""
    if reynolds <= 0:
        raise ValueError("Reynolds number must be positive")

    def haaland(re: float) -> float:
        inv = -1.8 * math.log10((rel_roughness / 3.7) ** 1.11 + 6.9 / re)
        return 1.0 / (inv * inv)

    if reynolds < 2300.0:
        return 64.0 / reynolds
    if reynolds < 4000.0:
        w = (reynolds - 2300.0) / 1700.0
        return (1.0 - w) * 64.0 / 2300.0 + w * haaland(4000.0)
    return haaland(reynolds)


def _viscosity_pa_s(props: OilProperties, t_c: float, basis: PipelineDesignBasis) -> float:
    mu1, mu2 = props.viscosity_cp_inlet, props.viscosity_cp_sea
    t1, t2 = basis.t_inlet_c, basis.t_sea_c
    if abs(t1 - t2) < 1e-9:
        return mu1 / 1000.0
    slope = (math.log(mu2) - math.log(mu1)) / (t2 - t1)
    return math.exp(math.log(mu1) + slope * (t_c - t1)) / 1000.0


def solve_hydraulics(q_sm3d: float, props: OilProperties, d_i_m: float, basis: PipelineDesignBasis,
                     u_w_m2k: float, steps: int = 200) -> dict[str, object]:
    """March along the pipe with temperature-dependent density and viscosity.

    Args:
        q_sm3d: stock-tank oil rate in Sm3/d.
        props: oil properties.
        d_i_m: inside diameter in metres.
        basis: design basis.
        u_w_m2k: overall heat-transfer coefficient referred to the inside area.
        steps: number of axial steps.

    Returns:
        Dictionary with inlet pressure (barg), friction and static pressure drop (bar), outlet temperature,
        velocity, Reynolds number at the outlet and axial profiles.
    """
    m_dot = q_sm3d * props.std_density_kg_m3 / 86400.0
    area = math.pi / 4.0 * d_i_m ** 2
    dx = basis.length_m / steps
    t = basis.t_inlet_c
    dp_fric = 0.0
    kp, temps, cum = [0.0], [t], [0.0]
    v_in = None
    re_out = 0.0
    v_out = 0.0
    rho_out = props.std_density_kg_m3
    for i in range(steps):
        rho = props.std_density_kg_m3 * (1.0 - props.thermal_expansion_per_k * (t - 15.0))
        mu = _viscosity_pa_s(props, t, basis)
        v = m_dot / (rho * area)
        re = rho * v * d_i_m / mu
        f = friction_factor(re, basis.roughness_mm / 1000.0 / d_i_m)
        dp_fric += f * dx / d_i_m * rho * v * v / 2.0
        decay = math.exp(-u_w_m2k * math.pi * d_i_m * dx / (m_dot * props.cp_j_kgk))
        t = basis.t_sea_c + (t - basis.t_sea_c) * decay
        kp.append((i + 1) * dx / 1000.0)
        temps.append(t)
        cum.append(dp_fric / 1e5)
        if v_in is None:
            v_in = v
        v_out, re_out, rho_out = v, re, rho
    dp_static = -rho_out * G * basis.net_elevation_m / 1e5
    p_in = basis.arrival_pressure_barg + dp_fric / 1e5 + dp_static
    return {
        "inlet_pressure_barg": p_in,
        "dp_friction_bar": dp_fric / 1e5,
        "dp_static_bar": dp_static,
        "t_out_c": t,
        "velocity_in_ms": v_in,
        "velocity_out_ms": v_out,
        "reynolds_out": re_out,
        "kp_km": kp,
        "temperature_c": temps,
        "cumulative_dp_bar": cum,
    }


def f101_checks(d_o_m: float, t_nom_m: float, basis: PipelineDesignBasis, rho_oil: float) -> dict[str, float]:
    """DNV-ST-F101 pressure containment and system collapse utilisation (hand calculation, screening).

    Pressure containment uses the incidental pressure 1.1 x design pressure at deck level and the local value
    at the seabed; collapse uses the external pressure at the deepest point with 0.5 % ovality.
    """
    t1 = t_nom_m * (1.0 - basis.fabrication_tolerance) - basis.corrosion_allowance_mm / 1000.0
    if t1 <= 0:
        return {"util_pressure": float("inf"), "util_collapse": float("inf"), "t1_mm": t1 * 1000.0,
                "d_over_t": d_o_m / t_nom_m}
    fy = basis.smys_mpa * basis.alpha_u
    fu = basis.smts_mpa * basis.alpha_u
    fcb = min(fy, fu / 1.15)
    p_b = 2.0 * t1 / (d_o_m - t1) * fcb * 2.0 / math.sqrt(3.0)
    gamma = basis.material_factor * basis.safety_class_factor
    p_inc = 1.1 * basis.design_pressure_barg / 10.0
    p_ext = RHO_SEAWATER * G * basis.max_water_depth_m / 1e6
    ref_h = basis.max_water_depth_m + (basis.riser_height_m - basis.max_water_depth_m)
    p_li_seabed = p_inc + rho_oil * G * ref_h / 1e6
    util_p = max(p_inc, p_li_seabed - p_ext) / (p_b / gamma)
    p_el = 2.0 * E_MOD_MPA * (t1 / d_o_m) ** 3 / (1.0 - POISSON ** 2)
    p_p = fy * basis.alpha_fab * 2.0 * t1 / d_o_m
    f0 = 0.005
    lo, hi = 1e-6, max(p_el, p_p) * 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if (mid - p_el) * (mid ** 2 - p_p ** 2) > mid * p_el * p_p * f0 * d_o_m / t1:
            hi = mid
        else:
            lo = mid
    p_c = 0.5 * (lo + hi)
    return {"t1_mm": t1 * 1000.0, "burst_mpa": p_b, "collapse_mpa": p_c, "util_pressure": util_p,
            "util_collapse": p_ext / (p_c / gamma), "d_over_t": d_o_m / t_nom_m}


def select_wall_thickness(d_o_m: float, basis: PipelineDesignBasis, rho_oil: float) -> dict[str, float]:
    """Smallest standard wall thickness that passes containment, collapse and the D/t handling limit."""
    for t_mm in basis.standard_wt_mm:
        c = f101_checks(d_o_m, t_mm / 1000.0, basis, rho_oil)
        if c["util_pressure"] <= 1.0 and c["util_collapse"] <= 1.0 and c["d_over_t"] <= basis.d_over_t_limit:
            c = dict(c)
            c["t_nom_mm"] = t_mm
            c["od_m"] = d_o_m
            c["id_m"] = d_o_m - 2.0 * t_mm / 1000.0
            c["steel_kg_per_m"] = math.pi * (d_o_m - t_mm / 1000.0) * t_mm / 1000.0 * 7850.0
            return c
    raise ValueError("no standard wall thickness satisfies the checks")


def size_pipeline(props: OilProperties, basis: PipelineDesignBasis, rates_sm3d: dict[str, float],
                  design_case: str, turndown_case: str, nps_list: Sequence[int] | None = None) -> dict[str, object]:
    """Sweep nominal sizes and recommend the smallest that meets the criteria at the design rate.

    Criteria: operating inlet pressure at the design rate below ``operating_fraction_of_design`` x design
    pressure, velocity at the design rate below ``v_max_ms`` and velocity at the turndown rate above
    ``v_min_ms``. The inlet pressure is what a new export pump must deliver at the source platform.

    Args:
        props: oil properties.
        basis: design basis.
        rates_sm3d: named rate cases in Sm3/d.
        design_case: key of the design rate in ``rates_sm3d``.
        turndown_case: key of the minimum rate in ``rates_sm3d``.
        nps_list: nominal sizes in inches; defaults to 8-20.

    Returns:
        Dictionary with ``wall``, ``cases`` and ``recommended`` (nominal size, or ``None`` with reasons).
    """
    sizes = list(nps_list or (8, 10, 12, 14, 16, 18, 20))
    wall: dict[int, dict[str, float]] = {}
    cases: list[dict[str, object]] = []
    for nps in sizes:
        w = select_wall_thickness(NPS_OD_M[nps], basis, props.std_density_kg_m3)
        wall[nps] = w
        u = overall_u(w["id_m"], w["t_nom_mm"] / 1000.0, basis)
        for name, q in rates_sm3d.items():
            h = solve_hydraulics(q, props, w["id_m"], basis, u)
            area = math.pi / 4.0 * w["id_m"] ** 2
            q_act = q * props.std_density_kg_m3 / 86400.0 / props.std_density_kg_m3
            cases.append({
                "nps": nps, "rate_case": name, "q_sm3d": q, "u_w_m2k": u,
                "inlet_pressure_barg": h["inlet_pressure_barg"], "dp_friction_bar": h["dp_friction_bar"],
                "t_out_c": h["t_out_c"], "velocity_ms": h["velocity_in_ms"], "reynolds_out": h["reynolds_out"],
                "pump_power_kw": q_act * h["dp_friction_bar"] * 1e5 / basis.pump_efficiency / 1000.0,
                "area_m2": area,
            })
    limit = basis.operating_fraction_of_design * basis.design_pressure_barg
    recommended: int | None = None
    reasons: dict[int, list[str]] = {}
    for nps in sizes:
        d = next(c for c in cases if c["nps"] == nps and c["rate_case"] == design_case)
        t = next(c for c in cases if c["nps"] == nps and c["rate_case"] == turndown_case)
        why = []
        if d["inlet_pressure_barg"] > limit:
            why.append(f"inlet {d['inlet_pressure_barg']:.0f} barg > {limit:.0f} barg")
        if d["velocity_ms"] > basis.v_max_ms:
            why.append(f"velocity {d['velocity_ms']:.2f} m/s > {basis.v_max_ms} m/s")
        if t["velocity_ms"] < basis.v_min_ms:
            why.append(f"turndown velocity {t['velocity_ms']:.2f} m/s < {basis.v_min_ms} m/s")
        reasons[nps] = why
        if not why and recommended is None:
            recommended = nps
    return {"wall": wall, "cases": cases, "recommended": recommended, "rejection_reasons": reasons,
            "operating_pressure_limit_barg": limit}
