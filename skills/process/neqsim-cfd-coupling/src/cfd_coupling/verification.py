"""Verification references for the explosion workflow: cases with a known answer that do not depend on congestion.

``aicc_isochoric`` is an independent adiabatic isochoric complete-combustion (AICC) equilibrium calculation with dissociation
(element-constrained Helmholtz minimisation, GRI-Mech NASA-7 data shipped in ``pdr_templates/nasa7_gri.json``). It is the reference for the
closed-vessel pressure ratio of the CFD (case V1). ``LITERATURE_RANGES`` are typical open-literature ranges, NOT values read from a
standard in this repository: quote them as ranges and verify against the standard text before citing a clause.
"""

from __future__ import annotations

import json
from pathlib import Path

R_GAS = 8.314462618
P_STD = 1.0e5
_NASA = Path(__file__).resolve().parent / "pdr_templates" / "nasa7_gri.json"
_ELEMENTS = {"C": 0, "H": 1, "O": 2, "N": 3}

LITERATURE_RANGES = {
    "methane_stoich_laminar_burning_velocity_m_s": (0.33, 0.42),
    "propane_stoich_laminar_burning_velocity_m_s": (0.42, 0.48),
    "methane_stoich_AICC_pressure_ratio_298K": (8.6, 9.2),
    "closed_vessel_measured_over_AICC_pressure": (
        0.80,
        1.00,
    ),  # heat loss and incomplete combustion lower the measured maximum
}


def _species() -> dict:
    return json.loads(_NASA.read_text(encoding="utf-8"))["species"]


def _h_rt(s: dict, t: float) -> float:
    a = s["hi"] if t > s["tc"] else s["lo"]
    return (
        a[0]
        + a[1] * t / 2
        + a[2] * t**2 / 3
        + a[3] * t**3 / 4
        + a[4] * t**4 / 5
        + a[5] / t
    )


def _s_r(s: dict, t: float) -> float:
    import math

    a = s["hi"] if t > s["tc"] else s["lo"]
    return (
        a[0] * math.log(t)
        + a[1] * t
        + a[2] * t**2 / 2
        + a[3] * t**3 / 3
        + a[4] * t**4 / 4
        + a[6]
    )


def aicc_isochoric(
    fuel: dict[str, float] | None = None,
    t0: float = 288.15,
    p0: float = 101325.0,
    phi: float = 1.0,
) -> dict:
    """Adiabatic isochoric complete-combustion temperature and pressure ratio of a premixed fuel-air mixture.

    ``fuel`` maps species names (``CH4``, ``C3H8``) to mole fractions of the fuel blend. Requires numpy and scipy.
    """
    import numpy as np
    from scipy.optimize import brentq, minimize

    sp = _species()
    fuel = fuel or {"CH4": 1.0}
    names = list(sp)
    o2 = sum(
        x * (sp[f]["el"].get("C", 0.0) + sp[f]["el"].get("H", 0.0) / 4.0)
        for f, x in fuel.items()
    )
    n0 = {f: x * phi for f, x in fuel.items()}
    n0["O2"] = o2
    n0["N2"] = o2 * 3.76
    v = sum(n0.values()) * R_GAS * t0 / p0
    a_mat = np.zeros((4, len(names)))
    for j, nm in enumerate(names):
        for e, i in _ELEMENTS.items():
            a_mat[i, j] = sp[nm]["el"].get(e, 0.0)
    b = a_mat @ np.array([n0.get(nm, 0.0) for nm in names])
    u0 = sum(n0[k] * (_h_rt(sp[k], t0) * R_GAS * t0 - R_GAS * t0) for k in n0)

    def equilibrium(t):
        g = np.array([_h_rt(sp[nm], t) - _s_r(sp[nm], t) for nm in names])

        def f(n):
            n = np.maximum(n, 1e-30)
            return float(np.sum(n * (g + np.log(n * R_GAS * t / (v * P_STD)))))

        def jac(n):
            n = np.maximum(n, 1e-30)
            return g + np.log(n * R_GAS * t / (v * P_STD)) + 1.0

        x0 = np.full(len(names), 1e-4)
        x0[names.index("CO2")] = o2 * 0.4
        x0[names.index("H2O")] = o2 * 0.8
        x0[names.index("N2")] = n0["N2"]
        res = minimize(
            f,
            x0,
            jac=jac,
            method="SLSQP",
            bounds=[(1e-20, None)] * len(names),
            constraints=[
                {"type": "eq", "fun": lambda n: a_mat @ n - b, "jac": lambda n: a_mat}
            ],
            options={"maxiter": 500, "ftol": 1e-14},
        )
        return np.maximum(res.x, 1e-30)

    def resid(t):
        n = equilibrium(t)
        return (
            sum(
                n[j] * (_h_rt(sp[nm], t) * R_GAS * t - R_GAS * t)
                for j, nm in enumerate(names)
            )
            - u0
        )

    t_ad = brentq(resid, 1500.0, 3500.0, xtol=0.5)
    n = equilibrium(t_ad)
    p = float(n.sum() * R_GAS * t_ad / v)
    return {"T_ad_K": float(t_ad), "P_ratio": p / p0, "P_abs_bar": p / 1e5}


def verify_closed_vessel(
    cfd_peak_ratio: float,
    t0: float = 288.15,
    p0: float = 1.0e5,
    fuel: dict[str, float] | None = None,
) -> dict:
    """Compare the closed-vessel CFD peak pressure ratio with the AICC reference. Status ``pass`` within 12 %, ``caution`` within 20 %."""
    ref = aicc_isochoric(fuel, t0, p0)
    dev = cfd_peak_ratio / ref["P_ratio"] - 1.0
    status = "pass" if abs(dev) <= 0.12 else "caution" if abs(dev) <= 0.20 else "fail"
    return {
        "cfd_ratio": cfd_peak_ratio,
        "aicc_ratio": ref["P_ratio"],
        "aicc_T_K": ref["T_ad_K"],
        "deviation": dev,
        "status": status,
    }
