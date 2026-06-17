# Compressor Operating Window Check

Educational compressor operating window screening skill for public examples and agent guidance.

This skill provides a simple Python `CompressorOperatingWindowModel` with placeholder indicators for surge margin, stonewall margin, the limiting margin, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/compressor-operating-window-check
```

## Run Example

```bash
python skills/process/compressor-operating-window-check/examples/basic_compressor_operating_window_check.py
```

## Run Tests

```bash
python -m pytest skills/process/compressor-operating-window-check/tests
```

## Public Scope

The model does not contain proprietary performance maps, vendor curves, anti-surge control data, or company-specific compressor specifications. For real calculations, use validated compressor performance methods (API 617), validated NeqSim compressor models and curves, and qualified process engineering review.
