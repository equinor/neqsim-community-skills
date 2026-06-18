# Compressor Power Screening

Educational centrifugal-compressor power screening skill for public examples and agent guidance.

This skill provides a simple Python `CompressorPowerModel` with placeholder indicators for polytropic head, discharge temperature, gas power, and a rated-power comparison using the open polytropic-head equation. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/compressor-power-screening
```

## Run Example

```bash
python skills/process/compressor-power-screening/examples/basic_compressor_power_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/compressor-power-screening/tests
```

## Public Scope

The model does not contain proprietary compressor curves, vendor data, or company specifications. For real calculations, use validated compressor methods (API 617, API 619), validated NeqSim compressor classes, and qualified rotating-equipment review.
