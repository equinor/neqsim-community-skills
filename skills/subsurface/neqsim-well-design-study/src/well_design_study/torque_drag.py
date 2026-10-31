"""Trajectory (minimum curvature, build-and-hold) and Johancsik soft-string torque and drag with a buckling check."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np

from .units import M_PER_IN, STEEL_DENSITY, STEEL_E_GPA


@dataclass
class Station:
    """A survey station."""

    md: float
    inc_deg: float
    azi_deg: float
    tvd: float = 0.0
    north: float = 0.0
    east: float = 0.0


def minimum_curvature(stations: Sequence[Station]) -> List[Station]:
    """Fill TVD, north and east of stations (first station is the origin) with the minimum-curvature method."""
    out = [Station(stations[0].md, stations[0].inc_deg, stations[0].azi_deg, stations[0].tvd, stations[0].north, stations[0].east)]
    for a, b in zip(stations[:-1], stations[1:]):
        dmd = b.md - a.md
        i1, i2 = math.radians(a.inc_deg), math.radians(b.inc_deg)
        a1, a2 = math.radians(a.azi_deg), math.radians(b.azi_deg)
        cosb = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (1.0 - math.cos(a2 - a1))
        beta = math.acos(max(-1.0, min(1.0, cosb)))
        rf = 1.0 if beta < 1e-9 else 2.0 / beta * math.tan(beta / 2.0)
        prev = out[-1]
        out.append(Station(b.md, b.inc_deg, b.azi_deg,
                           prev.tvd + dmd / 2.0 * (math.cos(i1) + math.cos(i2)) * rf,
                           prev.north + dmd / 2.0 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf,
                           prev.east + dmd / 2.0 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf))
    return out


def build_and_hold(target_tvd_m: float, target_departure_m: float, kop_m: float, dls_deg_per_30m: float, azimuth_deg: float = 0.0, step_m: float = 30.0) -> List[Station]:
    """Vertical-build-hold path that closes on the target TVD and departure. A zero departure returns a vertical well."""
    stations = [Station(0.0, 0.0, azimuth_deg)]
    if target_departure_m <= 0.5:
        md = 0.0
        while md < target_tvd_m:
            md = min(md + step_m, target_tvd_m)
            stations.append(Station(md, 0.0, azimuth_deg))
        return minimum_curvature(stations)
    r = 30.0 / math.radians(dls_deg_per_30m)
    dep_t, tvd_t = target_departure_m, target_tvd_m - kop_m
    d = math.hypot(dep_t - r, tvd_t)
    alpha = math.atan2(dep_t - r, tvd_t) + math.asin(max(-1.0, min(1.0, r / d)))
    build_len = r * alpha
    hold_len = math.sqrt(max(0.0, d * d - r * r))
    md = 0.0
    while md < kop_m:
        md = min(md + step_m, kop_m)
        stations.append(Station(md, 0.0, azimuth_deg))
    md0 = kop_m
    while md < md0 + build_len - 1e-9:
        md = min(md + step_m, md0 + build_len)
        stations.append(Station(md, math.degrees((md - md0) / r), azimuth_deg))
    md1 = md0 + build_len
    while md < md1 + hold_len - 1e-9:
        md = min(md + step_m, md1 + hold_len)
        stations.append(Station(md, math.degrees(alpha), azimuth_deg))
    return minimum_curvature(stations)


@dataclass
class StringComponent:
    """A drill-string component listed from the bit upward. ``weight_kg_per_m`` is air weight including joints."""

    name: str
    length_m: float
    weight_kg_per_m: float
    od_in: float
    id_in: float
    tool_joint_od_in: float = 0.0


def _buoyancy(mud_sg: float) -> float:
    return 1.0 - mud_sg * 1000.0 / STEEL_DENSITY


def torque_and_drag(
    stations: Sequence[Station],
    string: Sequence[StringComponent],
    mud_sg: float,
    ff_cased: float,
    ff_open: float,
    shoe_md_m: float,
    wob_kn: float = 0.0,
    operation: str = "trip_out",
    bit_md_m: float | None = None,
    hole_in: float = 8.5,
    casing_id_in: float = 8.68,
    tortuosity_deg_per_30m: float = 0.0,
) -> Dict[str, object]:
    """Soft-string torque and drag along the path from the bit to surface.

    Args:
        stations: survey stations (MD, inc, azi) with minimum-curvature coordinates.
        string: components from the bit upward; their lengths must cover the bit depth.
        operation: ``trip_out`` (pick-up), ``trip_in`` (slack-off), ``rotate_off`` or ``rotate_on`` (WOB and torque).
        shoe_md_m: casing shoe MD; friction factor changes from cased to open hole at this depth.
        tortuosity_deg_per_30m: micro-doglegs added to every element (an allowance for a real hole that is never straight; a
            perfectly vertical survey would otherwise give zero drag and torque). Typical allowance 0.2 to 0.5 deg per 30 m.

    Returns:
        Dict with hook load (kN), surface torque (kN m), arrays versus MD, and the sinusoidal buckling margin.
    """
    bit = bit_md_m if bit_md_m is not None else stations[-1].md
    mds = np.array([s.md for s in stations])
    inc = np.radians([s.inc_deg for s in stations])
    azi = np.radians([s.azi_deg for s in stations])

    def at(md: float):
        return float(np.interp(md, mds, inc)), float(np.interp(md, mds, azi))

    bf = _buoyancy(mud_sg)
    # discretise into elements of at most 10 m from the bit upward and assign component properties
    comps: List[tuple] = []
    start = bit
    for c in string:
        comps.append((start, max(0.0, start - c.length_m), c))
        start = max(0.0, start - c.length_m)
    if start > 1e-6:
        raise ValueError("string components do not reach surface from the bit depth")
    ft = -wob_kn if operation == "rotate_on" else 0.0   # axial force at bit, tension positive
    torque = 0.0
    mds_out, ft_out, tq_out = [bit], [ft], [0.0]
    buckling_margin = float("inf")
    for hi, lo, c in comps:
        n = max(1, int(math.ceil((hi - lo) / 10.0)))
        dl = (hi - lo) / n
        w = c.weight_kg_per_m * 9.80665 / 1000.0 * bf  # kN/m buoyed
        rt = (c.tool_joint_od_in or c.od_in) * M_PER_IN / 2.0
        r_pipe = c.od_in * M_PER_IN / 2.0
        for k in range(n):
            md_b = hi - k * dl
            md_t = md_b - dl
            i_b, a_b = at(md_b)
            i_t, a_t = at(md_t)
            im = 0.5 * (i_b + i_t)
            di = i_b - i_t
            da = a_b - a_t
            ff = ff_open if md_b > shoe_md_m else ff_cased
            di_eff = math.copysign(math.hypot(di, math.radians(tortuosity_deg_per_30m) / 30.0 * dl), di if di != 0.0 else 1.0)
            fn = math.sqrt((ft * da * math.sin(im)) ** 2 + (ft * di_eff + w * dl * math.sin(im)) ** 2)
            if operation in ("trip_out", "rotate_on_axial_pickup"):
                dft = w * dl * math.cos(im) + ff * fn
            elif operation == "trip_in":
                dft = w * dl * math.cos(im) - ff * fn
            else:  # rotating: axial drag vanishes, torque from the full contact force
                dft = w * dl * math.cos(im)
            torque += ff * fn * rt
            ft += dft
            if ft < 0 and fn > 0 and im > 1e-3:
                hole_d = (hole_in if md_b > shoe_md_m else casing_id_in) * M_PER_IN
                clearance = max(1e-3, 0.5 * (hole_d - c.od_in * M_PER_IN))
                i_area = math.pi / 64.0 * ((c.od_in * M_PER_IN) ** 4 - (c.id_in * M_PER_IN) ** 4)
                w_nm = max(1e-6, w * 1000.0)
                f_crit = 2.0 * math.sqrt(STEEL_E_GPA * 1e9 * i_area * w_nm * math.sin(im) / max(clearance, 1e-3)) / 1000.0
                buckling_margin = min(buckling_margin, f_crit / max(1e-9, -ft))
            mds_out.append(md_t)
            ft_out.append(ft)
            tq_out.append(torque)
    hook = ft_out[-1]
    return {
        "operation": operation, "hook_load_kn": hook, "surface_torque_knm": tq_out[-1] if operation.startswith("rotate") else 0.0,
        "md": mds_out[::-1], "axial_kn": ft_out[::-1], "torque_knm": tq_out[::-1],
        "buckling_margin_min": None if buckling_margin == float("inf") else buckling_margin,
        "max_tension_kn": max(ft_out),
    }


def torque_drag_envelope(stations, string, mud_sg, shoe_md_m, ff_cases: Dict[str, Dict[str, float]], wob_kn: float = 50.0, hole_in: float = 8.5, casing_id_in: float = 8.68,
                         tortuosity_deg_per_30m: float = 0.0) -> Dict[str, Dict[str, object]]:
    """Run trip-out, trip-in, rotate-off and rotate-on for each friction-factor case (e.g. low, base, high)."""
    res: Dict[str, Dict[str, object]] = {}
    for name, ff in ff_cases.items():
        res[name] = {
            op: torque_and_drag(stations, string, mud_sg, ff["cased"], ff["open"], shoe_md_m, wob_kn if op == "rotate_on" else 0.0, op,
                                hole_in=hole_in, casing_id_in=casing_id_in, tortuosity_deg_per_30m=tortuosity_deg_per_30m)
            for op in ("trip_out", "trip_in", "rotate_off", "rotate_on")
        }
    return res
