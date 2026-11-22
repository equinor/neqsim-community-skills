---
name: neqsim-co2-corrosion-profile
calculation_basis: "hybrid"
version: "0.1.0"
description: "CO2 corrosion rates along a flowline with NeqSim: profile from the Beggs-Brill pipe model or your own, free water and gas CO2/H2S from a CPA flash, M-506 pH, NORSOK M-506 Rev. 2 rate, inhibitor availability, wall loss vs allowance; dense-phase CO2 lines via DensePhaseCO2Corrosion; worst points through MaterialsReviewEngine and NORSOK M-001. USE WHEN: screening internal corrosion, corrosion allowance or carbon steel vs CRA for a flowline, tie-in or CO2 line."
last_verified: "2026-11-22"
requires:
  python_packages: [neqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# CO2 Corrosion Profile

Internal CO2 corrosion depends on where free water exists, the CO2 fugacity,
the in-situ pH, temperature and wall shear, and all of these change along a
flowline as it cools and loses pressure. A single-point M-506 calculation at
the inlet misses where the line actually corrodes fastest. This skill runs the
assessment station by station along a NeqSim pipeline profile (or one you
supply), turns rates into wall loss over the design life against the corrosion
allowance, and sends the inlet, outlet and worst station through NeqSim's
materials review.

## When to Use

- Corrosion allowance or carbon steel versus corrosion-resistant alloy for a
  new flowline, tie-in or export line.
- An existing carbon-steel line will receive a tie-in with more CO2, water or
  chloride: does the allowance still hold?
- Inhibitor availability needed to keep carbon steel within its allowance.
- CCS or CO2-injection lines: free-water and impurity risk in dense-phase CO2.

## Inputs

- `CorrosionFluid`: `components` (NeqSim names, any molar basis, must include
  `water`; add `CO2`, `H2S`), optional `pseudo_components`
  (`PseudoCut(name, amount, kg/mol, g/cm3)`), `chloride_mg_l` and
  `bicarbonate_mg_l` of the produced water (0 for condensed water), and for CO2
  lines `dense_phase_impurities_ppmv` (`O2`, `SO2`, `NOx`).
- Profile, either:
  - `neqsim_pipeline_profile(fluid, PipelineSpec(...))`: `length_m`,
    `inner_diameter_m`, `mass_flow_kg_h`, `inlet_pressure_bara`,
    `inlet_temperature_c`, `segments`, `elevation_change_m`, `roughness_m`,
    and optionally `ambient_temperature_c` with `overall_u_w_m2k`; or
  - a list of `ProfilePoint(distance_m, pressure_bara, temperature_c, ...)`
    with mixture velocity, density and viscosity, or `wall_shear_pa`.
- `DesignBasis`: `design_life_years` (25), `corrosion_allowance_mm` (3),
  `inhibitor_availability` (0-1, default 0), `inhibited_rate_mm_y` (0.1),
  `inner_diameter_m`, `roughness_m`, `default_wall_shear_pa`,
  `existing_material`.
- `chemistry`: `NeqSimChemistry()` (default) or `NeqSimChemistry(ph=5.6)` to
  fix a measured pH.

## Outputs

`CorrosionProfileReport` with:

- `stations`: per station `free_water`, `in_situ_ph`, `ph_source`, gas
  `CO2`/`H2S` mole fractions, `co2_fugacity_bar`, `wall_shear_pa`,
  `bare_rate_mm_y`, `design_rate_mm_y`, `wall_loss_mm`, `flags` (range
  clamps, no water, upper-bound rates), and `dense_phase` (NeqSim output) for
  CO2 lines.
- `summary`: maximum design rate and where, maximum wall loss, allowance
  needed, wet share of the line.
- `findings` (`info`/`warning`/`high`): `allowance-exceeded`,
  `allowance-margin`, `water-dropout`, `dry-line`, `outside-correlation`,
  `low-fugacity`, `sour-service`, `dense-phase-free-water`,
  `dense-phase-impurities`, `dense-phase-summary`, `materials-review-fail`.
- `m001_recommendation`: NORSOK M-001 material and allowance from the Rev. 2
  design rate at the worst station.
- `materials_review`: the NeqSim `MaterialsReviewEngine` report for the inlet,
  outlet and worst station.
- `rate_engine`, `mode`, `to_markdown()`, `to_dict()`.

## Engineering Method

1. **Profile.** NeqSim `PipeBeggsAndBrills` gives pressure, temperature,
   mixture velocity, density and viscosity per increment (SRK-CPA fluid), or
   the user supplies the stations.
2. **Water and acid gas.** At each station an SRK-CPA (Statoil) flash gives
   the phases; the aqueous phase is the liquid with more than 50 mol % water.
   Gas CO2/H2S come from the gas phase; with no gas phase the CO2 fugacity is
   taken from the equation of state.
3. **pH.** NORSOK M-506 pH model in NeqSim
   `NorsokM506CorrosionRate#calculateEquilibriumPH`: CO2 partial pressure,
   bicarbonate charge balance, ionic strength from chloride. Or a fixed pH.
4. **Wall shear.** `tau = f_D/8 rho v^2` with the Haaland friction factor on
   mixture properties, unless shear is supplied.
5. **Rate.** NORSOK M-506 Rev. 2 (2005) section 8.1 fugacity and section 5.2
   bare-steel rate from NeqSim `NorsokM506Rev2` when installed, otherwise a
   reference port tested against that class to 1e-12. Inputs outside the
   validity ranges (5-150 C, 0.1-10 bar, pH 3.5-6.5, 1-150 Pa) are moved to the
   nearest bound and flagged; below 0.1 bar the rate is an upper bound.
6. **Design rate and wall loss.**
   `CR = A min(CR_inh, CR_bare) + (1 - A) CR_bare`; wall loss =
   `CR x design life`, compared with the allowance.
7. **Dense-phase CO2.** When dry CO2 exceeds 50 mol %, NeqSim
   `DensePhaseCO2Corrosion` replaces M-506 at each station: phase state, water
   solubility margin, impurity checks, wet corrosion rate.
8. **Materials.** NeqSim `MaterialsReviewEngine` (NORSOK M-001 selection, CO2
   corrosion with its own legacy de Waard-Milliams rate, sour service, chloride
   SCC, dense CO2, hydrogen, oxygen and more) on the inlet, outlet and worst
   station; plus `NorsokM001MaterialSelection` driven by the Rev. 2 rate.

## Python Usage Pattern

```python
from co2_corrosion_profile import (
    CorrosionFluid, DesignBasis, PipelineSpec, assess_corrosion_profile,
    neqsim_pipeline_profile,
)

fluid = CorrosionFluid(
    {"methane": 82.0, "ethane": 6.0, "propane": 3.0, "CO2": 3.0, "H2S": 0.0005,
     "water": 2.0},
    chloride_mg_l=20000.0,
)
pipe = PipelineSpec(
    length_m=12000.0, inner_diameter_m=0.254, mass_flow_kg_h=90000.0,
    inlet_pressure_bara=110.0, inlet_temperature_c=85.0, segments=12,
    ambient_temperature_c=4.0, overall_u_w_m2k=15.0,
)
report = assess_corrosion_profile(
    fluid,
    neqsim_pipeline_profile(fluid, pipe),
    DesignBasis(design_life_years=25, corrosion_allowance_mm=6.0,
                inhibitor_availability=0.9, inner_diameter_m=0.254),
)
print(report.to_markdown())
```

`examples/wet_gas_flowline.py` runs a 12 km line in about 6 s.

## Validation Checklist

- [ ] The composition includes water; chloride and bicarbonate match the water
      at the station (condensed water: both 0).
- [ ] `rate_engine` is reported (Java class or reference port).
- [ ] Stations with range flags were reviewed; upper-bound rates are labelled.
- [ ] Inhibitor availability and inhibited rate are stated as design
      assumptions with their source.
- [ ] Wall shear comes from the profile or a stated default, not a guess.
- [ ] Sour-service warnings were passed to an ISO 15156 review.
- [ ] The materials review's legacy CO2 rate is not mixed up with the Rev. 2
      design rate.
- [ ] For CO2 lines, the dense-phase result is treated as screening, not
      DNV-RP-F104 evidence.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `add water to the composition` | Dry composition given | Add the water content; the flash decides where it drops out |
| Very high rates everywhere | Condensed-water pH with high CO2 fugacity | Correct for condensed water; check whether bicarbonate (formation water) applies |
| Many `pH below range` flags | Saline condensed water drives pH under 3.5 | Expected; the rate uses pH 3.5 and is flagged |
| `default_wall_shear_pa` error | Own profile without flow data | Give velocity, density, viscosity or `wall_shear_pa` per station |
| Engine says chloride SCC fails for carbon steel | `MaterialsReviewEngine` runs the chloride SCC check whenever chloride is given | Read it as a check for the CRA option, not for carbon steel |
| Engine CO2 rate differs from the station table | Engine uses NeqSim's legacy de Waard-Milliams model | Use the Rev. 2 design rate for the allowance |

## Limitations

- NORSOK M-506 Rev. 2 covers sweet CO2 corrosion of carbon steel in water-wet
  conditions; it does not cover H2S-dominated corrosion, top-of-line
  corrosion, under-deposit or microbial corrosion, or erosion.
- Free water is from an equilibrium flash; water accumulation at low points,
  stratified flow and condensation rates are not modelled.
- Wall shear uses homogeneous mixture properties.
- Inhibitor availability and inhibited rate are user assumptions.
- `DensePhaseCO2Corrosion` is a screening heuristic with illustrative
  impurity limits.
- Screening only: not a corrosion design basis, a materials selection report
  or a substitute for qualified corrosion and materials engineering.

## Related NeqSim Functionality

- `neqsim.process.corrosion.NorsokM506Rev2` (`fugacityBar`, `rateMmPerYear`;
  NeqSim after 3.29.0).
- `neqsim.process.corrosion.NorsokM506CorrosionRate#calculateEquilibriumPH()`.
- `neqsim.process.corrosion.DensePhaseCO2Corrosion`.
- `neqsim.process.materials.MaterialsReviewEngine` with
  `MaterialsReviewInput.fromJson(...)`.
- `neqsim.process.corrosion.NorsokM001MaterialSelection`.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` segment getters.
- `neqsim.thermo.system.SystemSrkCPAstatoil` with
  `ThermodynamicOperations#TPflash()`.
- Not used by default: `NorsokM506ElectrolyteBridge` (electrolyte CPA pH). In
  testing on NeqSim 3.29.0 it was slow with salinity and misassigned the water
  phase at low temperature.
- Related community skills: `neqsim-fluid-commingling-compatibility` (what the
  mixed stream contains), `neqsim-active-learning-surrogate` (allowance or
  inhibitor availability over uncertain conditions).

## References

- NORSOK M-506 Rev. 2 (2005). CO2 corrosion rate calculation model.
- NORSOK M-001 (Materials selection).
- Haaland, S.E. (1983). Simple and explicit formulas for the friction factor in
  turbulent pipe flow. J. Fluids Eng. 105(1), 89-90.
- NeqSim repository: https://github.com/equinor/neqsim
