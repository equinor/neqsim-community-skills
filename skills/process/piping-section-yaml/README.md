# Piping Section YAML

A declarative YAML schema and loader for piping route topology, intended as input to
NeqSim process builders.

The schema captures an ordered `flow_path` of nodes, pipe segments, inline equipment,
and parallel branches, plus a Crane TP-410 equivalent-length model for fittings. The
loader returns plain Python data structures and performs schema validation. It does no
thermodynamics or pressure-drop solving.

## Install

```bash
python -m pip install -e skills/process/piping-section-yaml
```

## Run Example

```bash
python skills/process/piping-section-yaml/examples/load_demo_section.py
```

## Run Tests

```bash
python -m pytest skills/process/piping-section-yaml/tests
```

## Public Scope

The schema, the example section, and the `FITTING_LD` table use only public,
generic values. No plant tags, document numbers, vendor data, or company-specific
piping standards are included. For detailed piping design use qualified engineering
methods and review.
