# Reservoir Souring Correlation

Educational skill: injected-seawater fraction from tracers, per-well H2S versus seawater-fraction correlations selected and updated automatically, and a substrate-limited mixing-zone H2S bound. Standard library only.

## Install

```bash
python -m pip install -e skills/subsurface/neqsim-reservoir-souring-correlation
```

## Run Tests

```bash
python -m pytest skills/subsurface/neqsim-reservoir-souring-correlation/tests
```

## Public Scope

No field data, well names, measurements or company models are included. The tests use synthetic data. Correlations are empirical fits and the mixing-zone model is an upper bound; for real souring forecasts use reservoir simulation and qualified review.
