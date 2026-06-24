# Step-Out Screening

Educational subsea tie-back step-out and arrival-pressure screening skill for public examples and agent guidance.

This skill provides a simple Python `StepOutScreeningModel` that compares a tie-back step-out distance, an arrival-pressure margin, and an optional hydrate margin against public guidelines and returns an overall screening verdict. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/subsea/step-out-screening
```

## Run Example

```bash
python skills/subsea/step-out-screening/examples/basic_step_out_screening.py
```

## Run Tests

```bash
python -m pytest skills/subsea/step-out-screening/tests
```

## Public Scope

The model does not perform hydraulic or thermodynamic calculations and contains no proprietary thresholds. Arrival pressure and hydrate margins must come from validated tools. Verdicts are screening indicators only. For real work, use validated NeqSim flow-assurance and hydraulic workflows and qualified subsea engineering review.
