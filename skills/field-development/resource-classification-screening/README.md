# Resource Classification Screening

Educational petroleum resource classification screening skill for public examples and agent guidance.

This skill provides a Python `ResourceClassificationModel` that reports public SODIR `RC0`-`RC9` project maturity separately from the corresponding SPE-PRMS category. Quantity uncertainty such as `1P/2P/3P` or `1C/2C/3C` is deliberately not inferred from maturity. It is intended for learning and workflow scaffolding only.

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

The model contains only public classification logic. It does not contain confidential volumes, reservoir data, company workflows, or corporate reporting rules. For a formal estimate, use SPE-PRMS, the SODIR resource-class scheme, validated NeqSim field-development utilities, and qualified subsurface review.
