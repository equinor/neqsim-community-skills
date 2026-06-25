# Piping Flexibility Screening

Educational piping-flexibility screening skill for public examples and agent guidance.

This skill provides a simple Python `PipingFlexibilityModel` with placeholder indicators for hoop (sustained) stress, free thermal expansion, displacement (expansion) stress range, and a flange-rating pressure check using open ASME B31.3 / B16.5 style relations. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/piping-flexibility-screening
```

## Run Example

```bash
python skills/process/piping-flexibility-screening/examples/basic_piping_flexibility_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/piping-flexibility-screening/tests
```

## Public Scope

The model contains no proprietary isometrics, stress-analysis models, or company specifications. For real calculations, use validated pipe-stress/flexibility methods (ASME B31.3, ASME B16.5), validated NeqSim mechanical-design classes, and qualified piping-engineering review.
