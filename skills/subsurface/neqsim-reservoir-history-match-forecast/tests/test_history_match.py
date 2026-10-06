import numpy as np
import pandas as pd
import pytest

pytest.importorskip("jneqsim")

from reservoir_history_match import (  # noqa: E402
    DepletionPath, FluidModel, Field, Matcher, Param, Scenario, Tank, TankSpec, Well, fit_deliverability, forecast, well_series,
    well_streams_at, stream_table, history_forecast_table,
)

LIGHT = {"nitrogen": 0, "CO2": 0, "methane": 0, "ethane": 0, "propane": 0, "i-butane": 0, "n-butane": 0, "i-pentane": 0, "n-pentane": 0, "n-hexane": 0}
TBP = [("C7", 96.0, 0.74), ("C10", 150.0, 0.80), ("C15", 210.0, 0.85), ("C25", 350.0, 0.90)]
Z_A = [0.004, 0.02, 0.70, 0.085, 0.045, 0.008, 0.016, 0.007, 0.008, 0.012, 0.03, 0.035, 0.02, 0.01]
Z_B = [0.003, 0.03, 0.74, 0.07, 0.035, 0.006, 0.012, 0.005, 0.006, 0.009, 0.025, 0.03, 0.015, 0.01]
T_K = 423.15
P0 = 600.0


@pytest.fixture(scope="module")
def fluid():
    return FluidModel.from_components(LIGHT, TBP)


@pytest.fixture(scope="module")
def specs(fluid):
    return [TankSpec("A", fluid, Z_A, T_K, P0, giip_gsm3=60.0, p_min=120.0, dp=20.0), TankSpec("B", fluid, Z_B, T_K, P0, giip_gsm3=40.0, p_min=120.0, dp=20.0)]


def _truth_field(specs):
    from reservoir_history_match.match import Matcher as M

    m = M(specs, {}, pd.DataFrame(), pd.DataFrame(dict(date=[], tank=[], kind=[], value=[], sigma=[])), [])
    return m


def _rates():
    idx = pd.date_range("2010-01-01", periods=96, freq="MS")
    r = pd.DataFrame(index=idx)
    for k, (w, base) in enumerate((("W1", 4.0e6), ("W2", 3.5e6), ("W3", 3.0e6), ("W4", 2.0e6))):
        r[w] = base * (1 + 0.3 * np.sin(np.arange(len(idx)) / 4.0 + k))
    return r


WELLS = {"W1": Well("W1", {"A": 1.0}, a=30.0, c=0.02), "W2": Well("W2", {"A": 1.0}, a=35.0, c=0.02), "W3": Well("W3", {"B": 1.0}, a=40.0, c=0.03),
         "W4": Well("W4", {"A": 0.5, "B": 0.5}, a=45.0, c=0.03)}


def test_depletion_path_physical(fluid):
    p = DepletionPath(fluid, Z_A, T_K, P0, 120.0, 20.0)
    assert np.all(np.diff(p.n_rem) <= 1e-9)  # moles in the cell fall as pressure falls
    assert p.n_rem[-1] < 0.9
    assert p.s_liq.max() > 0.0  # retrograde dropout appears
    cgr = 1e6 * p.cond_sm3_per_mol / p.gas_sm3_per_mol
    assert cgr[-1] < cgr[0]  # the produced stream gets leaner
    assert abs(p.y[-1].sum() - 1.0) < 1e-6


def test_single_tank_recovers_volume(specs):
    spec = specs[0]
    wells = {"W1": Well("W1", {"A": 1.0})}
    rates = _rates()[["W1"]] * 3.0
    truth = Matcher([TankSpec(**{**spec.__dict__, "giip_gsm3": 50.0})], wells, rates, pd.DataFrame(dict(date=[rates.index[0]], tank=["A"], kind=["p_res"], value=[0.0], sigma=[1.0])), [])
    sim = truth.build().simulate(rates)
    tab = sim.tanks()
    pick = tab.iloc[::8]
    obs = pd.concat([
        pd.DataFrame(dict(date=pick.date, tank="A", kind="p_res", value=pick.p_res + np.random.default_rng(1).normal(0, 2, len(pick)), sigma=3.0)),
        pd.DataFrame(dict(date=tab.date, tank="A", kind="cgr", value=1e6 * tab.cond_sm3d / tab.gas_sm3d, sigma=10.0)),
    ])
    m = Matcher([spec], wells, rates, obs, [Param("A", "giip_gsm3", 10.0, 200.0)])
    res = m.run(max_nfev=25)
    assert res.parameters.tuned.iloc[0] == pytest.approx(50.0, rel=0.1)
    assert res.quality().query("kind == 'p_res'").rmse.iloc[0] < 6.0


