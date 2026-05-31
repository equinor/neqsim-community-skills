# Separator Modelling

Educational gas/liquid separator screening skill for public examples and agent guidance.

This skill provides a simple Python `SeparatorModel` with placeholder indicators for gas load, liquid residence time, and capacity warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/separator-modelling
```

## Run Example

```bash
python skills/process/separator-modelling/examples/basic_separator_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/separator-modelling/tests
```

## Public Scope

The model does not contain proprietary separator design methods, confidential geometry, vendor data, or company-specific standards. For real calculations, use validated NeqSim process models and qualified engineering review.