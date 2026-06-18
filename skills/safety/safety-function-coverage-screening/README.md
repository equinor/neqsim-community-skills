# Safety Function Coverage Screening

Educational process safety-function coverage screening skill for public examples and agent guidance.

This skill provides a simple Python `SafetyFunctionCoverageModel` with placeholder logic for the API RP 14C / ISO 10418 SAFE-chart concept: it checks whether a component declares the typically required protective functions, lists the missing functions, and gives a coverage ratio. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/safety/safety-function-coverage-screening
```

## Run Example

```bash
python skills/safety/safety-function-coverage-screening/examples/basic_safety_function_coverage_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/safety-function-coverage-screening/tests
```

## Public Scope

The model does not contain proprietary SAFE charts, cause-and-effect matrices, or company safety specifications. For real analysis, use a formal API RP 14C / ISO 10418 SAFE-chart evaluation (mirrored by NeqSim `SafetyAnalysisFunctionEvaluation`) and qualified safety engineering review.
