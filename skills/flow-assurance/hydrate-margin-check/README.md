# Hydrate Margin Check

Educational hydrate operating-margin screening skill for public examples and agent guidance.

This skill provides a simple Python `HydrateMarginModel` with placeholder indicators for the hydrate margin, the subcooling into the hydrate region, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/flow-assurance/hydrate-margin-check
```

## Run Example

```bash
python skills/flow-assurance/hydrate-margin-check/examples/basic_hydrate_margin_check.py
```

## Run Tests

```bash
python -m pytest skills/flow-assurance/hydrate-margin-check/tests
```

## Public Scope

The model does not contain proprietary hydrate curves, confidential operating envelopes, inhibitor dosage rules, or company-specific flow assurance specifications. The hydrate equilibrium temperature must come from a validated NeqSim hydrate calculation. For real work, use validated NeqSim hydrate workflows and qualified flow assurance review.
