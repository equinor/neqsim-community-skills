# Fired Heater Duty Screening

Educational fired-heater duty and radiant-flux screening skill for public examples and agent guidance.

This skill provides a simple Python `FiredHeaterDutyModel` with placeholder indicators for process duty, fired duty, fuel rate, and average radiant flux using open energy-balance relations. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/fired-heater-duty-screening
```

## Run Example

```bash
python skills/process/fired-heater-duty-screening/examples/basic_fired_heater_duty_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/fired-heater-duty-screening/tests
```

## Public Scope

The model does not contain proprietary heater designs, vendor data, or company specifications. For real calculations, use validated fired-heater methods (API 560), validated NeqSim heater classes, and qualified process engineering review.
