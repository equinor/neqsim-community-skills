# Dry Gas Seal Screening (NeqSim Community Skill)

Educational, screening-level dry gas seal supply and condensation check for
centrifugal compressors. It estimates seal-gas and separation-gas supply demand
from the primary seal leakage rate and flags retrograde-condensation risk by
comparing the seal cavity temperature against a hydrocarbon dew point.

This is a public placeholder skill. It is not a seal vendor method and not a
replacement for validated dry gas seal analysis per API 692 and a qualified
rotating-equipment review.

## Install

```bash
python -m pip install -e skills/process/dry-gas-seal-screening
```

## Run Example

```bash
python skills/process/dry-gas-seal-screening/examples/basic_dry_gas_seal_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/dry-gas-seal-screening/tests
```

## Public Scope

This skill uses only open, published concepts (API 692 / API 614 seal-gas
intent). It contains no confidential seal vendor data, machine line lists, or
project seal-gas conditioning specifications. For design-grade work, use the
validated `neqsim.process.equipment.compressor.DryGasSealAnalyzer` class and a
qualified engineering review.
