"""Kick tolerance, casing-seat evaluation of a planned programme and bottom-up seat proposal."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .pressure import PressureModel
from .units import BAR_PER_SG_M, M_PER_IN

RISERLESS_SEA_SG = 1.03  # seawater density above the seabed in riserless sections


def annulus_capacity_m3_per_m(hole_in: float, pipe_od_in: float) -> float:
    """Annular capacity (m3 per m) between a hole and a pipe."""
    return math.pi / 4.0 * ((hole_in * M_PER_IN) ** 2 - (pipe_od_in * M_PER_IN) ** 2)


def kick_tolerance(
    shoe_tvd_m: float,
    next_td_tvd_m: float,
    mud_sg: float,
    frac_shoe_sg: float,
    ann_cap_m3pm: float,
    kick_intensity_sg: float = 0.06,
    influx_sg: float = 0.25,
    formation_sg: Optional[float] = None,
) -> Dict[str, float]:
    """Single-bubble gas kick tolerance at a casing shoe, well shut in.

    The formation pressure at ``next_td_tvd_m`` is ``(mud_sg + kick_intensity_sg)`` hydrostatic. The influx of
    height h sits at the bottom, mud fills the annulus above it and the pressure at the shoe must stay below the
    fracture pressure at the shoe. Solves h from the shoe pressure balance and returns the tolerable influx volume.

    Args:
        shoe_tvd_m: shoe depth (TVD RKB).
        next_td_tvd_m: depth of the next section (TVD RKB).
        mud_sg: mud weight in the next section.
        frac_shoe_sg: fracture or LOT EMW at the shoe (use the low case).
        ann_cap_m3pm: annular capacity of the open hole over the influx.
        kick_intensity_sg: overpressure of the kick over the mud weight in sg.
        influx_sg: influx density in sg at the conditions of the kick (about 0.2 to 0.3 for gas).
        formation_sg: formation pressure EMW at ``next_td_tvd_m``; replaces ``mud_sg + kick_intensity_sg`` when given.

    Returns:
        Dict with h_max_m, volume_m3, volume_bbl, shoe_pressure_margin_bar and a flag ``ok_to_shut_in``.
    """
    if next_td_tvd_m <= shoe_tvd_m:
        raise ValueError("next_td_tvd_m must be below shoe_tvd_m")
    g = BAR_PER_SG_M
    p_form = (formation_sg if formation_sg is not None else mud_sg + kick_intensity_sg) * g * next_td_tvd_m
    p_frac = frac_shoe_sg * g * shoe_tvd_m
    open_len = next_td_tvd_m - shoe_tvd_m
    p_shoe_no_influx = p_form - mud_sg * g * open_len
    margin0 = p_frac - p_shoe_no_influx
    denom = (mud_sg - influx_sg) * g
    h_max = margin0 / denom if denom > 0 else 0.0
    ok = margin0 > 0.0
    h_max = max(0.0, min(h_max, open_len))
    vol = h_max * ann_cap_m3pm
    return {
        "h_max_m": h_max,
        "volume_m3": vol,
        "volume_bbl": vol * 6.28981,
        "shoe_pressure_margin_bar": margin0,
        "ok_to_shut_in": ok,
        "formation_pressure_bar": p_form,
        "frac_shoe_bar": p_frac,
    }


@dataclass
class PlannedSection:
    """A planned hole section. ``shoe_*`` refer to the casing set at the bottom of the section."""

    name: str
    hole_in: float
    casing_od_in: float
    top_tvd_m: float
    shoe_tvd_m: float
    shoe_md_m: float
    mud_sg: float
    drill_pipe_od_in: float = 5.5
    riserless: bool = False
    strength_at_top_sg: Optional[float] = None
    open_hole: bool = False


def evaluate_plan(
    model: PressureModel,
    sections: Sequence[PlannedSection],
    kick_intensity_sg: float = 0.06,
    influx_sg: float = 0.25,
    kt_min_m3: float = 8.0,
    pore_case: str = "high",
    frac_case: str = "low",
    trip_margin_sg: float = 0.04,
    frac_margin_sg: float = 0.03,
    step_m: float = 10.0,
    kick_basis: str = "mud",
) -> List[Dict[str, object]]:
    """Check each planned section against the mud-weight window and kick tolerance.

    Each section is drilled with the mud weight ``mud_sg``; it passes the window check if ``mud_sg`` stays within
    [pore + trip margin, frac - frac margin] over the open-hole interval. The kick tolerance is evaluated at the
    top of the section (shoe of the casing above) against the bottom of the section.

    ``kick_basis`` selects the kick convention: ``"mud"`` (formation pressure = planned mud + kick intensity, the legacy
    and most conservative choice when the mud is far above pore pressure) or ``"pore"`` (formation pressure = the
    ``pore_case`` pore EMW at the section bottom + kick intensity, with the annulus mud limited to pore + trip margin).
    Sections flagged ``riserless`` get no kick tolerance (no shut-in is possible), and ``strength_at_top_sg`` replaces the
    model fracture EMW at the shoe when a planned or measured leak-off value must be checked.
    """
    out: List[Dict[str, object]] = []
    prev_shoe: Optional[float] = None
    for s in sections:
        top = s.top_tvd_m if prev_shoe is None else prev_shoe
        n = max(2, int((s.shoe_tvd_m - top) / step_m) + 1)
        depths = [top + (s.shoe_tvd_m - top) * i / (n - 1) for i in range(n)]
        win = [model.window(d, pore_case, frac_case, 0.0 if s.riserless else trip_margin_sg, 0.0 if s.riserless else frac_margin_sg) for d in depths]
        if s.riserless:
            # no riser: the mud column starts at the seabed and the seawater column above it carries the rest of the hydrostatic head
            ml, wd = model.mudline_tvd_m, model.water_depth_m
            keep = [i for i, d in enumerate(depths) if d - ml >= 20.0] or list(range(len(depths)))
            depths = [depths[i] for i in keep]
            win = [win[i] for i in keep]
            for w, d in zip(win, depths):
                for key in ("min_mw_sg", "max_mw_sg"):
                    w[key] = (w[key] * d - RISERLESS_SEA_SG * wd) / max(d - ml, 1.0)
        need = max(w["min_mw_sg"] for w in win)
        cap = min(w["max_mw_sg"] for w in win)
        i_need = max(range(len(win)), key=lambda i: win[i]["min_mw_sg"])
        i_cap = min(range(len(win)), key=lambda i: win[i]["max_mw_sg"])
        row: Dict[str, object] = {
            "section": s.name,
            "hole_in": s.hole_in,
            "casing_od_in": s.casing_od_in,
            "top_tvd_m": top,
            "bottom_tvd_m": s.shoe_tvd_m,
            "mud_sg_planned": s.mud_sg,
            "min_mw_required_sg": need,
            "min_mw_at_tvd_m": depths[i_need],
            "max_mw_allowed_sg": cap,
            "max_mw_at_tvd_m": depths[i_cap],
            "window_ok": bool(need <= cap and s.mud_sg >= need - 1e-9 and s.mud_sg <= cap + 1e-9),
            "window_margin_sg": cap - need,
            "mud_below_min_sg": max(0.0, need - s.mud_sg),
            "mud_above_max_sg": max(0.0, s.mud_sg - cap),
            "riserless": s.riserless,
            "open_hole": s.open_hole,
        }
        riser = top > model.mudline_tvd_m + 1.0 and not s.riserless
        if prev_shoe is not None and riser:
            cap_pm = annulus_capacity_m3_per_m(s.hole_in, s.drill_pipe_od_in)
            strength = s.strength_at_top_sg if s.strength_at_top_sg is not None else model.frac_sg(top, frac_case)
            if kick_basis == "pore":
                pore_td = model.pore_sg(s.shoe_tvd_m, pore_case)
                kt = kick_tolerance(top, s.shoe_tvd_m, min(s.mud_sg, pore_td + trip_margin_sg), strength, cap_pm, kick_intensity_sg, influx_sg,
                                    formation_sg=pore_td + kick_intensity_sg)
            else:
                kt = kick_tolerance(top, s.shoe_tvd_m, s.mud_sg, strength, cap_pm, kick_intensity_sg, influx_sg)
            row.update({"kt_volume_m3": kt["volume_m3"], "kt_volume_bbl": kt["volume_bbl"], "kt_h_max_m": kt["h_max_m"],
                        "kt_ok": bool(kt["ok_to_shut_in"] and kt["volume_m3"] >= kt_min_m3), "kt_required_m3": kt_min_m3,
                        "kt_strength_sg": strength, "kt_shoe_margin_bar": kt["shoe_pressure_margin_bar"], "kt_open_length_m": s.shoe_tvd_m - top,
                        "kt_limited_by_open_hole": bool(kt["h_max_m"] >= (s.shoe_tvd_m - top) - 1e-6)})
        else:
            row.update({"kt_volume_m3": None, "kt_volume_bbl": None, "kt_h_max_m": None, "kt_ok": None, "kt_required_m3": kt_min_m3,
                        "kt_strength_sg": None, "kt_shoe_margin_bar": None, "kt_open_length_m": None, "kt_limited_by_open_hole": None})
        out.append(row)
        prev_shoe = s.shoe_tvd_m
    return out


def propose_seats_bottom_up(
    model: PressureModel,
    td_tvd_m: float,
    shallow_limit_tvd_m: float,
    hole_in: float = 8.5,
    pipe_od_in: float = 5.5,
    kick_intensity_sg: float = 0.06,
    influx_sg: float = 0.25,
    kt_min_m3: float = 8.0,
    pore_case: str = "high",
    frac_case: str = "low",
    trip_margin_sg: float = 0.04,
    frac_margin_sg: float = 0.03,
    step_m: float = 10.0,
    min_section_m: float = 150.0,
) -> List[Dict[str, float]]:
    """Walk upward from TD and propose the shallowest shoes that satisfy window and kick tolerance.

    A seat at depth Ds is acceptable for a section ending at Db when the low fracture EMW at Ds minus the margin
    covers the mud weight needed at Db (pore high + trip margin) and the kick tolerance exceeds ``kt_min_m3``.
    The walk stops when a seat at or above ``shallow_limit_tvd_m`` is acceptable.
    """
    seats: List[Dict[str, float]] = []
    db = td_tvd_m
    guard = 0
    while db > shallow_limit_tvd_m and guard < 10:
        guard += 1
        mw = model.window(db, pore_case, frac_case, trip_margin_sg, frac_margin_sg)["min_mw_sg"]
        # worst mud weight in the section is at the bottom for a normally increasing pore profile
        best = None
        ds = shallow_limit_tvd_m
        while ds <= db - min_section_m:
            frac_ok = model.frac_sg(ds, frac_case) - frac_margin_sg >= mw
            cap = annulus_capacity_m3_per_m(hole_in, pipe_od_in)
            kt = kick_tolerance(ds, db, mw, model.frac_sg(ds, frac_case), cap, kick_intensity_sg, influx_sg)
            if frac_ok and kt["ok_to_shut_in"] and kt["volume_m3"] >= kt_min_m3:
                best = (ds, kt, mw)
                break
            ds += step_m
        if best is None:
            seats.append({"seat_tvd_m": float("nan"), "section_bottom_tvd_m": db, "mud_sg": mw, "kt_m3": 0.0, "status": "NO_SEAT_FOUND"})
            break
        ds, kt, mw = best
        seats.append({"seat_tvd_m": ds, "section_bottom_tvd_m": db, "mud_sg": mw, "kt_m3": kt["volume_m3"], "status": "OK"})
        if ds <= shallow_limit_tvd_m + 1e-6:
            break
        db = ds
    return seats
