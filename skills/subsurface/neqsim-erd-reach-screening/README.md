# ERD Reach Screening

Educational extended-reach well screening skill: build-and-hold path, soft-string torque and drag, and torque-limited reach versus friction and drill string.

## Install

```bash
python -m pip install -e skills/subsurface/neqsim-erd-reach-screening
```

## Run Tests

```bash
python -m pytest skills/subsurface/neqsim-erd-reach-screening/tests
```

## Public Scope

No rig data, vendor string data or company well design basis is included. Friction factors and torque limits are inputs that must be calibrated to the rig in question; for real well design use a validated torque-and-drag tool and qualified well engineering review.
