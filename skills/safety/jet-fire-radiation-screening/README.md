# Jet Fire Radiation Screening

Educational jet-fire thermal-radiation screening that estimates the radiative flux at a distance, or the distance to a target flux, using the public single-point-source flame radiation model. It routes real work to the validated NeqSim `JetFireModel`.

## Install

```bash
python -m pip install -e skills/safety/jet-fire-radiation-screening
```

## Run Example

```bash
python skills/safety/jet-fire-radiation-screening/examples/basic_jet_fire_radiation_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/jet-fire-radiation-screening/tests
```

## Public Scope

This skill uses only the public single-point-source flame radiation model. It is an educational screening placeholder and does not replace validated NeqSim fire modelling, solid-flame or CFD radiation tools, or qualified safety review.
