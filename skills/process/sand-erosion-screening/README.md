# Sand Erosion Screening

Educational sand-erosion and remaining-wall-life screening skill for public examples and agent guidance.

This skill provides a simple Python `SandErosionModel` with placeholder indicators for erosional velocity, a screening sand erosion rate, cumulative wall loss, remaining wall thickness, a remaining-life estimate, and an erosion warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/sand-erosion-screening
```

## Run Example

```bash
python skills/process/sand-erosion-screening/examples/basic_sand_erosion_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/sand-erosion-screening/tests
```

## Public Scope

The model does not contain proprietary erosion models, confidential sand-monitoring data, vendor data, or company-specific integrity specifications. The sand erosion coefficient is a transparent public placeholder, not the DNV RP O501 model. For real calculations, use the validated NeqSim `ErosionPredictionCalculator` (API RP 14E and DNV RP O501) and qualified engineering review.
