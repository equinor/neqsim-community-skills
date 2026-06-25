# Gas Scrubber Sizing Screening

Educational gas-scrubber sizing screening skill for public examples and agent guidance.

This skill provides a simple Python `GasScrubberSizingModel` with placeholder indicators for the Souders-Brown velocity, required vessel diameter, velocity utilisation, and mist-eliminator gas load using open GPSA / API RP 12J style relations. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/gas-scrubber-sizing-screening
```

## Run Example

```bash
python skills/process/gas-scrubber-sizing-screening/examples/basic_gas_scrubber_sizing_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/gas-scrubber-sizing-screening/tests
```

## Public Scope

The model contains no proprietary vessel data, vendor internals data, or company specifications. For real calculations, use validated separator sizing methods (GPSA, API RP 12J), validated NeqSim separator classes, and qualified review.
