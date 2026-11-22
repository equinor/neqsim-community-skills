# Active-Learning Surrogate

Builds a fast, validated stand-in for a slow NeqSim model by running NeqSim
only where the stand-in is least certain. Use it when a study needs thousands of
NeqSim evaluations, or when the question is where a limit starts to bind.

| Question | Mode | Typical NeqSim runs |
| --- | --- | --- |
| Maximum tie-in rate before the compressor driver, separator or export spec limits | `limit_state` | 15-40 |
| Probability of exceeding a limit over an uncertain operating envelope | `limit_state` | 15-40 |
| P10/P50/P90, tornado or Sobol on a slow flowsheet | `global` | 20-80 |
| Operating-envelope map or a fast proxy for a dashboard | `global` | 30-150 |

Method, equations, limitations and references are in [SKILL.md](SKILL.md).

## Install

From a NeqSim community workspace:

```bash
neqsim skill install neqsim-active-learning-surrogate --vscode
```

Or directly from a checkout of this repository:

```bash
python -m pip install -e "skills/process/neqsim-active-learning-surrogate[neqsim]"
```

Only `numpy` and `scipy` are needed for the learner itself; `neqsim` is needed
for the model you wrap.

## Quick Start

```bash
python skills/process/neqsim-active-learning-surrogate/examples/host_compressor_capacity_boundary.py
```

A synthetic host (well stream + tie-in gas -> separator -> export compressor).
In about 15 s it learns where the compressor exceeds its 6.5 MW driver from 21
NeqSim runs. It then gives the exceedance probability over 20,000 cases, the
maximum tie-in rate at the worst corner (checked with a direct NeqSim run), and
P10/P50/P90 through the uncertainty-quantification skill.

## How to Use

### 1. Wrap the NeqSim model as a function

```python
def host_model(values: dict[str, float]) -> dict[str, float]:
    from neqsim import jneqsim
    # build the fluid and ProcessSystem, set inputs from `values`, run
    ...
    system.run()
    return {
        "compressor_power_kw": compressor.getPower("kW"),
        "export_gas_msm3d": separator.getGasOutStream().getFlowRate("MSm3/day"),
    }
```

- **Inputs in, outputs out**, as plain dicts of floats keyed by name.
- **Build a fresh fluid and process on every call.** Reusing a solved
  `ProcessSystem` carries state between runs and makes results depend on the
  order they were run in.
- **Fail loudly.** Raise an exception or return `nan` when the flowsheet does not
  converge. The learner records the failure and avoids that region; a wrong
  number from a non-converged run silently corrupts the surrogate.
- **Time one call first.** Below about 10 ms per run, run the study on NeqSim
  directly instead.

### 2. Define the inputs and pick the mode

```python
from active_learning_surrogate import ActiveLearner, Parameter

parameters = [
    Parameter("tiein_rate_kgh", 0.0, 60000.0),
    Parameter("separator_pressure_bara", 30.0, 70.0),
    Parameter("inlet_temperature_c", 30.0, 70.0),
    # Parameter("water_cut", 0.01, 0.9, log=True)   # for ranges spanning decades
]
```

The ranges bound the surrogate: it is only valid inside them. Make them wide
enough to cover the study, but no wider. Every extra unit of range costs runs.

```python
# A limit: where does compressor power cross 6.5 MW?
learner = ActiveLearner(
    model=host_model,
    parameters=parameters,
    outputs=["compressor_power_kw", "export_gas_msm3d"],
    mode="limit_state",
    limit_output="compressor_power_kw",
    threshold=6500.0,
    max_evaluations=40,
    callback=lambda r: print(r.evaluations, r.min_u, r.q2),
)

# Accuracy everywhere (Monte Carlo, sensitivity, maps):
learner = ActiveLearner(host_model, parameters,
                        ["compressor_power_kw", "export_gas_msm3d"],
                        mode="global", tolerance=0.01)   # Q2 >= 0.99
```

### 3. Run and check that it converged

```python
result = learner.run()
print(result.summary())     # converged, stop_reason, evaluations, failures, Q2, min U
```

- `converged=False` with `stop_reason="budget exhausted"` means the budget ran
  out. Raise `max_evaluations` or narrow the ranges before using the result.
