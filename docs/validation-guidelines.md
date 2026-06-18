# Validation Guidelines

Validation for community skills should be lightweight, public, and reproducible.

## Required Checks

Run repository tests:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Run each changed skill example:

```bash
python skills/<domain>/<skill-name>/examples/<example>.py
```

## What to Validate

- Inputs are checked for missing values, non-finite numbers, and physically impossible signs.
- Outputs are deterministic for the public examples.
- Warnings and flags are covered by tests.
- Optional NeqSim integration does not break when NeqSim is not installed.
- `SKILL.md` usage patterns match executable code.
- Limitations prevent confusion between screening examples and validated calculations.
- `SKILL.md` includes a `Related NeqSim Functionality` section that links the skill to real NeqSim Java classes/methods or NeqSim MCP tools where possible, or states explicitly that none applies yet.

## Public Example Data

Examples must use synthetic or public-domain inputs. Do not use real asset data, project compositions, production rates, or internal design bases.

## Optional NeqSim Integration

Skills may detect the optional `neqsim` Python package and use it for validated calculations when appropriate. They must still have a fallback path for users who only want to run examples and tests.

Any NeqSim-dependent calculation should state which NeqSim API or method is used and should be tested when NeqSim is available.

## Screening vs. Engineering Design

Educational screening code is useful for examples and agent behavior. It must not be presented as:

- final equipment design
- a replacement for process simulation
- a safety or operability decision basis
- a proprietary or standards-compliant method

Use validated NeqSim methods and qualified review for real engineering work.