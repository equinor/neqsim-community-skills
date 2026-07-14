# PVT Regression of a Characterization Factor (community skill)

Public, dependency-free weighted multi-target regression of one split /
characterization factor against measured PVT and separator data (saturation
pressure, GOR, stock-tank-oil density, Bo), with per-target residual reporting.

See [SKILL.md](SKILL.md) for the method and NeqSim mapping.

## Install and test

```bash
pip install -e .[test]
pytest
```

## Scope

Screening-level, single-factor. The forward model is injected by the caller;
pair with `neqsim-pseudocomponent-split-characterization` (the split) and
`neqsim-reference-fluid-synthetic-generation` (generate fluids). For full EOS
tuning use the rigorous NeqSim PVT-simulation and regression classes. Results
require qualified PVT review before engineering use.
