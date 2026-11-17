"""3D well trajectory geometry: minimum curvature, dogleg severity and curve-hold planning.

Coordinates are (E, N, V) with V positive down (TVD below a common datum, e.g. TVDSS).
Angles are passed in degrees at the public API and handled in radians internally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np


def tangent(inc_rad, az_rad):
    """Unit tangent (E, N, V-down) for inclination/azimuth in radians (scalars or arrays)."""
    inc = np.asarray(inc_rad, float)
    az = np.asarray(az_rad, float)
    return np.stack(
        [np.sin(inc) * np.sin(az), np.sin(inc) * np.cos(az), np.cos(inc)], axis=-1
    )


def minimum_curvature(
    md: Sequence[float],
    inc_deg: Sequence[float],
    az_deg: Sequence[float],
    start_xyz: Sequence[float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Minimum-curvature station positions (E, N, V) from MD/inclination/azimuth in degrees."""
    md = np.asarray(md, float)
    t = tangent(np.radians(inc_deg), np.radians(az_deg))
    pos = np.zeros((len(md), 3))
    pos[0] = np.asarray(start_xyz, float)
    for i in range(1, len(md)):
        dl = math.acos(max(-1.0, min(1.0, float(np.dot(t[i - 1], t[i])))))
        rf = 1.0 if dl < 1e-9 else 2.0 / dl * math.tan(dl / 2.0)
        pos[i] = pos[i - 1] + (md[i] - md[i - 1]) / 2.0 * rf * (t[i - 1] + t[i])
    return pos


def dogleg_severity(
    md: Sequence[float],
    inc_deg: Sequence[float],
    az_deg: Sequence[float],
    course_length: float = 30.0,
) -> np.ndarray:
    """Dogleg severity in degrees per ``course_length`` (default deg/30 m); first station is 0."""
    md = np.asarray(md, float)
    t = tangent(np.radians(inc_deg), np.radians(az_deg))
    out = np.zeros(len(md))
    for i in range(1, len(md)):
        ang = math.degrees(
            math.acos(max(-1.0, min(1.0, float(np.dot(t[i - 1], t[i])))))
        )
        out[i] = ang / max(md[i] - md[i - 1], 1e-9) * course_length
    return out


@dataclass
class Wellpath:
    """A surveyed or planned wellbore: stations with MD, position, angles and optional covariance.

    ``xyz`` is (n, 3) in E, N, V-down; ``inc``/``az`` are radians; ``cov`` is (n, 3, 3) in m^2
    (E, N, V) or None when the uncertainty is to be modelled later.
    """

    name: str
    md: np.ndarray
    xyz: np.ndarray
    inc: np.ndarray
    az: np.ndarray
    cov: Optional[np.ndarray] = None
    parent: Optional[str] = None
    tie_md: Optional[float] = None
    info: dict = field(default_factory=dict)

    @classmethod
    def from_survey(
        cls,
        name: str,
        md,
        inc_deg,
        az_deg,
        start_xyz=(0.0, 0.0, 0.0),
        cov=None,
        xyz=None,
        parent: Optional[str] = None,
    ) -> "Wellpath":
        """Build from a survey listing. Positions are computed by minimum curvature unless ``xyz`` is given."""
        md = np.asarray(md, float)
        order = np.argsort(md)
        md = md[order]
        inc_deg = np.asarray(inc_deg, float)[order]
        az_deg = np.asarray(az_deg, float)[order]
        pos = (
            np.asarray(xyz, float)[order]
            if xyz is not None
            else minimum_curvature(md, inc_deg, az_deg, start_xyz)
        )
        c = None if cov is None else np.asarray(cov, float)[order]
        return cls(name, md, pos, np.radians(inc_deg), np.radians(az_deg), c, parent)

    @property
    def dls(self) -> np.ndarray:
        """Dogleg severity per station, deg/30 m."""
        return dogleg_severity(self.md, np.degrees(self.inc), np.degrees(self.az))

    def station_index(self, md: float, tol: float = 1e-6) -> int:
        """Index of the station at ``md`` (must coincide with a station)."""
        i = int(np.searchsorted(self.md, md - tol))
        if i >= len(self.md) or abs(self.md[i] - md) > tol:
            raise ValueError(
                f"MD {md} is not a station of {self.name}; pick a survey station as tie-in"
            )
        return i


