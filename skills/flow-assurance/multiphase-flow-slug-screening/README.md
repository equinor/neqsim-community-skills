# Multiphase Flow Slug Screening (NeqSim Community Skill)

Educational, screening-level multiphase slug-flow indicator and slug-catcher
volume estimate. It gives a coarse flow-regime label from superficial gas and
liquid velocities and a first-pass slug-catcher volume from slug geometry.

This is a public placeholder skill. It is not a validated flow-pattern map and
not a replacement for validated multiphase flow analysis and a qualified
flow-assurance review.

## Install

```bash
python -m pip install -e skills/flow-assurance/multiphase-flow-slug-screening
```

## Run Example

```bash
python skills/flow-assurance/multiphase-flow-slug-screening/examples/basic_slug_screening.py
```

## Run Tests

```bash
python -m pytest skills/flow-assurance/multiphase-flow-slug-screening/tests
```

## Public Scope

This skill uses only open, published multiphase flow concepts (Beggs and Brill,
Taitel-Dukler, NORSOK P-001/P-002). It contains no confidential pipeline
geometry, project flow-assurance reports, or company multiphase guidelines. For
design-grade work, use the validated
`neqsim.process.equipment.pipeline.PipeBeggsAndBrills` class and a qualified
engineering review.
