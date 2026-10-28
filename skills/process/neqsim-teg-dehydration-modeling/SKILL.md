---
name: neqsim-teg-dehydration-modeling
calculation_basis: "neqsim-java"
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
  makeup recycle recirculates dried overhead as stripping gas. Keep both coupled
  stripping-gas recycles at the same controller priority (currently 100); an
  intermediate priority may be skipped by the current `RecycleController` sequence.
7. **Makeup and energy coupling** — a `Calculator` sizes TEG makeup from TEG lost
   in the dry gas, flash gas, still vent, and water draws; the rich preheater is
   driven by the condenser energy stream:
   `richPreheat.setEnergyStream(column.getCondenser().getEnergyStream())`.
8. **Run** — `process.runAsThread()` then `thr.join(...)` (worker thread avoids
  blocking and tolerates the recycle iterations). A completed worker thread or
  successful unit statuses do not prove closed-loop convergence: require
  `process.solved()` and inspect `process.getConvergenceDiagnostics()` before
  accepting water or TEG closure.

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

## Regeneration-Pressure Sensitivity (reboiler floating on the LP flare)

Use this when the question is "does a few tens of mbar more reboiler pressure matter?" rather
than a full flowsheet. A reboiler/still connected to an LP flare header has no pressure control;
its pressure is the header pressure plus the pressure drop of the overhead path. Lean-TEG water
content at fixed temperature and vapour composition scales with total pressure, so the
effect is proportional (verified 2026-10-08, Aasta Hansteen, SRK-CPA, `mixingRule 10`):

- `p_w(x_water, T)` = `y_water * P_bubble` from `bubblePointPressureFlash(False)` on a
  `TEG`/`water` binary (`fl.getPhase(0)` is the gas); solve `x_water` so that
  `p_w = y_steam * P_reboiler` by bisection (`y_steam` = steam / (steam + stripping gas), about
  0.85 to 0.92 for 76 Sm3/h stripping gas and 690 kg/h water).
- Benchmark: 98.90 wt% TEG at 204 C and 1 atm without stripping gas (textbook value about 98.7).
- 0.200 to 0.215 barg at 198 C: lean-TEG water +1.29 % relative (about -0.005 wt%-points at the
  design 99.6 wt%), equal to about 0.6 C of reboiler temperature, and +0.16 C on the equilibrium
  dry-gas dew point at 69 barg. Reaching the 0.4 barg H alarm costs about +17 % water.
- Dry-gas equilibrium: flash gas + `water` + `TEG` with 5 mol TEG solution per mol gas so the
  liquid composition stays fixed; `dewPointTemperatureFlash()` for the dew point.
- Water load: saturate the gas at the WET-GAS-SCRUBBER temperature (e.g. 22 C), not the
  contactor lean-TEG inlet temperature (35 C); the two differ by a factor of two in kg/h.
- In `neqsim_dev_setup` task scripts use `ns.JClass("neqsim.thermo.system.SystemSrkCPAstatoil")`
  and the component name `TEG`.

## Drizo / solvent stripping (`stripping_mode="drizo"`)

Drizo regenerates TEG with a closed loop of recovered hydrocarbon solvent (BTEX) instead of
fuel gas. Oseberg D documents it (system 24 manual 11-4A-AV-C87-24001 pp. 15-16): flash vapour
cooled to 20 C and the condensate sent back to the still feed; still overhead (93 C) cooled to
20 C into a three-phase receiver; solvent vaporised and superheated to 220 C and fed to a packed
stripping column; excess solvent to the closed drain; reboiler 196-204 C at 0.35 barg.
`build_teg_plant(..., stripping_mode="drizo", drizo_solvent_kg_hr=..., still_pressure_bara=1.36)`
builds exactly this loop. Use `components=[...]` (with `feed_fractions` aligned) to add toluene
and m-Xylene so the solvent carries real BTEX, and `drizo_solvent_comp={"m-Xylene": 0.4, ...}`.

- The solvent circulation rate is a set-point (Splitter `setFlowRates([rate, -1.0], "kg/hr")`),
  not a result; the stripped purity depends on it, so scan it against the measured lean-TEG
  concentration. It is the main calibration knob for troubleshooting dehydration efficiency.
- Three recycles are closed by the loop (solvent recovery, solvent loop, stripping vapour to
  the reboiler) in addition to the lean-TEG recycle; a run takes several minutes, so use
  `runAsThread()` with a join of 900 s or more, check `process.solved()`, and if it is false call
  `process.run()` again (warm restart, up to 3 times; the stripping-vapour recycle often stops at
  its iteration cap on the first pass with `errComp` about 2e-2 and converges on the second).
