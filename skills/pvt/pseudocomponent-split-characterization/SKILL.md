---
name: neqsim-pseudocomponent-split-characterization
version: "0.1.0"
description: "Public plus-fraction (C7+) characterization by a controllable split factor: a Whitson three-parameter gamma molar split, a lumping split factor, delumping reconstruction, and the universal Paraffinic-Aromatic (P/A) heavy-lump split factor S (Uleberg 2026). USE WHEN: a task needs to divide a heavy end into pseudocomponents with one adjustable characterization/split factor, compute a delumping split factor from a reference fluid, reconstruct a detailed composition from a lumped one, or split heavy lumps into paraffinic/aromatic copies on a universal P/A set, before rigorous NeqSim characterization."
last_verified: "2026-07-14"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Pseudocomponent Split-Factor Characterization

Use this skill to represent a reservoir fluid with a **small, controllable
number of adjustable factors** instead of building a bespoke characterization
for every fluid. It provides three plant-agnostic, dependency-free building
blocks:

1. A **Whitson three-parameter gamma** molar split of a plus fraction (C7+),
   governed by a single split/characterization factor `alpha`.
2. A **lumping split factor** computed from a detailed reference composition.
3. A **delumping** reconstruction that turns a lumped composition back into
   detailed components using that split factor.

These are screening-level helpers. For design-grade work, move to the rigorous
NeqSim `neqsim.thermo.characterization` Java classes described below.

## When to Use

- When a fluid must be described by detailed light components plus a heavy
  pseudocomponent set, and you want one factor to control the heavy-end split.
- When you have a **reference fluid** and want to generate representative or
  synthetic fluids by adjusting the split factor.
- When a **lumped** composition (few components) must be **delumped** back to a
  detailed composition using the internal distribution of a reference fluid.
- When you need a transparent, reproducible split before running the rigorous
  NeqSim characterization for design-grade work.
- When a fluid is represented on a **universal Paraffinic-Aromatic (P/A)** set
  (fixed 10 light + N paraffinic + N aromatic heavy lumps) and its heavy-end
  character is carried by a single **split factor S** (the paraffinic fraction
  of each heavy lump), per the Uleberg (2026) universal characterisation.

## Inputs

- `z_plus`: total mole fraction of the plus fraction, in `(0, 1]`.
- `m_plus`: average molar mass of the plus fraction (g/mol).
- `boundaries`: increasing molar-mass boundaries (g/mol); `n+1` values give `n`
  pseudocomponents. The last boundary may be `math.inf`.
- `alpha`: gamma shape / split factor (`> 0`; `1.0` = exponential heavy end).
- `eta`: minimum molar mass of the distribution (g/mol).
- `full_composition` and `lumping_scheme` for the split-factor / delumping path.

## Outputs

- `GammaSplitResult`: per-pseudocomponent mole fractions and average molar masses.
- `SplitFactorResult`: per-component split factors and per-lump totals.
- Delumped detailed composition (tuple of mole fractions).

## Engineering Method

### Whitson gamma split

The heavy end is described by the three-parameter gamma probability density

$$ p(M) = \frac{(M-\eta)^{\alpha-1}\,\exp\!\left(-\frac{M-\eta}{\beta}\right)}{\beta^{\alpha}\,\Gamma(\alpha)}, \qquad \beta = \frac{M_{+}-\eta}{\alpha} $$

where `M` is molar mass, `eta` the minimum molar mass, `alpha` the split factor,
and `M+` the plus-fraction average molar mass. Mole fractions in each molar-mass
interval are obtained from the regularized lower incomplete gamma function
`P(alpha, y)`, and each pseudocomponent's average molar mass from
`P(alpha+1, y)`. `alpha = 1` yields an exponential (Pedersen-like) distribution;
higher `alpha` narrows the distribution and lightens the tail.

### Lumping split factor and delumping

