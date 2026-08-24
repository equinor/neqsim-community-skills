# Noise Screening

Standards-based gas-valve and restriction noise screening at a stated receiver distance. It can use a representative current operating measurement or a conservative pressure-drop energy model, and it keeps source prediction, workplace assessment, and AIV as separate decisions.

## Install

```bash
python -m pip install -e skills/process/noise-screening
```

## Run Example

```bash
python skills/process/noise-screening/examples/basic_noise_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/noise-screening/tests
```

## Public Scope

The model path is a triage calculation with explicit uncertainty, not a full IEC 60534-8-3 prediction. Measured levels retain their stated uncertainty and operating/receiver context. Detailed work routes to NeqSim `ControlValveNoise_IEC_60534_8_3`, ISO 3744/11201 measurement, ISO 9613-2 propagation, ISO 15664 open-plant design, and ISO 1999 exposure support. AIV remains a separate assessment.
