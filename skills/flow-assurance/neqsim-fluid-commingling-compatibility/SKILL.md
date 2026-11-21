---
name: neqsim-fluid-commingling-compatibility
calculation_basis: "hybrid"
version: "0.1.0"
description: "Blend-sweep screening of two commingled fluids with NeqSim: asphaltene destabilisation by dilution (live-oil refractive index, onset margin, de Boer), gas breakout on mixing, blend hydrate temperature, separator H2S/CO2. USE WHEN: a tie-in, commingled well or shared flowline mixes a new fluid with a host fluid and the question is whether the mixture behaves worse than either fluid alone, or which blend ratio is worst."
last_verified: "2026-11-21"
requires:
  python_packages: [neqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# Fluid Commingling Compatibility

Tie-in screening usually checks the new fluid on its own. Several flow-assurance
problems appear only in the mixture: a gas condensate diluting an asphaltenic
oil lowers its solvent power, two single-phase streams can release gas when
they meet, and the hydrate curve of the blend can sit above both end members.
This skill blends the two fluids on a molar basis over a grid of ratios, runs
each blend through NeqSim, and reports which ratio is worst for each check.

The thermodynamics come from NeqSim (equation-of-state flashes, bubble point,
hydrate equilibrium, Peneloux-corrected liquid density). The interpretation
is screening-level: published correlations and classes rank the blends and
point at the laboratory test or detailed model that should confirm a concern.

## When to Use

- A new well or field is tied into a host and its fluid mixes with the host or
  existing production upstream of the separator.
- Two reservoirs are produced through one well, manifold or flowline.
- An asphaltenic oil will receive gas, condensate or gas-lift gas.
- The task asks which blend ratio is worst, or whether end-member PVT can be
  interpolated for the mixture.

Do not use it for water-water scale mixing; use
`neqsim-produced-water-scale-screening` for that.

## Inputs

- `FluidSpec`: `label` (alphanumeric), `components` keyed by NeqSim component
  names on any consistent molar basis (mol %, mole fraction, kmol/h),
  optional `pseudo_components` (`PseudoComponent(name, amount, molar mass
  kg/mol, density g/cm3)`), and `asphaltenic=True` on the fluid that carries
  the asphaltenes of concern.
- `EvaluationConditions`:
  - `commingling_pressure_bara`, `commingling_temperature_c`: where the
    streams meet.
  - `path_end_pressure_bara` (default 10), `path_points` (default 12): the
    depressurisation path scanned for the refractive-index minimum.
  - `separator_pressure_bara`, `separator_temperature_c`: optional, for
    separator-gas H2S (ppm mol) and CO2 (mol %).
  - `hydrate_pressure_bara`: optional, for the blend hydrate temperature.
- `fractions`: mole fractions of fluid B to evaluate (default 0, 0.1 ... 1).
  Use `mole_fraction_from_rates(rate_a, rate_b)` to convert molar rates.
- `ScreeningLimits` (all optional): `onset_ri` (measured asphaltene onset
  refractive index of the asphaltenic fluid), `min_operating_temperature_c`,
  `h2s_limit_ppm`, `co2_limit_mol_pct`.
- `sara`: optional SARA weight fractions of the asphaltenic fluid, used to
  estimate the onset RI when it was not measured.

## Outputs

`CommingleReport` with:

- `blends`: one `BlendProperties` per fraction: `saturation_pressure_bara`,
  `phases_at_commingling`, `liquid_density_kg_m3`, `gas_volume_fraction`,
  `min_live_oil_ri` and the pressure where it occurs, `de_boer_risk`,
  `hydrate_temperature_c`, `free_water_assumed`, `separator_gas_h2s_ppm`,
  `separator_gas_co2_mol_pct`, `notes`.
- `findings`: `Finding(severity, code, message)` with severity `info`,
  `warning` or `high`. Codes: `asphaltene-onset-crossed`,
  `asphaltene-marginal`, `asphaltene-dilution`, `de-boer-worse-than-host`,
  `free-gas-at-commingling`, `saturation-nonlinear`, `hydrate-blend-maximum`,
  `hydrate-margin`, `h2s-limit`, `co2-limit` and informational notes.
- `worst_cases`: the worst blend per check.
- `to_markdown()` and `to_dict()` (JSON-safe, `calculation_basis: screening`).

## Engineering Method

1. **Blending.** Defined components are summed on a molar basis; each fluid's
   pseudo-components stay separate (`C10host`, `C10tiein`).
2. **Equation of state.** SRK with classic mixing and Peneloux volume
   correction; SRK-CPA (Statoil, mixing rule 10) when water is present.
   Asphaltene, density and saturation checks use the water-free blend.
3. **Asphaltene stability.** The refractive index of the live oil is computed
   from its NeqSim density with the Lorentz-Lorenz correlation of Buckley et
   al. (1998). Live-oil density, and so the index, is lowest just above the
   bubble point, so the path is scanned and the bubble point is sampled
   explicitly. With an onset RI (P_RI) the margin `RI - P_RI` is classed
   (> 0.03 very stable, > 0.02 stable, > 0.01 marginal, > 0 unstable, else
   highly unstable). Without it, the drop in minimum RI relative to the
   asphaltenic fluid alone is reported as a relative indicator. The de Boer
   class at the commingling point is reported alongside.
4. **Free gas.** A gas phase at commingling conditions is flagged, and raised
   to a warning when neither fluid alone has one.
5. **Saturation linearity.** When both end members are liquid, the blend
   bubble point is compared with linear interpolation.
6. **Hydrate.** NeqSim hydrate equilibrium temperature of each blend at the
   given pressure (free water added to dry blends and flagged). A maximum
   inside the blend range is flagged.
7. **Sour gas.** Separator-gas H2S and CO2 of each blend against the limits.

## Python Usage Pattern

```python
from fluid_commingling_compatibility import (
    EvaluationConditions, FluidSpec, NeqSimBlendEvaluator, PseudoComponent,
    ScreeningLimits, screen_commingling,
)

host = FluidSpec(
    "host",
    {"methane": 18.0, "ethane": 6.0, "propane": 5.0, "CO2": 1.0},
    [PseudoComponent("C10", 20.0, 0.14, 0.80), PseudoComponent("C30", 20.0, 0.45, 0.93)],
    asphaltenic=True,
)
tiein = FluidSpec("tiein", {"methane": 80.0, "ethane": 8.0, "CO2": 2.5},
                  [PseudoComponent("C7", 4.0, 0.098, 0.74)])
conditions = EvaluationConditions(
    commingling_pressure_bara=200.0, commingling_temperature_c=80.0,
    separator_pressure_bara=40.0, separator_temperature_c=60.0,
    hydrate_pressure_bara=120.0,
)
report = screen_commingling(
    host, tiein, conditions, NeqSimBlendEvaluator(),
    limits=ScreeningLimits(onset_ri=1.445, h2s_limit_ppm=400.0),
)
print(report.to_markdown())
```

A complete synthetic case is in `examples/heavy_oil_condensate_tie_in.py`.
Eight blends take about 15 s.

## Validation Checklist

- [ ] Component names are NeqSim names; pseudo-component molar masses are in
      kg/mol and densities in g/cm3.
- [ ] The blend basis is molar. Rates in Sm3/d were converted to molar rates.
- [ ] The asphaltenic fluid is marked, and an onset RI is measured or its
      source (SARA correlation) is stated in the report.
- [ ] The minimum RI pressure is near the bubble point for single-phase
      blends; if not, increase `path_points`.
- [ ] Hydrate results with `free_water_assumed` are labelled as such.
- [ ] `evaluation-note` findings (failed flashes) are reviewed.
- [ ] Flagged blends are confirmed with an onset titration, HPM test or a
      tuned asphaltene model before decisions are made.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every blend, including the host alone, is highly unstable | SARA-estimated onset RI compared with a light live oil | Use a measured onset RI, or rely on the relative indicator |
| de Boer says no problem while RI flags the blend | de Boer is a reservoir-depletion correlation; dilution raises the bubble point and shrinks undersaturation | Use the RI result for dilution; read de Boer as secondary |
| Hydrate temperature too high for a dry gas | Free water was assumed | Give the real water content or treat the value as a water-saturated bound |
| Pseudo-component error on construction | Molar mass given in g/mol | Divide by 1000 |
| Saturation linearity missing | One end member is a gas (dew point) | Expected; the comparison only applies to two liquids |

## Limitations

- Screening only. The refractive-index route is a published correlation of
  solvent power, not an asphaltene precipitation model; it does not predict
  the amount deposited.
- The cubic equation of state is not tuned to the fluids unless the supplied
  compositions come from a tuned characterisation.
- Wax and water-water scale are not assessed here (see the related skills).
- Public, synthetic examples only. Not a substitute for laboratory
  compatibility testing or engineering judgement.

## Related NeqSim Functionality

- `neqsim.thermo.system.SystemSrkEos`, `SystemPrEos`, `SystemSrkCPAstatoil`
  with `addTBPfraction`, `useVolumeCorrection`.
- `neqsim.thermodynamicoperations.ThermodynamicOperations#TPflash()`,
  `#bubblePointPressureFlash(boolean)`, `#hydrateFormationTemperature()`.
- `neqsim.pvtsimulation.flowassurance.DeBoerAsphalteneScreening` (called) and
  `RefractiveIndexAsphalteneScreening` (same RI correlation and classes).
- For design-grade asphaltene work on a characterised fluid:
  `ThermodynamicOperations#asphalteneOnsetPressure()`,
  `neqsim.pvtsimulation.flowassurance.AsphalteneStabilityAnalyzer` and
  `neqsim.thermo.characterization.AsphalteneCharacterization`.
- Reached from Python with `from neqsim import jneqsim`.
- Related community skills: `neqsim-produced-water-scale-screening`,
  `neqsim-hydrate-screening`, `neqsim-wax-margin-check`,
  `neqsim-active-learning-surrogate` (to sweep many blend and operating cases).

## References

- Buckley, J.S., Hirasaki, G.J., Liu, Y., Von Drasek, S., Wang, J.X., Gill,
  B.S. (1998). Asphaltene precipitation and solvent properties of crude oils.
  Petroleum Science and Technology 16(3-4), 251-285.
- de Boer, R.B., Leerlooyer, K., Eigner, M.R.P., van Bergen, A.R.D. (1995).
  Screening of crude oils for asphalt precipitation: theory, practice, and the
  selection of inhibitors. SPE Production & Facilities 10(1), 55-61.
- NeqSim repository: https://github.com/equinor/neqsim
