# NeqSim Community Skills

NeqSim Community Skills is a public, open-source starting point for community-contributed skills that support [NeqSim](https://github.com/equinor/neqsim) users, AI agents, students, researchers, and engineers.

A skill is a small, self-contained knowledge package. It can contain:

- `SKILL.md` agent guidance with YAML frontmatter
- optional Python implementation code
- examples using public inputs
- pytest tests
- documentation and references
- a validation checklist

This repository is for public knowledge only. Do not add proprietary methods, confidential data, internal tag names, private URLs, company-specific standards, unpublished correlations, or production design rules.

## Relationship to NeqSim

[NeqSim is a library for calculation of fluid behavior, phase equilibrium and process simulation](https://github.com/equinor/neqsim). It provides the thermodynamic and process simulation engine. This repository provides community skills that can guide agents and users when applying open workflows around NeqSim.

The main NeqSim repository documents the skill workflow in the [Skills Guide](https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md) and lists public community entries in [`community-skills.yaml`](https://github.com/equinor/neqsim/blob/master/community-skills.yaml).

Community skills can be discovered and installed with the NeqSim CLI:

```bash
neqsim skill list                    # browse the catalog
neqsim skill install <skill-name>    # install a skill
neqsim skill publish user/repo-name  # publish yours by creating a draft PR
```

For this multi-skill repository, each skill is cataloged by a path such as `skills/process/separator-modelling/SKILL.md`.

## Initial Skills

| Skill | Catalog name | Purpose |
| --- | --- | --- |
| [skills/process/separator-modelling](skills/process/separator-modelling) | `neqsim-separator-modelling` | Educational gas/liquid separator screening indicators |
| [skills/pvt/fluid-quality-check](skills/pvt/fluid-quality-check) | `neqsim-fluid-quality-check` | Public composition quality checks before simulation |
| [skills/flow-assurance/hydrate-screening](skills/flow-assurance/hydrate-screening) | `neqsim-hydrate-screening` | Educational hydrate risk screening placeholder |
| [skills/safety/relief-load-screening](skills/safety/relief-load-screening) | `neqsim-relief-load-screening` | Educational fire-case relief load screening placeholder |
| [skills/safety/depressurization-screening](skills/safety/depressurization-screening) | `neqsim-depressurization-screening` | Educational blowdown time and low-temperature screening placeholder |
| [skills/process/line-velocity-check](skills/process/line-velocity-check) | `neqsim-line-velocity-check` | Educational line velocity screening against erosional velocity and a guideline |
| [skills/process/compressor-operating-window-check](skills/process/compressor-operating-window-check) | `neqsim-compressor-operating-window-check` | Educational compressor surge/stonewall operating window screening placeholder |
| [skills/flow-assurance/hydrate-margin-check](skills/flow-assurance/hydrate-margin-check) | `neqsim-hydrate-margin-check` | Educational hydrate operating-margin (subcooling) screening placeholder |
| [skills/flow-assurance/wax-margin-check](skills/flow-assurance/wax-margin-check) | `neqsim-wax-margin-check` | Educational wax appearance temperature operating-margin screening placeholder |

These examples are intentionally simple. They are suitable for learning, testing agent workflows, and demonstrating the repository structure. They are not design tools.

## Install and Run

Use Python 3.10 or newer.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m pytest
```

Install a specific example skill in editable mode:

```bash
python -m pip install -e skills/process/separator-modelling
python skills/process/separator-modelling/examples/basic_separator_screening.py
```

The Python examples do not require confidential data. They detect whether the optional `neqsim` Python package is available and fall back to public placeholder logic when it is not installed.

## How Agents Use Skills

Agents read `SKILL.md` files when a task matches the skill description and `USE WHEN` trigger. A good skill gives the agent:

- clear trigger conditions
- expected inputs and outputs
- public engineering assumptions
- Python usage patterns
- validation checks
- common mistakes and limitations

Installed community skills are typically stored under `~/.neqsim/skills/<name>/SKILL.md`. VS Code users can also copy a skill file to their user prompts folder and reference it from chat.

## Contribute

Start from [templates/skill-template](templates/skill-template), then add your skill under the most relevant domain folder in [skills](skills). Follow [CONTRIBUTING.md](CONTRIBUTING.md) and the standards in [docs/skill-standard.md](docs/skill-standard.md).

Every contribution must:

- use public, reproducible examples
- include `SKILL.md`, `README.md`, `pyproject.toml`, `src`, `examples`, and `tests`
- include pytest coverage for Python logic
- document limitations clearly
- avoid confidential or company-specific information

## Public Limitations

Community skills are not a substitute for validated NeqSim models, peer-reviewed methods, project design bases, or qualified engineering judgment. Use validated NeqSim methods and appropriate review for production work, safety-critical decisions, and formal design.
