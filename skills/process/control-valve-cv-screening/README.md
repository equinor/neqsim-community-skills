# Control Valve Cv Screening

Educational control-valve sizing screening that estimates the required flow coefficient (Kv/Cv) and flags choked flow using the public IEC 60534-2-1 / ISA-75.01 equations for liquid and gas service. It routes real work to the validated NeqSim `ThrottlingValve` / `ControlValve`.

## Install

```bash
python -m pip install -e skills/process/control-valve-cv-screening
```

## Run Example

```bash
python skills/process/control-valve-cv-screening/examples/basic_control_valve_cv_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/control-valve-cv-screening/tests
```

## Public Scope

This skill uses only public control-valve sizing equations (IEC 60534-2-1 / ISA-75.01). It is an educational screening placeholder and does not replace validated NeqSim valve calculations, vendor valve sizing, or qualified control-valve selection.
