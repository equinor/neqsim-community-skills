# Heat Exchanger Fouling and Performance Assessment

Educational heat-exchanger condition assessment skill for public examples and agent guidance.

This skill provides a Python `HeatExchangerFoulingModel` that reduces an operating snapshot to an overall coefficient, normalises it to design flow without scaling the deposit, separates fouling from film resistance, rules out maldistribution, and converts the result into a capacity limit and a cleaning interval. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/neqsim-heat-exchanger-fouling-assessment
```

## Run Example

```bash
python skills/process/neqsim-heat-exchanger-fouling-assessment/examples/basic_fouling_assessment.py
```

## Run Tests

```bash
python -m pytest skills/process/neqsim-heat-exchanger-fouling-assessment/tests
```

## Public Scope

The model contains no proprietary vendor rating methods, data sheets, or company specifications. For design-grade work, use validated NeqSim heat-exchanger and thermal-design classes, vendor rating software, and qualified process engineering review. This skill does not replace that review.
