# Skill Standard

This standard defines the minimum shape of a public NeqSim community skill.

## Required Folder Contents

```text
skill-name/
├── SKILL.md
├── README.md
├── pyproject.toml
├── src/
├── examples/
└── tests/
```

Python code is optional. If a skill has no Python code, keep `src`, `examples`, and `tests` with placeholders that explain why no executable logic is provided.

## Naming

- Folder names use kebab-case, for example `hydrate-screening`.
- Python package names use snake_case, for example `hydrate_screening`.
- Catalog skill names must start with `neqsim-`, for example `neqsim-hydrate-screening`.

## SKILL.md Frontmatter

Every `SKILL.md` must start with YAML frontmatter:

```yaml
---
name: neqsim-topic-name
version: "0.1.0"
description: "Short description. USE WHEN: explicit trigger conditions."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---
```

Required fields are `name`, `version`, `description`, and `last_verified`. The description must contain `USE WHEN:` so agents can decide when to load the skill.

## Required SKILL.md Sections

Every skill must include:

- `When to Use`
- `Inputs`
- `Outputs`
- `Engineering Method`
- `Python Usage Pattern`
- `Validation Checklist`
- `Common Mistakes`
- `Limitations`
- `Related NeqSim Functionality`
- `References`

Use clear units for all engineering quantities. Distinguish screening assumptions from validated simulation methods.

## Linking to NeqSim Functionality

Where possible, every skill should link to NeqSim functionality in a `Related NeqSim Functionality` section. This makes the skill traceable to the validated engine that does the real calculation:

- Name the concrete NeqSim Java classes or methods the skill maps to, for example `neqsim.thermodynamicoperations.ThermodynamicOperations#TPflash()` or `neqsim.process.equipment.separator.Separator`, and/or the relevant NeqSim MCP tool.
- Note how NeqSim is reached, for example `from neqsim import jneqsim` in Python.
- If a skill only prepares, transports, or renders data (document reading, historian access, reporting), say so honestly and name the downstream NeqSim Java/MCP workflow the data feeds into rather than claiming it runs calculations itself.
- Only cite NeqSim classes, methods, or MCP tools that actually exist. If no NeqSim functionality applies yet, state that explicitly and, where useful, record it as a candidate NeqSim gap.

## Public Content Rules

Community skills must not include proprietary or confidential material. Avoid internal project examples, plant data, private tag names, private URLs, company standards, or unpublished correlations.

## Versioning

Use semantic versioning:

- Patch: wording fixes or test fixes that do not change behavior.
- Minor: new patterns, examples, checks, or public capabilities.
- Major: breaking changes to inputs, outputs, or interpretation.

Update `last_verified` whenever code patterns are re-run.