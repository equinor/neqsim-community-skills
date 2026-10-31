"""Pore pressure, fracture gradient and mud-weight window versus TVD (RKB reference)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import numpy as np

from .units import BAR_PER_SG_M


@dataclass
class EmwCurve:
    """Piecewise-linear equivalent-mud-weight curve (sg) against TVD below RKB (m)."""

    tvd_m: List[float]
    sg: List[float]

    def __post_init__(self) -> None:
        if len(self.tvd_m) != len(self.sg) or len(self.tvd_m) < 1:
            raise ValueError("tvd_m and sg must have the same non-zero length")
        order = np.argsort(self.tvd_m)
        self.tvd_m = [float(self.tvd_m[i]) for i in order]
        self.sg = [float(self.sg[i]) for i in order]

    def at(self, tvd_m: float) -> float:
        """Interpolate the curve at ``tvd_m`` (held constant outside the data range)."""
        return float(np.interp(tvd_m, self.tvd_m, self.sg))


@dataclass
class PressureModel:
    """Low/base/high pore and fracture curves. ``frac`` low is the conservative (lower) bound."""

    pore: Dict[str, EmwCurve]
    frac: Dict[str, EmwCurve]
    water_depth_m: float = 0.0
    air_gap_m: float = 0.0
    notes: List[str] = field(default_factory=list)

    @property
    def mudline_tvd_m(self) -> float:
        """Mudline depth below RKB."""
        return self.water_depth_m + self.air_gap_m

    def pore_sg(self, tvd_m: float, case: str = "base") -> float:
        """Pore pressure EMW at ``tvd_m`` for ``case`` (low, base, high)."""
        return self.pore[case].at(tvd_m)

    def frac_sg(self, tvd_m: float, case: str = "base") -> float:
        """Fracture (or LOT-limited) EMW at ``tvd_m`` for ``case`` (low, base, high)."""
        return self.frac[case].at(tvd_m)

    def pore_bar(self, tvd_m: float, case: str = "base") -> float:
        """Pore pressure in bar."""
        return self.pore_sg(tvd_m, case) * BAR_PER_SG_M * tvd_m

    def frac_bar(self, tvd_m: float, case: str = "base") -> float:
        """Fracture pressure in bar."""
        return self.frac_sg(tvd_m, case) * BAR_PER_SG_M * tvd_m

    def window(
        self,
        tvd_m: float,
        pore_case: str = "high",
        frac_case: str = "low",
        trip_margin_sg: float = 0.04,
        frac_margin_sg: float = 0.03,
    ) -> Dict[str, float]:
        """Drillable mud-weight window at one depth.

        Args:
            tvd_m: depth below RKB.
            pore_case: pore curve used for the lower bound (high is conservative).
            frac_case: fracture curve used for the upper bound (low is conservative).
            trip_margin_sg: margin above pore pressure for swab and trip safety.
            frac_margin_sg: margin below fracture gradient for surge and ECD.

        Returns:
            Dict with pore_sg, frac_sg, min_mw_sg, max_mw_sg and width_sg.
        """
        pore = self.pore_sg(tvd_m, pore_case)
        frac = self.frac_sg(tvd_m, frac_case)
        lo = pore + trip_margin_sg
        hi = frac - frac_margin_sg
        return {"tvd_m": tvd_m, "pore_sg": pore, "frac_sg": frac, "min_mw_sg": lo, "max_mw_sg": hi, "width_sg": hi - lo}

    def window_table(self, depths_m: Sequence[float], **kw) -> List[Dict[str, float]]:
        """Window at several depths."""
        return [self.window(float(d), **kw) for d in depths_m]


def overburden_sg(
    tvd_m: float,
    water_depth_m: float,
    air_gap_m: float = 0.0,
    rho_mudline: float = 1.80,
    rho_deep: float = 2.55,
    z_scale_m: float = 1500.0,
    rho_sea: float = 1.03,
) -> float:
    """Overburden gradient (EMW sg) with an exponential bulk-density trend below the mudline.

    The trend is an assumption: calibrate ``rho_mudline``, ``rho_deep`` and ``z_scale_m`` to a density log.
    """
    if tvd_m <= 0.0:
        raise ValueError("tvd_m must be positive")
    z_ml = water_depth_m + air_gap_m
    below = max(0.0, tvd_m - z_ml)
    sea = max(0.0, min(tvd_m, z_ml) - air_gap_m)
    n = 400
    zz = np.linspace(0.0, below, n + 1) if below > 0 else np.array([0.0])
    rho = rho_deep - (rho_deep - rho_mudline) * np.exp(-zz / z_scale_m)
    sed_mass = float(np.sum(0.5 * (rho[1:] + rho[:-1]) * np.diff(zz))) if below > 0 else 0.0
    return (rho_sea * sea + sed_mass) / tvd_m


def eaton_frac_sg(pore_sg: float, obg_sg: float, poisson: float = 0.30) -> float:
    """Matrix-stress (Eaton) fracture gradient: Pf = Pp + nu/(1-nu) (Sv - Pp), as EMW."""
    return pore_sg + poisson / (1.0 - poisson) * (obg_sg - pore_sg)


def curve_from_points(points: Sequence[Sequence[float]]) -> EmwCurve:
    """Build an EmwCurve from (tvd_m, sg) pairs."""
    return EmwCurve([p[0] for p in points], [p[1] for p in points])


def hydrostatic_pressure_bar(tvd_rkb_m: float, gradient_sg: float, air_gap_m: float, water_depth_m: float = 0.0, sea_sg: float = 1.03) -> float:
    """Normal (hydrostatic) pore pressure in bar at a depth below RKB.

    Pressure builds from mean sea level, not from the rotary table: the air gap carries no fluid. A normal 1.03 sg formation therefore
    has an EMW below 1.03 at RKB depth, and the difference matters close to the seabed (riserless sections, conductor and shallow
    seats). The seawater column of ``water_depth_m`` uses ``sea_sg``; the sediment column below it uses ``gradient_sg``.
    """
    below_msl = max(0.0, tvd_rkb_m - air_gap_m)
    sea = min(below_msl, water_depth_m)
    return BAR_PER_SG_M * (sea_sg * sea + gradient_sg * max(0.0, below_msl - sea))


def emw_curve_from_pressure_points(points_bar: Sequence[Sequence[float]]) -> EmwCurve:
    """Build an EmwCurve from (tvd_rkb_m, pressure_bar) pairs: EMW = p / (0.0980665 TVD). Use dense points when the pressure is not linear in depth."""
    return EmwCurve([p[0] for p in points_bar], [p[1] / (BAR_PER_SG_M * p[0]) for p in points_bar])
