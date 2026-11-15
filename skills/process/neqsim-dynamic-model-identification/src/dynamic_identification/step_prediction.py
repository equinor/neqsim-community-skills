"""Hybrid step forecasts: NeqSim gives the steady change, identified dynamics give the path to it.

A manipulated move (for example a well choke) is predicted as a first-order-plus-delay response

    y(t) = y0 + dy_ss * (1 - exp(-(t - delay) / tau))   for t > delay,

where ``dy_ss`` comes from re-solving a steady NeqSim flowsheet at the new setting and ``tau``/``delay`` come from
past moves in plant data (``fit_step_dynamics`` here, or ``identify_unit``). The helpers in this module need only
numpy; the data-only cross-check uses ``identify_unit`` and ``simulate_unit``.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


def fopdt_step(t_s: Sequence[float], dy: float, tau_s: float, delay_s: float) -> np.ndarray:
    """Deviation of a first-order-plus-delay response to a step at ``t = 0`` (zero before the delay)."""
    t = np.asarray(t_s, dtype=float) - float(delay_s)
    out = np.zeros_like(t)
    on = t > 0
    out[on] = dy * (1.0 - np.exp(-t[on] / max(float(tau_s), 1e-9)))
    return out


def hybrid_step_forecast(y0: float, dy_ss: float, tau_s: float, delay_s: float, horizon_s: float,
                         timebase_s: float = 60.0) -> Dict[str, object]:
    """Forecast after a move at ``t = 0``: the steady change from physics and the timing from identified dynamics.

    Returns the time axis, the trajectory and the times at which 63 % and 95 % of the change is reached.
    """
    t = np.arange(0.0, float(horizon_s) + 0.5 * timebase_s, float(timebase_s))
    y = float(y0) + fopdt_step(t, dy_ss, tau_s, delay_s)
    return {"t_s": t, "y": y, "y_final": float(y0) + float(dy_ss),
            "t63_s": float(delay_s) + float(tau_s), "t95_s": float(delay_s) + 3.0 * float(tau_s)}


def fit_step_dynamics(t_s: Sequence[float], y: Sequence[float], baseline_s: float = 3600.0,
                      taus_s: Optional[Iterable[float]] = None, delays_s: Optional[Iterable[float]] = None,
                      dy_fixed: Optional[float] = None) -> Dict[str, float]:
    """Fit gain, time constant and delay to one step window (step at ``t = 0``; negative times are the baseline).

    Grid search over ``tau`` and ``delay``; for each pair the step size is the least-squares value (or ``dy_fixed``).
    Also returns the baseline noise and the signal-to-noise ratio ``|dy| / noise``: below about 3 the timing is not
    identifiable from this move. NaN samples are ignored.
    """
    t = np.asarray(t_s, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(y)
    base = ok & (t <= 0) & (t >= -float(baseline_s))
    if base.sum() < 3:
        raise ValueError("need at least three valid baseline samples before the step")
    y0 = float(np.mean(y[base]))
    noise = float(np.std(y[base], ddof=1))
    after = ok & (t > 0)
    tt, dev = t[after], y[after] - y0
    span = float(tt.max()) if tt.size else 0.0
    taus = np.asarray(list(taus_s) if taus_s is not None else np.geomspace(60.0, max(span, 600.0), 40))
    delays = np.asarray(list(delays_s) if delays_s is not None else np.arange(0.0, min(span / 3.0, 3600.0) + 1.0, 300.0))
    best = None
    for d in delays:
        for tau in taus:
            shape = fopdt_step(tt, 1.0, tau, d)
            den = float(shape @ shape)
            if den <= 0:
                continue
            dy = float(dy_fixed) if dy_fixed is not None else float(shape @ dev) / den
            sse = float(np.sum((dev - dy * shape) ** 2))
            if best is None or sse < best[0]:
                best = (sse, dy, float(tau), float(d))
    sse, dy, tau, d = best
    sst = float(np.sum((dev - dev.mean()) ** 2)) or 1e-12
    return {"y0": y0, "dy": dy, "tau_s": tau, "delay_s": d, "fit_pct": 100.0 * (1.0 - sse / sst),
            "noise_std": noise, "snr": abs(dy) / noise if noise > 0 else float("inf"), "n_after": int(after.sum())}


def pooled_dynamics(fits: Sequence[Mapping[str, float]], min_snr: float = 3.0) -> Dict[str, float]:
    """Median time constant and delay over fitted moves whose signal-to-noise ratio is at least ``min_snr``."""
    good = [f for f in fits if f.get("snr", 0.0) >= min_snr]
    if not good:
        raise ValueError(f"no move with signal-to-noise >= {min_snr}")
    return {"tau_s": float(np.median([f["tau_s"] for f in good])),
            "delay_s": float(np.median([f["delay_s"] for f in good])), "n_moves": len(good)}


def score_forecast(y_meas: Sequence[float], y_pred: Sequence[float], y0: float,
                   tail: int = 12) -> Dict[str, float]:
    """Compare a forecast with the measured response after the move.

    ``skill`` is ``1 - rms / rms_persistence`` against the naive forecast "nothing changes" (``y0``): positive means
    the forecast is better than assuming no effect. ``final_*`` use the mean of the last ``tail`` samples.
    """
    ym, yp = np.asarray(y_meas, dtype=float), np.asarray(y_pred, dtype=float)
    ok = np.isfinite(ym) & np.isfinite(yp)
    ym, yp = ym[ok], yp[ok]
    rms = float(np.sqrt(np.mean((ym - yp) ** 2)))
    rms0 = float(np.sqrt(np.mean((ym - y0) ** 2)))
    fm, fp = float(np.mean(ym[-tail:])) - y0, float(np.mean(yp[-tail:])) - y0
    return {"rms": rms, "rms_persistence": rms0, "skill": 1.0 - rms / rms0 if rms0 > 0 else float("nan"),
            "final_meas": fm, "final_pred": fp, "final_error": fp - fm,
            "sign_agrees": bool(np.sign(fm) == np.sign(fp)) if abs(fm) > 0 else None}


def detect_steps(moves: pd.DataFrame, min_step: float, step_samples: int, quiet_before: int, quiet_after: int,
                 max_ripple: float = 1.0, max_other_move: float = 1.0) -> List[Dict[str, object]]:
    """Isolated steps: one column moves at least ``min_step`` within ``step_samples`` while it and all other
    columns stay within ``max_ripple`` / ``max_other_move`` for ``quiet_before`` samples before and ``quiet_after``
    samples after. ``moves`` holds the manipulated variables (for example every well choke) on a regular time base.
    """
    out: List[Dict[str, object]] = []
    for col in moves.columns:
        x = moves[col].to_numpy(dtype=float)
        others = moves.drop(columns=col).to_numpy(dtype=float)
        i = quiet_before
        while i < len(x) - quiet_after - step_samples:
            du = x[i + step_samples] - x[i]
            pre = x[i - quiet_before:i + 1]
            post = x[i + step_samples:i + step_samples + quiet_after]
            if (abs(du) >= min_step and np.nanmax(pre) - np.nanmin(pre) < max_ripple
                    and np.nanmax(post) - np.nanmin(post) < max_ripple):
                win = others[i - quiet_before:i + step_samples + quiet_after]
                other_move = float(np.nanmax(np.nanmax(win, axis=0) - np.nanmin(win, axis=0))) if win.size else 0.0
                if other_move < max_other_move:
                    out.append({"variable": col, "time": moves.index[i], "index": i, "u0": float(x[i]),
                                "u1": float(x[i + step_samples]), "du": float(du), "other_move": other_move})
                i += step_samples + quiet_after
            else:
                i += 1
    return out
