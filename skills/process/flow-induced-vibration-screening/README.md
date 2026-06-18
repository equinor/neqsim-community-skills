# Flow-Induced Vibration Screening

Educational flow-induced vibration (FIV) screening skill for public examples and agent guidance.

This skill provides a simple Python `FlowInducedVibrationModel` with placeholder indicators for the fluid kinetic-energy index `rho v^2`, a threshold ratio, a qualitative likelihood-of-failure band, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/flow-induced-vibration-screening
```

## Run Example

```bash
python skills/process/flow-induced-vibration-screening/examples/basic_flow_induced_vibration_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/flow-induced-vibration-screening/tests
```

## Public Scope

The model does not reproduce the proprietary Energy Institute Guidelines or any confidential scoring tables, line lists, vendor data, or company-specific piping specifications. It uses only the publicly known `rho v^2` kinetic-energy screening concept. For real calculations, use a validated FIV likelihood-of-failure assessment (Energy Institute guidelines), validated NeqSim property models, and qualified piping engineering review.
