# H2S Safety Impact

Screening helpers that turn an H2S estimate (or measurement) into safety numbers: partial pressure and sour-service flag, toxic reach of a release, detector equivalence, SO2 from flaring, export-gas blending, scavenger demand and vapour above produced water, with an evidence gate that keeps results UNVERIFIED until H2S is measured in a sample of the reservoir.

## Install

```bash
python -m pip install -e skills/safety/neqsim-h2s-safety-impact
```

## Run Tests

```bash
python -m pytest skills/safety/neqsim-h2s-safety-impact/tests
```

No NeqSim is needed for the helpers. Pair them with `neqsim-reservoir-h2s-estimation`, `neqsim-reservoir-souring-correlation` and `neqsim-h2s-phase-partitioning` for the H2S numbers and with `neqsim-gas-dispersion-distance-screening` (or NeqSim `GaussianPlume`) for the plume.

## Public Scope

All numbers in the tests are generic. Limits are arguments with a named source; the library never claims that a standard is met.
