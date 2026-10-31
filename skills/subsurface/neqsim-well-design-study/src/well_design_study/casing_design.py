"""Casing and tubing design: API TR 5C3 / ISO 10400 ratings, load cases, triaxial (von Mises) check, string selection.

Screening level. Design factors are operator-practice defaults, not code values: NORSOK D-010 requires documented
design factors and a verified standard-conform load basis, so every result is labelled NEEDS_REVIEW.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .units import (BAR_PER_PSI, BAR_PER_SG_M, KN_PER_KLBF, M_PER_IN, STEEL_E_GPA, STEEL_NU, STEEL_ALPHA, bar_to_psi, psi_to_bar)


@dataclass(frozen=True)
class Grade:
    """Steel grade with specified minimum yield and tensile strength (ksi) and a linear yield derating per kelvin."""

    name: str
    smys_ksi: float
    smts_ksi: float
    derate_per_k: float = 0.0005
    cra: bool = False


GRADES: Dict[str, Grade] = {
    g.name: g
    for g in (
        Grade("X56", 56.0, 71.0),
        Grade("J55", 55.0, 75.0),
        Grade("K55", 55.0, 95.0),
        Grade("L80", 80.0, 95.0),
        Grade("N80", 80.0, 100.0),
        Grade("C90", 90.0, 100.0),
        Grade("T95", 95.0, 105.0),
        Grade("P110", 110.0, 125.0),
        Grade("Q125", 125.0, 135.0),
        Grade("13Cr-L80", 80.0, 95.0, 0.0007, True),
        Grade("13Cr-95", 95.0, 105.0, 0.0007, True),
        Grade("S13Cr-110", 110.0, 125.0, 0.0007, True),
    )
}

# Nominal OD (in) -> wall thicknesses (in). Screening catalogue of common API 5CT sizes; confirm against the vendor
# pipe list before use. Plain-end weight is computed as 10.69 (OD - t) t lb/ft.
CATALOG: Dict[float, List[float]] = {
    36.0: [1.0, 1.25, 1.5],
    30.0: [1.0, 1.25],
    20.0: [0.438, 0.5, 0.635],
    18.625: [0.435, 0.5, 0.625],
    17.0: [0.435, 0.5, 0.55],
    16.0: [0.375, 0.438, 0.495, 0.655],
    13.625: [0.48, 0.55, 0.625, 0.72],
    13.375: [0.38, 0.43, 0.48, 0.514, 0.55, 0.58, 0.608],
    11.75: [0.375, 0.435, 0.489, 0.582],
    10.75: [0.35, 0.4, 0.45, 0.495, 0.545, 0.595, 0.672, 0.734],
    9.875: [0.545, 0.625, 0.689],
    9.625: [0.352, 0.395, 0.435, 0.472, 0.545, 0.595, 0.625, 0.672, 0.72],
    7.625: [0.375, 0.43, 0.5, 0.595, 0.625],
    7.0: [0.317, 0.362, 0.408, 0.453, 0.498, 0.54, 0.592, 0.65],
    5.5: [0.304, 0.361, 0.415, 0.476],
    4.5: [0.271, 0.337, 0.43],
    5.0: [0.296, 0.362, 0.408, 0.478],
    3.5: [0.254, 0.289, 0.368],
}


def plain_end_weight_lbft(od_in: float, wall_in: float) -> float:
    """Plain-end weight (lb/ft) of steel pipe."""
    return 10.69 * (od_in - wall_in) * wall_in


def yield_psi(grade: Grade, temp_c: float = 20.0) -> float:
    """Derated minimum yield strength in psi at ``temp_c``."""
    f = 1.0 - grade.derate_per_k * max(0.0, temp_c - 20.0)
    return grade.smys_ksi * 1000.0 * f


def _api_collapse_coefficients(yp: float) -> Tuple[float, float, float, float, float]:
    a = 2.8762 + 0.10679e-5 * yp + 0.21301e-10 * yp**2 - 0.53132e-16 * yp**3
    b = 0.026233 + 0.50609e-6 * yp
    c = -465.93 + 0.030867 * yp - 0.10483e-7 * yp**2 + 0.36989e-13 * yp**3
    ba = b / a
    x = (3.0 * ba) / (2.0 + ba)
    f = 46.95e6 * x**3 / (yp * (x - ba) * (1.0 - x) ** 2)
    g = f * ba
    return a, b, c, f, g


def collapse_rating_psi(od_in: float, wall_in: float, yp_psi: float) -> float:
    """API 5C3 / TR 5C3 collapse pressure rating (yield, plastic, transition or elastic regime)."""
    dt = od_in / wall_in
    a, b, c, f, g = _api_collapse_coefficients(yp_psi)
    bc = b + c / yp_psi
    d_yield = (math.sqrt((a - 2.0) ** 2 + 8.0 * bc) + (a - 2.0)) / (2.0 * bc)
    d_plastic = yp_psi * (a - f) / (c + yp_psi * (b - g))
    d_trans = (2.0 + b / a) / (3.0 * b / a)
    if dt <= d_yield:
        return 2.0 * yp_psi * (dt - 1.0) / dt**2
    if dt <= d_plastic:
        return yp_psi * (a / dt - b) - c
    if dt <= d_trans:
        return yp_psi * (f / dt - g)
    return 46.95e6 / (dt * (dt - 1.0) ** 2)


def burst_rating_psi(od_in: float, wall_in: float, yp_psi: float) -> float:
    """API 5C3 internal yield pressure (Barlow with 12.5 percent wall tolerance)."""
    return 0.875 * 2.0 * yp_psi * wall_in / od_in


def body_yield_kn(od_in: float, wall_in: float, yp_psi: float) -> float:
    """Pipe-body yield strength in kN."""
    area_in2 = math.pi / 4.0 * (od_in**2 - (od_in - 2.0 * wall_in) ** 2)
    return yp_psi * area_in2 / 1000.0 * KN_PER_KLBF


@dataclass
class Pipe:
    """A candidate pipe: OD, wall, grade."""

    od_in: float
    wall_in: float
    grade: str

    @property
    def id_in(self) -> float:
        return self.od_in - 2.0 * self.wall_in

    @property
    def weight_lbft(self) -> float:
        return plain_end_weight_lbft(self.od_in, self.wall_in)

    @property
    def weight_kg_per_m(self) -> float:
        return self.weight_lbft * 1.48816

    def label(self) -> str:
        return f'{self.od_in:g}" {self.weight_lbft:.1f} ppf {self.grade} (t={self.wall_in:.3f} in)'

    def ratings(self, temp_c: float = 20.0) -> Dict[str, float]:
        """Rated collapse, burst (bar) and body yield (kN), derated to ``temp_c``."""
        yp = yield_psi(GRADES[self.grade], temp_c)
        return {
            "collapse_bar": psi_to_bar(collapse_rating_psi(self.od_in, self.wall_in, yp)),
            "burst_bar": psi_to_bar(burst_rating_psi(self.od_in, self.wall_in, yp)),
            "body_yield_kn": body_yield_kn(self.od_in, self.wall_in, yp),
            "yield_psi": yp,
        }


def candidates(od_in: float, grades: Sequence[str]) -> List[Pipe]:
    """All catalogue pipes of an OD for the listed grades, lightest first."""
    walls = CATALOG.get(od_in)
    if walls is None:
        raise KeyError(f"OD {od_in} in is not in the screening catalogue")
    pipes = [Pipe(od_in, t, g) for t in walls for g in grades]
    return sorted(pipes, key=lambda p: (p.weight_lbft, GRADES[p.grade].smys_ksi))


@dataclass
class DesignFactors:
    """Minimum design factors (operator-practice defaults, NEEDS_REVIEW against the governing company requirement)."""

    burst: float = 1.10
    collapse: float = 1.00
    tension: float = 1.60
    triaxial: float = 1.25


@dataclass
class StringBasis:
    """Basis for one casing string. All depths TVD below RKB unless marked MD.

    Vertical or near-vertical wells only (TVD = MD along the string unless ``shoe_md_m`` differs, in which case the
    axial weight uses MD and pressures use TVD).
    """

    name: str
    od_in: float
    top_tvd_m: float
    shoe_tvd_m: float
    shoe_md_m: float
    toc_tvd_m: float
    mud_sg: float
    next_td_tvd_m: float
    next_mud_sg: float
    next_pore_sg: float
    frac_shoe_sg: float
    pore_sg_at: Optional[callable] = None
    gas_sg: float = 0.25
    kick_intensity_sg: float = 0.06
    packer_fluid_sg: float = 1.20
    shut_in_wellhead_bar: Optional[float] = None
    test_pressure_bar: Optional[float] = None
    evacuation_fraction: float = 0.5
    evacuation_basis: str = "fraction"  # "fraction" (fixed share of the string evacuated) or "pore_balance" (loss of returns to pore balance)
    evacuation_external: str = "mud_or_pore"  # external load in the evacuation case: higher of mud column and pore (legacy), or "set_cement" (pore below the cement top)
    cement_sg: float = 1.90
    water_depth_m: float = 0.0
    air_gap_m: float = 0.0
    sea_sg: float = 1.03
    max_temp_c: float = 20.0
    overpull_kn: float = 400.0
    ext_pore_case_sg: Optional[float] = None
    cap_gas_at_frac: bool = True


def _external_bar(basis: StringBasis, z: float) -> float:
    ml = basis.water_depth_m + basis.air_gap_m
    if z <= ml:
        return basis.sea_sg * BAR_PER_SG_M * max(0.0, z - basis.air_gap_m)
    p_ml = basis.sea_sg * BAR_PER_SG_M * basis.water_depth_m
    if z < basis.toc_tvd_m:
        return p_ml + basis.mud_sg * BAR_PER_SG_M * (z - ml)
    pore = basis.pore_sg_at(z) if basis.pore_sg_at else (basis.ext_pore_case_sg or basis.mud_sg)
    return pore * BAR_PER_SG_M * z


def load_cases(basis: StringBasis, n: int = 41) -> Dict[str, Dict[str, np.ndarray]]:
    """Internal and external pressure (bar) at ``n`` nodes for each load case, plus node depths.

    Cases: ``gas_kick`` (gas to surface after a kick, capped at the shoe fracture pressure), ``tubing_leak``
    (shut-in tubing pressure over packer fluid), ``pressure_test`` (test pressure over mud) and ``evacuation``
    (partial or full loss of internal fluid with the mud outside).
    """
    ml = basis.water_depth_m + basis.air_gap_m
    top = max(basis.top_tvd_m, ml)
    z = np.linspace(top, basis.shoe_tvd_m, n)
    g = BAR_PER_SG_M
    pext = np.array([_external_bar(basis, float(zz)) for zz in z])
    p_wh_sea = basis.sea_sg * g * basis.water_depth_m
    cases: Dict[str, Dict[str, np.ndarray]] = {}

    p_form = (basis.next_mud_sg + basis.kick_intensity_sg) * g * basis.next_td_tvd_m
    p_shoe_gas = p_form - basis.gas_sg * g * (basis.next_td_tvd_m - basis.shoe_tvd_m)
    if basis.cap_gas_at_frac:
        p_shoe_gas = min(p_shoe_gas, basis.frac_shoe_sg * g * basis.shoe_tvd_m)
    pi_gas = p_shoe_gas - basis.gas_sg * g * (basis.shoe_tvd_m - z)
    cases["gas_kick"] = {"z": z, "pi": pi_gas, "po": pext}

    if basis.shut_in_wellhead_bar is not None:
        pi_leak = p_wh_sea + basis.shut_in_wellhead_bar + basis.packer_fluid_sg * g * (z - ml)
        cases["tubing_leak"] = {"z": z, "pi": pi_leak, "po": pext}

    if basis.test_pressure_bar is not None:
        pi_test = p_wh_sea + basis.test_pressure_bar + basis.mud_sg * g * (z - ml)
        cases["pressure_test"] = {"z": z, "pi": pi_test, "po": pext}

    z_evac = ml + basis.evacuation_fraction * (basis.shoe_tvd_m - ml)
    if basis.evacuation_basis == "pore_balance" and basis.pore_sg_at is not None:
        # loss of returns: the fluid level falls until the internal hydrostatic head balances the pore pressure at the shoe
        pore_shoe_bar = basis.pore_sg_at(basis.shoe_tvd_m) * g * basis.shoe_tvd_m
        z_evac = max(ml, basis.shoe_tvd_m - pore_shoe_bar / (basis.next_mud_sg * g))
    pi_evac = np.where(z > z_evac, basis.next_mud_sg * g * (z - z_evac), 0.0)
    pext_run = np.array([max(basis.mud_sg * g * (zz - ml) + p_wh_sea, _external_bar(basis, float(zz))) for zz in z])
    if basis.evacuation_external == "set_cement":
        pext_run = pext
    cases["evacuation"] = {"z": z, "pi": pi_evac, "po": pext_run}
    return cases


def vme_stress_ratio(pipe: Pipe, pi_bar: float, po_bar: float, axial_eff_kn: float, temp_c: float) -> float:
    """Triaxial design factor: derated yield over von Mises equivalent stress, worst of inner and outer wall.

    ``axial_eff_kn`` is the effective (pressure-corrected) axial force; the true wall force adds Pi Ai - Po Ao.
    """
    ro = pipe.od_in * M_PER_IN / 2.0
    ri = pipe.id_in * M_PER_IN / 2.0
    ai, ao = math.pi * ri**2, math.pi * ro**2
    area = ao - ai
    pi, po = pi_bar * 1e5, po_bar * 1e5
    f_true = axial_eff_kn * 1e3 + pi * ai - po * ao
    sa = f_true / area
    st_in = (pi * (ri**2 + ro**2) - 2.0 * po * ro**2) / (ro**2 - ri**2)
    st_out = (2.0 * pi * ri**2 - po * (ri**2 + ro**2)) / (ro**2 - ri**2)
    best = 0.0
    for st, sr in ((st_in, -pi), (st_out, -po)):
        vme = math.sqrt(0.5 * ((sa - st) ** 2 + (st - sr) ** 2 + (sr - sa) ** 2))
        best = max(best, vme)
    yp_pa = yield_psi(GRADES[pipe.grade], 20.0) * BAR_PER_PSI * 1e5
    return yp_pa / best if best > 0 else float("inf")


def check_string(pipe: Pipe, basis: StringBasis, df: DesignFactors = DesignFactors(), n: int = 41) -> Dict[str, object]:
    """Design factors of one pipe for a string basis. Returns the minimum factor of each check and the governing case."""
    r = pipe.ratings(basis.max_temp_c)
    cases = load_cases(basis, n)
    out: Dict[str, object] = {"pipe": pipe.label(), "ratings": r}
    burst_min, collapse_min = (float("inf"), ""), (float("inf"), "")
    tri_min = (float("inf"), "")
    w_buoy = pipe.weight_kg_per_m * 9.80665 / 1000.0 * (1.0 - basis.mud_sg * 1000.0 / 7850.0)  # kN per m
    md_per_tvd = basis.shoe_md_m / basis.shoe_tvd_m if basis.shoe_tvd_m > 0 else 1.0
    ml = basis.water_depth_m + basis.air_gap_m
    for name, c in cases.items():
        z, pi, po = c["z"], c["pi"], c["po"]
        net_burst = pi - po
        net_coll = po - pi
        if np.max(net_burst) > 0:
            d = r["burst_bar"] / float(np.max(net_burst))
            if d < burst_min[0]:
                burst_min = (d, name)
        if np.max(net_coll) > 0:
            idx = int(np.argmax(net_coll))
            # biaxial correction of collapse resistance for axial tension (API TR 5C3 ellipse approximation)
            ax_eff = max(0.0, (basis.shoe_tvd_m - z[idx]) * md_per_tvd * w_buoy)
            sa_ratio = (ax_eff * 1e3 / (math.pi / 4 * ((pipe.od_in * M_PER_IN) ** 2 - (pipe.id_in * M_PER_IN) ** 2))) / (r["yield_psi"] * BAR_PER_PSI * 1e5)
            corr = math.sqrt(max(0.0, 1.0 - 0.75 * sa_ratio**2)) - 0.5 * sa_ratio
            d = r["collapse_bar"] * max(0.1, corr) / float(np.max(net_coll))
            if d < collapse_min[0]:
                collapse_min = (d, name)
        for k in range(0, len(z), max(1, len(z) // 8)):
            ax = max(0.0, (basis.shoe_tvd_m - z[k]) * md_per_tvd * w_buoy)
            if name == "pressure_test":
                ax += 0.0
            ratio = vme_stress_ratio(pipe, float(pi[k]), float(po[k]), ax, basis.max_temp_c)
            ratio *= 1.0 - GRADES[pipe.grade].derate_per_k * max(0.0, basis.max_temp_c - 20.0)
            if ratio < tri_min[0]:
                tri_min = (ratio, f"{name}@{z[k]:.0f}m")
    top_md = max(basis.top_tvd_m, ml) * md_per_tvd
    hang = (basis.shoe_md_m - top_md) * w_buoy + basis.overpull_kn
    tension_df = r["body_yield_kn"] / hang if hang > 0 else float("inf")
    out.update({
        "burst_df": float(burst_min[0]), "burst_case": burst_min[1],
        "collapse_df": float(collapse_min[0]), "collapse_case": collapse_min[1],
        "tension_df": float(tension_df), "tension_load_kn": hang,
        "triaxial_df": float(tri_min[0]), "triaxial_case": tri_min[1],
        "passes": bool(burst_min[0] >= df.burst and collapse_min[0] >= df.collapse and tension_df >= df.tension and tri_min[0] >= df.triaxial),
        "weight_kg_per_m": pipe.weight_kg_per_m,
        "string_weight_t": pipe.weight_kg_per_m * (basis.shoe_md_m - top_md) / 1000.0,
    })
    return out


def select_string(basis: StringBasis, grades: Sequence[str], df: DesignFactors = DesignFactors(), n: int = 41) -> Dict[str, object]:
    """Lightest catalogue pipe of ``basis.od_in`` and the listed grades that passes all design factors.

    Returns the selection and the full ranked candidate table for traceability.
    """
    table: List[Dict[str, object]] = []
    chosen: Optional[Dict[str, object]] = None
    for pipe in candidates(basis.od_in, grades):
        res = check_string(pipe, basis, df, n)
        table.append(res)
        if res["passes"] and chosen is None:
            chosen = res
    return {"string": basis.name, "od_in": basis.od_in, "selected": chosen, "candidates": table,
            "status": "SELECTED" if chosen else "NO_CATALOGUE_PIPE_PASSES"}


def check_tubing(pipe: Pipe, mudline_tvd_m: float, packer_tvd_m: float, water_depth_m: float, shut_in_wellhead_bar: float, gas_gradient_bar_per_m: float,
                 annulus_sg: float = 1.20, annulus_head_bar: float = 0.0, max_temp_c: float = 20.0, overpull_kn: float = 200.0,
                 df: DesignFactors = DesignFactors(), sea_sg: float = 1.03, n: int = 41) -> Dict[str, object]:
    """Design factors of a production tubing string with annulus fluid outside (hanger at the mudline, packer at ``packer_tvd_m``).

    Load cases: ``shut_in`` (gas to the tree, annulus fluid and applied annulus head outside) and ``evacuated`` (empty tubing, annulus
    fluid outside; collapse). Pressures are absolute; ``shut_in_wellhead_bar`` and ``annulus_head_bar`` are gauge values at the
    mudline (subsea tree). Triaxial factors use the effective axial force of the free-hanging string. Screening only: no packer
    movement, ballooning, thermal growth or erosion allowance is included.

    Returns:
        Dict with ``burst_df``, ``collapse_df``, ``tension_df``, ``triaxial_df``, the governing cases, ratings and ``passes``.
    """
    g = BAR_PER_SG_M
    z = np.linspace(mudline_tvd_m, packer_tvd_m, n)
    p_sea = sea_sg * g * water_depth_m
    po = p_sea + annulus_head_bar + annulus_sg * g * (z - mudline_tvd_m)
    cases = {
        "shut_in": p_sea + shut_in_wellhead_bar + gas_gradient_bar_per_m * (z - mudline_tvd_m),
        "evacuated": np.full_like(z, p_sea),
    }
    r = pipe.ratings(max_temp_c)
    w_buoy = pipe.weight_kg_per_m * 9.80665 / 1000.0 * (1.0 - annulus_sg * 1000.0 / 7850.0)
    burst = (float("inf"), "")
    collapse = (float("inf"), "")
    tri = (float("inf"), "")
    for name, pi in cases.items():
        nb = float(np.max(pi - po))
        nc = float(np.max(po - pi))
        if nb > 0.0 and r["burst_bar"] / nb < burst[0]:
            burst = (r["burst_bar"] / nb, name)
        if nc > 0.0 and r["collapse_bar"] / nc < collapse[0]:
            collapse = (r["collapse_bar"] / nc, name)
        for k in (0, len(z) // 2, len(z) - 1):
            ax = max(0.0, (packer_tvd_m - z[k]) * w_buoy)
            ratio = vme_stress_ratio(pipe, float(pi[k]), float(po[k]), ax, max_temp_c)
            ratio *= 1.0 - GRADES[pipe.grade].derate_per_k * max(0.0, max_temp_c - 20.0)
            if ratio < tri[0]:
                tri = (ratio, f"{name}@{z[k]:.0f}m")
    hang = (packer_tvd_m - mudline_tvd_m) * w_buoy + overpull_kn
    tension = r["body_yield_kn"] / hang if hang > 0.0 else float("inf")
    return {"pipe": pipe.label(), "ratings": r, "burst_df": float(burst[0]), "burst_case": burst[1], "collapse_df": float(collapse[0]),
            "collapse_case": collapse[1], "tension_df": float(tension), "tension_load_kn": hang, "triaxial_df": float(tri[0]), "triaxial_case": tri[1],
            "passes": bool(burst[0] >= df.burst and collapse[0] >= df.collapse and tension >= df.tension and tri[0] >= df.triaxial)}


def thermal_axial_force_kn(pipe: Pipe, delta_t_k: float) -> float:
    """Axial force (kN, compressive positive) of a fully restrained pipe heated by ``delta_t_k``."""
    area = math.pi / 4.0 * ((pipe.od_in * M_PER_IN) ** 2 - (pipe.id_in * M_PER_IN) ** 2)
    return STEEL_E_GPA * 1e9 * STEEL_ALPHA * delta_t_k * area / 1e3


def wellhead_rating_class(max_pressure_bar: float, classes_psi: Sequence[float] = (5000.0, 10000.0, 15000.0, 20000.0), margin: float = 1.0) -> Dict[str, float]:
    """Smallest API 6A pressure class (psi, bar) covering ``max_pressure_bar * margin``."""
    need = max_pressure_bar * margin
    for c in classes_psi:
        if psi_to_bar(c) >= need:
            return {"class_psi": c, "class_bar": psi_to_bar(c), "utilisation": need / psi_to_bar(c)}
    return {"class_psi": float("nan"), "class_bar": float("nan"), "utilisation": float("nan")}
