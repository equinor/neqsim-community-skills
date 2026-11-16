"""Virtual flow meter: the rate at which a tuned lift model reproduces a measured downhole gauge pressure."""

from __future__ import annotations

from typing import Callable, Optional


def rate_from_gauge(inlet_pressure_fn: Callable[[float], float], p_gauge_barg: float, lo: float = 0.5, hi: float = 1.5,
                    tol_bar: float = 0.3, max_iter: int = 10) -> Optional[float]:
    """Return the rate scale ``s`` with ``inlet_pressure_fn(s) == p_gauge_barg`` (regula falsi on [lo, hi]).

    ``inlet_pressure_fn(s)`` runs the tuned tubing model from the measured wellhead pressure with the test fluid at
    ``s`` times the test rate and returns the bottomhole (gauge depth) pressure. None when the gauge is not bracketed:
    the lift model and the gauge disagree beyond +-50 % of the rate - check the gauge depth and the tuning first.
    """
    fa, fb = inlet_pressure_fn(lo) - p_gauge_barg, inlet_pressure_fn(hi) - p_gauge_barg
    if fa * fb > 0:
        return None
    a, b = lo, hi
    m = a
    for _ in range(max_iter):
        m = b - fb * (b - a) / (fb - fa)
        fm = inlet_pressure_fn(m) - p_gauge_barg
        if abs(fm) < tol_bar:
            return float(m)
        if fa * fm < 0:
            b, fb = m, fm
        else:
            a, fa = m, fm
    return float(m)
