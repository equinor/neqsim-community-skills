"""Connect the reservoir model to process models: wellstreams per date and well, and history + future process runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .field import Field, SimResult
from .forecast import well_series

WATER_MW = 18.01528


@dataclass
class WellStream:
    """Process feed of one well at one date: wellstream mole fractions (hydrocarbons), molar rate and wellhead state."""

    well: str
    date: pd.Timestamp
    composition: np.ndarray  # reservoir wellstream, mole fractions of the EOS components
    gas_sm3d: float
    water_m3d: float
    mol_s: float  # hydrocarbon wellstream
    whp_bara: Optional[float] = None
    wht_c: Optional[float] = None
    cond_sm3d: float = 0.0


def well_streams_at(sim: SimResult, date, well_rates_sm3d: Dict[str, float], wgr: Optional[Dict[str, float]] = None,
                    whp: Optional[Dict[str, float]] = None, wht: Optional[Dict[str, float]] = None) -> List[WellStream]:
    """Wellstream of each well at ``date``: tank compositions mixed by the well shares, molar rate from the surface gas rate."""
    out = []
    for w, q in well_rates_sm3d.items():
        wl = sim.field.wells[w]
        tot = sum(wl.tank_weights.values())
        mol, comp, cond = 0.0, 0.0, 0.0
        for t, share in wl.tank_weights.items():
            st = sim.stream_at(t, date)
            n = q * share / tot * st.mol_per_sm3_gas
            mol += n
            comp = comp + n * st.y
            cond += q * share / tot * st.cgr_sm3_per_sm3 * sim.field.tanks[t].cgr_scale
        comp = comp / mol if mol > 0 else comp
        wg = (wgr or {}).get(w, wl.wgr)
        out.append(WellStream(w, pd.Timestamp(date), comp, q, q * wg, mol / 86400.0, (whp or {}).get(w), (wht or {}).get(w), cond))
    return out


def stream_table(streams: Sequence[WellStream], names: Sequence[str]) -> pd.DataFrame:
    """Flat table (one row per well and date) for a process-model case workbook."""
    rows = []
    for s in streams:
        rows.append(dict(date=s.date, well=s.well, gas_Sm3d=s.gas_sm3d, cond_Sm3d=s.cond_sm3d, water_m3d=s.water_m3d, mol_s=s.mol_s,
                         whp_barg=None if s.whp_bara is None else s.whp_bara - 1.01325, wht_C=s.wht_c, **dict(zip(names, s.composition))))
    return pd.DataFrame(rows)


def run_process_series(sim: SimResult, dates: Sequence, rates_at: Callable[[pd.Timestamp], Dict[str, float]],
                       run_case: Callable[[pd.Timestamp, List[WellStream]], dict], whp_at: Optional[Callable] = None) -> pd.DataFrame:
    """Run a process model for each date with reservoir-driven wellstreams and collect its KPIs.

    ``rates_at(date)`` gives well gas rates (Sm3/d) for the date (history or forecast); ``run_case(date, streams)`` builds
    and solves the process model (for example a ProcessPilot simulator whose well feeds are replaced) and returns a dict of
    KPIs (export gas, condensate, compressor power, utilisation). Failures are recorded, not raised.
    """
    rows = []
    for d in pd.to_datetime(list(dates)):
        streams = well_streams_at(sim, d, rates_at(d), whp=None if whp_at is None else whp_at(d))
        try:
            kpi = run_case(d, streams)
            kpi["status"] = "ok"
        except Exception as exc:  # noqa: BLE001 - a failed date must not stop the series
            kpi = dict(status=f"failed: {exc!r}")
        rows.append(dict(date=d, **kpi))
    return pd.DataFrame(rows)


def history_forecast_table(hist: SimResult, fc: SimResult) -> pd.DataFrame:
    """Field gas, condensate, CGR and tank pressures for history and forecast on one table."""
    parts = []
    for tag, s in (("history", hist), ("forecast", fc)):
        f = s.field_series()
        p = s.tanks().pivot(index="date", columns="tank", values="p_res").add_prefix("p_res_")
        parts.append(f.join(p).assign(period=tag))
    return pd.concat(parts)
