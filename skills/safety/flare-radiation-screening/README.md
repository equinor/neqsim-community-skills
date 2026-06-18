# Flare Radiation Screening

Educational flare thermal-radiation screening skill for public examples and agent guidance.

This skill provides a simple Python `FlareRadiationModel` with placeholder indicators for the API 521 / API 537 point-source radiant heat flux, a check against allowable limits, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/safety/flare-radiation-screening
```

## Run Example

```bash
python skills/safety/flare-radiation-screening/examples/basic_flare_radiation_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/flare-radiation-screening/tests
```

## Public Scope

The model does not contain proprietary flare designs, vendor tip data, or company radiation criteria. For real calculations, use validated flare-radiation methods (API 521, API 537), validated NeqSim flare classes, and qualified safety engineering review.
