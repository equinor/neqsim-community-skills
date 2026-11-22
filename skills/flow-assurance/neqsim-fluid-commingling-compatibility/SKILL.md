---
name: neqsim-fluid-commingling-compatibility
calculation_basis: "hybrid"
version: "0.3.0"
description: "Blend-sweep screening of two commingled fluids with NeqSim: asphaltene destabilisation (live-oil refractive index, de Boer, blend onset pressure from a solid model calibrated to a measured onset), gas breakout, blend hydrate and wax appearance temperature, calcium naphthenates, separator H2S/CO2. USE WHEN: a tie-in, commingled well or shared flowline mixes a new fluid with a host fluid and the question is whether the mixture behaves worse than either fluid alone, or which blend ratio is worst."
last_verified: "2026-11-22"
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
  kg/mol, density g/cm3[, Tc K, Pc bar, acentric factor])`), and
  `asphaltenic=True` on the fluid that carries the asphaltenes of concern.
- `EvaluationConditions`:
  - `commingling_pressure_bara`, `commingling_temperature_c`: where the
    streams meet.
  - `path_end_pressure_bara` (default 10), `path_points` (default 12): the
    depressurisation path scanned for the refractive-index minimum.
  - `separator_pressure_bara`, `separator_temperature_c`: optional, for
    separator-gas H2S (ppm mol) and CO2 (mol %).
  - `hydrate_pressure_bara`: optional, for the blend hydrate temperature.
  - `wax_pressure_bara`: optional, for the blend wax appearance temperature.
  - `separator_water`: optional `WaterChemistry(calcium_mg_l,
    bicarbonate_mg_l, chloride_mg_l)` of the produced water at the separator;
    gives the separator water pH for the naphthenate screen.
- `FluidSpec.tan_mg_koh_g`: total acid number of each stabilised oil, for the
  naphthenate screen.
- `fractions`: mole fractions of fluid B to evaluate (default 0, 0.1 ... 1).
  Include the operating ratio. Convert mass rates with
  `mole_fraction_from_mass_rates(m_a, M_a, m_b, M_b)`, taking molar masses from
  `NeqSimBlendEvaluator().molar_mass_kg_mol(fluid)`, or molar rates with
  `mole_fraction_from_rates(rate_a, rate_b)`. A light fluid takes a large mole
  fraction for a small mass rate.
- `ScreeningLimits` (all optional): `onset_ri` (measured asphaltene onset
  refractive index of the asphaltenic fluid), `min_operating_temperature_c`
  (hydrate and wax margins), `h2s_limit_ppm`, `co2_limit_mol_pct`, and the
  naphthenate screening thresholds `naphthenate_tan` (0.5 mg KOH/g),
  `naphthenate_ph` (6.0) and `naphthenate_calcium_mg_l` (100).
- `sara`: optional SARA weight fractions of the asphaltenic fluid, used to
  estimate the onset RI when it was not measured.
- `asphaltene_model`: optional `CalibratedAsphalteneModel(fluid,
  MeasuredOnset(temperature_c, pressure_bara, lower_pressure_bara=None),
  kij_exponent=1.0)`. The asphaltenic fluid then needs one pseudo-component
  named `Asphaltene...` with critical properties (for example
  `PseudoComponent("Asphaltene", 0.4, 1.0, 1.15, 1015.0, 15.7, 1.5)`).

## Outputs

`CommingleReport` with:

- `blends`: one `BlendProperties` per fraction: `saturation_pressure_bara`,
  `phases_at_commingling`, `liquid_density_kg_m3`, `gas_volume_fraction`,
  `min_live_oil_ri` and the pressure where it occurs, `de_boer_risk`,
  `hydrate_temperature_c`, `free_water_assumed`, `separator_gas_h2s_ppm`,
  `separator_gas_co2_mol_pct`, `wax_appearance_temperature_c`,
  `separator_water_ph`, `asphaltene_onset_bara` and
  `asphaltene_lower_onset_bara` (with an asphaltene model; `inf` if unstable
  at the top of the scan), `notes`.
- `findings`: `Finding(severity, code, message)` with severity `info`,
  `warning` or `high`. Codes: `asphaltene-onset-crossed`,
  `asphaltene-marginal`, `asphaltene-dilution`, `de-boer-worse-than-host`,
  `free-gas-at-commingling`, `saturation-nonlinear`, `hydrate-blend-maximum`,
  `hydrate-margin`, `wax-margin`, `wax-blend-maximum`, `calcium-naphthenate`,
  `naphthenate-not-assessed`, `h2s-limit`, `co2-limit`,
  `asphaltene-eos-onset-at-commingling`, `asphaltene-eos-onset-raised`,
  `asphaltene-eos-reference-unstable`, `asphaltene-eos-temperature`,
  `asphaltene-eos-model` and informational notes.
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
8. **Wax.** NeqSim `ThermodynamicOperations#calcWAT()` on each water-free
   blend with the TBP wax model (`getWaxModel().addTBPWax()`, SRK, mixing
   rule 2, solid complex phase, temporary database tables). Compared with the
   minimum operating temperature; a maximum inside the blend range is flagged.
