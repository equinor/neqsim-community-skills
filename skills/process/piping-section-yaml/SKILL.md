---
name: neqsim-piping-section-yaml
version: "0.1.0"
description: "Declarative YAML schema for piping section topology (segments, fittings, equipment, parallel branches) consumed by NeqSim process builders. USE WHEN: a task needs a structured, reviewable description of a piping route with equivalent-length fitting losses before building a NeqSim process model."
last_verified: "2026-06-05"
requires:
  python_packages: ["PyYAML"]
  java_packages: []
  env: []
  network: []
---

# Piping Section YAML

Use this skill to describe a piping route as a structured YAML document and load it
into plain Python data structures. The schema captures an ordered `flow_path` of
nodes, pipe segments, inline equipment, and parallel branches, plus a Crane TP-410
based equivalent-length model for fittings. The loaded structures are designed to be
consumed by a NeqSim process builder (see `neqsim-process-factory`), but this skill
is self-contained and does not require NeqSim.

## When to Use

- When you want a declarative, version-controlled description of a piping route
  instead of hard-coding topology in Python.
- When fitting minor losses (elbows, tees, valves, check valves) should be converted
  to equivalent pipe length using published L/D ratios.
- When a route includes parallel branches (a splitter/mixer pair) and you need an
  ordered traversal of all segments and equipment.
- When you want to validate a piping description (required fields, positive lengths
  and diameters) before building a simulation.

When you already have YAML and want to build a NeqSim `ProcessSystem`, use
`neqsim-process-factory`. For separator screening indicators, use
`neqsim-separator-modelling`.

## Inputs

A piping section is a mapping with:

- `section_id` (str, required): unique identifier for the section.
- `description` (str, optional): human-readable summary.
- `flow_path` (list, required): ordered list of items, each a mapping with `type`:
  - `node`: a connection point. Fields: `id`, optional `pressure_bara`,
    `temperature_C` (public reference values only).
  - `segment`: a pipe run. Fields: `id`, `length_m`, `inner_diameter_m`,
    optional `elevation_m` (default 0.0), `wall_roughness_m` (default 4.6e-5),
    `fittings` (list of `{type, count}`).
  - `equipment`: an inline unit. Fields: `id`, `equipment_type`
    (`three_phase_separator`, `gas_scrubber`, `cooler`, `valve`, `tuning_valve`),
    optional `Cv`, `pressure_drop_bar`.
  - `parallel`: a set of identical branches. Fields: `branches`
    (list of `flow_path` lists), optional `split_factors`.

All quantities use SI units: metres for length/diameter/elevation, bara for
pressure, °C for temperature.

## Outputs

- `PipingSection`: a parsed object exposing `section_id`, `description`,
  `nodes`, `segments`, `equipment`, and `flow_path`.
- `fittings_equivalent_length(fittings, inner_diameter_m)`: extra pipe length (m)
  contributed by fittings.
- `total_length(section)`, `total_elevation(section)`: route totals.
- `inspect_section(section)`: an ordered list of dicts describing every item for
  review or tabular display.
- `validate_section(data)`: raises `ValueError` listing schema problems.

## Engineering Method

Fitting minor losses are converted to equivalent pipe length using L/D ratios from
Crane Technical Paper No. 410 (turbulent, fully open):

```
extra_length_m = sum( (L/D)_fitting * inner_diameter_m * count )
```

The defaults in `FITTING_LD` are published, generic values (e.g. 90° long-radius
elbow ≈ 20, gate valve ≈ 8, swing check valve ≈ 50). A process builder adds this
extra length to the physical segment length so a single pressure-drop correlation
(e.g. Beggs & Brill) accounts for both straight pipe and fittings.

Parallel branches are traversed depth-first; a downstream builder inserts a splitter
before the branches and a mixer after them. `split_factors` (if present) describe the
nominal flow fraction per branch.

This skill performs no thermodynamics and no pressure-drop calculation itself — it
provides validated topology and equivalent-length geometry only.

## Python Usage Pattern

```python
from piping_section_yaml import (
    load_section, load_yaml_file, validate_section,
    fittings_equivalent_length, total_length, inspect_section,
)

data = {
    "section_id": "demo_inlet",
    "description": "Inlet header to scrubber with a parallel two-branch run",
    "flow_path": [
        {"type": "node", "id": "header", "pressure_bara": 90.0, "temperature_C": 40.0},
        {"type": "segment", "id": "S1", "length_m": 57.8, "inner_diameter_m": 0.467,
         "elevation_m": 3.5,
         "fittings": [{"type": "elbow_90", "count": 4}, {"type": "tee_branch", "count": 1}]},
        {"type": "equipment", "id": "scrubber", "equipment_type": "gas_scrubber"},
        {"type": "parallel", "branches": [
            [{"type": "segment", "id": "A1", "length_m": 20.0, "inner_diameter_m": 0.3}],
            [{"type": "segment", "id": "B1", "length_m": 20.0, "inner_diameter_m": 0.3}],
        ], "split_factors": [0.5, 0.5]},
        {"type": "node", "id": "outlet"},
    ],
}

validate_section(data)             # raises ValueError on schema problems
section = load_section(data)
print(section.section_id, len(section.segments), len(section.equipment))
print("total length [m]:", round(total_length(section), 2))

extra = fittings_equivalent_length(
    [{"type": "elbow_90", "count": 4}], inner_diameter_m=0.467
)
print("fitting equiv length [m]:", round(extra, 2))

for row in inspect_section(section):
    print(row["kind"], row.get("id"))

# Or load from a YAML file:
# section = load_section(load_yaml_file("demo_inlet.yaml"))
```

## Validation Checklist

- [ ] `section_id` is present and `flow_path` is a non-empty list.
- [ ] Every segment has positive `length_m` and `inner_diameter_m`.
- [ ] Fitting `type` values exist in `FITTING_LD` (unknown types contribute 0 and warn).
- [ ] Parallel branches each parse to at least one segment.
- [ ] Units are SI and consistent across the section.
- [ ] Example inputs are public and synthetic (no plant tags or document numbers).

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Fitting adds no length | `type` not in `FITTING_LD` | Use a known key or pass an explicit segment length |
| Negative net elevation surprises | `elevation_m` sign convention | Positive elevation means upward flow |
| Parallel branch ignored | branch is not a list of flow_path items | Wrap each branch as its own ordered list |
| Validation passes but build fails | equipment_type unknown to builder | Use a supported `equipment_type` |

## Limitations

- No thermodynamics, no pressure-drop solving, and no flow distribution is computed.
- `FITTING_LD` uses generic published L/D values, not project- or vendor-specific data.
- The schema is intentionally minimal; it omits mechanical, material, and code-class
  details required for detailed piping design.
- Not a substitute for stress analysis, line-sizing standards, or qualified review.

## References

- Crane Co., Technical Paper No. 410, "Flow of Fluids Through Valves, Fittings, and Pipe."
- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
