---
name: neqsim-reference-fluid-synthetic-generation
calculation_basis: "screening"
version: "0.2.0"
description: "Public helpers to generate representative or synthetic fluid cases from a common reference fluid by adjusting a split/characterization factor, match that factor to measured PVT/separator data, blend well/fluid compositions into a field composition by molar-rate allocation, and — when there is NO PVT report and possibly no sample at all — build a declared best-guess fluid basis from fundamentals and named analogues: reservoir temperature from a provincial geothermal gradient, fluid type from GOR/degAPI bands, GOR and stock-tank gravity interpolated on an analogue depth trend with low/base/high cases, a seed light-ends + C7+ cut composition ready for a NeqSim EOS characterization, a per-parameter provenance and assumption register, and a ranked data-acquisition plan. USE WHEN: a task must calibrate a heavy-end split factor against measurements, produce field-level or per-case representative fluids from a reference model, combine several wells/fluids into one allocated field fluid, or establish a fluid for a discovery or prospect that has no laboratory PVT, before rigorous NeqSim characterization."
last_verified: "2026-09-10"
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

- When there is **no PVT study at all** — a discovery, a prospect, an early
  concept — and a reservoir model still needs a fluid. See *No PVT data* below.
- When you have a **common reference EOS/fluid** and want field-specific or
  per-case fluids by adjusting one heavy-end split factor (the "common factor"
  idea: reuse one characterization method with field-specific calibration).
- When a split factor must be **calibrated** so the model reproduces a measured
  saturation pressure, GOR, or stock-tank-oil density.
- When production is **allocated** across several wells or fluids and you need
  one representative field composition.
- When a complete PVT study is unavailable and you must generate a usable fluid
  from a reference plus available measurements.

## No PVT data: build a best guess and say so

A reservoir model needs a fluid long before a laboratory PVT study exists, and
often before a sample has been taken. The alternative to guessing silently is
to guess explicitly.

```python
from reference_fluid import build_analogue_fluid_basis

basis = build_analogue_fluid_basis(
    depth_tvdss_m=3590.0,
    province="northern_north_sea",
    formation="Brent",
    water_depth_m=381.0,
    measured_temperature_C=129.0,     # anything measured is used and labelled
    measured_pressure_bara=542.0,     # ... and anything absent is derived
)
basis.targets["gor_sm3_sm3"]      # value + provenance + GOR DEFINITION
basis.seed["c7_plus_cuts"]        # ready for addTBPfraction / addPlusFraction
basis.assumptions                 # each with the measurement that retires it
basis.acquisition_plan            # ranked by how much it reduces the answer
```

### Derive temperature. Do not derive pressure.

This is the asymmetry that matters, and it is evidence-backed. On a Middle
Jurassic northern North Sea reservoir at 3590 m TVDSS:

| Quantity | From a gradient | Measured | Verdict |
| --- | --- | --- | --- |
| Temperature | 130.0 °C | 129 °C | trustworthy |
| Pressure | 399 bara (hydrostatic) | **542 bara** | **wrong by 163 bar** |

A seabed temperature and a provincial geothermal gradient reproduce reservoir
temperature to about a degree. Overpressure cannot be predicted from depth at
all, and 100–200 bar of it is routine in deep sections. So
`estimate_conditions()` returns a derived temperature marked `derived` with a
confidence note, and a derived pressure marked **`placeholder`** carrying a
warning and the list of what it blocks: undersaturation, the depletion path,
the well count, the drive mechanism.

Never present a study built on a derived pressure as anything but conditional
on an RFT/MDT measurement.

### Fluid type before anything else

`classify_fluid_type(gor, api)` places the fluid in the conventional GOR bands
(heavy oil → black oil → volatile oil → gas condensate → wet/dry gas), reports
whether a black-oil PVTO/PVDG table is adequate, and cross-checks the GOR
against the stock-tank gravity. A GOR and a gravity that disagree mean one of
them is wrong or the GOR is quoted on a different basis — which is the next
trap.

### The GOR definition trap

An unqualified "GOR" is ambiguous, and the spread is not small. The same tuned
volatile oil gave:

| Definition | Value |
| --- | --- |
| single-stage flash from reservoir | 290 Sm3/Sm3 |
| black-oil Rs at the bubble point (what the simulator uses) | 318 Sm3/Sm3 |
| three-stage separator train (what a production test reports) | 259 Sm3/Sm3 |

A spread of 58 Sm3/Sm3, about 20 % of the quoted number. `build_analogue_fluid_basis`
takes a `gor_definition` argument and, when it is not supplied, records
`"UNSTATED"` plus an assumption-register entry. `reconcile_gor_definitions()`
reports the spread once several are known, so the size and direction of the
correction stay visible.

### Seed composition, and how to tune it

`seed_composition()` returns a light-ends template for the classified fluid type
plus a nine-cut C7+ set with molar masses and densities. Two rules travel with
it because both were learned the hard way:

- **Tune the C7+ mole fraction against GOR and a common density offset against
  stock-tank density, each by bisection on a bracketed interval. Do not tune
  molar masses.** A 2-D Newton step on (C7+ fraction, molar-mass multiplier)
  runs to its bounds and produces a "C7" of 53 g/mol — a fluid that still
  flashes and is not a C7.
- **NeqSim `addTBPfraction`/`addPlusFraction` take kg/mol, not g/mol.** Passing
  g/mol fails silently: critical temperatures in the thousands of kelvin, an
  acentric factor near −1, and a standard-condition flash returning one phase
  typed GAS with a liquid density.

### Grade the result honestly

`basis_confidence(basis)` counts how much of the basis is measured and returns
`data-driven`, `partially data-driven`, `analogue`, or `conditional` when a
placeholder is present. A production forecast inherits the grade of its fluid
regardless of how good the static model is.

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