9. **Calcium naphthenates.** Blend TAN is the C7+-mass-weighted TAN of the two
   oils. Separator water pH comes from the NORSOK M-506 pH model in NeqSim
   (separator-gas CO2, bicarbonate, chloride ionic strength). A blend is at
   risk when TAN, pH and calcium all exceed the screening thresholds; high when
   TAN exceeds twice the threshold.
10. **Calibrated asphaltene onset (optional).** Nghiem-Coombe solid model:
    the solid asphaltene fugacity is anchored at the measured onset of the
    asphaltenic fluid, `ln f_s = ln f_L(T*, P*) + v_s (P - P*) / RT`, with
    `v_s` from the asphaltene molar mass and density, or fitted to a measured
    lower onset. The asphaltene interaction parameters follow a
    size-asymmetry correlation on the co-volume (`b ~ Tc/Pc`), large for
    N2/CO2/C1 and about 0 for heavy cuts. Each blend's upper and lower onset
    is found by scanning down from above the commingling pressure and
    bisecting. Uses NeqSim's `AsphalteneSolidModel` when the installed NeqSim
    has it, otherwise a Python implementation of the same equations on NeqSim
    SRK flashes (identical results; `model.backend` tells which). High when a
    blend's onset reaches the commingling pressure, warning when blending
    raises the onset by more than 10 bar.

## Python Usage Pattern

```python
from fluid_commingling_compatibility import (
    EvaluationConditions, FluidSpec, NeqSimBlendEvaluator, PseudoComponent,
    ScreeningLimits, mole_fraction_from_mass_rates, screen_commingling,
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
evaluator = NeqSimBlendEvaluator()
x_op = mole_fraction_from_mass_rates(                 # 150 t/h oil + 25 t/h condensate
    150_000.0, evaluator.molar_mass_kg_mol(host),
    25_000.0, evaluator.molar_mass_kg_mol(tiein),
)
report = screen_commingling(
    host, tiein, conditions, evaluator,
    fractions=(0.1, 0.2, 0.3, round(x_op, 2), 0.7),
    limits=ScreeningLimits(onset_ri=1.445, h2s_limit_ppm=400.0),
)
print(report.to_markdown())
```

A complete synthetic case is in `examples/heavy_oil_condensate_tie_in.py`.
Eight blends take about 15 s.

## Validation Checklist

- [ ] Component names are NeqSim names; pseudo-component molar masses are in
      kg/mol and densities in g/cm3.
- [ ] The blend basis is molar. Rates were converted to mole fractions and the
      operating ratio is in the sweep.
- [ ] The asphaltenic fluid is marked, and an onset RI is measured or its
      source (SARA correlation) is stated in the report.
