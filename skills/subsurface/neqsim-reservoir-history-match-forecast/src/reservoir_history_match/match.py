"""History matching: fit tank volume, aquifer, condensate yield scale and heavy-end scale to production and pressure data."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .core import DepletionPath, FluidModel
from .field import Field, SimResult, Tank, Well

PARAM_NAMES = ("giip_gsm3", "aquifer_c", "cgr_scale", "heavy_scale")


@dataclass
class TankSpec:
    """Everything needed to build a Tank; parameters listed in PARAM_NAMES can be matched."""

    name: str
    fluid: FluidModel
    z0: Sequence[float]
    T_K: float
    p_init: float
    giip_gsm3: float
    aquifer_c: float = 0.0
    cgr_scale: float = 1.0
    heavy_scale: float = 1.0
    p_min: float = 60.0
    dp: float = 10.0


@dataclass
class Param:
    tank: str
    name: str
    lo: float
    hi: float
    x0: Optional[float] = None  # defaults to the spec value
    prior_sigma: Optional[float] = None  # relative (log) prior width; None = no prior


class Matcher:
    """Least-squares history match of a multi-tank field to pressure and condensate-gas-ratio observations.

    Observations (DataFrame): date, tank ('FIELD' allowed for cgr), kind in {'p_res', 'cgr'}, value, sigma.
    cgr values are Sm3 per MSm3 and compare with the allocated condensate, so cgr_scale is usually matched too.
    """

    def __init__(self, specs: Sequence[TankSpec], wells: Dict[str, Well], rates: pd.DataFrame, obs: pd.DataFrame,
                 params: Sequence[Param], connections: Sequence[Tuple[str, str, float]] = ()):
        self.specs = {s.name: s for s in specs}
        self.wells, self.rates, self.obs = wells, rates, obs.copy()
        self.obs["date"] = pd.to_datetime(self.obs["date"])
        self.params, self.connections = list(params), list(connections)
        self._paths: Dict[tuple, DepletionPath] = {}
        for p in self.params:
            if p.name not in PARAM_NAMES:
                raise ValueError(f"unknown parameter {p.name}")
            if p.x0 is None:
                p.x0 = getattr(self.specs[p.tank], p.name)

    def path(self, spec: TankSpec) -> DepletionPath:
        key = (spec.name, round(spec.heavy_scale, 4))
        if key not in self._paths:
            z = spec.fluid.scaled(spec.z0, spec.heavy_scale)
            self._paths[key] = DepletionPath(spec.fluid, z, spec.T_K, spec.p_init, spec.p_min, spec.dp)
        return self._paths[key]

    def build(self, x: Optional[Sequence[float]] = None) -> Field:
        specs = {k: replace(v) for k, v in self.specs.items()}
        if x is not None:
            for p, v in zip(self.params, x):
                setattr(specs[p.tank], p.name, float(v))
        tanks = {k: Tank(k, self.path(s), s.giip_gsm3, s.aquifer_c, s.cgr_scale) for k, s in specs.items()}
        return Field(tanks, self.wells, list(self.connections))

    def _model_values(self, sim: SimResult) -> np.ndarray:
        tab, fs = sim.tanks(), sim.field_series()
        out = []
        for o in self.obs.itertuples():
            if o.kind == "p_res":
                d = tab[tab.tank == o.tank]
                k = d.date.searchsorted(o.date, side="right") - 1
                out.append(float(d.p_res.iloc[max(k, 0)]))
            elif o.kind == "cgr":
                if o.tank == "FIELD":
                    k = fs.index.searchsorted(o.date, side="right") - 1
                    out.append(float(fs.cgr_sm3_per_msm3.iloc[max(k, 0)]))
                else:
                    d = tab[tab.tank == o.tank]
                    k = d.date.searchsorted(o.date, side="right") - 1
                    r = d.iloc[max(k, 0)]
                    out.append(1e6 * r.cond_sm3d / r.gas_sm3d if r.gas_sm3d > 0 else np.nan)
            else:
                raise ValueError(o.kind)
        return np.array(out)

    def residuals(self, x) -> np.ndarray:
        sim = self.build(x).simulate(self.rates)
        r = (self._model_values(sim) - self.obs.value.values) / self.obs.sigma.values
        pri = [np.log(max(v, 1e-12) / max(p.x0, 1e-12)) / p.prior_sigma for p, v in zip(self.params, x) if p.prior_sigma]
        return np.concatenate([np.nan_to_num(r, nan=0.0), np.array(pri, float)])

    def run(self, max_nfev: int = 40) -> "MatchResult":
        from scipy.optimize import least_squares

        lo = [p.lo for p in self.params]
        hi = [p.hi for p in self.params]
        x0 = np.clip([p.x0 for p in self.params], lo, hi)
        scale = np.maximum(np.abs(x0), 1e-3)
        sol = least_squares(self.residuals, x0, bounds=(lo, hi), x_scale=scale, diff_step=0.02, max_nfev=max_nfev)
        field_ = self.build(sol.x)
        sim = field_.simulate(self.rates)
        obs = self.obs.assign(model=self._model_values(sim))
        obs["residual"] = obs.model - obs.value
        dof = max(len(sol.fun) - len(sol.x), 1)
        try:
            cov = np.linalg.inv(sol.jac.T @ sol.jac) * (2 * sol.cost / dof)
            std = np.sqrt(np.clip(np.diag(cov), 0, None))
        except np.linalg.LinAlgError:
            cov, std = None, np.full(len(sol.x), np.nan)
        rows = []
        for p, v, s in zip(self.params, sol.x, std):
            at_bound = bool(abs(v - p.lo) < 1e-3 * (p.hi - p.lo) or abs(v - p.hi) < 1e-3 * (p.hi - p.lo))
            rows.append(dict(tank=p.tank, name=p.name, initial=p.x0, tuned=float(v), lower=p.lo, upper=p.hi, std=float(s), at_bound=at_bound))
        return MatchResult(pd.DataFrame(rows), field_, sim, obs, sol.cost, sol.nfev, cov)


@dataclass
class MatchResult:
    parameters: pd.DataFrame
    field: Field
    sim: SimResult
    obs: pd.DataFrame
    cost: float
    nfev: int
    cov: Optional[np.ndarray] = None

    def quality(self) -> pd.DataFrame:
        """RMSE, bias and mean relative error per observation kind and tank."""
        g = self.obs.groupby(["kind", "tank"])
        q = g[["value", "residual"]].apply(lambda d: pd.Series(dict(n=len(d), bias=d.residual.mean(), rmse=float(np.sqrt((d.residual**2).mean())),
                                              rel_err_pct=100 * float((d.residual.abs() / d.value.abs()).mean())))).reset_index()
        return q

    def sample_parameters(self, n: int, seed: int = 1) -> np.ndarray:
        """Draws from the Gaussian posterior (for ensemble forecasts); clipped to the bounds."""
        if self.cov is None:
            raise ValueError("no covariance (singular Jacobian): parameters are not identifiable")
        rng = np.random.default_rng(seed)
        x = rng.multivariate_normal(self.parameters.tuned.values, self.cov, size=n)
        return np.clip(x, self.parameters.lower.values, self.parameters.upper.values)


def fit_deliverability(sim: SimResult, wells_hist: pd.DataFrame, trim: float = 0.1) -> Dict[str, dict]:
    """Fit P_res^2 - WHP^2 = a*q + c*q^2 per well from daily history and the matched tank pressure.

    ``wells_hist`` columns: date, well, q_ksm3d, whp (bara) and optionally water_sm3d for the water-gas ratio.
    Returns per well: a, c, wgr, n, r2.
    """
    field = sim.field
    tab = sim.tanks()
    out: Dict[str, dict] = {}
    for w, g in wells_hist.groupby("well"):
        if w not in field.wells:
            continue
        g = g[(g.q_ksm3d > 0) & g.whp.notna()].copy()
        if len(g) < 10:
            continue
        wt = field.wells[w].tank_weights
        tot = sum(wt.values())
        pres = np.zeros(len(g))
        for t, share in wt.items():
            d = tab[tab.tank == t]
            k = np.clip(d.date.searchsorted(pd.to_datetime(g.date), side="right") - 1, 0, len(d) - 1)
            pres += share / tot * d.p_res.values[k]
        g["y"] = (pres**2 - g.whp**2) / g.q_ksm3d
        g = g[g.y > 0]
        if len(g) < 10:
            continue
        for _ in range(2):  # trim the largest residuals once
            if g.q_ksm3d.std() < 1e-3 * g.q_ksm3d.mean():
                break
            c, a = np.polyfit(g.q_ksm3d, g.y, 1)
            res = np.abs(g.y - (a + c * g.q_ksm3d))
            g = g[res <= np.quantile(res, 1 - trim)]
        if g.q_ksm3d.std() < 1e-3 * g.q_ksm3d.mean():
            c, a = 0.0, float(g.y.mean())  # no rate variation: only a single point on the deliverability curve
        else:
            c, a = np.polyfit(g.q_ksm3d, g.y, 1)
        if c < 0:
            c, a = 0.0, float(g.y.mean())
        a = max(a, 1e-6)
        pred = a + c * g.q_ksm3d
        r2 = 1 - ((g.y - pred) ** 2).sum() / max(((g.y - g.y.mean()) ** 2).sum(), 1e-12)
        wgr = float("nan")
        if "water_sm3d" in wells_hist:
            gg = wells_hist[(wells_hist.well == w) & (wells_hist.q_ksm3d > 0)].tail(180)
            wgr = float(gg.water_sm3d.sum() / (1e3 * gg.q_ksm3d.sum())) if len(gg) else float("nan")
        out[w] = dict(a=float(a), c=float(c), wgr=wgr, n=int(len(g)), r2=float(r2))
    return out
