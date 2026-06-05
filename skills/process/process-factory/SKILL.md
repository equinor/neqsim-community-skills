---
name: neqsim-process-factory
version: "0.1.0"
description: "Turn a declarative piping/flow-path description into an ordered NeqSim unit-operation plan and (when NeqSim is available) a ProcessSystem. USE WHEN: you have YAML/dict topology and want to build a process model declaratively instead of writing imperative NeqSim code."
last_verified: "2026-06-05"
requires:
  python_packages: []
  java_packages: ["neqsim (optional, for ProcessSystem construction)"]
  env: []
  network: []
---

# Process Factory

Use this skill to convert a declarative flow-path description (the same shape produced
by `neqsim-piping-section-yaml`) into an ordered list of unit operations, and, when the
optional `neqsim` package is installed, into an actual `ProcessSystem`. Pipe segments
become `PipeBeggsAndBrills` with fitting losses folded into an effective length;
equipment becomes separators, scrubbers, coolers, or valves; parallel branches become a
splitter/mixer pair.

## When to Use

- When you have YAML/dict topology and want a code-free way to assemble a process model.
- When you want to inspect or test the build order without running NeqSim.
- When fitting minor losses should be added to pipe length automatically.

When you are building a model imperatively from scratch in Python, a code-first
platform-modeling approach may be clearer. For the YAML schema itself, see
`neqsim-piping-section-yaml`.

## Inputs

- `section`: a mapping with `section_id` and an ordered `flow_path` list. Items have a
  `type` of `node`, `segment`, `equipment`, or `parallel` (see
  `neqsim-piping-section-yaml` for the schema).
- For `build_process_system`: an inlet `stream` / `fluid` object and a NeqSim
  `ProcessSystem`-like container (only required when `neqsim` is installed).

## Outputs

- `build_plan(section, prefix=None)`: an ordered `list[UnitOp]`. Each `UnitOp` has a
  `kind` (`pipe`, `three_phase_separator`, `gas_scrubber`, `cooler`, `valve`,
  `splitter`, `mixer`), a `name`, and a `params` dict (e.g. `effective_length_m`).
- `build_process_system(section, inlet_stream, process_system, prefix=None)`: builds
  units on a real NeqSim `ProcessSystem`; raises `RuntimeError` if `neqsim` is missing.

## Engineering Method

The factory walks the `flow_path` in order, threading an outlet stream from each unit
into the next:

- `segment` → `PipeBeggsAndBrills` with
  `effective_length_m = length_m + Σ (L/D)·diameter·count` (Crane TP-410 fittings).
- `three_phase_separator` / `gas_scrubber` → vessel; downstream stream is the gas outlet.
- `cooler` → cooler to a target outlet temperature, optionally followed by a Cv valve
  for flow-dependent pressure drop.
- `valve` → pass-through (choke/control dP validated separately, not simulated here).
- `parallel` → a `splitter` before the branches and a `mixer` after them.

The plan is deterministic, so it can be unit-tested without NeqSim. The
`build_process_system` step performs the same traversal but instantiates real units.

## Python Usage Pattern

```python
from process_factory import build_plan

section = {
    "section_id": "demo",
    "flow_path": [
        {"type": "node", "id": "inlet"},
        {"type": "segment", "id": "S1", "length_m": 50.0, "inner_diameter_m": 0.45,
         "fittings": [{"type": "elbow_90", "count": 4}]},
        {"type": "equipment", "id": "scrubber", "equipment_type": "gas_scrubber"},
        {"type": "parallel", "branches": [
            [{"type": "segment", "id": "A1", "length_m": 20.0, "inner_diameter_m": 0.3}],
            [{"type": "segment", "id": "B1", "length_m": 20.0, "inner_diameter_m": 0.3}],
        ]},
        {"type": "node", "id": "outlet"},
    ],
}

plan = build_plan(section)
for unit in plan:
    print(unit.kind, unit.name, unit.params)

# With NeqSim installed:
# from process_factory import build_process_system
# out_stream = build_process_system(section, inlet_stream, process_system)
```

## Validation Checklist

- [ ] The plan order matches the intended flow direction.
- [ ] Pipe `effective_length_m` exceeds the physical length when fittings are present.
- [ ] Each `parallel` produces exactly one `splitter` and one `mixer`.
- [ ] Unknown `equipment_type` raises a clear error.
- [ ] Example inputs are public and synthetic.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `RuntimeError: neqsim not installed` | calling `build_process_system` without NeqSim | install `neqsim` or use `build_plan` |
| Valve appears missing in plan | valves are pass-through by design | model choke dP separately |
| Branch units missing | parallel branch not a list of flow_path items | wrap each branch as its own list |
| Pipe too short | fittings omitted | add `fittings` to the segment |

## Limitations

- Construction details (recycles, controllers, anti-surge, detailed scrubber internals)
  are intentionally out of scope; this skill builds the primary flow path.
- Valves are pass-through; choke/control pressure drop is not simulated here.
- Requires the optional `neqsim` package only for actual `ProcessSystem` construction.
- Not a substitute for a validated, reviewed process model.

## References

- Crane Co., Technical Paper No. 410 (fitting equivalent lengths).
- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
