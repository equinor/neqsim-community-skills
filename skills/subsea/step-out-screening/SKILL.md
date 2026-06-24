---
name: neqsim-step-out-screening
version: "0.1.0"
description: "Educational subsea tie-back step-out and arrival-pressure screening with optional hydrate-margin input. USE WHEN: a task needs a public, screening-level check of whether a tie-back step-out distance and arrival pressure stay within simple guidelines before detailed flow-assurance and hydraulic design."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Step-Out Screening

Use this skill for a quick, public screening that ties subsea layout geometry to early flow-assurance and process limits. Given a tie-back step-out distance, an estimated arrival pressure, and a minimum required arrival pressure, it produces simple step-out and arrival-pressure warnings and an overall verdict. An optional hydrate temperature margin can be supplied so the thermal side contributes to the overall flag. It is intentionally simple and should guide users toward validated NeqSim flow-assurance and hydraulic workflows.

## When to Use

- When a user has a tie-back step-out distance and wants a first check against a simple step-out guideline.
- When an arrival-pressure estimate should be screened against a minimum required arrival pressure.
- When an agent should combine geometry, pressure, and an optional hydrate margin into one screening verdict before detailed analysis.

## Inputs

- `step_out_km`: tie-back step-out distance from host to the tied-back development.
- `arrival_pressure_bara`: estimated arrival pressure at the host.
- `min_arrival_pressure_bara`: minimum required arrival pressure.
- `max_step_out_km`: configurable public step-out guideline (default 50 km).
- `hydrate_margin_c`: optional temperature margin above the hydrate equilibrium temperature.

## Outputs

- `step_out_warning`: `ok`, `watch`, or `high` against the step-out guideline.
- `arrival_pressure_margin_bar`: arrival pressure minus the minimum required arrival pressure.
- `pressure_warning`: `ok`, `watch`, or `high` based on the arrival-pressure margin.
- `hydrate_warning`: `ok`, `watch`, `high`, or `not_assessed` from the optional hydrate margin.
- `overall_warning`: the worst of the individual warnings.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

The step-out distance is compared to a configurable public guideline: at or above the guideline is `high`, above 80 % is `watch`, otherwise `ok`. The arrival-pressure margin is the estimated arrival pressure minus the minimum required arrival pressure; a negative margin is `high`, a small positive margin (below 10 % of the minimum) is `watch`, otherwise `ok`. If a hydrate temperature margin is supplied, a negative margin is `high`, below a small threshold is `watch`, otherwise `ok`; if omitted it is `not_assessed`. The overall warning is the most severe of the assessed warnings.

This skill performs no hydraulic or thermodynamic calculation. The arrival pressure and hydrate margin must come from validated tools; this skill only applies simple guideline comparisons to supplied values.

## Python Usage Pattern

```python
from step_out_screening import StepOutScreeningModel

model = StepOutScreeningModel(max_step_out_km=50.0)
result = model.evaluate(
    step_out_km=42.0,
    arrival_pressure_bara=95.0,
    min_arrival_pressure_bara=90.0,
    hydrate_margin_c=3.0,
)

print(result.step_out_warning)
print(result.arrival_pressure_margin_bar)
print(result.pressure_warning)
print(result.hydrate_warning)
print(result.overall_warning)
print(result.assumptions)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim flow-assurance and hydraulic workflows. If not, the example still runs with the public guideline logic.

## Validation Checklist

- [ ] Arrival pressure comes from a validated hydraulic calculation, not a guess.
- [ ] Minimum required arrival pressure reflects the real receiving-facility constraint.
- [ ] The step-out guideline is documented as a configurable public guideline only.
- [ ] Any hydrate margin comes from a validated hydrate calculation.
- [ ] A `high` or `watch` verdict is escalated to detailed flow-assurance review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Optimistic verdict | Arrival pressure estimate too high | Use a validated hydraulic arrival pressure |
| Hydrate side always `not_assessed` | No hydrate margin supplied | Provide a hydrate margin from a validated calculation |
| Step-out always `ok` | Guideline set too high | Use a service-appropriate step-out guideline |

## Limitations

- No hydraulic, thermal, or thermodynamic calculation is performed.
- Guideline thresholds are illustrative public values only.
- A single arrival pressure and step-out cannot represent a full route.
- Results are screening indicators only and are not design decisions.

## Related NeqSim Functionality

This skill only applies simple guideline comparisons. The validated calculations behind its inputs live in NeqSim and in the community skills:

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — multiphase arrival pressure and temperature along a route.
- The NeqSim MCP `runPipeline` and `runFlowAssurance` tools for arrival conditions and hydrate screening.
- Community `pressure-drop-screening`, `line-velocity-check`, and `hydrate-margin-check` for the upstream screening inputs.

In Python the NeqSim classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`). For governed, live reservoir-to-facility routing the enterprise `enterprise-well-production-routing` skill is the counterpart.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Related community skills: `pipe-route-profile`, `subsea-layout-geometry`, `pressure-drop-screening`, `line-velocity-check`, `hydrate-margin-check`