def _bisect(f, lo: float, hi: float, tol: float = 1e-12, maxit: int = 200) -> float:
    """Plain bisection on a bracketed sign change."""
    flo = f(lo)
    for _ in range(maxit):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def curve_hold(p0, t0, target, dls_deg30: float, step: float = 10.0):
    """3D constant-DLS arc in the plane of ``t0`` and ``target - p0``, then a straight hold to the target.

    Returns ``(s, inc_rad, az_rad, arc_length, hold_length)`` where ``s`` is the along-hole distance from
    ``p0``. Raises ``ValueError`` when the target lies inside the turning circle (unreachable at that DLS).
    """
    p0 = np.asarray(p0, float)
    t0 = np.asarray(t0, float) / np.linalg.norm(t0)
    target = np.asarray(target, float)
    kappa = math.radians(dls_deg30) / 30.0
    r = 1.0 / kappa
    d = target - p0
    a = float(np.dot(d, t0))
    vperp = d - a * t0
    b = float(np.linalg.norm(vperp))
    if b < 1e-6:
        if a <= 0:
            raise ValueError("target lies behind the tie-in direction")
        theta, lhold, v = 0.0, a, np.zeros(3)
    else:
        v = vperp / b
        if a * a + (b - r) ** 2 < r * r:
            raise ValueError(
                "target inside the turning circle: raise DLS or move the tie-in/kick-off"
            )

        def miss(th):
            px, py = r * math.sin(th), r * (1 - math.cos(th))
            return math.cos(th) * (b - py) - math.sin(th) * (a - px)

        grid = np.linspace(1e-6, math.pi - 1e-6, 2000)
        vals = [miss(g) for g in grid]
        idx = next(
            (i for i in range(len(grid) - 1) if vals[i] * vals[i + 1] <= 0), None
        )
        if idx is None:
            raise ValueError("no curve-hold solution for this target and DLS")
        theta = _bisect(miss, grid[idx], grid[idx + 1])
        px, py = r * math.sin(theta), r * (1 - math.cos(theta))
        lhold = math.hypot(a - px, b - py)
    larc = theta * r
    total = larc + lhold
    s = np.append(np.arange(0.0, total, step), total)
    th = np.minimum(s, larc) * kappa
    tvec = np.cos(th)[:, None] * t0[None] + np.sin(th)[:, None] * v[None]
    inc = np.arccos(np.clip(tvec[:, 2], -1, 1))
    az = np.mod(np.arctan2(tvec[:, 0], tvec[:, 1]), 2 * math.pi)
    return s, inc, az, larc, lhold


def plan_sidetrack(
    parent: Wellpath,
    tie_md: float,
    target,
    dls_deg30: float,
    name: str = "plan",
    step: float = 10.0,
) -> Wellpath:
    """Plan a sidetrack (or re-entry) that follows ``parent`` to ``tie_md`` then curves and holds to ``target``.

    The parent covariance up to the tie-in is copied when present; add new-hole uncertainty with
    :func:`well_trajectory_anticollision.uncertainty.add_model_covariance`.
    """
    i = parent.station_index(tie_md)
    p0 = parent.xyz[i]
    t0 = tangent(parent.inc[i], parent.az[i])
    s, inc, az, larc, lhold = curve_hold(p0, t0, target, dls_deg30, step)
    md = np.concatenate([parent.md[: i + 1], tie_md + s[1:]])
    inc_all = np.concatenate([parent.inc[: i + 1], inc[1:]])
    az_all = np.concatenate([parent.az[: i + 1], az[1:]])
    new_xyz = minimum_curvature(tie_md + s, np.degrees(inc), np.degrees(az), p0)
    xyz = np.concatenate([parent.xyz[: i + 1], new_xyz[1:]])
    cov = None
    if parent.cov is not None:
        cov = np.concatenate(
            [parent.cov[: i + 1], np.repeat(parent.cov[i][None], len(s) - 1, 0)]
        )
    wp = Wellpath(name, md, xyz, inc_all, az_all, cov, parent.name, tie_md)
    wp.info = {
        "tie_index": i,
        "arc_length_m": larc,
        "hold_length_m": lhold,
        "target_miss_m": float(np.linalg.norm(xyz[-1] - np.asarray(target, float))),
    }
    return wp


def plan_from_surface(
    slot_xyz,
    kop_depth: float,
    target,
    dls_deg30: float,
    name: str = "plan",
    step: float = 10.0,
) -> Wellpath:
    """Vertical to the kick-off (``kop_depth`` measured along hole from ``slot_xyz``), then curve-hold to target."""
    slot_xyz = np.asarray(slot_xyz, float)
    md_v = np.append(np.arange(0.0, kop_depth, step), kop_depth)
    vert = Wellpath(
        "vertical",
        md_v,
        slot_xyz[None] + np.outer(md_v, [0.0, 0.0, 1.0]),
        np.zeros(len(md_v)),
        np.zeros(len(md_v)),
    )
    wp = plan_sidetrack(vert, kop_depth, target, dls_deg30, name, step)
    wp.parent, wp.tie_md = None, None
    wp.info["kop_md"] = kop_depth
    return wp


def summarize(wp: Wellpath, slot_en=None) -> dict:
    """Key plan figures: TD, hold angle, max DLS, horizontal displacement and step-out ratio."""
    i0 = wp.info.get("tie_index", 0)
    slot_en = np.asarray(slot_en if slot_en is not None else wp.xyz[0, :2], float)
    horiz = float(np.linalg.norm(wp.xyz[-1, :2] - slot_en))
    depth = float(wp.xyz[-1, 2] - wp.xyz[0, 2])
    return {
        "td_md_m": round(float(wp.md[-1]), 1),
        "td_v_m": round(float(wp.xyz[-1, 2]), 1),
        "tie_or_kop_md_m": round(float(wp.md[i0]), 1),
        "hold_inc_deg": round(math.degrees(wp.inc[-1]), 2),
        "hold_az_deg": round(math.degrees(wp.az[-1]), 2),
        "arc_length_m": round(wp.info.get("arc_length_m", float("nan")), 1),
        "hold_length_m": round(wp.info.get("hold_length_m", float("nan")), 1),
        "max_dls_deg_per_30m": round(
            float(wp.dls[i0 + 1 :].max()) if len(wp.md) > i0 + 1 else 0.0, 2
        ),
        "horizontal_displacement_m": round(horiz, 1),
        "step_out_ratio": round(horiz / depth, 2) if depth > 0 else None,
        "target_miss_m": round(wp.info.get("target_miss_m", float("nan")), 3),
    }
