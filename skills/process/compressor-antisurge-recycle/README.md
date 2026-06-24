# Compressor Anti-Surge Recycle Setup

Educational NeqSim skill for setting up anti-surge recycle (spill-back) control
on a centrifugal compressor, including auto-generating a compressor chart with
surge and stonewall curves when no vendor chart is given.

This skill provides a pure-Python `AntiSurgeRecycleModel` that mirrors NeqSim's
proportional anti-surge step so an agent can estimate the recycle flow needed to
keep a compressor off surge and decide whether a chart must be generated first.
The `SKILL.md` documents the validated NeqSim wiring pattern (surge curve,
recycle stream, discharge splitter, anti-surge `Calculator`, anti-surge valve,
`Recycle`) and the chart-generation API. It is intended for learning and
workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/compressor-antisurge-recycle
```

## Run Example

```bash
python skills/process/compressor-antisurge-recycle/examples/basic_compressor_antisurge_recycle.py
```

## Run Tests

```bash
python -m pytest skills/process/compressor-antisurge-recycle/tests
```

## Public Scope

The model does not contain proprietary performance maps, vendor curves,
anti-surge controller settings, or company-specific compressor data. The example
data are generic. For real anti-surge control, use validated NeqSim compressor
models and curves, vendor performance maps, and qualified rotating-equipment
review per API 617 and API 692.
