---
name: neqsim-teg-dehydration-modeling
version: "0.1.0"
description: "Build a validated, closed-loop TEG (triethylene glycol) gas dehydration plant in NeqSim, including absorber, flash drum, regeneration column, stripper, lean-TEG recycle, and still-vent emission classification. USE WHEN: a task needs a runnable NeqSim TEG dehydration flowsheet (water dew point, lean-TEG purity, NMVOC/methane/benzene still-vent emissions) rather than a screening-level water-content estimate."
last_verified: "2026-06-26"
requires:
  python_packages: [neqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# TEG Dehydration Modeling

Use this skill to build a complete, converging triethylene-glycol (TEG) gas
dehydration plant in NeqSim. It captures a validated flowsheet topology and the
non-obvious settings (CPA fluid setup, regeneration-column tolerances, recycle
priorities, condenser/preheat energy coupling, makeup calculator) needed for the
process to solve as a closed loop. It returns a `ProcessSystem` plus the key
streams an agent needs for water dew point, lean-TEG purity, and still-vent
emission classification.

This is a real NeqSim build, not a public correlation placeholder. For a quick
"is dehydration required?" triage without building a plant, use
`neqsim-water-dewpoint-dehydration-screening` instead.

## When to Use

- When a user asks to model a TEG dehydration unit and read water dew point, lean
  TEG purity, or regeneration still-vent emissions.
- When an agent needs a runnable TEG flowsheet to study stripping gas, reboiler
  temperature, TEG circulation rate, or once-through vs recirculated stripping gas.
- When emissions (NMVOC, methane, benzene, CO2, water) from the regeneration
  still vent must be quantified and classified for an environmental screening.

## Inputs

The `build_teg_plant(...)` function is fully parameterized. Key inputs:

- `feed_fractions`: list of mole fractions (or percentages) aligned with
  `GAS_COMPONENTS` (nitrogen, CO2, methane, ... , benzene).
- `feed_flow_MSm3_day`: wet/dry feed gas flow rate in MSm3/day.
- `feed_temp_C`, `feed_pressure_bara`: feed gas conditions.
- `absorber_pressure_bara`, `absorber_temp_C`: contactor conditions.
- `teg_flow_kg_hr`, `teg_feed_temp_C`, `lean_teg_purity`: lean TEG circulation.
- `flash_drum_pressure_bara`, `reboiler_temp_C`, `stripping_gas_Sm3_hr`:
  regeneration conditions.
- `n_absorber_stages`, `stage_efficiency`: absorber model resolution.
- `water_mode`: `'saturated'` (water-saturate the feed) or `'specified'`
  (set an inlet water content in mol-ppm via `water_content_ppm_mol`).
- `saturation_temp_C`, `saturation_pressure_bara`: optional saturation TP setter.
- `recirculate_stripping_gas`: `True` builds a true closed-loop stripping-gas
  recycle (split dried overhead, blower, heater) to cut still-vent emissions.

## Outputs

`build_teg_plant(...)` returns `(process, streams)`:

- `process`: a NeqSim `ProcessSystem` ready to run.
- `streams`: a dict of handles — `dehydratedGas`, `flashGas`, `stillVent`,
  `leanTEGtoAbs`, `waterDewAnalyser`, `strippingGas`, `recircBlower`.

Helper functions produce the engineering results:

- `comp_mass_flows_kg_hr(stream)`: per-component mass flow (kg/hr).
- `teg_mass_fraction(stream)`: TEG weight percent of a stream.
- `classify_emissions(stream)`: dict with `NMVOC`, `methane`, `CO2`, `water`,
  `TEG`, `benzene`, and `total` mass flows (kg/hr).

## Engineering Method

The flowsheet follows the standard TEG dehydration topology:

1. **Fluid** — `SystemSrkCPAstatoil` (CPA EOS) with `setMixingRule(10)` and
   `setMultiPhaseCheck(False)`. TEG is added **last** so the lean-TEG composition
   maps to `leanComp[-1] = lean_teg_purity` and `leanComp[-2] = 1 - lean_teg_purity`.
2. **Feed conditioning** — optional saturation TP setter + `StreamSaturatorUtil`
   (saturated mode) or an inlet water component (specified mode), then a heater to
   absorber TP.
3. **Absorber** — `SimpleTEGAbsorber` with gas-in and lean-TEG solvent-in streams.
4. **Rich TEG let-down and pre-heat** — HP flash valve, rich preheater,
   lean/rich exchangers (`HeatExchanger` with UA values), degassing separator,
   fine filter, LP flash valve.
5. **Regeneration** — `DistillationColumn` (reboiler + condenser) with **loosened
   tolerances** (temperature 5e-2, mass 2e-1, enthalpy 2e-1) so the glycol/water
   split converges; stripping gas fed to the reboiler tray; `WaterStripperColumn`
   for deep lean-TEG purity.
6. **Recycles** — lean-TEG recycle (priority 200, `setDownstreamProperty('flow rate')`)
   closes the solvent loop; the internal stripping-gas recycle returns stripper
   overhead to the reboiler. With `recirculate_stripping_gas=True`, a second
   makeup recycle (priority 150) recirculates dried overhead as stripping gas.
7. **Makeup and energy coupling** — a `Calculator` sizes TEG makeup from TEG lost
   in the dry gas, flash gas, still vent, and water draws; the rich preheater is
   driven by the condenser energy stream:
   `richPreheat.setEnergyStream(column.getCondenser().getEnergyStream())`.
8. **Run** — `process.runAsThread()` then `thr.join(...)` (worker thread avoids
   blocking and tolerates the recycle iterations).

## Python Usage Pattern

```python
from teg_dehydration_modeling import (
    DEFAULT_FEED,
    build_teg_plant,
    classify_emissions,
    teg_mass_fraction,
)

process, streams = build_teg_plant(
    feed_fractions=DEFAULT_FEED,
    feed_flow_MSm3_day=4.65,
    feed_temp_C=25.0,
    feed_pressure_bara=70.0,
    absorber_pressure_bara=85.0,
    absorber_temp_C=35.0,
    teg_flow_kg_hr=5500.0,
    teg_feed_temp_C=48.5,
    lean_teg_purity=0.97,
    flash_drum_pressure_bara=4.8,
    reboiler_temp_C=197.5,
    stripping_gas_Sm3_hr=180.0,
    n_absorber_stages=4,
    stage_efficiency=0.7,
)

thr = process.runAsThread()
thr.join(300000)  # ~15 s once-through, ~40 s with stripping-gas recirculation

water_dew_C = float(streams["waterDewAnalyser"].getMeasuredValue("C"))
lean_teg_wt = teg_mass_fraction(streams["leanTEGtoAbs"])
still_vent = classify_emissions(streams["stillVent"])

print(water_dew_C, lean_teg_wt, still_vent["NMVOC"])
```

## Validation Checklist

- [ ] Water dew point of the dry gas is well below 0 C at the reference pressure.
- [ ] Lean TEG purity is above 90 wt% (typically 97-99 wt% with stripping gas).
- [ ] Still-vent NMVOC and methane mass flows are finite and non-negative.
- [ ] With `recirculate_stripping_gas=True`, still-vent NMVOC and methane do not
      increase versus the once-through case.
- [ ] The process is run on a worker thread and the join timeout is large enough
      for the recycles to converge.
- [ ] Example inputs are public and synthetic.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Regeneration column will not converge | Default tolerances too tight for glycol/water split | Loosen `setTemperatureTolerance(5e-2)`, `setMassBalanceTolerance(2e-1)`, `setEnthalpyBalanceTolerance(2e-1)` |
| Lean TEG purity wrong / NaN | TEG not added last, or composition indices off | Add `water` then `TEG` last; set `leanComp[-1]=purity`, `leanComp[-2]=1-purity` |
| Lean-TEG loop never closes | Recycle priority/property not set | Lean TEG recycle priority 200 with `setDownstreamProperty('flow rate')` |
| Class not found | Wrong CPA class name | Use `SystemSrkCPAstatoil` (lowercase `statoil`) |
| Run blocks or stalls | Running inline instead of on a thread | Use `process.runAsThread()` + `thr.join(timeout_ms)` |
| TEG inventory drifts | No makeup | Add the `Calculator` makeup sized from TEG in dry gas, flash gas, still vent, water draws |
| Water balance looks ~1-2% open | Only counting still vent + regen water draw | Water removed from the gas leaves via **still vent + regen water/HC draw + degassing flash gas**; include the flash-gas water term and closure tightens to <0.1% |

## Limitations

- Inputs and examples are public and synthetic; no proprietary plant data,
  vendor glycol packages, or company emission factors are included.
- Emission classification is a component-bucketing of stream mass flows
  (NMVOC/methane/benzene/CO2/water); it is not a regulatory emission inventory.
- The absorber uses `SimpleTEGAbsorber` with stage efficiency, not a rate-based
  contactor model; deep dew-point design needs validated review.
- Convergence depends on reasonable inputs; extreme TEG rates, stripping gas, or
  reboiler temperatures may require tolerance or guess-temperature tuning.

## Related NeqSim Functionality

- `neqsim.thermo.system.SystemSrkCPAstatoil` — CPA equation of state for
  glycol/water/hydrocarbon systems (reached via `from neqsim import jneqsim`).
- `neqsim.process.equipment.absorber.SimpleTEGAbsorber`,
  `neqsim.process.equipment.absorber.WaterStripperColumn` — TEG contactor and stripper.
- `neqsim.process.equipment.distillation.DistillationColumn` — TEG regeneration column.
- `neqsim.process.equipment.util.Recycle`, `Calculator` — solvent/stripping-gas
  recycles and TEG makeup sizing.
- `neqsim.process.measurementdevice.WaterDewPointAnalyser` — dry-gas water dew point.
- For a screening-only water-content triage before building a plant, use the
  `neqsim-water-dewpoint-dehydration-screening` community skill.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim TEG dehydration emissions notebook:
  https://github.com/equinor/neqsim/blob/master/examples/notebooks/teg_dehydration_emissions.ipynb
- NeqSim Skills Guide:
  https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
