# Field Layout Import

Educational subsea field-layout import and normalization skill for public examples and agent guidance.

This skill provides a simple Python `FieldLayoutImporter` that turns an already-parsed GeoJSON `FeatureCollection` or a list of CSV-like rows into a clean, validated node list (well, manifold, host, riser base) with data-quality issues flagged. It performs no file or network I/O and is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/subsea/field-layout-import
```

## Run Example

```bash
python skills/subsea/field-layout-import/examples/basic_field_layout_import.py
```

## Run Tests

```bash
python -m pytest skills/subsea/field-layout-import/tests
```

## Public Scope

The model does not read files, fetch URLs, or embed proprietary coordinates, survey data, or internal sources. Callers parse GeoJSON or load tables themselves and pass already-parsed Python objects. The normalized node list is a data-shaping aid only. For real work, use validated NeqSim routing and hydraulic workflows and qualified subsea engineering review.
