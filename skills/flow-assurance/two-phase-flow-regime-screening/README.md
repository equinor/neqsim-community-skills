# Two-Phase Flow Regime Screening

Educational two-phase flow-regime screening that classifies a horizontal gas-liquid flow pattern from superficial velocities using a simplified Mandhane-style map and flags slug risk. It pairs with slug and flow-induced-vibration work and routes real work to validated NeqSim multiphase pipe flow.

## Install

```bash
python -m pip install -e skills/flow-assurance/two-phase-flow-regime-screening
```

## Run Example

```bash
python skills/flow-assurance/two-phase-flow-regime-screening/examples/basic_two_phase_flow_regime_screening.py
```

## Run Tests

```bash
python -m pytest skills/flow-assurance/two-phase-flow-regime-screening/tests
```

## Public Scope

This skill uses only public, simplified Mandhane-style flow-regime boundaries. It is an educational screening placeholder and does not replace validated NeqSim multiphase flow modelling, mechanistic regime maps, or qualified flow assurance review.
