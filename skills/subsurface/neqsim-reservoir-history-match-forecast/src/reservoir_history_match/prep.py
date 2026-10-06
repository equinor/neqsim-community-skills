"""Turn production-database exports into the inputs of the history match: monthly well rates and observations."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd


def monthly_rates(wells: pd.DataFrame, well_col: str = "well", date_col: str = "date", gas_col: str = "gas_sm3") -> pd.DataFrame:
    """Mean daily gas rate (Sm3/d) per well and month; rows with no production are dropped."""
    d = wells.assign(month=pd.to_datetime(wells[date_col]).dt.to_period("M").dt.to_timestamp())
    r = d.pivot_table(index="month", columns=well_col, values=gas_col, aggfunc="mean").fillna(0.0)
    return r[r.sum(axis=1) > 0]


def field_cgr_observations(gas_daily: pd.Series, cond_daily: pd.Series, months: pd.DatetimeIndex, rel_sigma: float = 0.12) -> pd.DataFrame:
    """Monthly condensate-gas ratio (Sm3/MSm3) of the field from daily allocated volumes (Sm3), with a relative sigma."""
    g = gas_daily.resample("MS").sum()
    c = cond_daily.resample("MS").sum()
    cgr = (c / g.replace(0, np.nan) * 1e6).reindex(months).dropna()
    return pd.DataFrame(dict(date=cgr.index, tank="FIELD", kind="cgr", value=cgr.values, sigma=rel_sigma * cgr.values))


def shut_in_pressure_observations(wells: pd.DataFrame, tank_col: str = "tank", wellbore_col: str = "wellbore", date_col: str = "date",
                                  hours_col: str = "on_stream_hrs", dh_col: str = "dh_press", min_age_days: int = 540, p_range=(30.0, 830.0),
                                  exclude: Optional[dict] = None, quantile: float = 0.25, sigma: float = 20.0, min_days: int = 2) -> pd.DataFrame:
    """Static reservoir-pressure observations (bara) from downhole gauges of shut-in wells.

    A reading counts when the well is shut in (< 1 h on stream) and the wellbore is older than ``min_age_days`` (new completions
    read virgin or isolated compartments). Per tank and month the lower ``quantile`` of the well medians is used because
    shut-in gauges read at or below static pressure and compartments only add high readings. ``exclude`` maps a tank to a
    regex of wellbores that belong to other compartments.
    """
    w = wells.copy()
    w[date_col] = pd.to_datetime(w[date_col])
    w["month"] = w[date_col].dt.to_period("M").dt.to_timestamp()
    first = w.groupby(wellbore_col)[date_col].transform("min")
    s = w[(w[hours_col] < 1) & (w[dh_col] > p_range[0]) & (w[dh_col] < p_range[1]) & ((w[date_col] - first).dt.days > min_age_days)]
    rows = []
    for tank, d in s.groupby(tank_col):
        if exclude and tank in exclude:
            d = d[~d[wellbore_col].str.contains(exclude[tank])]
        pw = d.groupby(["month", wellbore_col])[dh_col].agg(["median", "count"])
        pw = pw[pw["count"] >= min_days].reset_index()
        m = pw.groupby("month")["median"].quantile(quantile)
        rows.append(pd.DataFrame(dict(date=m.index, tank=tank, kind="p_res", value=m.values, sigma=sigma)))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "tank", "kind", "value", "sigma"])


def deliverability_history(wells: pd.DataFrame, well_col: str = "well", date_col: str = "date", gas_col: str = "gas_sm3", hours_col: str = "on_stream_hrs",
                           whp_col: str = "whp_barg", water_col: Optional[str] = None, min_hours: float = 12.0) -> pd.DataFrame:
    """Daily on-stream rate (kSm3/d) and tubing-head pressure (bara) per well for ``fit_deliverability``."""
    d = wells[wells[hours_col] > min_hours].copy()
    out = pd.DataFrame(dict(date=pd.to_datetime(d[date_col]), well=d[well_col], q_ksm3d=d[gas_col] / 1e3 / (d[hours_col].clip(lower=1) / 24.0), whp=d[whp_col] + 1.01325))
    if water_col:
        out["water_sm3d"] = d[water_col]
    return out.dropna(subset=["whp"])
