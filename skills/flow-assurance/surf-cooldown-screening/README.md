# SURF Cooldown Screening

Educational subsea flowline/riser cooldown and no-touch-time screening skill for
public examples and agent guidance.

This skill provides a simple Python `SurfCooldownModel` with placeholder
indicators for the no-touch time (time to reach the hydrate region after
shutdown), the hydrate target temperature, and an operating verdict. It is
intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/flow-assurance/surf-cooldown-screening
```

## Run Example

```bash
python skills/flow-assurance/surf-cooldown-screening/examples/basic_surf_cooldown_screening.py
```

## Run Tests

```bash
python -m pytest skills/flow-assurance/surf-cooldown-screening/tests
```

## Public Scope

The model does not contain proprietary insulation data, confidential cooldown
specifications, inhibitor dosage rules, or company-specific flow assurance
envelopes. The hydrate equilibrium temperature and the thermal time constant must
come from validated NeqSim calculations. For real work, use validated NeqSim
cooldown and hydrate workflows and qualified flow assurance review.
