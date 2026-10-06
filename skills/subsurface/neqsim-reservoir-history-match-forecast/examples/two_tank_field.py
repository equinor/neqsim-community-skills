"""Two formations, four wells: generate a history, match it, forecast, and print the wellstream handed to a process model."""
import numpy as np
import pandas as pd

from reservoir_history_match import (DepletionPath, Field, FluidModel, Matcher, Param, Scenario, Tank, TankSpec, Well, forecast, well_streams_at)

LIGHT = {"nitrogen": 0, "CO2": 0, "methane": 0, "ethane": 0, "propane": 0, "i-butane": 0, "n-butane": 0, "i-pentane": 0, "n-pentane": 0, "n-hexane": 0}
TBP = [("C7", 96.0, 0.74), ("C10", 150.0, 0.80), ("C15", 210.0, 0.85), ("C25", 350.0, 0.90)]
Z_A = [0.004, 0.02, 0.70, 0.085, 0.045, 0.008, 0.016, 0.007, 0.008, 0.012, 0.03, 0.035, 0.02, 0.01]
Z_B = [0.003, 0.03, 0.74, 0.07, 0.035, 0.006, 0.012, 0.005, 0.006, 0.009, 0.025, 0.03, 0.015, 0.01]

fluid = FluidModel.from_components(LIGHT, TBP)
idx = pd.date_range("2010-01-01", periods=96, freq="MS")
rates = pd.DataFrame({w: b * (1 + 0.2 * np.sin(np.arange(96) / 5 + k)) for k, (w, b) in enumerate((("W1", 4e6), ("W2", 3.5e6), ("W3", 3e6), ("W4", 2e6)))}, index=idx)
wells = {"W1": Well("W1", {"A": 1.0}, a=30, c=0.02), "W2": Well("W2", {"A": 1.0}, a=35, c=0.02), "W3": Well("W3", {"B": 1.0}, a=40, c=0.03), "W4": Well("W4", {"A": 0.5, "B": 0.5}, a=45, c=0.03)}
specs = [TankSpec("A", fluid, Z_A, 423.15, 600.0, giip_gsm3=60.0, p_min=120.0, dp=20.0), TankSpec("B", fluid, Z_B, 423.15, 600.0, giip_gsm3=40.0, p_min=120.0, dp=20.0)]

truth = Matcher([TankSpec(**{**s.__dict__, "giip_gsm3": g}) for s, g in zip(specs, (35.0, 25.0))], wells, rates,
                pd.DataFrame(dict(date=[idx[0]], tank=["A"], kind=["p_res"], value=[0.0], sigma=[1.0])), []).build().simulate(rates)
tab = truth.tanks()
pick = tab[tab.date.isin(idx[::12])]
obs = pd.concat([pd.DataFrame(dict(date=pick.date, tank=pick.tank, kind="p_res", value=pick.p_res, sigma=3.0)),
                 pd.DataFrame(dict(date=truth.field_series().index, tank="FIELD", kind="cgr", value=truth.field_series().cgr_sm3_per_msm3, sigma=15.0))])

res = Matcher(specs, wells, rates, obs, [Param("A", "giip_gsm3", 10, 200), Param("B", "giip_gsm3", 10, 200)]).run()
print(res.parameters[["tank", "name", "initial", "tuned", "std"]].round(2))
print(res.quality().round(2))

hist = res.field.simulate(rates)
fc = forecast(res.field, hist.state, Scenario(idx[-1] + pd.offsets.MonthBegin(1), pd.Timestamp("2030-01-01"), target_gas_sm3d=12e6, min_whp_bara=80.0))
print(fc.field_series().iloc[[0, -1]].round(0))
for s in well_streams_at(fc, fc.field_series().index[0], {"W1": 3e6, "W4": 2e6}):
    print(s.well, round(s.mol_s, 1), "mol/s", "C1 =", round(float(s.composition[fluid.names.index("methane")]), 3))
