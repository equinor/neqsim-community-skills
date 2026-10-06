"""Compositional depletion path of a gas-condensate (or dry-gas) reservoir fluid on a NeqSim EOS.

The path is a constant-volume depletion (CVD) from the initial pressure: at each pressure step the cell is brought
back to its initial volume by removing the gas phase (liquid dropout is immobile). Because the path depends only on
pressure, it is computed once per fluid and reused by the material-balance tank for any production history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

SM3_PER_MOL = 0.0236443  # ideal gas at 15 C, 1.01325 bara
STD_T_K = 288.15
STD_P_BARA = 1.01325


def _neqsim():
    from jneqsim import neqsim  # imported lazily so the package imports without a JVM

    return neqsim


class FluidModel:
    """A NeqSim EOS with a fixed component order; flashes any mole-fraction vector.

    Args:
        base_fluid: initialised NeqSim system with all components (mixing rule and parameters already set).
        names: component names in the order of ``base_fluid``.
        heavy_idx: indices scaled by the heavy-end factor in history matching (optional).
        volume_shift: optional (indices, offset) applied to the volume correction of those components.
    """

    def __init__(self, base_fluid, names: Sequence[str], heavy_idx: Optional[Sequence[int]] = None):
        self.base = base_fluid
        self.names = list(names)
        self.heavy_idx = list(heavy_idx or [])

    @classmethod
    def from_components(cls, light: Dict[str, float], tbp: Sequence[tuple] = (), eos: str = "PR"):
        """Build a PR/SRK fluid from database components and TBP pseudo components.

        ``light`` maps a NeqSim database name to a placeholder amount; ``tbp`` is a list of
        (name, molar mass g/mol, density g/cm3). Water is not included.
        """
        ns = _neqsim()
        fluid = ns.thermo.system.SystemPrEos(288.15, 1.01325) if eos == "PR" else ns.thermo.system.SystemSrkEos(288.15, 1.01325)
        names = []
        for nm in light:
            fluid.addComponent(nm, 1.0)
            names.append(nm)
        heavy = []
        for nm, mw, rho in tbp:
            fluid.addTBPfraction(nm, 1.0, mw / 1000.0, rho)
            heavy.append(len(names))
            names.append(nm)
        fluid.setMixingRule(2)
        fluid.init(0)
        return cls(fluid, names, heavy)

    def scaled(self, z: Sequence[float], heavy_scale: float = 1.0) -> np.ndarray:
        z = np.array(z, float)
        if heavy_scale != 1.0 and self.heavy_idx:
            z[self.heavy_idx] *= heavy_scale
        return z / z.sum()

    def flash(self, z: Sequence[float], T_K: float, P_bara: float):
        f = self.base.clone()
        f.setMolarComposition([max(float(v), 1e-20) for v in z])
        f.setTemperature(float(T_K))
        f.setPressure(float(P_bara))
        _neqsim().thermodynamicoperations.ThermodynamicOperations(f).TPflash()
        f.initProperties()
        return f

    def phases(self, z: Sequence[float], T_K: float, P_bara: float) -> dict:
        """Per mole of feed: gas/liquid moles and volumes (m3), gas and liquid compositions. A single phase counts as gas."""
        f = self.flash(z, T_K, P_bara)
        out = dict(ng=0.0, nl=0.0, vg=0.0, vl=0.0, y=None, x=None, nph=f.getNumberOfPhases())
        ntot = f.getTotalNumberOfMoles()
        for i in range(f.getNumberOfPhases()):
            ph = f.getPhase(i)
            is_gas = f.getNumberOfPhases() == 1 or str(ph.getType()).lower() == "gas"
            n = ph.getNumberOfMolesInPhase() / ntot
            vol = n * ph.getMolarMass() / ph.getDensity("kg/m3")
            comp = np.array([ph.getComponent(j).getx() for j in range(len(self.names))])
            if is_gas:
                out["ng"] += n
                out["vg"] += vol
                out["y"] = comp
            else:
                out["nl"] += n
                out["vl"] += vol
                out["x"] = comp
        return out

    def surface_yield(self, z: Sequence[float]) -> dict:
        """Standard-condition split of one mole of wellstream ``z``: gas Sm3, condensate Sm3 and molar mass (kg/mol)."""
        s = self.phases(z, STD_T_K, STD_P_BARA)
        return dict(gas_sm3=s["ng"] * SM3_PER_MOL, cond_sm3=s["vl"])

    def dew_point(self, z: Sequence[float], T_K: float, p_lo: float = 100.0, p_hi: float = 900.0, tol: float = 0.5) -> float:
        if self.phases(z, T_K, p_hi)["nph"] > 1:
            return float("nan")
        lo, hi = p_lo, p_hi
        if self.phases(z, T_K, lo)["nph"] == 1:
            return float("nan")
        while hi - lo > tol:
            mid = 0.5 * (lo + hi)
            if self.phases(z, T_K, mid)["nph"] > 1:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)


@dataclass
class StreamState:
    """Produced wellstream at one pressure: composition and surface yields."""

    y: np.ndarray
    gas_sm3_per_mol: float
    cond_sm3_per_mol: float

    @property
    def mol_per_sm3_gas(self) -> float:
        return 1.0 / self.gas_sm3_per_mol

    @property
    def cgr_sm3_per_sm3(self) -> float:
        return self.cond_sm3_per_mol / self.gas_sm3_per_mol


class DepletionPath:
    """CVD path of one reservoir fluid: moles left, liquid saturation, stream composition and surface yield versus pressure."""

    def __init__(self, fluid: FluidModel, z0: Sequence[float], T_K: float, p_init: float, p_min: float = 60.0, dp: float = 10.0):
        self.fluid, self.T_K, self.p_init = fluid, float(T_K), float(p_init)
        self.z0 = np.array(z0, float) / np.sum(z0)
        self.p = np.arange(p_init, p_min - 1e-9, -dp)
        self._compute()

    def _compute(self):
        fl, T = self.fluid, self.T_K
        s0 = fl.phases(self.z0, T, self.p_init)
        self.v_cell = s0["vg"] + s0["vl"]  # m3 per mole in place at the initial pressure
        z, n = self.z0.copy(), 1.0
        n_rem, s_liq, ys, gas, cond, zc = [], [], [], [], [], []
        for p in self.p:
            s = fl.phases(z, T, p)
            v_tot = n * (s["vg"] + s["vl"])
            dv = v_tot - self.v_cell
            y = s["y"] if s["y"] is not None else z
            if dv > 0 and s["ng"] > 0 and p < self.p_init:
                vmol_g = s["vg"] / s["ng"]
                nrem = min(dv / vmol_g, 0.95 * n * s["ng"])
                z_new = np.clip((n * z - nrem * y) / (n - nrem), 1e-20, None)
                z, n = z_new / z_new.sum(), n - nrem
            n_rem.append(n)
            s_liq.append(n * s["vl"] / self.v_cell)
            ys.append(np.array(y))
            zc.append(z.copy())
            sy = fl.surface_yield(y)
            gas.append(sy["gas_sm3"])
            cond.append(sy["cond_sm3"])
        self.n_rem = np.array(n_rem)
        self.s_liq = np.array(s_liq)
        self.y = np.array(ys)
        self.z_cell = np.array(zc)
        self.gas_sm3_per_mol = np.array(gas)
        self.cond_sm3_per_mol = np.array(cond)
        # the initial pressure row produces the initial fluid
        self.mol_per_sm3_gas0 = 1.0 / self.gas_sm3_per_mol[0]

    def pressure_for(self, n_rel: float) -> float:
        """Pressure at which the cell holds ``n_rel`` moles per initial mole (increasing in pressure)."""
        order = np.argsort(self.n_rem)
        return float(np.interp(n_rel, self.n_rem[order], self.p[order]))

    def depleted(self, n_rel: float) -> bool:
        return n_rel < float(self.n_rem.min())

    def stream(self, p: float) -> StreamState:
        order = np.argsort(self.p)
        pp = self.p[order]
        y = np.array([np.interp(p, pp, self.y[order][:, j]) for j in range(self.y.shape[1])])
        y = y / y.sum()
        return StreamState(y, float(np.interp(p, pp, self.gas_sm3_per_mol[order])), float(np.interp(p, pp, self.cond_sm3_per_mol[order])))

    def composition_table(self, names: Optional[Sequence[str]] = None):
        import pandas as pd

        df = pd.DataFrame(self.y, columns=names or self.fluid.names)
        df.insert(0, "p_bara", self.p)
        df["s_liq"] = self.s_liq
        df["cgr_sm3_per_msm3"] = 1e6 * self.cond_sm3_per_mol / self.gas_sm3_per_mol
        return df
