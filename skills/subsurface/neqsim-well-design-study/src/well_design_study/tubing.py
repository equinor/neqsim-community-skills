"""Tubing and completion screening: erosional velocity, liquid-loading (Turner) and tubing size versus rate."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence

from .units import M_PER_IN

P_STD_BAR = 1.01325
T_STD_K = 288.15


def actual_velocity_ms(q_sm3d: float, p_bar: float, t_c: float, z: float, id_mm: float) -> float:
    """Gas velocity in a tube of internal diameter ``id_mm`` from standard rate ``q_sm3d`` at (p, T, z)."""
    q_act = q_sm3d / 86400.0 * (P_STD_BAR / p_bar) * ((t_c + 273.15) / T_STD_K) * z
    area = math.pi / 4.0 * (id_mm / 1000.0) ** 2
    return q_act / area


def erosional_velocity_ms(rho_mix_kg_m3: float, c_factor: float = 100.0) -> float:
    """API RP 14E erosional velocity Ve = C / sqrt(rho) with C in lb/(ft s2)^0.5 (100 continuous, up to 150 to 200 for CRA with sand-free service)."""
    rho_lb_ft3 = rho_mix_kg_m3 * 0.062428
    return c_factor / math.sqrt(rho_lb_ft3) * 0.3048


def turner_critical_velocity_ms(rho_gas_kg_m3: float, rho_liq_kg_m3: float, sigma_n_m: float = 0.02) -> float:
    """Turner liquid-droplet unloading velocity (m/s); multiply by 1.2 for the commonly used adjusted value."""
    sigma_dyn = sigma_n_m * 1000.0
    rg = rho_gas_kg_m3 * 0.062428
    rl = rho_liq_kg_m3 * 0.062428
    v_fts = 1.593 * sigma_dyn**0.25 * (rl - rg) ** 0.25 / math.sqrt(rg)
    return v_fts * 0.3048


def tubing_table(q_sm3d_list: Sequence[float], ids_mm: Sequence[float], p_bar: float, t_c: float, z: float,
                 rho_gas_kg_m3: float, rho_mix_kg_m3: float, rho_liq_kg_m3: float = 700.0, sigma_n_m: float = 0.02,
                 c_factor: float = 100.0) -> List[Dict[str, float]]:
    """Velocity, erosional ratio and Turner ratio for each (rate, tubing ID) at one pressure and temperature."""
    ve = erosional_velocity_ms(rho_mix_kg_m3, c_factor)
    vt = turner_critical_velocity_ms(rho_gas_kg_m3, rho_liq_kg_m3, sigma_n_m)
    rows = []
    for q in q_sm3d_list:
        for d in ids_mm:
            v = actual_velocity_ms(q, p_bar, t_c, z, d)
            rows.append({"q_sm3d": q, "id_mm": d, "velocity_ms": v, "erosional_ms": ve, "erosion_ratio": v / ve,
                         "turner_ms": vt, "turner_ratio": v / vt})
    return rows


def max_rate_for_erosion(id_mm: float, p_bar: float, t_c: float, z: float, rho_mix_kg_m3: float, c_factor: float = 100.0) -> float:
    """Largest standard rate (Sm3/d) that keeps velocity below the erosional velocity at the given conditions."""
    ve = erosional_velocity_ms(rho_mix_kg_m3, c_factor)
    area = math.pi / 4.0 * (id_mm / 1000.0) ** 2
    q_act = ve * area
    return q_act * 86400.0 / ((P_STD_BAR / p_bar) * ((t_c + 273.15) / T_STD_K) * z)


def shut_in_tubing_pressure_bar(reservoir_p_bar: float, tvd_m: float, gas_sg_gradient: float) -> float:
    """Shut-in tubing head pressure for a gas column of average gradient ``gas_sg_gradient`` (sg equivalent)."""
    return reservoir_p_bar - gas_sg_gradient * 0.0980665 * tvd_m
