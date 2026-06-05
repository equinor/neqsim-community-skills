# Digital Twin Validation

Compare simulated values against measured reference data with per-channel tolerances,
aggregate pass/fail status, and render a portable HTML report.

This skill *measures and reports* model accuracy. It does not tune model parameters.
It has no third-party dependencies.

## Install

```bash
python -m pip install -e skills/process/digital-twin-validation
```

## Run Example

```bash
python skills/process/digital-twin-validation/examples/validate_demo_train.py
```

## Run Tests

```bash
python -m pytest skills/process/digital-twin-validation/tests
```

## Public Scope

The example uses synthetic measured/simulated values only. No plant tags, historian
data, or company-specific tolerances are included. For decisions about model fidelity,
use qualified engineering review.
