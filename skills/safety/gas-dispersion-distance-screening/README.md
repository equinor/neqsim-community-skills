# Gas Dispersion Distance Screening

Educational Gaussian point-source dispersion screening that estimates the downwind distance at which a continuous gas release falls to a target concentration (for example the LFL or a toxic ppm limit) using the public Pasquill-Gifford / Briggs rural model. It routes real work to validated NeqSim dispersion scenarios.

## Install

```bash
python -m pip install -e skills/safety/gas-dispersion-distance-screening
```

## Run Example

```bash
python skills/safety/gas-dispersion-distance-screening/examples/basic_gas_dispersion_distance_screening.py
```

## Run Tests

```bash
python -m pytest skills/safety/gas-dispersion-distance-screening/tests
```

## Public Scope

This skill uses only the public Gaussian plume model with Briggs rural dispersion coefficients. It is an educational screening placeholder and does not replace validated NeqSim dispersion modelling, CFD or integral consequence tools, or qualified safety review.
