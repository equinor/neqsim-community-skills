---
name: neqsim-dynamic-model-identification
calculation_basis: "hybrid"
version: "0.3.0"
description: "Dynamic model identification from plant data with equinor/TimeSeriesAnalysis, joined to NeqSim physics: gain, time constant and delay; PID tuning; closed-loop model and disturbance; NeqSim gains to check identified ones; physics residuals that separate equipment change from sensor fault; replay of identified models; move forecasts (NeqSim steady change, identified timing) with backtest; usability gate. USE WHEN: root cause, control-loop or monitoring studies use historian data."
last_verified: "2026-11-15"
requires:
  python_packages: [pythonnet, numpy, pandas, matplotlib, neqsim]
  java_packages: []
  env: [TIMESERIESANALYSIS_ASSEMBLY_PATH]
  network: []
---

# Dynamic Model Identification from Plant Data

Use this skill to turn historian series into identified dynamics. Examples are how strongly and how fast a controller output moves a measurement, what PI tuning a loop actually runs, and how large the disturbance a loop rejects is. It wraps [equinor/TimeSeriesAnalysis](https://github.com/equinor/TimeSeriesAnalysis) (Apache-2.0, .NET), which is built for non-ideal industrial data, through pythonnet. Every result carries a usability verdict, so an agent cannot pass on a meaningless fit.

NeqSim and TimeSeriesAnalysis do different jobs and work best together. NeqSim gives the physics at an operating point: steady gains, expected power, temperatures and phase behaviour. It has no time constants. TimeSeriesAnalysis gives the dynamics from data: lags, delays, loop behaviour and disturbances. It has no thermodynamics. The `neqsim_bridge` module joins them, following the worked example notebook [NeqSim x TimeSeriesAnalysis: large-process analytics](https://colab.research.google.com/github/EvenSol/NeqSim-Colab/blob/master/notebooks/advanced_analytics/neqsim_timeseriesanalysis_large_process.ipynb).

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
  - `unit`: `output` role and up to six `inputs` (open-loop: inputs not set by feedback from the output); `estimate_delay`; `method` (`best` by default, or `auto`, `linear`, `static`).
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
2. **Unit model**: `y = bias + sum_i K_i (u_i - u0_i)` through a first-order lag with time constant and time delay. The default `method: best` runs `UnitIdentifier.Identify` (which also tries curvature and static candidates) and `IdentifyLinear` (linear dynamic), and keeps the higher fit score. The other is recorded under `alternatives`. `Identify` alone can settle on a static model when a linear dynamic one fits better: on a lagged compressor-power test it gave a 0 s time constant at 82 % fit, where `IdentifyLinear` gave the right gains and lag at 98 %.
3. **PID** (`PidIdentifier`): Kp, Ti, Td from measurement, setpoint and output. Kp is in engineering units unless `out_range` and `pv_range` give the controller's scaling.
4. **Closed loop** (`ClosedLoopUnitIdentifier`): the process model from data where the input is set by feedback, and the disturbance series the controller rejected. Without given tuning, the PID is identified first and passed in; `pid_used.source` says which.
5. **Usability gate.** A result is `usable: false` when:
   - the solver failed or returned its initial heuristic ("no minimum found");
   - more than half the points were bad;
   - or the fit score is negative.

   Separately, time constants and delays below two samples are flagged as unresolved. An exception inside the engine is reported as a warning (`engine_error`), not raised.

Verified on plant data: lube-oil return temperature against compressor speed in 60 s stop/start windows on five compressor trains gave gains of 5.4-7.1 °C per 1000 rpm, time constants of 1.7-2.5 min, a 1 min delay and fit scores of 95-97 %. The same site's hourly cooler-loop data was correctly rejected (dynamics below the time base, no minimum found).

## Using with NeqSim

`dynamic_identification.neqsim_bridge` joins a NeqSim `ProcessSystem` or `ProcessModel` to the identified dynamics. NeqSim (JPype) and TimeSeriesAnalysis (pythonnet CoreCLR) run in the same Python process. Both start orders were verified on Windows; on Linux load CoreCLR first, as the notebook does.

1. **Map tags to NeqSim addresses first.** Use `process.getAutomation().getVariableList(unit)` for addresses such as `feed.flowRate` and `comp.power`.
   - State the units and flow basis (mass, molar, standard or actual volume).
   - Convert gauge pressures to absolute.
   - Align clocks, and estimate transport delays before comparing measured with predicted.

   `automation_evaluator(process, {"flow": "feed.flowRate|kg/sec"}, {"power": "comp.power|kW"})` returns a function that sets inputs, runs and reads outputs.
2. **Physics residuals.** At each observed operating point, NeqSim gives the expected value of a measurement. `physics_residuals(measured, expected, calibration=slice(...))` standardises measured minus expected on a healthy calibration window and low-pass filters it.

   `two_residual_diagnosis(power_flag, temperature_flag)` compares two independently measured signals:
   - both flagged means a physical change candidate, for example an efficiency loss;
   - one flagged means a measurement or model candidate, for example a meter bias.

   The second signal must not be fitted.
3. **Physics checks the identification.** `steady_gains(evaluate, base, steps)` gives NeqSim central-difference gains with a half-step convergence check. `compare_gains(identified["gains"], physics["gains"][output])` tests sign and size. A sign error or a ratio far from one points to one of:
   - a wrong tag;
   - a unit or flow-basis mismatch;
   - closed-loop bias;
   - an unmodelled effect.

   NeqSim gains can also seed a reduced model when data cannot identify the gain; the time constants still come from data.
4. **Replay.** `simulate_unit(model, inputs, timebase_s)` runs an identified model forward with `UnitModel.Iterate`. Use it for a chronological hold-out (train on the first part of the window, test on the rest, never shuffle) and for what-if inputs within the identified range.
5. **Choose the fidelity.**
   - Reduced TSA models suit stable regimes with identifiable dominant dynamics.
   - Inventory, phase redistribution, network hydraulics and slugging need native NeqSim dynamic equipment (`neqsim-dynamic-simulation`).
   - Calling a steady process repeatedly does not make a transient model.
   - Revalidate after maintenance, sensor changes or operation outside the identified envelope.

Verified with NeqSim: on a compressor (methane-rich gas, 30 to 90 bara, polytropic efficiency 0.78), NeqSim gave power gains of 217 kW per kg/s of flow and -161 kW per bar of suction pressure. Identification on a lagged historian generated from that map gave 216.6 and -161.8 with a 53 s time constant (55 s expected), and the replay held out within 30 kW RMS. Physics residuals labelled an efficiency drop to 0.73 as a physical change and a 400 kW meter bias as a measurement candidate.

## Forecasting the effect of a move

To answer "what happens to output y if we move input u", without simulating the full transient, combine:
- NeqSim for the steady change;
- plant data for the timing.

`dynamic_identification.step_prediction` provides:
- `fit_step_dynamics`, `pooled_dynamics`: time constant and delay from past moves, with a signal-to-noise ratio per move;
- `hybrid_step_forecast`: `y(t) = y0 + dy_NeqSim * (1 - exp(-(t - delay)/tau))`;
- `detect_steps`: isolated moves of one manipulated variable while the others stay quiet;
- `score_forecast`: skill against persistence, the forecast "nothing changes".

1. Re-solve the steady NeqSim flowsheet at the new setting, or use `steady_gains`. Convert a valve move to the
   quantity the model takes: for a choke in critical flow, q is proportional to Cv(z)·P_up, and the upstream pressure
   falls as the valve opens. Measure that damping on past moves rather than assuming dq/q = dz/z.
2. Find isolated past moves (`detect_steps`). Then reject confounded windows: every other feed of the same unit
   (other arrival temperatures, pressures, flows) must be steady. A large "response" with a moving neighbour is not
   evidence about the move.
3. Backtest leave-one-out before using the forecast. Fit timing on the other moves, predict each held-out move, and
   compare with persistence. Report how many moves rise above the measurement noise.
4. Add the NeqSim *change* to the measured current value; the model's absolute level is usually offset.
5. Gate the physics as well. A small trim cannot move a mixed stream by more than the trimmed stream's share times
   its temperature difference. A larger NeqSim change is a solver branch jump, not a prediction.

A data-only model (identify u → y on past moves, then `simulate_unit`) is a useful cross-check but rarely a
forecaster on its own. With a few moves per input and noisy outputs, its gains are unstable and can have the wrong
sign; the physics fixes magnitude and sign. If both the physics and the data say the effect is below the noise,
that is the answer.

## Plant data sources

Any historian works when it delivers `time,value` CSVs per tag in UTC (`neqsim-plant-data` covers PI and IP.21 through tagreader). Company-specific historian services belong in the company's own skill catalogue. A good one writes these CSVs and returns the config `series` block, marking `hold` on raw reads from exception-stored historians.

## Python Usage Pattern

```python
from dynamic_identification import identify_unit, identify_pid, identify_closed_loop
from dynamic_identification.neqsim_bridge import (automation_evaluator, steady_gains, compare_gains,
                                                  physics_residuals, two_residual_diagnosis, simulate_unit)

model = identify_unit(y, {"flow": flow, "ps": suction}, timebase_s=10.0)     # open loop, method="best"
tuning = identify_pid(pv, sp, out, timebase_s=10.0, controller_type="Temperature")
process_model = identify_closed_loop(pv, sp, out, timebase_s=10.0)            # gain and disturbance under feedback

evaluate = automation_evaluator(process, {"flow": "feed.flowRate|kg/sec", "ps": "feed.pressure|bara"},
                                {"power": "comp.power|kW"})
physics = steady_gains(evaluate, {"flow": 20.0, "ps": 30.0}, {"flow": 0.5, "ps": 0.5}, ["power"])
check = compare_gains(model["gains"], physics["gains"]["power"])            # sign and size against physics
replay = simulate_unit(model, {"flow": flow_new, "ps": suction_new}, 10.0)

from dynamic_identification.step_prediction import fit_step_dynamics, pooled_dynamics, hybrid_step_forecast, score_forecast
fits = [fit_step_dynamics(t_rel_s, y_win) for t_rel_s, y_win in past_moves]   # step at t = 0 in each window
dyn = pooled_dynamics(fits, min_snr=3.0)
forecast = hybrid_step_forecast(y_now, dT_neqsim, dyn["tau_s"], dyn["delay_s"], horizon_s=6 * 3600)
```

## Validation Checklist

- [ ] The window holds excitation: setpoint changes, load changes, starts. Flat data identifies nothing; the setpoint warning says so.
- [ ] The time base is at least five times shorter than the expected time constant. Hourly averages cannot identify a cooler or pressure loop; read raw or minute data for event windows.
- [ ] Every number used downstream has `usable: true`.
- [ ] Closed-loop data uses `loop`, not `unit` (an open-loop fit on feedback data is biased).
- [ ] Identified tuning is compared with the control-system configuration before conclusions about the loop.
- [ ] Where a NeqSim model of the unit exists, identified gains agree with `steady_gains` in sign and size (`compare_gains`), or the difference is explained.
- [ ] Physics residuals were calibrated on a window confirmed healthy, and the second signal of a two-residual diagnosis is independent of the first.
- [ ] A move forecast was backtested leave-one-out on unconfounded past moves against persistence, and the number of moves above the noise is reported.
- [ ] Hold-out validation is chronological; the identified model is used only inside its identified envelope.

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
- Worked example: [NeqSim x TimeSeriesAnalysis: large-process analytics](https://colab.research.google.com/github/EvenSol/NeqSim-Colab/blob/master/notebooks/advanced_analytics/neqsim_timeseriesanalysis_large_process.ipynb). It covers a six-train NeqSim facility, constrained load allocation, identified cooler dynamics, `PlantSimulator` networks with six PID loops, compressor diagnosis from physics residuals, and JSON process graphs projected to TSA models.
- Related skills: `neqsim-dynamic-simulation` (use the identified model), `neqsim-plant-data` and `neqsim-model-calibration-and-data-reconciliation` (historian data), `neqsim-root-cause-analysis` (hypotheses this evidence supports or weakens).
