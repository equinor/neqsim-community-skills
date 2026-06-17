# Wax Margin Check

Educational wax operating-margin screening skill for public examples and agent guidance.

This skill provides a simple Python `WaxMarginModel` with placeholder indicators for the wax margin, whether the operating point is below the wax appearance temperature, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/flow-assurance/wax-margin-check
```

## Run Example

```bash
python skills/flow-assurance/wax-margin-check/examples/basic_wax_margin_check.py
```

## Run Tests

```bash
python -m pytest skills/flow-assurance/wax-margin-check/tests
```

## Public Scope

The model does not contain proprietary wax deposition models, confidential crude assays, pour-point specifications, or company-specific flow assurance limits. The wax appearance temperature must come from a validated NeqSim wax calculation or a public lab measurement. For real work, use validated NeqSim wax workflows and qualified flow assurance review.
