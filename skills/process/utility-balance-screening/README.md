# Utility Balance Screening

Educational utility-balance screening skill for public examples and agent guidance.

This skill provides a simple Python `UtilityBalanceModel` with placeholder indicators for instrument air demand, cooling water flow, fuel gas Wobbe index compliance, and utility capacity utilisation using open NORSOK U-001 / ISA-7.0.01 / ISO 6976 style relations. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/utility-balance-screening
```

## Run Example

```bash
python skills/process/utility-balance-screening/examples/basic_utility_balance_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/utility-balance-screening/tests
```

## Public Scope

The model contains no proprietary utility loads, vendor data, or company specifications. For real calculations, use validated utility-balance methods (NORSOK U-001, ISA-7.0.01, ISO 6976), validated NeqSim resources, and qualified utility design.
