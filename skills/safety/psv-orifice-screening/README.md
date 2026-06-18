# PSV Orifice Screening

Educational pressure-safety-valve orifice screening skill for public examples and agent guidance.

This skill provides a simple Python `PsvOrificeModel` with placeholder indicators for the API 520 Part I required orifice area for critical gas flow, a mapped API 526 orifice letter, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/safety/psv-orifice-screening
```

## Run Example

```bash
python skills/safety/psv-orifice-screening/examples/basic_psv_orifice_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/psv-orifice-screening/tests
```

## Public Scope

The model does not contain proprietary valve data, vendor capacity charts, or company relief specifications. For real calculations, use validated relief-valve sizing methods (API 520, API 526), validated NeqSim relief classes, and qualified safety engineering review.
