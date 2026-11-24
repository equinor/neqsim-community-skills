---
name: neqsim-simulator-state-proxy
calculation_basis: "screening"
version: "1.0.0"
description: "Turn Eclipse or OPM Flow summary results into reservoir-state proxy tables (pressure, water cut, GOR, productivity index against cumulative volumes) for the NeqSim hybrid reservoir-well-network production model, with result inventory, profile-replay baseline and error metrics. USE WHEN: an existing reservoir simulation should drive a fast production-profile or network what-if model (choke, routing, separator pressure, injection), or a hybrid model must be validated against simulator runs."
last_verified: "2026-11-24"
requires:
  python_packages: [numpy, resdata]
  java_packages: []
  env: []
  network: []
---

# Simulator State Proxy (Eclipse / OPM Flow results for the NeqSim hybrid production model)

A production profile replayed from a reservoir simulator gives the same rate at the same cumulative production
whatever the production network does. The NeqSim hybrid model (`neqsim.process.fielddevelopment.hybrid`) keeps the
reservoir *state* from the simulator instead and solves the well rates from inflow, lift curves and network
back-pressure. This skill is the simulator side of that model: it reads the summary results, builds the proxy tables,
and supplies the baseline and the error metrics for validation. It runs no simulator and needs no NeqSim.

## When to Use

- Simulator runs exist and the question is a what-if on wells, chokes, routing, separator pressure or injection.
- A production-profile generator must respond to network pressure and facility capacity.
- A hybrid model must be validated against the simulator before it is used for decisions.
- Do not use it to replace a reservoir simulation, to history match, or to extrapolate beyond the simulated volumes.

## Inputs

- Summary results of one or more simulator runs (`CASE.SMSPEC` and `CASE.UNSMRY`), with the vectors listed below.
- The wells of each drainage unit and the `FIPNUM` region (or other pressure vector) that represents it.
- The initial reservoir pressure, for the first row of the tables.
- For scenario blending: the vector of the second coordinate, for example the cumulative water injected of the unit.

## Outputs

- `inventory(...)`: per well, which proxy quantities the run supplies and which SUMMARY vectors are missing.
- `StateTable` per well: cumulative oil, pressure, water cut, gas-oil ratio, productivity index, elapsed time and
  optional injection columns; written as CSV in the layout of `ReservoirStateProxy.fromCsv`.
- `StateTable` per drainage unit: pressure against the cumulative oil of all its wells.
- `performance_curve` and `replay_profile`: the profile-replay baseline.
- `compare(...)`: mean and maximum absolute relative error, bias and root-mean-square error against the simulator.

## Engineering Method

1. **Inventory.** `inventory(SummaryData.from_file("CASE.SMSPEC"))` lists, per well, which proxy quantities the run
   can supply and which SUMMARY vectors are missing. Rerun the simulator with the missing vectors before going on.
2. **Choose the reference pressure** (see below) and build one table per well with `well_state_table` and one per
   drainage unit with `unit_pressure_table`.
3. **Write the tables** with `StateTable.to_csv`; the Java side reads them with
   `ReservoirStateProxy.fromCsv(name, CumulativeQuantity.OIL_PRODUCED, path)`.
4. **Validate the base case first**: the hybrid model built from a run must reproduce that run (`compare`).
5. **Then predict a changed strategy** and compare with a simulator run of that strategy. Use `performance_curve`
   and `replay_profile` as the baseline that shows what a replayed profile would have said.
6. **Refresh or add scenarios** where the errors are too large (see "How far a proxy reaches").

## Python Usage Pattern

```python
from simulator_state_proxy import SummaryData, inventory, well_state_table, unit_pressure_table, compare

data = SummaryData.from_file("out/BASE.SMSPEC")
report = inventory(data)                      # report["missing"] must be empty

well = well_state_table(data, "A1", "RPR:1", extra_quantities={"WATER_INJECTED": "WWIT:IA"}, initial_pressure=180.0)
unit = unit_pressure_table(data, "unit_A", ["A1", "A2"], "RPR:1", {"WATER_INJECTED": "WWIT:IA"})
well.to_csv("proxy/A1.csv")
unit.to_csv("proxy/unit_A.csv")

errors = compare(data.time_days, data.get("WOPR:A1"), model_time, model_rate)   # mean_abs_pct, max_abs_pct, bias_pct
```

