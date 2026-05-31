# Repository Structure

This repository is a multi-skill community repository. Skills are grouped by engineering domain so they can be cataloged individually while sharing tests, documentation, and contribution rules.

```text
neqsim-community-skills/
├── README.md
├── CONTRIBUTING.md
├── LICENSE.md
├── pyproject.toml
├── community-skills.yaml
├── skills/
│   ├── process/
│   │   └── separator-modelling/
│   ├── pvt/
│   │   └── fluid-quality-check/
│   └── flow-assurance/
│       └── hydrate-screening/
├── templates/
│   └── skill-template/
└── docs/
    ├── skill-standard.md
    ├── repository-structure.md
    ├── validation-guidelines.md
    └── governance.md
```

## Skill Paths

The NeqSim community catalog identifies each skill by repository and path:

```yaml
repo: "equinor/neqsim-community-skills"
path: "skills/process/separator-modelling/SKILL.md"
```

This lets one public repository host several independent skills.

## Domain Folders

- `skills/process`: process equipment, process modeling, and operational screening workflows.
- `skills/pvt`: fluid characterization, composition quality, and PVT workflow helpers.
- `skills/flow-assurance`: hydrate, wax, corrosion, multiphase flow, and transport screening workflows.

Add a new top-level domain only when an existing domain is clearly unsuitable.

## Python Packages

Each executable skill is an independent Python package with its own `pyproject.toml`. The root `pyproject.toml` configures repository-level testing across all starter skills.

## Templates

[templates/skill-template](../templates/skill-template) is a copyable scaffold for new skills. It contains the required files and required `SKILL.md` sections.