- [ ] The minimum RI pressure is near the bubble point for single-phase
      blends; if not, increase `path_points`.
- [ ] Hydrate results with `free_water_assumed` are labelled as such.
- [ ] `evaluation-note` findings (failed flashes) are reviewed.
- [ ] Flagged blends are confirmed with an onset titration or HPM test on the
      blend before decisions are made.
- [ ] Wax results use the same characterisation as the PVT report; WAT is
      compared with the coldest point of the line, not the arrival temperature.
- [ ] Naphthenate screening thresholds are replaced with operator experience
      where it exists; TAN values are for the stabilised oils.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every blend, including the host alone, is highly unstable | SARA-estimated onset RI compared with a light live oil | Use a measured onset RI, or rely on the relative indicator |
| de Boer says no problem while RI flags the blend | de Boer is a reservoir-depletion correlation; dilution raises the bubble point and shrinks undersaturation | Use the RI result for dilution; read de Boer as secondary |
| Hydrate temperature too high for a dry gas | Free water was assumed | Give the real water content or treat the value as a water-saturated bound |
| Pseudo-component error on construction | Molar mass given in g/mol | Divide by 1000 |
| Saturation linearity missing | One end member is a gas (dew point) | Expected; the comparison only applies to two liquids |
| Operating point looks "safe" on the sweep | Blend axis read as mass or volume fraction | Convert with `mole_fraction_from_mass_rates`; light fluids take a large mole fraction |

## Limitations

- Screening only. The refractive-index route is a published correlation of
  solvent power, not an asphaltene precipitation model; it does not predict
  the amount deposited.
- The cubic equation of state is not tuned to the fluids unless the supplied
  compositions come from a tuned characterisation.
- Water-water scale is not assessed here (see the related skills). Wax is
  the appearance temperature only, not a deposition rate.
- The naphthenate screen uses fixed thresholds on TAN, pH and calcium; it
  does not model naphthenic acid partitioning or soap formation.
- The calibrated onset model needs a measured onset of the asphaltenic
  fluid; the asphaltene properties (molar mass, density, Tc, Pc, acentric
  factor) and the interaction exponent are assumptions unless fitted. Without
  a temperature term the onset is extrapolated from the test temperature.
  Do not calibrate NeqSim's database asphaltene by its interaction parameters
  alone (the route tried before 0.3.0): it needs negative values that make
  light components good asphaltene solvents, and then predicts that
  condensate lowers the onset, the wrong sign. The solid model anchors the
  solid fugacity instead and predicts that light diluents raise the onset.
  Confirm flagged blends with onset tests on the actual blends.
- Public, synthetic examples only. Not a substitute for laboratory
  compatibility testing or engineering judgement.

## Related NeqSim Functionality

- `neqsim.pvtsimulation.flowassurance.AsphalteneSolidModel` (NeqSim after
  3.29.0): calibrated solid asphaltene model used by `CalibratedAsphalteneModel`.
- `neqsim.thermo.system.SystemSrkEos`, `SystemPrEos`, `SystemSrkCPAstatoil`
  with `addTBPfraction`, `useVolumeCorrection`.
- `neqsim.thermodynamicoperations.ThermodynamicOperations#TPflash()`,
  `#bubblePointPressureFlash(boolean)`, `#hydrateFormationTemperature()`.
- `ThermodynamicOperations#calcWAT()` with `getWaxModel().addTBPWax()` and
  `addSolidComplexPhase("wax")` (blend wax appearance temperature).
- `neqsim.process.corrosion.NorsokM506CorrosionRate#calculateEquilibriumPH()`
  (separator water pH).
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
- Vindstad, J.E. et al. (2003). Fighting naphthenate deposition at the Heidrun
  field. SPE 80375 (calcium naphthenate field experience and pH dependence).
- Brandal, O. (2005). Interfacial (o/w) properties of naphthenic acids and
  metal naphthenates. PhD thesis, NTNU.
- NeqSim repository: https://github.com/equinor/neqsim
