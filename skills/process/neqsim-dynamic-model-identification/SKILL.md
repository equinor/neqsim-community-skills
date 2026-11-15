---
name: neqsim-dynamic-model-identification
calculation_basis: "screening"
version: "0.1.0"
description: "Dynamic model identification from imperfect plant data with equinor/TimeSeriesAnalysis: process gain, time constant and delay; PID tuning; closed-loop process model and disturbance; bad, frozen and on-change data handled; saturation for control authority; usability gate per result. USE WHEN: root cause, control-loop or trend studies need identified dynamics from historian data."
last_verified: "2026-11-15"
requires:
  python_packages: [pythonnet, numpy, pandas, matplotlib]
  java_packages: []
  env: [TIMESERIESANALYSIS_ASSEMBLY_PATH]
  network: []
---

# Dynamic Model Identification from Plant Data

Use this skill to turn historian series into identified dynamics. Examples are how strongly and how fast a controller output moves a measurement, what PI tuning a loop actually runs, and how large the disturbance a loop rejects is. It wraps [equinor/TimeSeriesAnalysis](https://github.com/equinor/TimeSeriesAnalysis) (Apache-2.0, .NET), which is built for non-ideal industrial data, through pythonnet. Every result carries a usability verdict, so an agent cannot pass on a meaningless fit.

## When to Use

- Root-cause work that needs to know whether an input really drives an output, with which gain and lag (for example oil temperature against cooler valve, or bearing temperature against load).
- Control-authority and loop reviews: identified PI tuning, process gain from closed-loop data, saturation share at each stop, and the disturbance the loop rejects.
- Turning a historian trend into a model for a NeqSim dynamic simulation or controller tuning (`neqsim-dynamic-simulation`, `control-system` work).

Do not use it to prove causality: an identified gain between correlated series is evidence, not proof.

## Inputs

Config for `<python> -m dynamic_identification run config.json`:

- `series`: role to `{path, column, time_column, sentinels, hold}`. Each entry is one CSV with a time column (default `time`) and a value column (default `avg`, else the second column). `sentinels` are fault codes that become bad data. Set `hold: true` for on-change tags (setpoints, modes, pump status) and for raw tags stored by exception (compressed PI/IMS data, where a gap means "unchanged within the deadband"), so the last value holds until the next sample.
- `window` (`start`, `end`), `timebase_s` (default: the slowest median sample interval), `max_gap_s`, `frozen_samples` (runs of identical values to mark as frozen).
- `analyses`:
  - `loop`: `pv`, `sp`, `out` roles, optional `out_range` (saturation and PID scaling), `pv_range`, `controller_type` (`Temperature`, `Pressure`, `Level`, `Flow`, ...), and known `pid` tuning (`kp`, `ti_s`, `td_s`).
  - `unit`: `output` role and up to six `inputs` (open-loop: inputs not set by feedback from the output); `estimate_delay`.
- `out_dir`.

Engine setup, once per machine: `<python> -m dynamic_identification setup` publishes TimeSeriesAnalysis 1.4.38 and its dependencies from NuGet with the .NET SDK into `~/.neqsim/timeseriesanalysis/1.4.38`. It is explicit and user-run, never automatic. Alternatives: set `TIMESERIESANALYSIS_ASSEMBLY_PATH`, or install equinor/timeseriesanalysis-py (Python 3.13), whose `_assemblies` folder is found. Runtime needs the .NET 8 runtime or newer.

## Outputs

`dynamic_identification_evidence.v1` (`identification_evidence.json`), always `unverified`:
- `data`: time base, window, samples, bad fraction per series.
- `results.loop`:
  - `saturation` (share at each stop, P01/P50/P99);
  - `pid` (`kp`, `ti_s`, `td_s`, fitting, `usable`);
  - `process_closed_loop` (gain, time constant, delay, bias, `u0`, `pid_used` with its source, disturbance statistics, `usable`).
- `results.unit`: gain per input with uncertainty, time constant, delay, bias, `u0`, fitting, `usable`.
- `warnings` (unusable results with reasons, unresolved dynamics, saturation, constant setpoint, open-loop fit on closed-loop data), `engine` (assembly folder), `required_checks`.
- Files: `identification.png` (measured against model), `disturbance.csv` (closed loop).

## Engineering Method

1. **Data.** Each series is put on one uniform grid. A grid point takes the latest sample within one time base; older samples are bad, except for `hold` series. Sentinels and frozen runs are bad. Bad points go to TimeSeriesAnalysis as its bad-data marker (-9999) and are skipped in fitting, not interpolated.
2. **Unit model** (`UnitIdentifier.Identify`): `y = bias + sum_i K_i (u_i - u0_i)` through a first-order lag with time constant and time delay. Linear and static variants are compared and the best fit is kept.
3. **PID** (`PidIdentifier`): Kp, Ti, Td from measurement, setpoint and output. Kp is in engineering units unless `out_range` and `pv_range` give the controller's scaling.
4. **Closed loop** (`ClosedLoopUnitIdentifier`): the process model from data where the input is set by feedback, and the disturbance series the controller rejected. Without given tuning, the PID is identified first and passed in; `pid_used.source` says which.
5. **Usability gate.** A result is `usable: false` when:
   - the solver failed or returned its initial heuristic ("no minimum found");
   - more than half the points were bad;
   - or the fit score is negative.

   Separately, time constants and delays below two samples are flagged as unresolved. An exception inside the engine is reported as a warning (`engine_error`), not raised.

Verified on plant data: lube-oil return temperature against compressor speed in 60 s stop/start windows on five compressor trains gave gains of 5.4-7.1 °C per 1000 rpm, time constants of 1.7-2.5 min, a 1 min delay and fit scores of 95-97 %. The same site's hourly cooler-loop data was correctly rejected (dynamics below the time base, no minimum found).

## Python Usage Pattern

```python
from dynamic_identification import identify_unit, identify_pid, identify_closed_loop

model = identify_unit(y, {"valve": u}, timebase_s=10.0)          # open loop
print(model["gains"], model["time_constant_s"], model["time_delay_s"], model["fitting"]["fit_score_pct"])
tuning = identify_pid(pv, sp, out, timebase_s=10.0, controller_type="Temperature")
process = identify_closed_loop(pv, sp, out, timebase_s=10.0)     # gain and disturbance under feedback
```

## Validation Checklist

- [ ] The window holds excitation: setpoint changes, load changes, starts. Flat data identifies nothing; the setpoint warning says so.
- [ ] The time base is at least five times shorter than the expected time constant. Hourly averages cannot identify a cooler or pressure loop; read raw or minute data for event windows.
- [ ] Every number used downstream has `usable: true`.
- [ ] Closed-loop data uses `loop`, not `unit` (an open-loop fit on feedback data is biased).
- [ ] Identified tuning is compared with the control-system configuration before conclusions about the loop.

## Common Mistakes

- Treating hold-last, on-change or exception-stored (compressed) tags as continuous signals without `hold`; they come out largely bad, and the engine can fail on the gaps.
- Reading the bias as the operating level: it is the output at `u0`, the mean input of the window.
- Concluding "no dynamics" from a zero time constant on coarse data: the dynamics are faster than the sampling.
- Including starts and stops in a window meant for steady control: identify per regime.

## Limitations

- First-order-plus-delay structure per input, with optional curvature; no oscillatory or integrating process models through this wrapper.
- Identification is only as good as the excitation and the time base; results are screening evidence and need human review.
- The engine needs .NET; without the assemblies the run is blocked with the setup command, and no other fit is substituted.

## References

- equinor/TimeSeriesAnalysis (Apache-2.0): https://github.com/equinor/TimeSeriesAnalysis and API documentation https://equinor.github.io/TimeSeriesAnalysis
- equinor/timeseriesanalysis-py: Python proxies over the same assemblies (Python 3.13).
- Related skills: `neqsim-dynamic-simulation` (use the identified model), `neqsim-plant-data` and `neqsim-model-calibration-and-data-reconciliation` (historian data), `neqsim-root-cause-analysis` (hypotheses this evidence supports or weakens).
