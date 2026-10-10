---
name: neqsim-reservoir-history-match-forecast
calculation_basis: "neqsim-java"
version: "0.1.0"
description: "Compositional material-balance model of a gas-condensate field with several formations, compartments and wells: history match to rates, pressure and condensate yield, produced composition versus depletion, forecast under wellhead-pressure limits, and wellstreams for process models. USE WHEN: a multi-formation or multi-well gas field must be matched and forecast, composition change is needed, or a process model needs reservoir-driven feeds."
last_verified: "2026-10-06"
requires:
  python_packages: [numpy, pandas, scipy, jneqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# Reservoir History Match and Forecast

A reservoir model cheap enough to re-match whenever new data arrives, with a compositional fluid,
that feeds the process model with the fluid the wells actually produce.

## When to Use

- A gas or gas-condensate field with several formations, compartments or wells must be matched to its
  production history and forecast.
- The produced composition changes with depletion and the process model should see it.
- Production and composition must be shown for history and future through a process model.
- Not for black-oil or volatile-oil reservoirs with mobile oil (use the grid route in
  `neqsim-near-well-and-injectivity`) and not for open-data volume screening
  (`neqsim-reservoir-model-builder`).

## Inputs

- Daily well gas, condensate, water, on-stream hours, wellhead pressure, downhole pressure.
- Field allocated gas, condensate and water series.
- Well-to-formation and compartment map; initial pressure and temperature per tank.
- Tuned reservoir fluid per formation (NeqSim EOS, component names, heavy indices).
- Scenario: target rate, minimum wellhead pressure, well schedule.

## Outputs

- Matched tank parameters (`giip_gsm3`, `aquifer_c`, `cgr_scale`, `heavy_scale`) with std and bound hits.
- Match quality by observation kind and tank.
- Well deliverability (a, c) and water-gas ratio.
- Produced composition and condensate-gas ratio versus date and pressure.
- History and forecast tables per tank and well; P10/P50/P90 when identifiable.
- Wellstream tables (composition, molar rate, water, WHP) for process models and process KPI series.

## Engineering Method

**Model.** A *tank* is one reservoir, formation or pressure compartment with its own fluid, volume
(`giip_gsm3`, wet gas in place as standard gas volume), optional Schilthuis aquifer (`aquifer_c`) and a
condensate-yield scale (`cgr_scale`). The *depletion path* (`DepletionPath`) is a constant-volume
depletion on a NeqSim EOS: moles left, liquid saturation, produced-stream composition and surface
yield versus pressure. It depends on pressure only, so it is computed once per fluid and the material
balance looks pressure up from cumulative moles produced. A *well* has deliverability
`P_res^2 - WHP^2 = a q + c q^2` fitted from daily history and a share of each tank it drains. A *field*
is tanks + wells + optional tank connections. History is driven by well gas rates; the forecast takes
min(target, sum of well capacities at the minimum wellhead pressure).

**Workflow.**

1. Data: `monthly_rates`, `field_cgr_observations`, `shut_in_pressure_observations`,
   `deliverability_history` turn exports into inputs. Normalise sidetracks to well slots, but keep a
   sidetrack separate when it reads another pressure.
2. Tanks: one per formation and one per compartment the data separate; wrap the NeqSim fluid in `FluidModel`.
3. Match: `Matcher(specs, wells, rates, obs, params).run()`; bound `giip_gsm3` below by cumulative production.
4. Wells: `fit_deliverability` with the matched tank pressure.
5. Forecast: `forecast(field, history.state, Scenario(...))` for several `min_whp_bara`; `ensemble()` for ranges.
6. Composition: `SimResult.composition_series`, `stream_at`.
7. Process link: `well_streams_at`, `stream_table`, `run_process_series`; plot `history_forecast_table`.

**Pressure data and compartments.**

- A new sidetrack reads the pressure of the block it penetrates. Drop wellbores younger than about
  18 months; a wellbore whose readings stay far above the field is an isolated compartment and gets
  its own tank (own initial pressure and volume).
- Use the lower quartile of the well medians per month for the main tank: static gauges read at or below
  true pressure and compartments only add high values.
- Flowing bottom-hole pressure is a lower bound for reservoir pressure, not an observation.

**Hand-off to process models.** Replace each well feed by `WellStream.composition` and `mol_s` at the date of
the case, keep wellhead pressure and temperature from measurements (history) or the forecast WHP.
`run_process_series` takes any callable that builds and solves the process model for a date. Compare the
feeds with allocation-recombined feeds on the same plant model before claiming an improvement.

## Python Usage Pattern

```python
from reservoir_history_match import (FluidModel, TankSpec, Well, Param, Matcher, Scenario,
                                     forecast, fit_deliverability, well_streams_at)

fluid = FluidModel(neqsim_base_fluid, component_names, heavy_idx=heavy_indices)
specs = [TankSpec("Brent", fluid, z_brent, T_K, 770.0, giip_gsm3=110.0, p_min=15.0, dp=15.0)]
wells = {"A-1": Well("A-1", {"Brent": 1.0})}
m = Matcher(specs, wells, monthly_rates_df, obs_df,
            [Param("Brent", "giip_gsm3", 1.05 * cum_gsm3, 400.0), Param("Brent", "cgr_scale", 0.5, 2.0)])
res = m.run()
hist = res.field.simulate(monthly_rates_df)
fc = forecast(res.field, hist.state, Scenario(start, end, target_gas_sm3d=8e6, min_whp_bara=31.0))
streams = well_streams_at(hist, "2026-09-01", {"A-1": 0.6e6})
```

See `examples/two_tank_field.py` for a runnable two-formation example.

## Validation Checklist

- Recovery per tank is below about 90 % and the end pressure is above the lowest flowing gauge of its wells.
- Condensate yield within the 10-15 % noise of the allocation; pressure within the scatter of the gauges.
- Parameter `std` is small and `at_bound` is false; otherwise the data do not identify the parameter and
  ensembles must not be drawn from the fit.
- Wells add up to the allocated field gas before matching.
- Single-well tanks are reported as weakly constrained.
- The process model reproduces the allocation with allocation-recombined feeds before the reservoir feeds are judged.

## Common Mistakes

- Averaging the pressure of an isolated compartment into the main tank.
- Letting `giip_gsm3` fall below cumulative production, or accepting a bound hit as a result.
- Reading flowing BHP as static pressure.
- Treating the allocated condensate as a stock-tank flash of the wellstream: it is a plant product, and
  `cgr_scale` only absorbs part of the difference. Check the plant model before changing the reservoir fluid.
- Claiming an improvement from composition change without the same-plant comparison.

## Revitalising a depleted HPHT field (learned on Kristin, 2026-10)

Use the tank model to answer "which drainage point, and is it drillable" before any simulator work:

1. **One tank per pressure signature.** Group wells by static pressure (upper decile per quarter), compute
   `p/z` with NeqSim Z at reservoir T, give P10-P90 from pressure scatter x Z x cumulative; report the
   volume reachable at >= 250 bara separately from the total. Flag compartments whose only pressure
   gauge is a dead well (no reservoir communication) as POOR data rather than averaging it in.
2. **Rate vs wellhead pressure.** Replace Beggs-Brill by an average-T/Z momentum balance with NeqSim Z for
   wet-gas tubing at low rate (Beggs-Brill was slow, non-monotonic and returned NaN below about 0.3 MSm3/d).
   Calibrate `C` in `q = C (Pr^2 - Pwf^2)` on the latest 45 days of allocated rate and WHP. The low-pressure (LPP)
   lever is large only at low reservoir pressure (x5 at 120 bara, <10 % at 300 bara).
3. **Drilling window Monte Carlo** (all geomechanics are ranges, state them): pore pressure from the tank;
   `Shmin = k_h Sv - A (Pi - Pr)` with stress path `A` 0.40-0.75; shale floor = overburden shale pore
   pressure + trip margin (about 1.96 SG for Kristin, checked against the 1.98 SG used by the Q-4 clean-up).
   Compare four strategies: conventional single mud weight, open reservoir on MPD, MPD with wellbore
   strengthening, liner cemented across the shale. The last is the one that fails when the sand is drawn down
   by hundreds of bar; that is the technology gap, not drilling itself.
4. **Compaction slip**: `slip = (dP / M) h f_loc` against an assumed liner tolerance; re-pressurisation
   effect is the cheapest mitigation to quote.
5. **Value**: success probability = window x isolation x shear survival x water penalty; keep the P50 NPV
   (negative for a gated sidetrack) and the expected NPV side by side; the tornado must use common random
   numbers (seed per evaluation) or one-at-a-time swings are Monte Carlo noise.

## Limitations

Material balance, not a grid: no gravity, coning, areal sweep or interference beyond tank connections.
Gas phase produced, liquid dropout immobile. Deliverability uses P^2 with constant coefficients. Water is a
ratio per well. Compositions are as good as the EOS tuning; report the tuning quality with the match.

## References

- Whitson, C.H., Brule, M.R., Phase Behavior, SPE Monograph 20 (constant-volume depletion).
- Craft and Hawkins, Applied Petroleum Reservoir Engineering (gas material balance, Schilthuis aquifer).
- Related skills: `neqsim-reservoir-model-builder`, `neqsim-reservoir-depletion-screening`,
  `neqsim-near-well-and-injectivity`, `neqsim-pseudocomponent-split-characterization`,
  `neqsim-pvt-regression-characterization-factor`, `neqsim-process-modeling`.