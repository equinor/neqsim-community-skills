# Artificial Lift Screening

Educational artificial-lift screening skill for public examples and agent guidance.

This skill provides a simple Python `ArtificialLiftModel` with placeholder indicators for natural deliverability from a straight-line IPR and gas lift / ESP feasibility from a required bottomhole-pressure reduction. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/field-development/artificial-lift-screening
```

## Run Example

```bash
python skills/field-development/artificial-lift-screening/examples/basic_artificial_lift_screening.py
```

## Run Tests

```bash
python -m pytest skills/field-development/artificial-lift-screening/tests
```

## Public Scope

The model contains no proprietary well models, vendor pump curves, or field data. For real calculations, use validated nodal analysis, validated NeqSim resources (WellFlow, SimpleReservoir), and qualified artificial-lift design.
