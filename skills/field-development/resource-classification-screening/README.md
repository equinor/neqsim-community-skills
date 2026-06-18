# Resource Classification Screening

Educational petroleum resource classification screening skill for public examples and agent guidance.

This skill provides a simple Python `ResourceClassificationModel` that maps a project maturity stage to a reserves, contingent-resources, or prospective-resources category using the open SPE-PRMS framework and the public Norwegian Petroleum Directorate resource-class scheme. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/field-development/resource-classification-screening
```

## Run Example

```bash
python skills/field-development/resource-classification-screening/examples/basic_resource_classification_screening.py
```

## Run Tests

```bash
python -m pytest skills/field-development/resource-classification-screening/tests
```

## Public Scope

The model does not contain confidential volumes, reservoir data, or company estimates. For a formal resource estimate, use SPE-PRMS, the Norwegian Petroleum Directorate resource-class scheme, validated NeqSim field-development utilities, and qualified subsurface review.
