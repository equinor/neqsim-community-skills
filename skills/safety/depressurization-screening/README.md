# Depressurization Screening

Educational emergency depressurization (blowdown) screening skill for public examples and agent guidance.

This skill provides a simple Python `DepressurizationModel` with placeholder indicators for blowdown time, a simplified cold-end temperature estimate, and a low-temperature flag. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/safety/depressurization-screening
```

## Run Example

```bash
python skills/safety/depressurization-screening/examples/basic_depressurization_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/depressurization-screening/tests
```

## Public Scope

The model does not contain proprietary blowdown valve data, confidential vessel geometry, or company-specific depressurization bases. For real calculations, use validated NeqSim transient depressurization models, API 521, materials low-temperature review, and qualified process safety review.
