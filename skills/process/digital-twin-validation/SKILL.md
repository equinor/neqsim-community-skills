---
name: neqsim-digital-twin-validation
version: "0.1.0"
description: "Systematic comparison of simulated values against measured reference data with per-channel tolerances, pass/fail aggregation, and an HTML report. USE WHEN: a task needs to measure and report how closely a NeqSim model matches reference/plant data, not to tune model parameters."
last_verified: "2026-06-05"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Digital Twin Validation

Use this skill to compare a model's predicted values against measured reference values
across many operating points and channels, apply per-channel tolerances, aggregate
pass/fail status, and render a portable HTML report. It is a *read-only* accuracy
measurement: it reports the mismatch, it does not change model parameters.

## When to Use

- When you have pairs of (measured, simulated) values for several operating points
  and want a structured pass/fail comparison with tolerances.
- When you need a shareable HTML or tabular summary of model accuracy.
- When you want to express tolerances either as absolute units or as a percentage.

When NOT to use: to *tune* model parameters so the simulation matches data, use a
calibration / data-reconciliation workflow instead (bounded optimization). This skill
only measures and reports accuracy. For result-document quality conventions, follow a
professional reporting skill if your project defines one.

## Inputs

- `specs`: a list of `ChannelSpec(name, tolerance, unit="")`, where `tolerance` is a
  `Tolerance(value, kind)` with `kind` in `{"abs", "pct"}`.
- For each operating point: a `point_id`, a `measured` mapping `{channel: value}`,
  and a `simulated` mapping `{channel: value}`. Missing values are allowed and yield
  a `SKIP` for that channel.

## Outputs

- `PointResult`: per-point list of `ChannelResult` plus an aggregate `status`
  (`PASS`, `FAIL`, or `SKIP`).
- `ChannelResult`: `measured`, `simulated`, `difference`, `rel_pct`, `tolerance`,
  `passed` (`True` / `False` / `None`).
- `ValidationReport`: collection of points with `pass_rate()`, `status`,
  `summary_rows()` (list of flat dicts), and `to_html()`.

## Engineering Method

For each channel a value is compared with its tolerance:

- Absolute tolerance: `passed = abs(simulated - measured) <= value`.
- Percent tolerance: `passed = abs(simulated - measured) / |measured| * 100 <= value`.

A channel with a missing measured or simulated value is `None` (SKIP) and does not
fail the point. A point passes only if every decided channel passes; if no channel is
decided the point is `SKIP`. The report pass-rate counts decided points only.

This is a transparent comparison method. It does not weight channels, propagate
uncertainty, or perform statistical hypothesis testing.

## Python Usage Pattern

```python
from digital_twin_validation import (
    Tolerance, ChannelSpec, evaluate_point, ValidationReport,
)

specs = [
    ChannelSpec("suction_pressure", Tolerance(0.5, "abs"), unit="bara"),
    ChannelSpec("discharge_temperature", Tolerance(2.0, "abs"), unit="C"),
    ChannelSpec("power", Tolerance(5.0, "pct"), unit="MW"),
]

report = ValidationReport(name="demo-train")
report.add(evaluate_point(
    "case_A",
    measured={"suction_pressure": 60.0, "discharge_temperature": 95.0, "power": 12.0},
    simulated={"suction_pressure": 60.3, "discharge_temperature": 96.2, "power": 12.4},
    specs=specs,
))
report.add(evaluate_point(
    "case_B",
    measured={"suction_pressure": 58.0, "discharge_temperature": 90.0, "power": 11.0},
    simulated={"suction_pressure": 59.2, "discharge_temperature": 90.5},  # power missing -> SKIP
    specs=specs,
))

print("pass rate:", report.pass_rate())
print("overall:", report.status)
for row in report.summary_rows():
    print(row["point_id"], row["channel"], row["passed"])

html = report.to_html()  # portable, self-contained string
```

## Validation Checklist

- [ ] Each `ChannelSpec` has a positive tolerance value.
- [ ] Measured and simulated channels use the same units.
- [ ] Percent tolerances are not used where the measured value can be near zero.
- [ ] Missing data produces `SKIP`, not a silent pass.
- [ ] Example inputs are public and synthetic.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Everything passes unexpectedly | channels missing from `simulated` are skipped | confirm channel names match exactly |
| Percent tolerance explodes | measured value near zero | use an absolute tolerance for near-zero channels |
| Point passes but a channel failed | only decided channels are aggregated; a SKIP never fails | check for missing simulated values |
| Report looks empty | no points added | call `report.add(...)` for each point |

## Limitations

- This skill measures accuracy; it does not tune or reconcile model parameters.
- No uncertainty propagation, channel weighting, or statistical testing is performed.
- The HTML report is a simple self-contained table, not a full reporting framework.
- Not a substitute for qualified engineering review of model fidelity.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- General model validation concepts from public engineering literature.
