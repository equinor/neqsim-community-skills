# Dynamic Process Preparation

Public NeqSim community skill for preparing `ProcessSystem` and `ProcessModel` flowsheets for dynamic simulation.

The skill provides a lightweight Python readiness checker and documents the NeqSim API sequence for dynamic mode, mechanical-design handoff, equipment volume initialization, and transient execution.

## Install

```bash
python -m pip install -e skills/process/dynamic-process-preparation
```

## Run Example

```bash
python skills/process/dynamic-process-preparation/examples/basic_dynamic_preparation.py
```

## Run Tests

```bash
python -m pytest skills/process/dynamic-process-preparation/tests
```

## Public Scope

The helper does not run NeqSim and does not include proprietary dynamic design rules. For real calculations, use validated NeqSim process models, NeqSim mechanical-design classes, and qualified engineering review.
