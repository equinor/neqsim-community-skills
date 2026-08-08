# Benchmark Reference Data

Independent reference data and model-vs-reference comparison for NeqSim benchmark
validation.

Benchmark validation is a mandatory step in the NeqSim task workflow, but it is
usually written from scratch in every notebook. This skill supplies the pieces
that should not be rewritten: a registry of independent reference sources with
authority tiers and validated ranges, an offline anchor table that works with no
optional dependency, an optional CoolProp bridge for arbitrary states, and a
comparison layer that emits the `benchmark_validation` block the task report
generator and CI gate already consume.

## Install

```bash
python -m pip install -e skills/pvt/benchmark-reference-data
```

Optional reference generator:

```bash
python -m pip install CoolProp
```

## Run Examples

```bash
python skills/pvt/benchmark-reference-data/examples/validate_against_anchor_points.py
python skills/pvt/benchmark-reference-data/examples/validate_with_coolprop.py
```

The CoolProp example prints an install hint and exits cleanly when CoolProp is
not installed.

## Run Tests

```bash
python -m pytest skills/pvt/benchmark-reference-data/tests
```

## Public Scope

All reference values are published constants from openly cited reference
formulations (IAPWS-95, Span-Wagner, Setzmann-Wagner, GERG-2008 and related).
No proprietary correlations, lab data, or internal acceptance criteria are
included. The default tolerances are screening defaults, not project acceptance
criteria — a study must state its own.
