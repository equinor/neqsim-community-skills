---
name: neqsim-continuous-improvement-toolkit
calculation_basis: "advisory"
version: "0.1.0"
description: "Generic building blocks for NeqSim living tasks (continuous task solving): a tagreader historian adapter for PI / IP.21 that plugs into cycle_plan.yaml, Gaussian-process Bayesian optimisation with expected improvement for solve stages on expensive NeqSim models, an ensemble Kalman parameter update, and an SVD identifiability check that shows which model parameters the measurements can actually determine. USE WHEN: a living task needs historian data without enterprise adapters, a solve loop must choose the next setpoint trial and quantify its expected gain for the stop rule, model parameters must be updated cycle by cycle from measurements, or a calibration must be checked for unidentifiable parameters before it is trusted."
last_verified: "2026-09-25"
requires:
  python_packages: [numpy]
  java_packages: []
  env: []
  network: []
---

# Continuous Improvement Toolkit

Public, plant-agnostic helpers for the NeqSim living-task runner
(`neqsim task-living`, `task-cycle`, `task-solve`, `task-backtest`; see the core
skill `neqsim-continuous-task-improvement`). Everything here runs without
enterprise access.

## When to Use

- A living task must read a PI or IP.21 historian: use `TagreaderAdapter`.
- A solve stage tunes a few bounded setpoints and each trial is a NeqSim run:
  use `propose_next` (GP + expected improvement). Pass its
  `expected_improvement` as the candidate's `predicted_delta` so the stop rule
  can declare *converged* when no trial is worth its cost.
- Model parameters drift (fouling factor, efficiency, meter bias): update them
  every cycle with `enkf_update`.
- Before trusting a calibration: `identifiability(J)` — a rank below the number
  of parameters means some combination is set by noise, not data.

## Inputs

- `TagreaderAdapter`: tagreader `source`, `imstype`, `step_seconds` and a
  `tags` map (logical name -> historian tag), plus the runner's watermark window.
- `propose_next`: previous trials `X` (list of setpoint vectors), results `y`,
  `bounds` per variable, `maximize`, and an optional `seed`.
- `enkf_update`: parameter ensemble (members x parameters), matching model
  predictions (members x observations), the measured vector and `obs_std`.
- `identifiability`: a sensitivity Jacobian (observations x parameters),
  optional parameter `names` and `parameter_scale`.

## Outputs

- `TagreaderAdapter.fetch(...)` returns a `SourceResult` (`ok`, `partial`,
  `stale`, `failed`, `not_installed`) and writes a CSV part file to the task's
  `continuous/data/` folder.
- `propose_next` returns `{"x", "expected_improvement", "predicted",
  "predicted_std", "best_so_far"}`.
- `enkf_update` returns the updated ensemble array.
- `identifiability` returns `singular_values`, `condition_number`, `rank`,
  `n_parameters`, an `identifiable` flag, `unidentifiable_directions` and a
  per-parameter `sensitivity_norm`.

## Engineering Method

- Bayesian optimisation: Gaussian-process surrogate (RBF kernel on the unit
  cube) with the expected-improvement acquisition, maximised over random
  candidates inside the bounds.
- Parameter tracking: stochastic ensemble Kalman filter with perturbed
  observations, using ensemble cross-covariances between parameters and
  predictions.
- Identifiability: singular-value decomposition of the scaled Jacobian; a
  parameter combination whose singular value is below the noise level is not
  determined by the data.

## Python Usage Pattern

The sections below show the historian source, a solve stage and a parameter
update as used from a living task.

## Historian source in `cycle_plan.yaml`

```yaml
sources:
  historian:
    adapter: "continuous_improvement_toolkit.tagreader_adapter:TagreaderAdapter"
    initial_lookback_days: 1
    overlap_hours: 2
    options:
      source: "MY-PI-SERVER"      # tagreader data source
      imstype: "piwebapi"          # or "aspenone"
      step_seconds: 3600
      tags:                        # logical name -> historian tag
        suction_pressure_bara: "AREA.PT-0001"
        discharge_pressure_bara: "AREA.PT-0002"
```

The runner resolves the dotted path, so no entry point is needed. Without
`tagreader` installed the source reports `not_installed` and the cycle is
**degraded**, not failed. Authentication failures set `interaction_required`.

## Solve stage with Bayesian optimisation

```python
from continuous_improvement_toolkit import propose_next

def run(ctx):
    trials = ...                      # [(x, y), ...] kept in ctx.state_dir
    step = propose_next([t[0] for t in trials], [t[1] for t in trials],
                        bounds=[(40.0, 60.0), (20.0, 35.0)], maximize=True, seed=len(trials))
    y = evaluate_with_neqsim(step["x"])   # ProcessAutomation.evaluate(...)
    return {"kpis": {"uplift": y},
            "solve": {"value": max(y, best), "validated": True, "confidence": "medium",
                      "candidates": [{"action": "next BO trial", "p_success": 1.0,
                                      "predicted_delta": step["expected_improvement"]}]}}
```

## Parameter update and identifiability

```python
from continuous_improvement_toolkit import enkf_update, identifiability
ensemble = enkf_update(ensemble, predictions, measured, obs_std=[0.2, 0.5])
report = identifiability(jacobian, names=["eta", "fouling"], parameter_scale=[0.01, 1e-4])
if not report["identifiable"]:
    ...  # fix one parameter or add a measurement before calibrating
```

## Validation Checklist

- Backtest the living task (`neqsim task-backtest`) before trusting the drift or
  solve loop on live data.
- Check the `SourceResult` status each cycle; `stale` or `partial` data must not
  drive a solve step.
- Run `identifiability` before accepting an EnKF or calibration result.
- Confirm that a proposed setpoint is inside the bounds and was evaluated with
  the NeqSim model (`validated: True`) before reporting it.

## Common Mistakes

- Mapping logical names to the wrong historian tags or units. Check the `tags`
  map against the P&ID.
- Reporting `expected_improvement` as a realised gain. It is a prediction that
  feeds the stop rule.
- Running the EnKF with too few members, which collapses the ensemble spread.
- Calibrating parameters that `identifiability` reports as undetermined.

## Limitations

- The GP uses a fixed RBF length scale on the unit cube; with fewer than ~5
  trials the proposal is close to space-filling. It is a screening optimiser,
  not a replacement for NeqSim's `AgenticProcessOptimizer` on smooth problems.
- EnKF assumes approximately Gaussian errors; use at least 20 members.
- Nothing here validates a result — validation stays with the NeqSim model and
  the backtest.

## References

- Jones, D. R., Schonlau, M. and Welch, W. J. (1998). Efficient global
  optimization of expensive black-box functions. J. Global Optim. 13, 455-492.
- Evensen, G. (2009). Data Assimilation: The Ensemble Kalman Filter, 2nd ed.
  Springer.
- Page, E. S. (1954). Continuous inspection schemes. Biometrika 41, 100-115.
- tagreader-python: https://github.com/equinor/tagreader-python
