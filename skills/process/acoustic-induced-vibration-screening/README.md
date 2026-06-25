# Acoustic-Induced Vibration Screening

Educational acoustic-induced-vibration (AIV) screening skill for public examples and agent guidance.

This skill provides a simple Python `AcousticInducedVibrationModel` with placeholder indicators for sound power level, pipe diameter-to-thickness ratio, allowable sound power level, and a likelihood-of-failure index using the open Energy Institute / Carucci-Mueller AIV screening form. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/acoustic-induced-vibration-screening
```

## Run Example

```bash
python skills/process/acoustic-induced-vibration-screening/examples/basic_acoustic_induced_vibration_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/acoustic-induced-vibration-screening/tests
```

## Public Scope

The model contains no proprietary valve data, vendor noise curves, or company specifications. For real calculations, use validated AIV methods (Energy Institute guidelines), validated NeqSim vibration classes, and qualified piping-vibration review.
