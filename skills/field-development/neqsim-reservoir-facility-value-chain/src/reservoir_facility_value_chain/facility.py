"""Facility side of the value chain: capacity from process-model sweeps, supply/capacity balance, flow balance."""

from __future__ import annotations

from bisect import bisect_left
from typing import Callable, Sequence


def capacity_from_sweep(rates: Sequence[float], utilisation: Sequence[float]) -> dict:
    """Rate at which the first-constraint utilisation reaches 1.0 in a throughput sweep.

    Returns {"capacity", "status"}. status is "ok", "infeasible" (utilisation above 1 at every tested rate; a head or
    speed limit independent of flow, so treat the pressure as below the facility floor) or "not_reached" (still below
    1.0 at the highest tested rate; capacity is a lower bound).
    """
    pairs = sorted(zip(rates, utilisation))
    for (q0, u0), (q1, u1) in zip(pairs, pairs[1:]):
        if u0 <= 1.0 < u1:
            return {"capacity": q0 + (1.0 - u0) * (q1 - q0) / (u1 - u0), "status": "ok"}
    if all(u > 1.0 for _, u in pairs):
        return {"capacity": None, "status": "infeasible"}
    return {"capacity": max(r for r, _ in pairs), "status": "not_reached"}


class PressureCapacityCurve:
    """Piecewise-linear capacity vs separator pressure, extrapolated linearly from the end segments."""

    def __init__(self, pressure: Sequence[float], capacity: Sequence[float]):
        if len(pressure) != len(capacity) or len(pressure) < 2:
            raise ValueError("need at least two points of equal length")
        if any(b <= a for a, b in zip(pressure, pressure[1:])):
            raise ValueError("pressures must be strictly ascending")
        self.p, self.c = list(pressure), list(capacity)

    def __call__(self, pressure: float) -> float:
        i = min(max(bisect_left(self.p, pressure), 1), len(self.p) - 1)
        t = (pressure - self.p[i - 1]) / (self.p[i] - self.p[i - 1])
        return max(0.0, self.c[i - 1] + t * (self.c[i] - self.c[i - 1]))


def maximise_rate(supply: Callable[[float], float], capacity: Callable[[float], float], p_min: float, p_max: float):
    """Maximise min(supply(p), capacity(p)); supply falls with p, capacity rises with p.

    Returns (pressure, rate, binding) with binding "SUPPLY" (wells limit even at p_min) or "FACILITY".
    Mirrors neqsim.process.fielddevelopment.integrated.SupplyCapacityBalance.
    """
    if p_min >= p_max:
        raise ValueError("p_min must be below p_max")
    s_lo, c_lo = supply(p_min), capacity(p_min)
    if s_lo <= c_lo:
        return p_min, s_lo, "SUPPLY"
    s_hi, c_hi = supply(p_max), capacity(p_max)
    if s_hi >= c_hi:
        return p_max, c_hi, "FACILITY"
    lo, hi = p_min, p_max
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if supply(mid) > capacity(mid):
            lo = mid
        else:
            hi = mid
    p = 0.5 * (lo + hi)
    return p, min(supply(p), capacity(p)), "FACILITY"


def flow_balance(rate_at_whp: Callable[[float], float], sep_barg: float, dp_ref: float, q_ref: float) -> float:
    """Solve q = rate(sep + dp_ref (q/q_ref)^2) by bisection.

    Plain fixed-point iteration oscillates and can collapse to zero when the drawdown is small, so bisect.
    """
    lo, hi = 0.0, rate_at_whp(sep_barg)
    if hi <= 0.0:
        return 0.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if rate_at_whp(sep_barg + dp_ref * (mid / q_ref) ** 2) > mid:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