- `result.failed_samples` lists the inputs where NeqSim failed. A cluster can
  mark a real physical limit (no gas phase, a compressor out of range); report
  it rather than ignoring it.
- `result.samples` and `result.responses` hold every NeqSim run, so they can be
  reused as data.

### 4. Validate against fresh NeqSim runs

```python
from active_learning_surrogate import validate

check = validate(result.surrogate, host_model, n=10)
print(check.classification_agreement)  # limit_state: should be 1.0
print(check.normalised_rmse, check.coverage_2sigma)  # global: small, and about 0.95
```

Always report this check alongside the results.

### 5. Use the surrogate

```python
surrogate = result.surrogate

# Predictions with uncertainty, one or many input sets
surrogate.predict({"tiein_rate_kgh": 30000, "separator_pressure_bara": 45,
                   "inlet_temperature_c": 50})

# Largest tie-in rate that keeps power below the limit at the worst corner
surrogate.max_feasible("tiein_rate_kgh",
                       {"separator_pressure_bara": 40, "inlet_temperature_c": 60})
# -> {"best_estimate": 28200.0, "conservative": 28050.0}   (kg/h)

# Probability of exceeding the limit over sampled operating cases
surrogate.exceedance_probability(samples)       # samples: list of input dicts

# Monte Carlo, tornado and Sobol with the uncertainty-quantification skill
from uncertainty_quantification import Triangular, Uniform, UncertaintyStudy
study = UncertaintyStudy(
    parameters=[Triangular("tiein_rate_kgh", "kg/h", low=10000, base_value=35000, high=55000),
                Uniform("separator_pressure_bara", "bara", low=40, high=60),
                Uniform("inlet_temperature_c", "C", low=35, high=60)],
    output_name="compressor_power_kw", output_unit="kW",
    model=surrogate.as_model("compressor_power_kw"),
)
print(study.run(5000).summary)

# Save and reload
surrogate.to_json("host_surrogate.json")
```

- `surrogate.extrapolating(values)` names any input outside the trained range;
  do not use predictions where it is non-empty.
- `max_feasible` assumes feasibility shrinks as the scanned input grows. If
  that may not hold, inspect `predict` along the line.
- Confirm the decision value (for example the maximum rate) with one direct
  NeqSim run, and report both numbers.

## Choosing Settings

| Setting | Default | When to change |
| --- | --- | --- |
| `initial_samples` | `max(2d + 2, 6)` | Raise for strongly non-linear responses |
| `max_evaluations` | 60 | Raise for more inputs or tighter tolerances |
| `tolerance` (global) | 0.01 (Q2 >= 0.99) | Lower for decision-critical maps |
| `u_stop` (limit state) | 2.0 (97.7 % side-of-limit confidence) | 3.0 for a stricter boundary |
| `pool_size` | 3000 | Raise above 3000 for 6+ inputs |
| `seed` | 42 | Change to check the result is not seed-dependent |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Q2 stalls below target | The response has a jump (phase disappears, logic switch): split the range there, or learn the jump as a limit |
| Limit-state converges almost at once | The threshold lies outside the reachable output range; check `result.responses` |
| `SurrogateError: only n of m evaluations succeeded` | The model fails almost everywhere; test it on a few points by hand |
| 2-sigma coverage well below 0.95 | Over-confident fit: add `initial_samples`, lower `tolerance`, validate with more points |
| Slow learning on a wide-range input | Use `Parameter(..., log=True)` |

## Tests

```bash
python -m pytest skills/process/neqsim-active-learning-surrogate/tests
```

The Gaussian process and the learner are tested on analytic functions without
Java (convergence, boundary learning, exceedance probability against brute
force, `max_feasible` against the exact limit, failure handling, JSON round
trip). `tests/test_neqsim_integration.py` learns a real NeqSim flowsheet
boundary and is skipped when `neqsim` is not installed.

## Public Scope

Standard published methods (Gaussian-process regression, Latin hypercube,
AK-MCS active learning) implemented with numpy and scipy. Example process data
are synthetic. A surrogate is a study tool: it does not replace a NeqSim run at
the final design point, vendor data or engineering judgement.
