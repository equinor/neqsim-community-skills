# Line Velocity Check

Educational process line velocity screening skill for public examples and agent guidance.

This skill provides a simple Python `LineVelocityModel` with placeholder indicators for erosional velocity, velocity ratio, a recommended velocity guideline ratio, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/line-velocity-check
```

## Run Example

```bash
python skills/process/line-velocity-check/examples/basic_line_velocity_check.py
```

## Run Tests

```bash
python -m pytest skills/process/line-velocity-check/tests
```

## Public Scope

The model does not contain proprietary piping classes, confidential line lists, vendor data, or company-specific piping specifications. For real calculations, use validated line sizing methods (API RP 14E, NORSOK P-001), validated NeqSim property models, and qualified process engineering review.
