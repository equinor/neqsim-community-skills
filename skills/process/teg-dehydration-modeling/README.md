# TEG Dehydration Modeling

Build a validated, closed-loop triethylene-glycol (TEG) gas dehydration plant in
NeqSim — absorber, flash drum, regeneration column, stripper, lean-TEG recycle,
TEG makeup, and still-vent emission classification.

This skill captures a known-good flowsheet topology and the non-obvious settings
(CPA fluid, regeneration-column tolerances, recycle priorities, condenser/preheat
energy coupling) needed for the process to solve as a closed loop. It returns a
runnable NeqSim `ProcessSystem` plus the streams an agent needs for water dew
point, lean-TEG purity, and emissions.

Unlike `neqsim-water-dewpoint-dehydration-screening` (a public correlation
triage), this skill builds and runs a real NeqSim process, so it needs the
`neqsim` package.

## Install

```bash
python -m pip install -e skills/process/teg-dehydration-modeling
```

NeqSim is required to build the plant. Install it with:

```bash
python -m pip install neqsim
```

## Run Example

```bash
python skills/process/teg-dehydration-modeling/examples/basic_teg_dehydration_modeling.py
```

## Run Tests

```bash
python -m pytest skills/process/teg-dehydration-modeling/tests
```

Tests that build a plant are skipped automatically when NeqSim is not installed.

## Public Scope

Inputs and the default feed composition are public and synthetic. The skill does
not contain proprietary plant data, vendor glycol packages, or company emission
factors. Emission classification buckets stream mass flows (NMVOC, methane,
benzene, CO2, water) and is not a regulatory emission inventory. For final
design, use validated NeqSim CPA models and qualified process-engineering review.
