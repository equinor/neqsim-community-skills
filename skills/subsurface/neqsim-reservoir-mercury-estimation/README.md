# Reservoir Mercury Estimation

Screening estimate of elemental mercury in the gas of a reservoir, prospect or discovery: a shrinkage model calibrated on tested wells, analogue tests, NeqSim mineral limits (cinnabar and liquid mercury) and a report with P10/P50/P90 and the reasoning behind it.

## Install

```bash
python -m pip install -e skills/subsurface/neqsim-reservoir-mercury-estimation
```

The mineral limits need the `neqsim` Python package with a NeqSim version that contains `neqsim.thermo.util.mineral.ReservoirMercuryEstimator`. The report figures need `matplotlib`; the Word report needs `python-docx`.

## Run Tests

```bash
python -m pytest skills/subsurface/neqsim-reservoir-mercury-estimation/tests
```

## Public Scope

No field data, well names, measurements or company models are included. The tests use synthetic data. Bring your own calibration registry and test table. The estimate is an order of magnitude with a wide range; a gas sample from the reservoir is the only way to narrow it.