## SUMMARY vectors the simulator run must write

| Vector | Used for |
|---|---|
| `WOPR`, `WOPT` | rate (flowing filter, productivity index) and the abscissa |
| `WBHP` | productivity index |
| `WWCT`, `WGOR` | water cut and gas-oil ratio |
| `RPR` (with `FIPNUM` per drainage unit) or `FPR` | reservoir pressure of the unit |
| `WBP9` | optional: pressure around the well |
| `WTHP`, `GPR` | validation of lift curves and network node pressures |
| `WWIT`, `WGIT` | scenario blending on cumulative injection |

Put the `FIPNUM` regions on the hydrocarbon zone of each pressure-connected unit. A region that includes a large
aquifer reports the aquifer pressure.

## Choosing the reference pressure

The productivity index is derived as `WOPR / (pressure - WBHP)`, so it is consistent with whatever pressure is chosen;
never combine the simulator's `WPI` (referred to the well block) with a region pressure.

| Reference | Pressure follows | Use when |
|---|---|---|
| Region pressure `RPR:n`, keyed on the cumulative oil of all wells of the unit | the unit | wells of the unit are in good pressure communication |
| Well block pressure `WBP9:well`, keyed on the well's own cumulative oil | the well | wells drain their own areas (low permeability, large spacing) |

Measured on a synthetic two-compartment field (40 to 120 mD, two wells per compartment, OPM Flow 2026.04, 2026-11-24):
both references reproduce the source run to 0.03 % in well oil rate. After a choke swap the well reference gave
0.7 % mean error over eight years and the unit reference 2.5 %, because the two wells of a compartment did not
equilibrate. After a rise in separator pressure the order was reversed, but only just (20 % against 17 %, both from
one run). Test both against one changed simulator run before choosing.

## How far a proxy reaches

A table from one run is exact for that run. It stays good while the *depletion path* is similar and degrades when the
rate history changes, because water cut and productivity index at the same cumulative oil depend on how fast it was
produced (coning, aquifer influx, voidage replacement). Measured on the same field over eight years against the
simulator: mean absolute error of the well oil rates, with the error of the cumulative oil in brackets.

| Change of strategy | One-run proxy | With more runs | Profile replay |
|---|---|---|---|
| None (source run) | 0.03 % (0.00 %) | - | 1.5 % (+0.6 %) |
| Choke swap on two wells | 0.7 % (-0.06 %) | 0.03 % after a refresh from the new run | 1.8 % (+0.4 %), 33 % on one well at the swap |
| Separator pressure +10 bar after one year | 17 % (-9.3 %) | 1.5 % (-0.6 %), two runs blended on elapsed time | 27 % (+18 %) |
| Water injection at half the rate of the high scenario | 33 % (-26 %) | 16 % (+3.0 %), two scenarios on cumulative injection | 34 % (-25 %) |
| Water injection starting in year 2 | 30 % (-25 %) | 3.6 % (-0.6 %), three scenarios | 31 % (-24 %) |

What the figures say:

- One run is enough for a change that moves production between wells for a limited time. It is not enough for a
  change that alters the depletion rate for the rest of field life. For separator-pressure rises of 2, 5, 10 and 15
  bar the one-run proxy overstated the loss of cumulative oil by 58 to 73 % of the true effect at every step size,
  while the replay showed no loss. With one run, report the two as bounds.
- Two runs that bracket the change, blended on elapsed time, kept the cumulative oil within 0.6 % for all four steps.
- Two injection scenarios gave the oil total but a gas rate that was 74 % off, because the gas-oil ratio switches at
  the bubble point. Use three scenarios when gas rates matter.
- The wells of this field sit near their lift limit late in life, which makes relative rate errors large. Judge a
  model on cumulative volumes as well.

