# Relief Load Screening

Educational fire-case pressure-relief load screening skill for public examples and agent guidance.

This skill provides a simple Python `ReliefLoadModel` with placeholder indicators for fire heat input, vapor relief mass rate, and a capacity warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/safety/relief-load-screening
```

## Run Example

```bash
python skills/safety/relief-load-screening/examples/basic_relief_load_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/relief-load-screening/tests
```

## Public Scope

The model does not contain proprietary relief device data, confidential vessel geometry, vendor curves, or company-specific relief design bases. For real calculations, use validated relief sizing methods (API 520/521), validated NeqSim property models, and qualified process safety review.
