# Water Dewpoint Dehydration Screening

Educational gas water-content and dehydration screening skill for public examples and agent guidance.

This skill provides a simple Python `WaterDewpointModel` with placeholder indicators for the GPSA Bukacek saturated water content, a check against a sales-gas water spec, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/water-dewpoint-dehydration-screening
```

## Run Example

```bash
python skills/process/water-dewpoint-dehydration-screening/examples/basic_water_dewpoint_dehydration_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/water-dewpoint-dehydration-screening/tests
```

## Public Scope

The model does not contain proprietary dehydration designs, glycol data, or company gas specifications. For real calculations, use validated water-content methods (GPSA, rigorous thermodynamics), validated NeqSim CPA models, and qualified process engineering review.
