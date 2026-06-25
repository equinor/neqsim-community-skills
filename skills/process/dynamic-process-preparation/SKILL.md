---
name: neqsim-dynamic-process-preparation
version: "0.1.0"
description: "Prepare NeqSim ProcessSystem and ProcessModel flowsheets for dynamic simulation, including equipment holdup, mechanical-design, and volume-readiness checks. USE WHEN: a task needs to convert a steady-state NeqSim process into a dynamic-ready model before runTransient calculations."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Dynamic Process Preparation

Use this skill when an agent must prepare a NeqSim `ProcessSystem` or multi-area `ProcessModel` for dynamic calculations. It focuses on model-readiness checks, mechanical-design handoff, equipment holdup and volume initialization, and the transient run sequence.

## When to Use

- When a user asks to turn a steady-state NeqSim process into a dynamic-ready process.
- When a `ProcessSystem` or `ProcessModel` needs equipment volumes, holdups, or initial liquid levels before transient simulation.
- When an agent needs a documented workflow for `run()`, `storeInitialState()`, `setTimeStep(...)`, and `runTransient()`.
- When mechanical design should be estimated with NeqSim classes before dynamic calculations.

## Inputs

- `process_name`: public process or model name used in reports.
- `process_kind`: `ProcessSystem` or `ProcessModel`.
- `equipment`: dynamic candidate equipment records with `name`, `equipment_type`, optional `length_m`, `diameter_m`, `liquid_level_fraction`, and `requires_mechanical_design`.
- `time_step_seconds`: proposed transient time step.
- `total_time_seconds`: optional total transient duration.
- `initialization_basis`: steady-state case, public design point, or synthetic example basis.

## Outputs

- `dynamic_ready`: boolean indicator for whether the supplied preparation metadata passes basic checks.
- `equipment_actions`: per-equipment actions such as enable dynamic mode, estimate mechanical design, set vessel geometry, and set initial level.
- `estimated_volumes_m3`: geometric cylindrical volume estimates for public readiness checks when dimensions are supplied.
- `neqsim_sequence`: NeqSim API sequence for initialization and transient execution.
- `warnings`: missing information or setup gaps that should be fixed before transient calculations.

## Engineering Method

The Python class `DynamicProcessPreparationModel` is a public planning and validation helper. It does not run NeqSim itself. It checks that a dynamic-ready NeqSim workflow has the minimum metadata needed to initialize dynamic equipment and points the user to the NeqSim APIs that should do the real work.

For vessels and separators, geometric volume is estimated as:

$$
V = \frac{\pi D^2}{4} L
$$

where $D$ is internal diameter and $L$ is vessel length. This is only a readiness and reporting estimate. For design-grade work, use the appropriate NeqSim mechanical-design classes and qualified engineering review.

## Python Usage Pattern

```python
from dynamic_process_preparation import DynamicProcessPreparationModel

model = DynamicProcessPreparationModel()
plan = model.evaluate(
    process_name="public separator train",
    process_kind="ProcessSystem",
    time_step_seconds=10.0,
    equipment=[
        {
            "name": "V-001",
            "equipment_type": "separator",
            "length_m": 4.0,
            "diameter_m": 1.0,
            "liquid_level_fraction": 0.25,
            "requires_mechanical_design": True,
        }
    ],
)

print(plan.dynamic_ready)
print(plan.estimated_volumes_m3["V-001"])
print(plan.neqsim_sequence)
```

NeqSim implementation pattern:

```python
# process is a neqsim.process.processmodel.ProcessSystem or a ProcessModel area process
separator.setCalculateSteadyState(False)
separator.initMechanicalDesign()
design = separator.getMechanicalDesign()
design.calcDesign()
separator.setSeparatorLength(4.0)
separator.setInternalDiameter(1.0)
separator.setLiquidLevel(0.25)

process.run()
process.storeInitialState()
process.setTimeStep(10.0)
process.runTransient()
```

For `ProcessModel`, prepare each contained `ProcessSystem` and preserve cross-area stream object references before running the model-level transient workflow.

## Validation Checklist

- [ ] The steady-state process converges before dynamic conversion.
- [ ] Dynamic candidate units are identified and documented.
- [ ] Dynamic units that support it call `setCalculateSteadyState(False)`.
- [ ] Separators or vessels have geometry, initial levels, and holdup basis.
- [ ] Mechanical design is initialized and calculated where NeqSim supports it.
- [ ] `storeInitialState()` is called after the steady-state initialization run.
- [ ] Time step and total simulation time are documented.
- [ ] Dynamic results are checked for mass balance, pressure realism, and controller stability.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Transient run starts from an unrealistic state | `storeInitialState()` was skipped after steady-state initialization | Run the process, inspect state, then call `storeInitialState()` before `runTransient()` |
| Separator level jumps or becomes nonphysical | Geometry or initial liquid level was missing | Set vessel length, internal diameter, and liquid level before transient runs |
| Equipment behaves steady-state during transient | Dynamic mode was not enabled | Call `setCalculateSteadyState(False)` on supported dynamic equipment |
| ProcessModel area coupling changes unexpectedly | Cross-area streams were copied instead of shared by object reference | Keep explicit shared stream objects between areas and document boundaries |

## Limitations

- The Python helper does not execute NeqSim or replace NeqSim dynamic simulation.
- Geometric volume checks are public readiness estimates, not pressure-vessel design.
- No proprietary vessel-sizing, control, or dynamic stability criteria are included.
- Human review is required before engineering or operational decisions.

## Related NeqSim Functionality

- `neqsim.process.processmodel.ProcessSystem#run()` — steady-state initialization before dynamic simulation.
- `neqsim.process.processmodel.ProcessSystem#storeInitialState()` — stores the initialized state for transient calculations.
- `neqsim.process.processmodel.ProcessSystem#setTimeStep(double)` and `runTransient()` — transient execution.
- `neqsim.process.processmodel.ProcessModel` — multi-area process composition where contained systems should be prepared consistently.
- `neqsim.process.equipment.separator.Separator#setCalculateSteadyState(boolean)`, `setSeparatorLength(double)`, `setInternalDiameter(double)`, and `setLiquidLevel(double)` — separator dynamic preparation.
- `neqsim.process.mechanicaldesign.separator.SeparatorMechanicalDesign` — NeqSim separator mechanical-design and sizing support.

In Python these classes are reachable through the `neqsim` package, for example `from neqsim import jneqsim`.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- NeqSim dynamic separator public examples and NeqSim process simulation documentation.