- The still receiver must be a `ThreePhaseSeparator` (water out, oil out = solvent, gas out =
  vent); a two-phase separator mixes the solvent into the water draw.
- Without stripping, TEG at 204 C and 1 atm is about 98.9 wt%; a lean purity near that value means
  the solvent loop is not stripping (rate too low, or the loop has not converged), not that
  the model is right.
- Report lean quality with `glycol_purity_wt()` (TEG/(TEG+water)). `WaterStripperColumn` lets
  heavy solvent dissolve in the glycol, so `teg_mass_fraction()` falls as solvent rate rises
  (97.95 wt% of liquid at 1500 kg/h) while the glycol/water purity rises (99.8 wt%); mixing the
  two bases hides the stripping effect (measured 2026-10-28, 11.75 t/h semi-lean 97.8 wt%, 204 C,
  1.36 bara, 2 vs 4 stages).
- Stages matter more than rate: 4 stages with 300 Sm3/h dry gas gives 99.95 wt% where 2 stages
  give 99.79. Use 4 stages for a packed stripping column unless vendor data says otherwise.
- Convergence evidence: the Drizo loop was validated on the Oseberg D basis (12.3 MSm3/d feed,
  11.75 t/h TEG, 4 stripper stages, 1000 kg/h solvent): converged in about 100 s after one warm
  restart to lean 99.95 wt%, reboiler 0.83 MW (design 1.35 MW), dew point -49 C at 69 barg. The
  generic default case of this skill (4.65 MSm3/d, 5.5 t/h TEG) did NOT converge in 8 warm
  restarts with 300 or 600 kg/h solvent (lean purity oscillating 98.2-99.2 wt%); tune circulation,
  solvent rate and stripper stages for your own case and check `process.solved()` before use.
- The same-solvent-rate effect is non-monotonic if you read the wrong basis (see above).

## Validation Checklist

- [ ] Water dew point of the dry gas is well below 0 C at the reference pressure.
- [ ] Lean TEG purity (`glycol_purity_wt`, TEG/(TEG+water)) is in the range of the real plant:
      about 99.9 wt% (0.1 wt% water) for a stripped or Drizo unit, 98.7-99 wt% only when there
      is no stripping. A value of 90-97 wt% means the regeneration is not representative.
- [ ] Still-vent NMVOC and methane mass flows are finite and non-negative.
- [ ] With `recirculate_stripping_gas=True`, still-vent NMVOC and methane do not
      increase versus the once-through case.
- [ ] The process is run on a worker thread and the join timeout is large enough
      for the recycles to converge.
- [ ] `process.solved()` is true and every active recycle reports `solved() == True`;
  record priority, iterations, and residuals for any unsolved recycle.
- [ ] Water and TEG closure are interpreted only after the closed loop converges.
- [ ] Example inputs are public and synthetic.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Regeneration column will not converge | Default tolerances too tight for glycol/water split | Loosen `setTemperatureTolerance(5e-2)`, `setMassBalanceTolerance(2e-1)`, `setEnthalpyBalanceTolerance(2e-1)` |
| Lean TEG purity wrong / NaN | TEG not added last, or composition indices off | Add `water` then `TEG` last; set `leanComp[-1]=purity`, `leanComp[-2]=1-purity` |
| Lean-TEG loop never closes | Recycle priority/property not set | Lean TEG recycle priority 200 with `setDownstreamProperty('flow rate')` |
| Stripping-gas makeup recycle never executes | Coupled stripping-gas recycles use different priorities and an intermediate level is skipped | Assign the makeup recycle the same priority as the internal stripping-gas recycle; verify both with convergence diagnostics |
| Class not found | Wrong CPA class name | Use `SystemSrkCPAstatoil` (lowercase `statoil`) |
| Run blocks or stalls | Running inline instead of on a thread | Use `process.runAsThread()` + `thr.join(timeout_ms)` |
| TEG inventory drifts | No makeup | Add the `Calculator` makeup sized from TEG in dry gas, flash gas, still vent, water draws |
| Water balance looks open | Closed-loop convergence was not established, or a water outlet was omitted | First require `process.solved()` and all recycle diagnostics solved; then include **still vent + regen water/HC draw + degassing flash gas** in the water accounting |
| Plant has solvent recovery / 220 C superheated stripping vapour but is modelled with fuel gas | The unit is a Drizo plant | Use `stripping_mode="drizo"`; read the system manual for the solvent loop before choosing the stripping scheme |
| Regeneration column reports `FALLBACK_PRODUCTS` / reboiler duty about 0 | Feed on tray 1 with stripping gas on tray 1 and a high condenser temperature | Feed at tray 0, stripping gas through `getReboiler().addStream(...)`, condenser near the real overhead temperature, as in the `TEGdehydrationProcessDistillationJS` example |

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