**Find out which variable fails.** With two runs, build a proxy from the first run and replace one column at a time
(pressure, productivity index, water cut, gas-oil ratio) by the column of the second run, then score each variant
against the second run. On this field water cut and productivity index carried the error of the back-pressure case
(with only water cut from the wrong run 12 %, productivity index 7 %, pressure 2 %, gas-oil ratio 1 %), and reservoir
pressure carried the error of the injection case (38 %). The remedy follows: more runs along the rate axis in the
first case, along the injection axis in the second.

Scenario blending in NeqSim: `ScenarioReservoirState(name, CumulativeQuantity.WATER_INJECTED)` or
`...ELAPSED_TIME` with one `ReservoirStateProxy` per run. Every table written here carries an `ELAPSED_TIME` column;
pass injection columns through `extra_quantities`.

## Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Rates and cumulative volumes do not satisfy `cum[n] = cum[n-1] + rate[n] * dt` | `resdata` values read with `report_only=True` are resampled to whole-day report dates (30.0 instead of 30.4375 days) | read every time step; `SummaryData.from_file` does |
| Base case off by several per cent in the first years, node pressures 2 to 5 bar high | simulator network balanced at the start of each time step (`NETBALAN 0`), so node pressures lag the rates | balance in every Newton iteration (`NETBALAN -1`), or compare node pressures with the tables at the simulator's own rates before blaming the model |
| Negative or huge productivity index | reference pressure below the flowing bottom-hole pressure, or an aquifer inside the region | another pressure source; `FIPNUM` on the hydrocarbon zone |
| Model dies or jumps at the end of a run | cumulative volume beyond the last row of a table; values are held, not extrapolated | run the source cases longer than the cases they are used for; watch `isOutsideProxyValidity()` |
| Blend never leaves the first scenario | second coordinate is itself predicted by the proxy (cumulative water or gas produced) | blend on something the strategy drives: cumulative injection or elapsed time |
| Good mean error, wrong response | the mean over many years hides the months after a change | also compare the rate change over the first step after the event |
| Large relative errors late in life | wells close to their lift limit: a few bar of drawdown left, so 0.1 in water cut changes the rate by tens of per cent | report absolute errors and cumulative volumes too; treat late-life rates as sensitive |

## Validation Checklist

- [ ] `inventory(...)["missing"]` is empty for every well used.
- [ ] Bottom-hole pressure from the tubing table at the simulator's rates and wellhead pressure equals `WBHP`
      (it did within 0.08 bar over 396 points): this proves the lift-curve lookup matches the simulator's interpolation.
- [ ] Node pressures from the branch tables at the simulator's group rates equal `GPR` within the network tolerance.
- [ ] The hybrid model built from a run reproduces that run (well oil rates within about 0.1 %).
- [ ] At least one changed strategy is compared with its own simulator run, per well, including the first step after
      the change.
- [ ] Steps where the proxy is outside its data are reported and not used.

## Limitations

- The proxy is a function of one cumulative volume, or two with scenario blending. It cannot represent a strategy
  outside the envelope of the simulator runs it came from.
- Black-oil results carry no composition; the molar feed then comes from recombining fixed surface gas and oil
  compositions at the well's gas-oil ratio and water cut. A compositional run can supply compositions as extra
  table columns (`z:<component>`, `molesPerSm3`).
- Oil-rate basis (water cut, gas-oil ratio). Gas-condensate wells need a gas-rate basis that the Java model does not
  have yet.
- Screening and engineering support only; not a substitute for the reservoir simulation or its review.

## References

- NeqSim package `neqsim.process.fielddevelopment.hybrid` and its guide
  `docs/fielddevelopment/HYBRID_RESERVOIR_NETWORK_MODEL.md` (equinor/neqsim).
- `resdata`, Eclipse-format output reader: https://github.com/equinor/resdata
- OPM Flow: https://opm-project.org

## Related Skills

- `neqsim-near-well-and-injectivity`: OPM Flow in a container, deck traps, black-oil tables from a NeqSim fluid.
- `neqsim-vfp-lift-curves` (neqsim repo): generating the lift curves the simulator and the hybrid model share.
- `neqsim-integrated-production-and-lifecycle` (neqsim repo): the Java classes of the hybrid model.
- `neqsim-opm-open-reservoir-decks`: open decks to practise on.
