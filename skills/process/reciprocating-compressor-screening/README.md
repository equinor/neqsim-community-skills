# Reciprocating Compressor Screening

Educational reciprocating-compressor screening skill for public examples and agent guidance.

This skill provides a simple Python `ReciprocatingCompressorModel` with placeholder indicators for volumetric efficiency, actual inlet capacity, required staging, discharge temperature, and a rod-load utilisation ratio using open API 618 / API 619 style relations. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/reciprocating-compressor-screening
```

## Run Example

```bash
python skills/process/reciprocating-compressor-screening/examples/basic_reciprocating_compressor_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/reciprocating-compressor-screening/tests
```

## Public Scope

The model contains no proprietary compressor data, vendor curves, or company specifications. For real calculations, use validated reciprocating-compressor methods (API 618, API 619), validated NeqSim compressor classes, and qualified rotating-equipment review.
