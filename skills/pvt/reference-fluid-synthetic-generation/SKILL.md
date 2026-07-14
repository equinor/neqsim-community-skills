---
name: neqsim-reference-fluid-synthetic-generation
version: "0.1.0"
description: "Public helpers to generate representative or synthetic fluid cases from a common reference fluid by adjusting a split/characterization factor, match that factor to measured PVT/separator data, and blend well/fluid compositions into a field composition by molar-rate allocation. USE WHEN: a task must calibrate a heavy-end split factor against measurements, produce field-level or per-case representative fluids from a reference model, or combine several wells/fluids into one allocated field fluid, before rigorous NeqSim characterization."
last_verified: "2026-07-14"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reference-Fluid Synthetic Generation

Use this skill for the "**common reference fluid → adjust split factor → match
measured data → generate representative fluids**" workflow. It provides three
plant-agnostic, dependency-free helpers:

1. `match_split_factor` — a robust golden-section 1-D search that finds the
   split / characterization factor best reproducing a measured target.
2. `generate_fluid_cases` — build representative or synthetic fluid cases by
   applying a range of factors to a common reference fluid.
3. `blend_compositions` — combine several well or fluid compositions into a
   single field composition by molar-rate allocation.

The forward model / fluid builder is **injected** by the caller, so this skill
has no dependency on a particular EOS. In practice it wraps the community
`pseudocomponent-split-characterization` gamma split or a NeqSim
characterization call, so the same factor drives both the split and the match.

## When to Use

- When you have a **common reference EOS/fluid** and want field-specific or
  per-case fluids by adjusting one heavy-end split factor (the "common factor"
  idea: reuse one characterization method with field-specific calibration).
- When a split factor must be **calibrated** so the model reproduces a measured
  saturation pressure, GOR, or stock-tank-oil density.
- When production is **allocated** across several wells or fluids and you need
  one representative field composition.
- When a complete PVT study is unavailable and you must generate a usable fluid
  from a reference plus available measurements.

## Inputs

- `objective(factor) -> scalar`: caller-supplied non-negative objective (for
  example sum of squared relative residuals against measured data).
- `low`, `high`: bounds of the split-factor search interval.
- `builder(factor) -> composition`: caller-supplied fluid builder.
- `weighted_compositions`: `(molar_rate, composition)` pairs for blending.

## Outputs

- `MatchResult`: the best factor, objective, iterations, and convergence flag.
- A list of generated composition cases.
- `BlendResult`: the normalized field composition, total molar rate, and weights.

## Engineering Method

### Common reference fluid and split factor

A single **common reference EOS/fluid** (a validated, detailed characterization)
is the basis. Field or per-case fluids are produced by re-splitting the heavy
end with an adjustable factor rather than characterizing every fluid from
scratch. This is the "common EOS" concept: FluidMagic pairs a common `eos_full`
with a lumped `eos_pseudo` and converts between them; NeqSim recommends a
consistent characterization model via `TBPfractionModel.recommendTBPModel`.

### Matching the factor to measured data

`match_split_factor` minimizes a caller-supplied objective by golden-section
search — no gradients, robust for the noisy, feasibility-gated forward models
produced by flash/PVT calculations. Wrap the measured targets (saturation
pressure, GOR, stock-tank density) as a sum of squared relative residuals.

### Blending by allocation

`blend_compositions` converts each stream's mole fractions to moles using its
molar rate, sums per component, and renormalizes — the correct way to combine
allocated well or fluid streams into a field composition.

## Python Usage Pattern

```python
from reference_fluid import match_split_factor, generate_fluid_cases, blend_compositions

# 1. Calibrate the split factor against a measured saturation pressure.
def objective(alpha):
    predicted_psat = my_forward_model(alpha)   # e.g. NeqSim saturation pressure
    rel = (predicted_psat - measured_psat) / measured_psat
    return rel * rel

match = match_split_factor(objective, low=0.5, high=3.0)

# 2. Generate representative low/base/high cases from a reference fluid.
cases = generate_fluid_cases([0.8, match.factor, 1.2], build_fluid_from_reference)

# 3. Blend three wells into one field fluid by molar rate.
field = blend_compositions([
    (3200.0, well_1_composition),
    (1500.0, well_2_composition),
    (900.0, well_3_composition),
])
```

## Related NeqSim Functionality

- `neqsim.thermo.characterization.PlusFractionModel` / `PlusCharacterize` — the
  heavy-end split whose `alpha`/`eta` is the factor matched here.
- `neqsim.thermo.characterization.TBPfractionModel.recommendTBPModel` — pick a
  consistent characterization model (PedersenSRK/PR, Twu, RiaziDaubert).
- `neqsim.thermo.characterization.Recombine` — recombine separator gas and oil.
- Rigorous saturation-pressure / GOR / density come from a `SystemInterface`
  fluid with `ThermodynamicOperations` (for example `bubblePointPressureFlash`).

Pair this skill with `neqsim-pseudocomponent-split-characterization` for the
split itself and `neqsim-pvt-regression-characterization-factor` for a
multi-target regression.

## Validation Checklist

- The common reference fluid and its source are documented.
- The objective used by `match_split_factor` is stated (which measured targets,
  which residual form) and the returned `converged` flag is checked.
- Generated fluid cases span a justified factor range (for example low/base/high).
- Blend molar rates are non-negative, their source is stated, and the blended
  composition sums to 1.
- Assumptions and limitations are recorded and qualified PVT review is planned.

## Common Mistakes

- Passing `low >= high` to `match_split_factor` (raises).
- Using an objective that is not smooth/unimodal over the interval, so the
  golden-section search returns a non-global point.
- Blending mole fractions without weighting by molar rate (loses allocation).
- Assuming one factor represents a whole field when the fluid varies by region.

## Limitations

- Screening-level; the caller's forward model determines physical accuracy.
- A single factor may not represent a whole field — evaluate per-region or
  per-well factors when the fluid varies significantly.
- Results require qualified PVT review before design or operational use.

## References

- Whitson, C.H., Brulé, M.R. (2000). *Phase Behavior*, SPE Monograph 20.
- Pedersen, K.S. et al. (2015). *Phase Behavior of Petroleum Reservoir Fluids*, 2nd ed.
- NeqSim: https://github.com/equinor/neqsim
