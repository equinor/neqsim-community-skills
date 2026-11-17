"""Inverse control-valve capacity screening for a gas valve held at a travel stop.

The forward sizing model answers "what Cv is required". Operations often ask the
inverse questions: *what Cv did a capacity test really demonstrate, how much will
the same valve pass at another pressure drop, and how far must a travel stop move
to meet a flow limit?* This module answers them with the public IEC 60534-2-1
gas equation (Fk/xT expansion factor, choked limit), in terms of standard
volumetric flow.

All functions are plant-agnostic screening helpers. Pressures are bar absolute,
temperature in K, flow in Sm3/h (15 C, 1.01325 bar).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

# Fisher/IEC constant for Sm3/h at 15 C, p in bar abs, T in K: Q = 417*Cv*p1*Y*sqrt(x/(G*T*Z))
_N_SM3H = 417.0
_AIR_MW = 28.96


def _expansion(p1: float, p2: float, k: float, xt: float) -> tuple[float, float]:
    """Return (x_effective, Y) with the choked limit applied."""
    if p1 <= 0 or p2 < 0 or p2 >= p1:
        raise ValueError("require p1 > p2 >= 0 (bar abs)")
    if k <= 0 or xt <= 0:
        raise ValueError("k and xt must be positive")
    fk = k / 1.4
    x = (p1 - p2) / p1
    x_eff = min(x, fk * xt)
    y = 1.0 - x_eff / (3.0 * fk * xt)
    return x_eff, y


def gas_flow_sm3h(
    cv: float,
    p1_bara: float,
    p2_bara: float,
    temperature_k: float,
    molar_mass: float,
    z: float = 1.0,
    k: float = 1.3,
    xt: float = 0.5,
) -> float:
    """Standard gas flow (Sm3/h) through a valve of flow coefficient ``cv``."""
    x_eff, y = _expansion(p1_bara, p2_bara, k, xt)
    g = molar_mass / _AIR_MW
    return _N_SM3H * cv * p1_bara * y * sqrt(x_eff / (g * temperature_k * z))


def cv_from_gas_flow(
    q_sm3h: float,
    p1_bara: float,
    p2_bara: float,
    temperature_k: float,
    molar_mass: float,
    z: float = 1.0,
    k: float = 1.3,
    xt: float = 0.5,
) -> float:
    """Effective Cv demonstrated by a measured flow and pressure pair (exact inverse)."""
    unit = gas_flow_sm3h(1.0, p1_bara, p2_bara, temperature_k, molar_mass, z, k, xt)
    return q_sm3h / unit


@dataclass(frozen=True)
class StopCapacityResult:
    """Result of :func:`verify_stop_capacity`."""

    cv_effective: tuple[float, ...]
    cv_nominal_at_stop: float
    ratio_to_nominal: tuple[float, ...]
    implied_opening_fraction: tuple[float, ...]
    flow_at_limit_case_sm3h: float
    opening_fraction_for_limit: float | None
    notes: tuple[str, ...]


def verify_stop_capacity(
    tests: list[dict],
    *,
    cv_max: float,
    stop_fraction: float,
    temperature_k: float,
    molar_mass: float,
    z: float = 1.0,
    k: float = 1.3,
    xt: float = 0.5,
    limit_case: dict | None = None,
    characteristic: str = "linear",
) -> StopCapacityResult:
    """Back-calculate Cv at a travel stop from capacity tests and predict a limit case.

    ``tests`` items: ``{"q_sm3h":..., "p1_bara":..., "p2_bara":...}``.
    ``limit_case``: ``{"p1_bara":..., "p2_bara":..., "q_limit_sm3h":...}``; when given, the
    result holds the flow the stop passes in that case and the opening fraction that
    would just meet the limit. Only the ``linear`` characteristic is implemented (an
    equal-percentage valve needs the vendor curve; the function then refuses).
    """
    if characteristic != "linear":
        raise ValueError(
            "only linear characteristic is implemented; supply vendor curve for others"
        )
    if not 0 < stop_fraction <= 1:
        raise ValueError("stop_fraction must be in (0, 1]")
    cvs = tuple(
        cv_from_gas_flow(
            t["q_sm3h"], t["p1_bara"], t["p2_bara"], temperature_k, molar_mass, z, k, xt
        )
        for t in tests
    )
    nominal = cv_max * stop_fraction
    ratios = tuple(c / nominal for c in cvs)
    openings = tuple(c / cv_max for c in cvs)
    notes = [
        "Linear characteristic assumed: Cv = Cv_max * opening fraction.",
        "xT, Z, molar mass and temperature are inputs; report sensitivity before relying on the result.",
    ]
    q_lim = float("nan")
    open_lim = None
    if limit_case:
        cv_mean = sum(cvs) / len(cvs)
        q_lim = gas_flow_sm3h(
            cv_mean,
            limit_case["p1_bara"],
            limit_case["p2_bara"],
            temperature_k,
            molar_mass,
            z,
            k,
            xt,
        )
        cv_lim = cv_from_gas_flow(
            limit_case["q_limit_sm3h"],
            limit_case["p1_bara"],
            limit_case["p2_bara"],
            temperature_k,
            molar_mass,
            z,
            k,
            xt,
        )
        open_lim = cv_lim / cv_max
        if open_lim > 1.0:
            notes.append("Limit exceeds the valve at 100 % opening in this case.")
    return StopCapacityResult(
        cvs, nominal, ratios, openings, q_lim, open_lim, tuple(notes)
    )