For each lump, the split factor of a detailed component is its mole fraction
divided by the lump total (each lump's factors sum to 1). A lumped composition
is delumped by multiplying each lump value by its component split factors. This
mirrors FluidMagic's `EOSConverter.calculate_split_factor` / `_delump`.

### Universal Paraffinic-Aromatic (P/A) split factor S

The universal characterisation of Uleberg (2026) keeps one fixed component set
(10 light + N paraffinic + N aromatic heavy lumps) and carries each feed's
heavy-end character in a single split factor. For heavy lump `i` with total mole
fraction `Z_i`, the split factor `S_i` (the paraffinic fraction) divides it into
a paraffinic copy `P_i = S_i Z_i` and an aromatic copy `A_i = (1 - S_i) Z_i`, so
moles are conserved. The recommended operational form is a **single constant
`S`** applied to every heavy lump; a general two-endpoint form interpolates `S_i`
linearly in molecular weight between `S1` (lightest heavy lump) and `Sn`
(heaviest), clipped to `[eps, 1-eps]`. For a feed with no separator calibration,
`S` is assigned provisionally from the screening correlation
`S ~= 1.3298 - 0.003531 * MW_C7+` (MW in g/mol; clipped). `S` calibrates the
heavy-end **stock-tank-oil density** (and only weakly GOR); the light/heavy
molar ratio — hence the GOR — is set by the feed's own composition (its ZI),
not by `S`. The fixed critical properties, acentric factors, volume shifts and
BIPs of the paraffinic and aromatic families live in the universal EOS; this
skill only performs the molar split.

## Python Usage Pattern

```python
import math
from pseudocomponent_split import (
    gamma_mole_split,
    calculate_split_factor,
    delump_composition,
)

# 1. Split a C7+ plus fraction into 4 pseudocomponents with split factor alpha.
split = gamma_mole_split(
    z_plus=0.05,
    m_plus=220.0,
    boundaries=[90.0, 140.0, 200.0, 300.0, math.inf],
    alpha=1.0,
    eta=90.0,
)
print(split.mole_fractions, split.molar_masses)

# 2. Split factor from a detailed reference fluid, then delump a lumped fluid.
full = [0.70, 0.10, 0.06, 0.04, 0.03, 0.07]
scheme = [[0], [1, 2], [3, 4, 5]]
sf = calculate_split_factor(full, scheme)
detailed = delump_composition(list(sf.lump_totals), sf.split_factors, scheme)
```

### Universal P/A split factor S

```python
from pseudocomponent_split import (
    c7plus_split_correlation,
    constant_pa_split,
    apply_constant_split_to_vector,
)

# Provisional constant S when a feed has no separator calibration.
S = c7plus_split_correlation(mw_c7plus=210.0)   # ~0.588, clipped to [0.02, 0.98]

# Split heavy-lump totals into paraffinic / aromatic copies (P_i, A_i).
core_totals = [0.02, 0.015, 0.01, 0.005]
paraffinic, aromatic = constant_pa_split(core_totals, S)

# Re-split a fluid already on a universal P/A set (names end in P / A) with a
# new constant S; light components pass through unchanged, moles conserved.
names = ["N2", "C1", "C7P", "C7A", "C8P", "C8A"]
zi = [0.02, 0.90, 0.03, 0.01, 0.03, 0.01]
zi_new = apply_constant_split_to_vector(names, zi, split_factor=0.5)
```

Map a feed's **own** composition (its ZI) onto the universal P/A cores by
nearest molecular weight (paper Section 2.2), so the light/heavy ratio — hence
the GOR — comes from the feed, not from a template:

```python
from pseudocomponent_split import map_source_to_pa_core_totals

m = map_source_to_pa_core_totals(
    source_names=["C1", "CO2", "C7", "C10", "C30"],
    source_fractions=[0.80, 0.02, 0.10, 0.05, 0.03],
    source_molecular_weights=[16.0, 44.0, 96.0, 140.0, 400.0],
    light_names=["N2", "CO2", "C1", "C2", "C3"],
    core_labels=["C7", "C10-14", "C31-50"],
    core_molecular_weights=[96.0, 150.0, 500.0],
)
# m.light_fractions -> light slots; m.core_totals -> heavy-lump Z_i to split by S
```



## Related NeqSim Functionality

For rigorous, design-grade characterization use the NeqSim Java classes in
`neqsim.thermo.characterization`:

- `PlusFractionModel` — gamma molar distribution with `alpha`, `eta`, and a
  Watson `Kw`-based auto-estimate of `alpha` (`estimateAlpha`, `setAlpha`,
  `setEta`, `setGammaParameters`).
- `PlusCharacterize` / `Characterise` — drive the plus-fraction split from
  `SystemInterface` composition and plus-fraction molar mass / density.
- `TBPCharacterize` / `TBPfractionModel` — true-boiling-point pseudocomponents.
- `LumpingModel` + `LumpingConfigBuilder` and `PseudoComponentCombiner` —
  lumping of detailed components into pseudocomponents.
- `Recombine` — recombine separator gas and oil to a reservoir fluid.

In Python these are reachable through the `neqsim` package (for example
`from neqsim import jneqsim`).

## Validation Checklist

- Plus-fraction mole fraction (`z_plus`), molar mass (`m_plus`), `eta`, and the
  molar-mass boundaries are stated with sources.
- The split factor `alpha` is documented, and the resulting pseudocomponent mole
  fractions sum to `z_plus`.
- Per-pseudocomponent average molar masses increase monotonically and the
  mole-fraction-weighted average is close to `m_plus`.
- For delumping, each lump's split factors sum to 1 and a round-trip
  reconstruction reproduces the reference composition.
- Assumptions and limitations are recorded and qualified PVT review is planned.

## Common Mistakes

- Choosing boundaries below `eta`, or a non-increasing boundary list (raises).
- Setting `m_plus` at or below `eta` (the mean must exceed the minimum).
- Treating the screening split as a tuned EOS; it sets a distribution, not
  critical properties.
- Reusing one lump's split factor for a different reference fluid whose internal
  distribution differs.

## Limitations

- The gamma split and split factor are screening-level. They do not tune an EOS,
  set critical properties, or guarantee phase-behavior accuracy.
- Boundaries, `eta`, and `alpha` must be chosen with engineering judgement.
- Results must be reviewed by a qualified PVT engineer before design or
  operational use.

## References

- Uleberg, K. (2026). *Legacy Common-Slate vs. Universal Paraffinic-Aromatic
  Fluid Characterisation in Process Simulation: A Sleipner A Multi-Feed Case
  Study*, Equinor ASA (universal P/A split factor S, Eqs. 3-4, Section 2.2).
- Whitson, C.H., Brulé, M.R. (2000). *Phase Behavior*, SPE Monograph 20.
- Pedersen, K.S., Christensen, P.L., Shaikh, J.A. (2015). *Phase Behavior of
  Petroleum Reservoir Fluids*, 2nd ed.
- NeqSim: https://github.com/equinor/neqsim