def test_two_tanks_recover_volumes(specs):
    rates = _rates()
    truth_specs = [TankSpec(**{**specs[0].__dict__, "giip_gsm3": 35.0}), TankSpec(**{**specs[1].__dict__, "giip_gsm3": 25.0})]
    t = Matcher(truth_specs, WELLS, rates, pd.DataFrame(dict(date=[rates.index[0]], tank=["A"], kind=["p_res"], value=[0.0], sigma=[1.0])), [])
    sim = t.build().simulate(rates)
    tab = sim.tanks()
    rng = np.random.default_rng(2)
    pick = tab[tab.date.isin(rates.index[::12])]
    obs = pd.concat([
        pd.DataFrame(dict(date=pick.date, tank=pick.tank, kind="p_res", value=pick.p_res + rng.normal(0, 2, len(pick)), sigma=3.0)),
        pd.DataFrame(dict(date=sim.field_series().index, tank="FIELD", kind="cgr", value=sim.field_series().cgr_sm3_per_msm3 * (1 + rng.normal(0, 0.02, len(rates))), sigma=15.0)),
    ])
    m = Matcher(specs, WELLS, rates, obs, [Param("A", "giip_gsm3", 10.0, 200.0), Param("B", "giip_gsm3", 10.0, 200.0)])
    res = m.run(max_nfev=30)
    got = dict(zip(res.parameters.tank, res.parameters.tuned))
    assert got["A"] == pytest.approx(35.0, rel=0.15)
    assert got["B"] == pytest.approx(25.0, rel=0.15)


def test_deliverability_fit_and_forecast(specs):
    rates = _rates()
    fld = Field({s.name: Tank(s.name, DepletionPath(s.fluid, s.z0, s.T_K, s.p_init, s.p_min, s.dp), s.giip_gsm3) for s in specs}, WELLS)
    sim = fld.simulate(rates)
    tab = sim.tanks()
    hist = []
    for w, wl in WELLS.items():
        for d, row in rates[[w]].iterrows():
            pres = sum(tab[(tab.tank == t) & (tab.date == d)].p_res.iloc[0] * s for t, s in wl.tank_weights.items()) / sum(wl.tank_weights.values())
            q = row[w] / 1e3
            hist.append(dict(date=d, well=w, q_ksm3d=q, whp=wl.whp_for(pres, q)))
    fit = fit_deliverability(sim, pd.DataFrame(hist))
    assert fit["W1"]["a"] == pytest.approx(30.0, rel=0.25)
    # forecast: low target is met, high target is capacity limited, pressure falls monotonically
    sc = Scenario(pd.Timestamp("2018-01-01"), pd.Timestamp("2030-01-01"), target_gas_sm3d=12.5e6, min_whp_bara=80.0)
    fc = forecast(fld, sim.state, sc)
    f = fc.field_series()
    assert f.gas_sm3d.iloc[0] == pytest.approx(12.5e6, rel=1e-6) or f.gas_sm3d.iloc[0] < 12.5e6
    assert f.gas_sm3d.max() <= 12.5e6 * (1 + 1e-9)
    p = fc.tanks().query("tank == 'A'").p_res.values
    assert np.all(np.diff(p) <= 1e-6)
    assert (fc.tanks().limited_by == "capacity").any()
    assert len(well_series(fc)) > 0
    tbl = history_forecast_table(sim, fc)
    assert set(tbl.period) == {"history", "forecast"}
    # composition of the produced fluid becomes leaner with depletion
    c1 = fc.field.tanks["A"].path.fluid.names.index("methane")
    comp = fc.composition_series("A", fld.tanks["A"].path.fluid.names)
    assert comp.methane.iloc[-1] > comp.methane.iloc[0]


def test_wellstreams(specs):
    rates = _rates()
    fld = Field({s.name: Tank(s.name, DepletionPath(s.fluid, s.z0, s.T_K, s.p_init, s.p_min, s.dp), s.giip_gsm3) for s in specs}, WELLS)
    sim = fld.simulate(rates)
    streams = well_streams_at(sim, "2015-01-01", {"W1": 4e6, "W4": 2e6})
    assert all(s.mol_s > 0 and abs(s.composition.sum() - 1.0) < 1e-6 for s in streams)
    tbl = stream_table(streams, fld.tanks["A"].path.fluid.names)
    assert {"gas_Sm3d", "mol_s", "methane"} <= set(tbl.columns)
