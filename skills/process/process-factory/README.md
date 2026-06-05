# Process Factory

Convert a declarative flow-path description into an ordered NeqSim unit-operation plan,
and (when the optional `neqsim` package is installed) into a real `ProcessSystem`.

Pipe segments become `PipeBeggsAndBrills` with fitting losses folded into an effective
length; equipment becomes separators, scrubbers, coolers, or pass-through valves;
parallel branches become a splitter/mixer pair. The `build_plan` function is
deterministic and testable without NeqSim.

## Install

```bash
python -m pip install -e skills/process/process-factory
```

## Run Example

```bash
python skills/process/process-factory/examples/build_demo_plan.py
```

## Run Tests

```bash
python -m pytest skills/process/process-factory/tests
```

## Public Scope

The example uses a synthetic flow path. No plant topology, tags, or vendor data are
included. Constructing a real `ProcessSystem` requires the optional `neqsim` package.
