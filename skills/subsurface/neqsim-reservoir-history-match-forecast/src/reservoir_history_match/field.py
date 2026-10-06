"""Multi-tank material balance: tanks (reservoirs/formations), wells, connections, aquifer and production history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .core import DepletionPath, StreamState


@dataclass
class Tank:
    """One reservoir or formation compartment with its own fluid, volume and aquifer.

    Args:
        name: tank label (formation or segment).
        path: depletion path of its fluid.
        giip_gsm3: initial wet gas in place (standard gas volume of the produced wellstream, 1e9 Sm3).
        aquifer_c: Schilthuis aquifer constant (m3 per day per bar of pressure drop); 0 = volumetric depletion.
        cgr_scale: multiplier from the EOS surface condensate yield to the allocated (plant) condensate.
    """

    name: str
    path: DepletionPath
    giip_gsm3: float
    aquifer_c: float = 0.0
    cgr_scale: float = 1.0

    @property
    def n0(self) -> float:
        return self.giip_gsm3 * 1e9 * self.path.mol_per_sm3_gas0

    @property
    def hcpv0(self) -> float:
        return self.n0 * self.path.v_cell

    def pressure(self, np_mol: float, we_m3: float) -> Tuple[float, bool]:
        n_rel = (self.n0 - np_mol) / (self.n0 * max(1.0 - we_m3 / self.hcpv0, 1e-6))
        return self.path.pressure_for(n_rel), self.path.depleted(n_rel)


@dataclass
class Well:
    """A producer: share of each tank it drains, gas deliverability and water-gas ratio.

    Deliverability is P_res^2 - WHP^2 = a*q + c*q^2 with q in kSm3/d, pressures in bara (a, c are fitted from history).
    """

    name: str
    tank_weights: Dict[str, float]
    a: float = 0.0
    c: float = 0.0
    wgr: float = 0.0  # Sm3 water per Sm3 gas

    def capacity(self, p_res: float, whp: float) -> float:
        """Gas rate (kSm3/d) at tubing-head pressure ``whp``."""
        dp2 = max(p_res**2 - whp**2, 0.0)
        if dp2 <= 0:
            return 0.0
        if self.c <= 1e-12:
            return dp2 / max(self.a, 1e-12)
        return (-self.a + np.sqrt(self.a**2 + 4.0 * self.c * dp2)) / (2.0 * self.c)

    def whp_for(self, p_res: float, q_ksm3d: float) -> float:
        return float(np.sqrt(max(p_res**2 - self.a * q_ksm3d - self.c * q_ksm3d**2, 0.0)))


@dataclass
class Field:
    """Tanks connected by optional transmissibilities and drained by wells."""

    tanks: Dict[str, Tank]
    wells: Dict[str, Well]
    connections: List[Tuple[str, str, float]] = field(default_factory=list)  # (tank a, tank b, kSm3/d per bar)

    def initial_state(self) -> dict:
        return {t: dict(np=0.0, we=0.0) for t in self.tanks}

    def tank_rates(self, well_rates: Dict[str, float]) -> Dict[str, float]:
        """Gas rate per tank (Sm3/d) from well gas rates (Sm3/d) and the well-to-tank shares."""
        q = {t: 0.0 for t in self.tanks}
        for w, rate in well_rates.items():
            wl = self.wells[w]
            tot = sum(wl.tank_weights.values()) or 1.0
            for t, wt in wl.tank_weights.items():
                q[t] += rate * wt / tot
        return q

    def step(self, state: dict, q_tank_sm3d: Dict[str, float], dt_days: float) -> dict:
        """Advance every tank by one step; returns per-tank record and updates ``state`` in place."""
        p0, rec = {}, {}
        for t, tk in self.tanks.items():
            p0[t], _ = tk.pressure(state[t]["np"], state[t]["we"])
        flows = {t: 0.0 for t in self.tanks}
        for a, b, trans in self.connections:
            f = trans * 1e3 * (p0[a] - p0[b])  # Sm3/d of gas equivalent from a to b
            flows[a] += f
            flows[b] -= f
        for t, tk in self.tanks.items():
            st0 = tk.path.stream(p0[t])
            q = q_tank_sm3d.get(t, 0.0) + flows[t]
            n_dot = q * st0.mol_per_sm3_gas
            np_guess = state[t]["np"] + n_dot * dt_days
            we = state[t]["we"] + tk.aquifer_c * max(tk.path.p_init - p0[t], 0.0) * dt_days
            p_end, depl = tk.pressure(np_guess, we)
            st = tk.path.stream(0.5 * (p0[t] + p_end))
            n_dot = q * st.mol_per_sm3_gas
            state[t]["np"] += n_dot * dt_days
            state[t]["we"] = we
            p_end, depl = tk.pressure(state[t]["np"], we)
            rec[t] = dict(p_res=p_end, p_start=p0[t], gas_sm3d=q, cond_sm3d=q * st.cgr_sm3_per_sm3 * tk.cgr_scale, mol_s=n_dot / 86400.0,
                          recovery=state[t]["np"] / tk.n0, we_m3=we, depleted=depl, stream=st)
        return rec

    def simulate(self, rates: pd.DataFrame, dt_days: Optional[Sequence[float]] = None) -> "SimResult":
        """Run a production history. ``rates``: index = step start dates, columns = well gas rates (Sm3/d)."""
        idx = pd.DatetimeIndex(rates.index)
        if dt_days is None:
            ext = idx.append(pd.DatetimeIndex([idx[-1] + (idx[-1] - idx[-2])]))
            dt_days = (ext[1:] - ext[:-1]).days.astype(float)
        state = self.initial_state()
        rows = []
        for k, d in enumerate(idx):
            q_w = {w: float(rates.iloc[k][w]) for w in rates.columns if w in self.wells and np.isfinite(rates.iloc[k][w])}
            rec = self.step(state, self.tank_rates(q_w), float(dt_days[k]))
            for t, r in rec.items():
                rows.append(dict(date=d, tank=t, dt_days=float(dt_days[k]), **{k2: v for k2, v in r.items() if k2 != "stream"}, _stream=r["stream"]))
        return SimResult(self, pd.DataFrame(rows), state)


@dataclass
class SimResult:
    field: Field
    table: pd.DataFrame
    state: dict

    def tanks(self) -> pd.DataFrame:
        return self.table.drop(columns=["_stream"])

    def field_series(self) -> pd.DataFrame:
        g = self.table.groupby("date")
        out = pd.DataFrame({"gas_sm3d": g.gas_sm3d.sum(), "cond_sm3d": g.cond_sm3d.sum()})
        out["cgr_sm3_per_msm3"] = 1e6 * out.cond_sm3d / out.gas_sm3d.replace(0, np.nan)
        return out

    def stream_at(self, tank: str, date) -> StreamState:
        t = self.table[(self.table.tank == tank)]
        row = t.iloc[int(np.argmin(np.abs((pd.DatetimeIndex(t.date) - pd.Timestamp(date)).values.astype("int64"))))]
        return row["_stream"]

    def composition_series(self, tank: str, names: Sequence[str]) -> pd.DataFrame:
        t = self.table[self.table.tank == tank]
        df = pd.DataFrame([s.y for s in t._stream], columns=list(names))
        df.insert(0, "date", list(t.date))
        df.insert(1, "p_res", list(t.p_res))
        return df
