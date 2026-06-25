# Dynamic Instrument Controller Setup

Public NeqSim community skill for setting up measurement devices and PID-style controllers in dynamic simulations.

The skill provides a lightweight Python loop checker and documents the NeqSim API sequence for transmitters, controller devices, valve manipulation, controller action, PID settings, and autotuning event logs.

## Install

```bash
python -m pip install -e skills/process/dynamic-instrument-controller-setup
```

## Run Example

```bash
python skills/process/dynamic-instrument-controller-setup/examples/basic_controller_setup.py
```

## Run Tests

```bash
python -m pytest skills/process/dynamic-instrument-controller-setup/tests
```

## Public Scope

The helper does not tune controllers or run NeqSim. For real dynamic studies, use validated NeqSim models, deliberate transient tests, and qualified process-control review.
