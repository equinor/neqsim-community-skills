---
name: neqsim-design-basis-screening
version: "0.1.0"
description: "Educational design-basis margin screening for flow, pressure, and temperature design margins versus operating conditions, with a standards-basis echo. USE WHEN: a task needs a public, screening-level check that proposed design capacities and conditions carry sensible margins over operating before detailed mechanical design and code rating."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Design Basis Screening

Use this skill to assemble and sanity-check a screening design basis: it
compares operating capacities and conditions against the proposed design
capacities and conditions, computes indicative flow, pressure, and temperature
margins, and flags margins below transparent public thresholds. It also echoes
the design standards basis. It is intentionally simple and should guide users
toward validated mechanical design, the applicable standards (ASME, API, DNV,
NORSOK), and qualified engineering review.

## When to Use

- When an early concept needs a quick design-margin sanity check.
- When an agent needs an upstream "design basis" feed for a facilities or
  cost-estimate screening chain.
- When documenting the capacities and conditions a downstream model should use.

## Inputs

- `operating_flow` / `design_flow`: operating and design flow rate (same unit).
- `operating_pressure_bara` / `design_pressure_bara`: operating and design pressure.
- `operating_temperature_c` / `design_temperature_c`: operating and design temperature.
- `standards`: optional list of design standards labels.

## Outputs

- `flow_margin`, `pressure_margin`: design/operating ratios.
- `temperature_margin_c`: design minus operating temperature.
- `flow_flag`, `pressure_flag`, `temperature_flag`: `ok` or `low`.
- `standards`: normalized standards basis.
- `design_warning`: `ok` or `watch`.
- `flags`: human-readable warnings.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

The skill computes simple margins: flow and pressure as design/operating
ratios, temperature as a design-minus-operating difference. Each margin is
compared against an indicative public threshold (default 1.10 for flow and
pressure ratios, 10 C for temperature). A `low` flag is raised when a margin is
below its threshold, and a missing standards basis is flagged. The verdict is
`watch` when any flag is raised, otherwise `ok`.

This skill performs no code-rating, wall-thickness, or mechanical-design check.
It is a transparent placeholder that must be replaced by validated mechanical
design for any quantitative use.

## Python Usage Pattern

```python
from design_basis_screening import DesignBasisModel

model = DesignBasisModel()
result = model.evaluate(
    operating_flow=100.0,
    design_flow=120.0,
    operating_pressure_bara=60.0,
    design_pressure_bara=70.0,
    operating_temperature_c=40.0,
    design_temperature_c=60.0,
    standards=("ASME VIII Div.1", "NORSOK P-001"),
)

print(result.flow_margin, result.pressure_margin, result.temperature_margin_c)
print(result.design_warning)
for flag in result.flags:
    print(flag)
```

## Validated NeqSim Path

This screening is a placeholder. For a real design basis use:

- NeqSim mechanical-design classes (`neqsim.process.mechanicaldesign`) for
  vessel, pipe, compressor, and heat-exchanger design with code factors.
- The applicable standards databases (ASME, API, DNV, NORSOK) for ratings.
- The community `pressure-drop-screening`, `line-velocity-check`, and
  `pipe-wall-thickness-screening` skills for related hydraulic and mechanical
  screening.

## Escalation

Escalate any `watch` verdict, and any quantitative use, to validated NeqSim
mechanical design and qualified engineering review against the applicable codes.
