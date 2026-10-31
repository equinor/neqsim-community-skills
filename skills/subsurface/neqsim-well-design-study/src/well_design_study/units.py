"""Unit helpers and constants. Internal units: m, bar, sg (EMW), kg, kN unless a name says otherwise."""

from __future__ import annotations

import math

G = 9.80665
BAR_PER_PSI = 0.0689475729
M_PER_IN = 0.0254
KN_PER_KLBF = 4.4482216
BAR_PER_SG_M = 0.0980665  # hydrostatic bar per metre for 1 sg
KG_M3_PER_SG = 1000.0
STEEL_E_GPA = 207.0
STEEL_NU = 0.3
STEEL_ALPHA = 1.2e-5  # 1/K
STEEL_DENSITY = 7850.0


def psi_to_bar(p_psi: float) -> float:
    """Convert psi to bar."""
    return p_psi * BAR_PER_PSI


def bar_to_psi(p_bar: float) -> float:
    """Convert bar to psi."""
    return p_bar / BAR_PER_PSI


def hydro_bar(sg: float, tvd_m: float) -> float:
    """Hydrostatic pressure in bar of a fluid of density ``sg`` over ``tvd_m`` metres."""
    return sg * BAR_PER_SG_M * tvd_m


def emw_sg(p_bar: float, tvd_m: float) -> float:
    """Equivalent mud weight in sg of a pressure ``p_bar`` at depth ``tvd_m`` (RKB reference)."""
    if tvd_m <= 0.0:
        raise ValueError("tvd_m must be positive")
    return p_bar / (BAR_PER_SG_M * tvd_m)


def sg_to_ppg(sg: float) -> float:
    """Convert sg to lb/gal."""
    return sg * 8.3454


def ring_area_m2(od_m: float, id_m: float) -> float:
    """Annular steel or flow area between two diameters."""
    return math.pi / 4.0 * (od_m**2 - id_m**2)
