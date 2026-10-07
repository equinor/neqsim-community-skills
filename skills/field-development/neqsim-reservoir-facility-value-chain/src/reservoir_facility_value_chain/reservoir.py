"""p/z material-balance tank, shut-in history match, Rawlins-Schellhardt deliverability (dependency-free)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .gasprops import Gas, P_STD


def fit_pz_line(cum_gas, p_over_z, reject_sigma: float = 2.0, max_iter: int = 8):
    """Least squares p/z = a - b*Gp with iterative sigma-clipping.

    Returns (a, b, giip, rms, keep) where giip = a / b and keep marks the points of the final fit.
    """
    x, y = list(map(float, cum_gas)), list(map(float, p_over_z))
    n = len(x)
    if n != len(y) or n < 3:
        raise ValueError("need at least three points of equal length")
    keep = [True] * n
    a = b = rms = 0.0
    for _ in range(max_iter):
        idx = [i for i in range(n) if keep[i]]
        m = len(idx)
        sx = sum(x[i] for i in idx)
        sy = sum(y[i] for i in idx)
        sxx = sum(x[i] * x[i] for i in idx)
        sxy = sum(x[i] * y[i] for i in idx)
        slope = (m * sxy - sx * sy) / (m * sxx - sx * sx)
        a = (sy - slope * sx) / m
        b = -slope
        res = [y[i] - (a - b * x[i]) for i in range(n)]
        rms = (sum(res[i] ** 2 for i in idx) / m) ** 0.5
        limit = reject_sigma * max(rms, 1e-12)
        new = [abs(r) < limit for r in res]
        if new == keep:
            break
        keep = new
    return a, b, a / b, rms, keep


@dataclass
class GasTank:
    """Volumetric gas tank, p/z = (p/z)_i (1 - (1 - support) Gp / G), pressure from the real-gas Z(p)."""

    gas: Gas
    t_res_k: float
    pz_i: float
    giip: float
    support: float = 0.0
    cum: float = 0.0
    log: list = field(default_factory=list)

    def pressure(self, cum: float | None = None) -> float:
        gp = self.cum if cum is None else cum
        target = self.pz_i * max(1.0 - gp * (1.0 - self.support) / self.giip, 1e-3)
        lo, hi = 0.0, max(2.0 * target, 10.0)
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if mid / self.gas.z(max(mid, 1e-3), self.t_res_k) < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def produce(self, volume: float) -> float:
        self.cum = min(self.cum + max(volume, 0.0), self.giip)
        return self.pressure()


@dataclass
class RSDeliverability:
    """q = C (pr^2 - pwh^2)^n with pr in bara and the wellhead pressure in barg. Fit on choke-open rows only."""

    c: float
    n: float

    def rate(self, pr_bara: float, whp_barg: float) -> float:
        dp2 = pr_bara**2 - (whp_barg + P_STD) ** 2
        return 0.0 if dp2 <= 0 else self.c * dp2**self.n

    def whp_for_rate(self, pr_bara: float, q: float) -> float:
        v = pr_bara**2 - (q / self.c) ** (1.0 / self.n)
        return max(v, 0.0) ** 0.5 - P_STD

    @classmethod
    def fit(cls, pr_bara, whp_barg, rate, n_bounds: tuple[float, float] | None = (0.5, 1.0)) -> "RSDeliverability":
        """Log-log least squares; if the exponent falls outside n_bounds it is clipped and C re-fitted."""
        xs, ys = [], []
        for pr, w, q in zip(pr_bara, whp_barg, rate):
            dp2 = pr**2 - (w + P_STD) ** 2
            if dp2 > 0 and q > 0:
                xs.append(math.log(dp2))
                ys.append(math.log(q))
        m = len(xs)
        if m < 3:
            raise ValueError("need at least three rows with positive drawdown and rate")
        sx, sy = sum(xs), sum(ys)
        sxx = sum(v * v for v in xs)
        sxy = sum(a * b for a, b in zip(xs, ys))
        n = (m * sxy - sx * sy) / (m * sxx - sx * sx)
        if n_bounds is not None:
            n = min(max(n, n_bounds[0]), n_bounds[1])
        ln_c = (sy - n * sx) / m
        return cls(math.exp(ln_c), n)
