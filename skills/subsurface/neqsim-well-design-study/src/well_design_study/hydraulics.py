"""Annular and pipe pressure loss (Bingham plastic, API RP 13D style), ECD, bit hydraulics and hole-cleaning velocity."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .units import BAR_PER_SG_M, M_PER_IN

PSI_PER_FT_TO_PA_PER_M = 22620.6


@dataclass
class MudRheology:
    """Bingham-plastic mud: density (sg), plastic viscosity (cP) and yield point (lbf per 100 ft2)."""

    sg: float
    pv_cp: float
    yp_lb100: float


@dataclass
class FlowSection:
    """A flow path segment. ``pipe_od_in`` is the inner body of the annulus; ``pipe_id_in`` the bore of the pipe."""

    name: str
    pipe_od_in: float
    pipe_id_in: float
    hole_in: float
    length_md_m: float
    tvd_per_md: float = 1.0


def _loss_pa_per_m(mud: MudRheology, q_m3s: float, d_hyd_in: float, area_m2: float, annulus: bool) -> float:
    v = q_m3s / area_m2
    v_fpm = v * 196.85
    lam = mud.pv_cp * v_fpm / ((60000.0 if annulus else 90000.0) * d_hyd_in**2)
    lam += mud.yp_lb100 / ((200.0 if annulus else 225.0) * d_hyd_in)
    lam *= PSI_PER_FT_TO_PA_PER_M
    d = d_hyd_in * M_PER_IN
    rho = mud.sg * 1000.0
    mu = max(1e-4, mud.pv_cp * 1e-3)
    re = rho * v * d / mu
    f = 0.0791 / max(re, 1.0) ** 0.25
    turb = 2.0 * f * rho * v**2 / d
    return max(lam, turb)


def circulation(sections: Sequence[FlowSection], mud: MudRheology, flow_lpm: float, nozzle_tfa_in2: float = 0.6, pump_limit_bar: float = 345.0) -> Dict[str, object]:
    """Pressure losses, ECD profile and pump pressure for one flow rate.

    Sections are ordered from the surface downward. The annulus sections carry the return flow upward; the ECD at the
    bottom of a section adds the annular loss above that depth to the static mud weight.
    """
    q = flow_lpm / 1000.0 / 60.0
    dp_pipe = 0.0
    ann_dp_each: List[float] = []
    for s in sections:
        area_p = math.pi / 4.0 * (s.pipe_id_in * M_PER_IN) ** 2
        dp_pipe += _loss_pa_per_m(mud, q, s.pipe_id_in, area_p, False) * s.length_md_m / 1e5
        area_a = math.pi / 4.0 * ((s.hole_in * M_PER_IN) ** 2 - (s.pipe_od_in * M_PER_IN) ** 2)
        ann_dp_each.append(_loss_pa_per_m(mud, q, s.hole_in - s.pipe_od_in, area_a, True) * s.length_md_m / 1e5)
    tfa_m2 = nozzle_tfa_in2 * M_PER_IN**2
    dp_bit = (mud.sg * 1000.0) * q**2 / (2.0 * 0.95**2 * tfa_m2**2) / 1e5
    tvd = 0.0
    ecd_rows = []
    cum = 0.0
    for s, dpa in zip(sections, ann_dp_each):
        tvd += s.length_md_m * s.tvd_per_md
        cum += dpa
        ecd_rows.append({"section": s.name, "bottom_tvd_m": tvd, "annulus_dp_bar": dpa,
                         "ecd_sg": mud.sg + cum / (BAR_PER_SG_M * tvd) if tvd > 0 else mud.sg,
                         "annular_velocity_ms": q / (math.pi / 4.0 * ((s.hole_in * M_PER_IN) ** 2 - (s.pipe_od_in * M_PER_IN) ** 2))})
    total = dp_pipe + dp_bit + sum(ann_dp_each)
    return {"flow_lpm": flow_lpm, "pipe_dp_bar": dp_pipe, "bit_dp_bar": dp_bit, "annulus_dp_bar": sum(ann_dp_each),
            "pump_pressure_bar": total, "pump_ok": bool(total <= pump_limit_bar), "ecd_rows": ecd_rows,
            "ecd_bottom_sg": ecd_rows[-1]["ecd_sg"] if ecd_rows else mud.sg}


def flow_sweep(sections: Sequence[FlowSection], mud: MudRheology, flows_lpm: Sequence[float], **kw) -> List[Dict[str, object]]:
    """Circulation results for several flow rates."""
    return [circulation(sections, mud, q, **kw) for q in flows_lpm]
