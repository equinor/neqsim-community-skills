# Compressor Validation

Centrifugal compressor performance checks: polytropic head from suction/discharge
conditions, vendor-curve head/efficiency lookup with fan-law speed scaling, chart
tuning multipliers, and a simple drivetrain shaft-power estimate.

No third-party dependencies.

## Install

```bash
python -m pip install -e skills/process/compressor-validation
```

## Run Example

```bash
python skills/process/compressor-validation/examples/check_operating_point.py
```

## Run Tests

```bash
python -m pytest skills/process/compressor-validation/tests
```

## Public Scope

The example uses a synthetic performance curve and gas state. No vendor performance
data, plant tags, or guarantee curves are included. For design or guarantee work, use
vendor models and qualified review.
