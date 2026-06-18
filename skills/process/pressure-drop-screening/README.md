# Pressure Drop Screening

Educational single-phase line pressure-drop screening skill for public examples and agent guidance.

This skill provides a simple Python `PressureDropModel` with placeholder indicators for the Reynolds number, the Darcy friction factor, a pressure gradient in bar per 100 m, a total pressure drop, a guideline ratio, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/pressure-drop-screening
```

## Run Example

```bash
python skills/process/pressure-drop-screening/examples/basic_pressure_drop_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/pressure-drop-screening/tests
```

## Public Scope

The model does not contain proprietary piping classes, confidential line lists, vendor data, or company-specific piping specifications. For real calculations, use validated hydraulic methods (NORSOK P-002, GPSA), validated NeqSim property and pipe-flow models, and qualified process engineering review.
