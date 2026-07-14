# Reference-Fluid Synthetic Generation (community skill)

Public, dependency-free helpers for the "common reference fluid → adjust split
factor → match measured data → generate representative fluids" workflow:

- `match_split_factor` — golden-section 1-D search to calibrate a split factor.
- `generate_fluid_cases` — build representative/synthetic fluids from a reference.
- `blend_compositions` — combine well/fluid compositions by molar-rate allocation.

See [SKILL.md](SKILL.md) for the method and NeqSim mapping.

## Install and test

```bash
pip install -e .[test]
pytest
```

## Scope

Screening-level. The forward model / fluid builder is injected by the caller;
pair with `neqsim-pseudocomponent-split-characterization` (the split) and
`neqsim-pvt-regression-characterization-factor` (multi-target regression).
Results require qualified PVT review before engineering use.
