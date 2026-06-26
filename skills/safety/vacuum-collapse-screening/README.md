# Vacuum Collapse Screening

Educational vacuum-collapse (external-pressure implosion) screening skill for public examples and agent guidance.

This skill provides a simple Python `VacuumCollapseModel` with placeholder indicators for the final pressure after a blocked-in vessel cooldown, a vacuum-depth estimate, and an external-rating flag. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/safety/vacuum-collapse-screening
```

## Run Example

```bash
python skills/safety/vacuum-collapse-screening/examples/basic_vacuum_collapse_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/vacuum-collapse-screening/tests
```

## Public Scope

The model does not contain proprietary vessel geometry, confidential external-pressure ratings, or company-specific vacuum design bases. For real calculations, use the validated NeqSim `VacuumCollapseAnalyzer` constant-volume cooldown model, a code external-pressure (buckling) review such as ASME BPVC Section VIII, vacuum relief sizing, and qualified process safety review.
