"""Forecast: well deliverability against a minimum wellhead pressure, plateau or profile targets, well schedule and ensembles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

from .field import Field, SimResult


@dataclass
class Scenario:
    """Operating scenario for a forecast.

    Args:
        start, end: forecast window (end exclusive).
        target_gas_sm3d: constant plateau (Sm3/d), a callable of the date, or a Series indexed by date.
        min_whp_bara: minimum wellhead pressure the process allows (scalar, callable or Series); the well capacity limit.
        schedule: per well (online_from, online_to) dates; a missing well is online throughout. New wells need a, c set.
        step_days: step length.
        abandon_sm3d: stop when the field capacity falls below this rate.
    """

    start: pd.Timestamp
    end: pd.Timestamp
    target_gas_sm3d: Union[float, Callable, pd.Series]
    min_whp_bara: Union[float, Callable, pd.Series] = 30.0
    schedule: Dict[str, tuple] = field(default_factory=dict)
    step_days: float = 30.0
    abandon_sm3d: float = 0.5e6


def _val(x, d):
    if callable(x):
        return float(x(d))
    if isinstance(x, pd.Series):
        k = x.index.searchsorted(d, side="right") - 1
        return float(x.iloc[max(k, 0)])
    return float(x)


def forecast(fld: Field, state: dict, sc: Scenario) -> SimResult:
    """Run the forecast from a history ``state`` (copied); rate = min(target, sum of well capacities at the minimum WHP)."""
    state = {t: dict(v) for t, v in state.items()}
    rows = []
    d = pd.Timestamp(sc.start)
    while d < pd.Timestamp(sc.end):
        pres = {t: tk.pressure(state[t]["np"], state[t]["we"])[0] for t, tk in fld.tanks.items()}
        whp_min = _val(sc.min_whp_bara, d)
        cap = {}
        for w, wl in fld.wells.items():
            on = sc.schedule.get(w)
            if on and not (pd.Timestamp(on[0]) <= d < pd.Timestamp(on[1])):
                continue
            p_w = sum(pres[t] * s for t, s in wl.tank_weights.items()) / sum(wl.tank_weights.values())
            cap[w] = wl.capacity(p_w, whp_min) * 1e3  # Sm3/d
        total_cap = sum(cap.values())
        target = _val(sc.target_gas_sm3d, d)
        q_tot = min(target, total_cap)
        if q_tot < sc.abandon_sm3d:
            break
        q_w = {w: q_tot * c / total_cap for w, c in cap.items()}
        wd = {}
        for w, q in q_w.items():
            wl = fld.wells[w]
            p_w = sum(pres[t] * s for t, s in wl.tank_weights.items()) / sum(wl.tank_weights.values())
            wd[w] = dict(q_sm3d=q, whp=wl.whp_for(p_w, q / 1e3), wgr=wl.wgr)
        rec = fld.step(state, fld.tank_rates(q_w), sc.step_days)
        for t, r in rec.items():
            rows.append(dict(date=d, tank=t, dt_days=sc.step_days, **{k: v for k, v in r.items() if k != "stream"}, _stream=r["stream"],
                             capacity_sm3d=total_cap, limited_by="capacity" if total_cap < target else "target", _wells=wd))
        d += pd.Timedelta(days=sc.step_days)
    return SimResult(fld, pd.DataFrame(rows), state)


def well_series(sim: SimResult) -> pd.DataFrame:
    """Per-well forecast table: date, well, gas, water, WHP (forecast results only)."""
    out = []
    for _, r in sim.table.iterrows():
        for w, v in (r.get("_wells") or {}).items():
            out.append(dict(date=r.date, well=w, gas_sm3d=v["q_sm3d"], water_m3d=v["q_sm3d"] * v["wgr"], whp_bara=v["whp"]))
    return pd.DataFrame(out).drop_duplicates(["date", "well"]) if out else pd.DataFrame(columns=["date", "well", "gas_sm3d", "water_m3d", "whp_bara"])


def ensemble(matcher, result, scenario: Scenario, n: int = 20, seed: int = 1) -> pd.DataFrame:
    """P10/P50/P90 of field gas and condensate rates from posterior parameter draws (identifiable parameters only)."""
    draws = result.sample_parameters(n, seed)
    series = []
    for x in draws:
        f = matcher.build(x)
        hist = f.simulate(matcher.rates)
        fc = forecast(f, hist.state, scenario).field_series()
        series.append(fc[["gas_sm3d", "cond_sm3d"]].add_suffix(f"_{len(series)}"))
    df = pd.concat(series, axis=1)
    out = pd.DataFrame(index=df.index)
    for k in ("gas_sm3d", "cond_sm3d"):
        cols = [c for c in df if c.startswith(k)]
        out[f"{k}_p90"] = df[cols].quantile(0.10, axis=1)  # P90 = low case
        out[f"{k}_p50"] = df[cols].quantile(0.50, axis=1)
        out[f"{k}_p10"] = df[cols].quantile(0.90, axis=1)
    return out

