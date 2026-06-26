# Contributing to NeqSim Community Skills

Thank you for helping build a public catalog of reusable NeqSim skills. Contributions should be useful to students, researchers, engineers, and open-source users without exposing private or proprietary information.

## Where Does This Belong?

Before adding a skill here, confirm this is the right repository. See the
[Where Does This Go? placement guide](docs/where-does-this-go.md): community
skills hold **educational, screening-level** methods that reference — but do not
replace — the validated Java classes in core NeqSim. Validated calculations
belong in core neqsim; company-policy or confidential content belongs in the
enterprise repos.

## Add a New Skill

1. Copy [templates/skill-template](templates/skill-template) into the relevant domain folder under [skills](skills).
2. Rename the folder with a short kebab-case topic name, for example `skills/pvt/phase-envelope-check`.
3. Give the skill a catalog name that starts with `neqsim-`, for example `neqsim-phase-envelope-check`.
4. Fill in `SKILL.md` using the required sections in [docs/skill-standard.md](docs/skill-standard.md).
5. Add Python code under `src` if the skill includes executable logic.
6. Add examples that run with public inputs only.
7. Add pytest tests for all executable behavior.
8. Update any local catalog preview, README tables, or documentation that should mention the skill.

## Required Files

Each skill folder must contain:

```text
skill-name/
├── SKILL.md
├── README.md
├── pyproject.toml
├── src/
├── examples/
└── tests/
```

`SKILL.md` is required even for a documentation-only skill. Python code is optional, but tests and examples are still expected when the skill describes runnable code patterns.

## Testing Requirements

Run the full repository tests before opening a pull request:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

For a single skill, run its example and tests:

```bash
python -m pip install -e skills/<domain>/<skill-name>
python skills/<domain>/<skill-name>/examples/<example>.py
python -m pytest skills/<domain>/<skill-name>/tests
```

Tests should verify normal behavior, boundary conditions, invalid inputs, and documented warnings or flags.

## Documentation Requirements

Every skill must document:

- when to use it
- inputs and units
- outputs and interpretation
- engineering method and assumptions
- Python usage pattern
- validation checklist
- common mistakes
- limitations
- references

Documentation must distinguish educational screening logic from validated NeqSim calculations.

## Public Data and Confidentiality

Do not contribute:

- proprietary or unpublished engineering methods
- confidential plant data, production data, composition data, or project data
- internal URLs, host names, authentication patterns, tag names, or document identifiers
- company-specific standards, procedures, or design bases
- text copied from licensed standards or restricted documents

Use small synthetic examples and cite public references only.

## Review Checklist

Before requesting review, confirm that:

- [ ] The skill name starts with `neqsim-`.
- [ ] `SKILL.md` has valid YAML frontmatter and all required sections.
- [ ] Examples run with public data.
- [ ] Tests pass with Python 3.10 or newer.
- [ ] Optional NeqSim integration has a fallback when NeqSim is not installed.
- [ ] The contribution contains no confidential or company-specific information.
- [ ] Limitations are explicit enough to prevent production misuse.
- [ ] References are public and traceable.

Maintainers may ask for clearer limitations, stronger tests, or removal of content that is not appropriate for a public repository.