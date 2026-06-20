# Noise Screening

Educational valve and line aerodynamic-noise indicator that estimates a screening sound-pressure level from gas mass flow, pressure drop, and density using a public IEC 60534-8 style energy approach. It routes real work to validated NeqSim valve modelling and full IEC 60534-8 prediction.

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

This skill uses only a public energy-based aerodynamic-noise indicator. It is an educational screening placeholder and is not a full IEC 60534-8-3 noise prediction; it does not replace validated NeqSim valve modelling, vendor noise data, or qualified acoustic review.
