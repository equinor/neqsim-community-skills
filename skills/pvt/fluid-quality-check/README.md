# Fluid Quality Check

Public composition quality checks for NeqSim examples and agent workflows.

The checker verifies that mole fractions sum close to 1.0, rejects negative fractions, checks required components, and flags water, CO2, and H2S when present.

## Install

```bash
python -m pip install -e skills/pvt/fluid-quality-check
```

## Run Example

```bash
python skills/pvt/fluid-quality-check/examples/check_public_composition.py
```

## Run Tests

```bash
python -m pytest skills/pvt/fluid-quality-check/tests
```

## Public Scope

This skill performs transparent data-quality checks only. It does not include confidential fluid data, internal quality procedures, or proprietary PVT interpretation logic.