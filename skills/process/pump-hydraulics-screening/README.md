# Pump Hydraulics Screening

Educational centrifugal-pump screening for hydraulic and shaft power, available NPSH, and the best-efficiency-point (BEP) operating window using public pump relations. It routes real work to the validated NeqSim `Pump`.

## Install

```bash
python -m pip install -e skills/process/pump-hydraulics-screening
```

## Run Example

```bash
python skills/process/pump-hydraulics-screening/examples/basic_pump_hydraulics_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/pump-hydraulics-screening/tests
```

## Public Scope

This skill uses only public pump hydraulics relations (`P = rho g Q H`, NPSH-available, and BEP flow ratio). It is an educational screening placeholder and does not replace validated NeqSim pump calculations or qualified rotating-equipment review.
