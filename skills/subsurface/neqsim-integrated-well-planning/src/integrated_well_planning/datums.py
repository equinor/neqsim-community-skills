"""Depth datums, survey geometry and pressure/volume reference bookkeeping.

All depths in the planning basis are metres. ``MD`` is measured depth along hole from the
depth reference (default rotary table/RKB), ``TVD`` is true vertical depth from the same
reference and ``TVDSS`` is true vertical depth below mean sea level. Conversion between them
needs the reference elevation above mean sea level, so it is always carried explicitly.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

STANDARD_CONDITIONS = {"temperature_C": 15.0, "pressure_bara": 1.01325, "note": "15 C and 1.01325 bara, ideal-gas molar volume 23.645 Sm3/kmol"}
BAR_PER_PSI = 0.0689475729
SEA_LEVEL_PRESSURE_BARA = 1.01325


@dataclass
class DepthReference:
    """Depth datum definition for one study."""

    reference: str = "RKB"
    reference_elevation_msl_m: float = 25.0
    water_depth_m: float = 0.0
    environment: str = "platform"
    coordinate_system: str = "ED50-UTM31N (placeholder - synthetic)"
    pressure_reference: str = "bara (absolute)"
    standard_conditions: Dict[str, object] = field(default_factory=lambda: dict(STANDARD_CONDITIONS))

    def tvdss(self, tvd_m: float) -> float:
        """Convert TVD below the reference to TVDSS (positive down, below mean sea level)."""
        return tvd_m - self.reference_elevation_msl_m

    def tvd_from_tvdss(self, tvdss_m: float) -> float:
        """Convert TVDSS to TVD below the reference."""
        return tvdss_m + self.reference_elevation_msl_m

    def seabed_tvd_m(self) -> Optional[float]:
        """Return the seabed TVD below the reference, or None for onshore wells."""
        if self.environment == "onshore":
            return None
        return self.water_depth_m + self.reference_elevation_msl_m

    def to_dict(self) -> Dict[str, object]:
        """Return a plain dictionary."""
        return asdict(self)


def barg_to_bara(p_barg: float) -> float:
    """Gauge to absolute pressure (bar)."""
    return p_barg + SEA_LEVEL_PRESSURE_BARA


def bara_to_barg(p_bara: float) -> float:
    """Absolute to gauge pressure (bar)."""
    return p_bara - SEA_LEVEL_PRESSURE_BARA


def psi_to_bar(psi: float) -> float:
    """Pounds per square inch to bar."""
    return psi * BAR_PER_PSI


def minimum_curvature(md: Sequence[float], inc_deg: Sequence[float], azi_deg: Sequence[float]) -> Dict[str, List[float]]:
    """Minimum-curvature survey calculation.

    Args:
        md: measured depths (m), increasing.
        inc_deg: inclination from vertical (deg).
        azi_deg: azimuth from grid north (deg).

    Returns:
        Dictionary of lists ``md, inc, azi, tvd, north, east, dls`` (dls in deg/30 m).

    Raises:
        ValueError: on unequal lengths, fewer than two stations or non-increasing MD.
    """
    n = len(md)
    if not (n == len(inc_deg) == len(azi_deg)) or n < 2:
        raise ValueError("survey needs >= 2 stations of equal length")
    tvd, north, east, dls = [0.0], [0.0], [0.0], [0.0]
    for i in range(1, n):
        dmd = md[i] - md[i - 1]
        if dmd <= 0:
            raise ValueError("measured depth must increase (station {})".format(i))
        i1, i2 = math.radians(inc_deg[i - 1]), math.radians(inc_deg[i])
        a1, a2 = math.radians(azi_deg[i - 1]), math.radians(azi_deg[i])
        cos_dl = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (1.0 - math.cos(a2 - a1))
        dl = math.acos(max(-1.0, min(1.0, cos_dl)))
        rf = 1.0 if dl < 1e-9 else 2.0 / dl * math.tan(dl / 2.0)
        tvd.append(tvd[-1] + dmd / 2.0 * (math.cos(i1) + math.cos(i2)) * rf)
        north.append(north[-1] + dmd / 2.0 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf)
        east.append(east[-1] + dmd / 2.0 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf)
        dls.append(math.degrees(dl) / dmd * 30.0)
    return {"md": list(md), "inc": list(inc_deg), "azi": list(azi_deg), "tvd": tvd, "north": north, "east": east, "dls": dls}


def build_and_hold(kop_md: float, build_rate_deg_per_30m: float, hold_inc_deg: float, td_md: float, azimuth_deg: float = 0.0,
                   step_m: float = 25.0) -> Dict[str, List[float]]:
    """Synthetic build-and-hold well path (vertical, constant-rate build, tangent)."""
    md = [0.0]
    inc = [0.0]
    m = 0.0
    while m < td_md - 1e-9:
        m = min(m + step_m, td_md)
        if m <= kop_md:
            i = 0.0
        else:
            i = min(hold_inc_deg, (m - kop_md) / 30.0 * build_rate_deg_per_30m)
        md.append(m)
        inc.append(i)
    return minimum_curvature(md, inc, [azimuth_deg] * len(md))


def survey_summary(survey: Dict[str, List[float]], max_dls_limit: Optional[float] = None) -> Dict[str, object]:
    """Summarise a computed survey: TD, step-out, max inclination and max DLS."""
    horizontal = [math.hypot(n, e) for n, e in zip(survey["north"], survey["east"])]
    out = {
        "td_md_m": survey["md"][-1],
        "td_tvd_m": survey["tvd"][-1],
        "step_out_m": horizontal[-1],
        "max_inclination_deg": max(survey["inc"]),
        "max_dls_deg_per_30m": max(survey["dls"]),
        "dls_limit_deg_per_30m": max_dls_limit,
        "dls_limit_status": "NOT_ASSESSED (no limit supplied)" if max_dls_limit is None else (
            "PASS" if max(survey["dls"]) <= max_dls_limit else "FAIL"),
    }
    return out


def check_datum_consistency(md_m: Optional[float], tvd_m: Optional[float], inc_at_td_deg: Optional[float] = None,
                            survey: Optional[Dict[str, List[float]]] = None, tol_m: float = 5.0) -> List[str]:
    """Return a list of consistency problems between supplied MD, TVD and survey (empty = consistent)."""
    problems: List[str] = []
    if md_m is not None and tvd_m is not None and tvd_m > md_m + 1e-6:
        problems.append("TVD ({:.1f}) exceeds MD ({:.1f})".format(tvd_m, md_m))
    if survey and tvd_m is not None:
        if abs(survey["tvd"][-1] - tvd_m) > tol_m:
            problems.append("survey TVD at TD ({:.1f}) differs from basis TVD ({:.1f}) by more than {:.1f} m".format(
                survey["tvd"][-1], tvd_m, tol_m))
        if md_m is not None and abs(survey["md"][-1] - md_m) > tol_m:
            problems.append("survey MD at TD differs from basis MD by more than {:.1f} m".format(tol_m))
    if inc_at_td_deg is not None and md_m is not None and tvd_m is not None:
        if inc_at_td_deg < 1.0 and abs(md_m - tvd_m) > tol_m:
            problems.append("near-vertical well but MD and TVD differ by {:.1f} m".format(abs(md_m - tvd_m)))
    return problems


def interpolate_tvd(survey: Dict[str, List[float]], md_m: float) -> float:
    """Linear interpolation of TVD from MD on a computed survey."""
    md, tvd = survey["md"], survey["tvd"]
    if md_m <= md[0]:
        return tvd[0]
    if md_m >= md[-1]:
        return tvd[-1]
    for i in range(1, len(md)):
        if md_m <= md[i]:
            f = (md_m - md[i - 1]) / (md[i] - md[i - 1])
            return tvd[i - 1] + f * (tvd[i] - tvd[i - 1])
    return tvd[-1]


def mean_inclination_deg(md_m: float, tvd_m: float) -> float:
    """Average inclination from vertical implied by MD and TVD (a straight-hole equivalent)."""
    if md_m <= 0 or tvd_m <= 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, tvd_m / md_m))))
