"""Nodal analysis at the bottom-hole node on plain callables.

``inflow_pwf(q)`` returns the flowing bottom-hole pressure the reservoir can sustain at rate ``q`` (decreasing
in ``q`` for a producer) and ``outflow_pwf(q)`` the bottom-hole pressure required by the tubing + wellhead back
pressure. A stable operating point is an intersection where the surplus ``inflow - outflow`` crosses zero from
positive to negative with increasing rate; the reverse crossing is the unstable (loading) branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np


@dataclass
class Intersection:
    """One inflow/outflow crossing."""

    rate: float
    bhp_bara: float
    stable: bool


@dataclass
class NodalResult:
    """Result of :func:`solve_nodal`."""

    rates: List[float]
    inflow_pwf: List[float]
    outflow_pwf: List[float]
    intersections: List[Intersection] = field(default_factory=list)
    operating_point: Optional[Intersection] = None
    status: str = "NO_INTERSECTION"
    outflow_min_rate: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-friendly dictionary."""
        return {
            "status": self.status,
            "rates": self.rates,
            "inflow_pwf_bara": self.inflow_pwf,
            "outflow_pwf_bara": self.outflow_pwf,
            "intersections": [i.__dict__ for i in self.intersections],
            "operating_point": self.operating_point.__dict__ if self.operating_point else None,
            "outflow_min_rate": self.outflow_min_rate,
        }


def solve_nodal(inflow_pwf: Callable[[float], float], outflow_pwf: Callable[[float], float], q_min: float, q_max: float, n_scan: int = 14,
                refine: int = 6) -> NodalResult:
    """Scan, bracket and refine all inflow/outflow intersections.

    Args:
        inflow_pwf: callable q -> pwf (bara) from the reservoir.
        outflow_pwf: callable q -> pwf (bara) required by the outflow.
        q_min: lowest scanned rate (> 0).
        q_max: highest scanned rate.
        n_scan: number of scan points.
        refine: bisection steps per bracket.

    Returns:
        :class:`NodalResult`; ``status`` is ``STABLE``, ``UNSTABLE_ONLY``, ``STABLE_AT_RANGE_END`` (inflow above outflow over the whole range) or ``NO_INTERSECTION``.
    """
    if q_min <= 0 or q_max <= q_min:
        raise ValueError("need 0 < q_min < q_max")
    qs = np.linspace(q_min, q_max, int(n_scan))
    ipr = [float(inflow_pwf(q)) for q in qs]
    vlp = [float(outflow_pwf(q)) for q in qs]
    surplus = np.array(ipr) - np.array(vlp)
    res = NodalResult([float(q) for q in qs], ipr, vlp)
    res.outflow_min_rate = float(qs[int(np.argmin(vlp))])
    for i in range(len(qs) - 1):
        a, b = surplus[i], surplus[i + 1]
        if a == 0.0 or a * b < 0.0:
            lo, hi, flo = float(qs[i]), float(qs[i + 1]), a
            for _ in range(refine):
                mid = 0.5 * (lo + hi)
                fm = float(inflow_pwf(mid)) - float(outflow_pwf(mid))
                if flo * fm <= 0.0:
                    hi = mid
                else:
                    lo, flo = mid, fm
            q = 0.5 * (lo + hi)
            stable = bool(a > 0.0 and b < 0.0) or (a == 0.0 and b < 0.0)
            res.intersections.append(Intersection(q, float(inflow_pwf(q)), stable))
    stables = [x for x in res.intersections if x.stable]
    if stables:
        res.operating_point = max(stables, key=lambda x: x.rate)
        res.status = "STABLE"
    elif res.intersections:
        res.operating_point = res.intersections[-1]
        res.status = "UNSTABLE_ONLY"
    elif bool(np.all(surplus > 0.0)):
        # the inflow stays above the outflow over the whole scanned range: the rate is limited by the scan range (the inflow limit), not by the tubing
        res.operating_point = Intersection(float(qs[-1]), float(ipr[-1]), True)
        res.status = "STABLE_AT_RANGE_END"
    return res


def surplus_at(inflow_pwf: Callable[[float], float], outflow_pwf: Callable[[float], float], q: float) -> float:
    """Inflow minus outflow bottom-hole pressure at rate ``q`` (positive = the well can deliver ``q``)."""
    return float(inflow_pwf(q)) - float(outflow_pwf(q))


def composite_oil_ipr(p_res: float, p_bubble: float, pi_sm3d_per_bar: float) -> Dict[str, Callable[[float], float]]:
    """Linear (above bubble point) / Vogel (below) composite IPR after Standing.

    Returns:
        ``{"rate": f(pwf), "pwf": f(q), "aof": value}``.
    """
    pb = min(max(p_bubble, 0.0), p_res) if p_bubble == p_bubble else 0.0
    qb = pi_sm3d_per_bar * (p_res - pb)
    qv = pi_sm3d_per_bar * pb / 1.8

    def rate(pwf: float) -> float:
        pwf = max(0.0, min(pwf, p_res))
        if pwf >= pb:
            return pi_sm3d_per_bar * (p_res - pwf)
        x = pwf / pb if pb > 0 else 0.0
        return qb + qv * (1.0 - 0.2 * x - 0.8 * x * x)

    aof = qb + qv

    def pwf(q: float) -> float:
        if q <= 0:
            return p_res
        if q >= aof:
            return 0.0
        if q <= qb or pb <= 0:
            return p_res - q / pi_sm3d_per_bar
        # solve qv (1 - 0.2x - 0.8x^2) = q - qb for x = pwf/pb
        c = (q - qb) / qv
        disc = 0.04 + 3.2 * (1.0 - c)
        x = (-0.2 + disc ** 0.5) / 1.6
        return max(0.0, x * pb)

    return {"rate": rate, "pwf": pwf, "aof": aof}
