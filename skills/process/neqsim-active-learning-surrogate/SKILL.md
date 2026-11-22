---
name: neqsim-active-learning-surrogate
calculation_basis: "hybrid"
version: "0.1.0"
description: "Active-learning Gaussian-process surrogate of a NeqSim flowsheet: runs NeqSim only where the surrogate is least certain, learns where a capacity or spec limit binds (AK-MCS), survives failed runs and feeds neqsim-uncertainty-quantification. USE WHEN: a study needs thousands of NeqSim runs (Monte Carlo, sensitivity, envelope maps) but each takes seconds, or the question is where a limit such as compressor power or a product spec starts to bind."
last_verified: "2026-11-21"
requires:
  python_packages: [numpy, scipy, neqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# Active-Learning Surrogate

A NeqSim host model takes about half a second to a minute per run. A Monte
Carlo study with 20,000 samples, a sensitivity analysis or an operating-envelope
map then costs hours or days. Fitting a surrogate to a fixed design does not
solve this well: most of the runs land where the answer is already obvious.

This skill builds the surrogate actively. It starts from a small
Latin-hypercube design, fits a Gaussian process per output, and asks NeqSim for
one new point at a time where it is least certain about what the study needs:

- **global** mode improves accuracy everywhere and stops when every output's
  leave-one-out Q2 reaches `1 - tolerance`;
- **limit_state** mode learns only where one output crosses a threshold, for
  example the compressor driver rating, and stops when the side of the limit
  is known with at least 97.7 % confidence (U >= 2) at every candidate point.

In the bundled example a three-input host flowsheet needs 21 NeqSim runs to
find where the export compressor exceeds its 6.5 MW driver. The surrogate then
gives the exceedance probability over 20,000 operating cases in 0.1 s. Its
maximum tie-in rate at the worst corner, 28.2 t/h, gives 6,492 kW in a direct
NeqSim run, just under the 6,500 kW limit.

## When to Use

- A Monte Carlo, tornado, Sobol or optimisation study wraps a NeqSim flowsheet
  that is too slow to call thousands of times.
- The question is a boundary: maximum tie-in rate before a constraint binds,
  operating window of a separator or compressor, where a product spec fails.
- An operating-envelope map or a fast proxy for a dashboard is needed.
- Some flowsheet runs fail to converge and the study must carry on.

Not for: dynamic time series, problems with more than about 10 inputs, or
responses with jumps (phase disappearance, discrete logic) unless the jump is
the limit being learned.

## Inputs

- `model`: Python callable `dict[input, value] -> mapping[output, value]`
  that runs NeqSim. Raise an exception or return NaN when the run fails.
- `parameters`: `Parameter(name, low, high, log=False)` per input, in
  engineering units.
- `outputs`: output names to learn.
- `mode`: `"global"` or `"limit_state"`; for limit state also
  `limit_output` and `threshold` (in that output's units).
- `tolerance` (global, default 0.01 -> Q2 >= 0.99), `u_stop` (limit state,
  default 2.0), `initial_samples` (default `max(2d + 2, 6)`),
  `max_evaluations` (default 60, failures included), `pool_size` (candidate
  points, default 3000), `patience` (default 2), `seed`.

## Outputs

- `LearningResult`: `surrogate`, `converged`, `stop_reason`, `evaluations`,
  `failures`, `failed_samples`, `history` (Q2 and min U per iteration),
  `samples`/`responses` (all NeqSim runs, reusable as data), `model_time_s`,
  `summary()` for reports.
- `Surrogate`: `predict(values)` (mean and standard deviation per output, one
  or many input sets), `predict_mean`, `as_model(output)` (a `dict -> float`
  callable for `UncertaintyStudy(model=...)`), `exceedance_probability(samples)`,
  `max_feasible(parameter, fixed)` (largest input value that keeps the output
  below the threshold: best estimate and mean + 2 sigma conservative value),
  `extrapolating(values)`, `to_json()` / `from_json()`.
- `validate(surrogate, model, n)` -> `ValidationReport` with RMSE, maximum
  error, normalised RMSE, 2-sigma coverage and, in limit-state mode, the
  share of fresh NeqSim runs on the same side of the limit as predicted.

## Engineering Method

1. Inputs are scaled to the unit cube (optionally on a log scale).
2. Each output gets a Gaussian process with a Matern 5/2 kernel, one length
   scale per input (automatic relevance: an input that does not matter gets a
   long length scale), a small nugget for solver noise, and hyperparameters
   from maximum marginal likelihood (L-BFGS-B, multiple restarts).
3. Accuracy is measured by closed-form leave-one-out residuals (Q2) without
   refitting.
4. Next point: global mode takes the candidate with the largest summed
   predictive standard deviation, each output scaled by its spread;
   limit-state mode takes the candidate with the smallest
   `U = |mean - threshold| / std` (AK-MCS, Echard et al., 2011).
5. Failed runs are stored and candidates within `0.05 sqrt(d)` of a failure
   are excluded.
6. Exceedance probability averages `Phi((mean - threshold) / std)` over the
   samples, so remaining surrogate uncertainty near the limit is included.

The physics stays in NeqSim; the surrogate is an interpolator of NeqSim
results inside the trained box and carries no physics of its own.

## Python Usage Pattern

```python
from active_learning_surrogate import ActiveLearner, Parameter, validate

def host_model(values):           # wraps a NeqSim ProcessSystem
    ...                           # build, set inputs, system.run()
    return {"compressor_power_kw": compressor.getPower("kW")}

result = ActiveLearner(
    model=host_model,
    parameters=[Parameter("tiein_rate_kgh", 0, 60000),
                Parameter("separator_pressure_bara", 30, 70)],
    outputs=["compressor_power_kw"],
    mode="limit_state", limit_output="compressor_power_kw", threshold=6500.0,
).run()
print(result.summary())
check = validate(result.surrogate, host_model, n=8)    # always spot-check
limit = result.surrogate.max_feasible("tiein_rate_kgh", {"separator_pressure_bara": 40})
# confirm limit["best_estimate"] with one direct NeqSim run

# Feed the existing UQ skill with a millisecond model
from uncertainty_quantification import Triangular, Uniform, UncertaintyStudy
study = UncertaintyStudy(
    parameters=[Triangular("tiein_rate_kgh", "kg/h", low=10000, base_value=35000, high=55000),
                Uniform("separator_pressure_bara", "bara", low=40, high=60)],
    output_name="compressor_power_kw",
    model=result.surrogate.as_model("compressor_power_kw"),
)
print(study.run(5000).summary)
```

The complete case is `examples/host_compressor_capacity_boundary.py`
(about 15 s with NeqSim installed).

## Validation Checklist

- [ ] `validate()` was run on fresh NeqSim points and the result is reported;
      limit-state agreement should be at or near 100 %, 2-sigma coverage near
      95 % in global mode.
- [ ] `converged` is true; if the budget ran out, the report says so.
- [ ] Every prediction used lies inside the trained box
      (`extrapolating()` is empty).
- [ ] Failed runs were reviewed: a cluster of failures can hide a real
      operating limit (for example, no gas phase).
- [ ] Input distributions for the Monte Carlo come from the study basis, not
      from the surrogate ranges.
- [ ] The NeqSim model behind the surrogate was itself checked against data
      or a reference case.
- [ ] A decision value from `max_feasible` was confirmed with a direct NeqSim
      run, and both numbers are reported.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Q2 stalls below target | Discontinuous response (phase change, logic) | Split the range at the discontinuity, or learn the boundary in limit-state mode |
| Limit-state stops early with a wrong boundary | Threshold outside the reachable output range, or pool too small | Check the output range in `responses`; raise `pool_size` |
| Coverage far below 95 % | Over-confident GP from too few points | Lower `tolerance`, add `initial_samples`, check with more validation points |
| Many failures in one corner | Flowsheet not converging there | Inspect `failed_samples`; narrow the range or fix the model |
| Slow learning | Inputs spanning decades on a linear scale | Use `Parameter(..., log=True)` |

## Limitations

- Accuracy holds only inside the trained box; no extrapolation.
- Practical up to about 10 inputs and a few hundred runs (cubic cost in the
  number of runs).
- Assumes a smooth response; the nugget absorbs only small solver noise.
- The surrogate is a screening and study tool, not a substitute for running
  NeqSim at a final design point or for engineering judgement.

## Related NeqSim Functionality

- Wraps any NeqSim calculation reached with `from neqsim import jneqsim`,
  typically `neqsim.process.processmodel.ProcessSystem#run()` with
  `neqsim.process.equipment.compressor.Compressor#getPower(String)` or
  `neqsim.process.equipment.separator.Separator` outputs.
- The JSON export carries the training data and hyperparameters; the Java-side
  runtime home for fast proxies is
  `neqsim.process.ml.surrogate.SurrogateModelRegistry` (with
  `predictWithFallback` to the physics model). This skill does not register
  models there automatically.
- Related community skills: `neqsim-uncertainty-quantification` (consumes
  `as_model`), `neqsim-fluid-commingling-compatibility`,
  `neqsim-compressor-operating-window-check`.

## References

- Echard, B., Gayton, N., Lemaire, M. (2011). AK-MCS: an active learning
  reliability method combining Kriging and Monte Carlo simulation. Structural
  Safety 33(2), 145-154.
- Rasmussen, C.E., Williams, C.K.I. (2006). Gaussian Processes for Machine
  Learning. MIT Press.
- Jones, D.R., Schonlau, M., Welch, W.J. (1998). Efficient global
  optimization of expensive black-box functions. Journal of Global
  Optimization 13, 455-492.
- NeqSim repository: https://github.com/equinor/neqsim
