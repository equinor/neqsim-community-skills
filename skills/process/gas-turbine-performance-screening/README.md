# Gas Turbine Performance Screening

Educational gas-turbine performance screening skill for public examples and agent guidance.

This skill provides a simple Python `GasTurbinePerformanceModel` with placeholder indicators for site-rated shaft power, site heat rate, thermal efficiency, fuel heat input, exhaust mass flow, and exhaust temperature using open ISO 3977 / GL1029 style derate factors. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/gas-turbine-performance-screening
```

## Run Example

```bash
python skills/process/gas-turbine-performance-screening/examples/basic_gas_turbine_performance_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/gas-turbine-performance-screening/tests
```

## Public Scope

The model contains no proprietary vendor performance maps, fuel data, or company specifications. For real calculations, use validated gas-turbine performance methods (ISO 3977, ISO 2314), validated NeqSim power-generation classes, and qualified package review.
