# Control Authority Screening

Educational screening for **loss of control authority** — a control valve driven onto its stop, after which the loop can no longer reject any disturbance.

The failure mode is easy to misdiagnose because the process appears to get worse while the disturbance is unchanged, so an investigation goes looking for a new external cause that does not exist. The screening needs only two tags that are almost always historised, a controller output and its process value.

## Install

```bash
python -m pip install -e skills/process/control-authority-screening
```

## Run Example

```bash
python skills/process/control-authority-screening/examples/basic_control_authority_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/control-authority-screening/tests
```

## Public Scope

The model contains no proprietary controller data, vendor tuning rules, or company specifications. It is a screening layer that decides when to invoke a validated loop performance review; real tuning, valve sizing, and rangeability work belongs to `neqsim-controllability-operability` and qualified engineering review.
