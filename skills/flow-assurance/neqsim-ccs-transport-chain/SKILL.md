---
name: neqsim-ccs-transport-chain
calculation_basis: "hybrid"
version: "0.1.0"
description: "CO2 transport chain screening for CCS with NeqSim: pipeline profile, single-phase margin to the two-phase boundary at every station, water solubility margin, impurity specification (DensePhaseCO2Corrosion), depressurisation temperature and dry ice, and the injection well (CO2InjectionWellAnalyzer) against reservoir and fracture pressure. USE WHEN: screening a CO2 pipeline-to-injector chain, its CO2 specification, operating pressure or blowdown."
last_verified: "2026-11-22"
requires:
  python_packages: [neqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# CCS Transport Chain

A CO2 transport system fails at its weakest link. The stream can drop into
two-phase flow somewhere along a cooling pipeline, free water can form where
solubility is lowest, a blowdown can freeze, or the dense CO2 column can push
the bottom-hole pressure past fracture. This skill follows one CO2 stream from
the pipeline inlet to the reservoir. It checks each link with NeqSim and
reports the binding one.

## When to Use

- Screening a CO2 pipeline and injection well for a capture project.
- Setting or checking a CO2 specification (light impurities, water).
- Choosing pipeline operating pressure and arrival pressure.
- Depressurisation and vent design: minimum temperature and dry ice.

## Inputs

- `Co2Stream(components, so2_ppmv=0, nox_ppmv=0)`: mole amounts with NeqSim
  names (`CO2`, `nitrogen`, `argon`, `hydrogen`, `oxygen`, `methane`, `H2S`,
  `CO`, `water`); at least 80 mol % CO2. `water` is the dissolved water
  delivered by dehydration.
- `Co2Pipeline(length_m, inner_diameter_m, mass_flow_kg_h,
  inlet_pressure_bara, inlet_temperature_c, ambient_temperature_c=4,
  overall_u_w_m2k=5, elevation_change_m=0, roughness_m, segments=20)`.
- `InjectionWell(depth_m, tubing_inner_diameter_m, reservoir_pressure_bara,
  top_formation_temperature_c, bottom_formation_temperature_c,
  fracture_pressure_bara=None)`: optional.
- `ChainLimits(min_single_phase_margin_bar=10, water_margin_factor=2,
  min_design_temperature_c=-46, maop_bara=None)`: user-stated limits.
- `stations`: optional own pressure-temperature profile (`Station` list).

## Outputs

`ChainReport` with:

- `stations`: per station pressure, temperature, phase count, density,
  two-phase boundary pressure, single-phase margin, water solubility and its
  ratio to the water content.
- `depressurisation`: isenthalpic and isentropic final temperature at
  atmospheric pressure from the highest-pressure and coldest stations.
- `impurities`: NeqSim `DensePhaseCO2Corrosion` result at the coldest
  station (phase state, water limit, impurity issues, risk level).
- `well`: bottom-hole pressure and temperature, injectivity and fracture
  margins, and the full `CO2InjectionWellAnalyzer` result.
- `summary`, `findings` (`two-phase-flow`, `single-phase-margin`,
  `free-water`, `water-margin`, `impurity-specification`, `dry-ice`,
  `below-design-temperature`, `above-maop`, `no-injectivity`,
  `above-fracture-pressure`, `well-analyzer`), `to_markdown()`, `to_dict()`.

## Engineering Method

1. **Pipeline.** NeqSim `PipeBeggsAndBrills` with Peng-Robinson, heat
   transfer to the ambient through an overall U value.
2. **Two-phase boundary.** At each station temperature, TP flashes scan
   down from above the operating pressure; the first two-phase pressure is
   refined by bisection to 0.1 bar. This is the bubble pressure below the
   mixture critical temperature, and the upper retrograde boundary above it.
   No boundary means the stream stays single-phase at that temperature. A
   full envelope trace is not used: on NeqSim 3.29.0 it failed for
   hydrogen-bearing CO2.
3. **Water.** SRK-CPA (Statoil) flash with 5 mol % added water; the water
   fraction of the CO2-rich phase is the solubility. The margin factor is
   solubility divided by water content.
4. **Impurities.** NeqSim `DensePhaseCO2Corrosion` at the coldest station.
5. **Depressurisation.** PH (valve) and PS (vessel blowdown) flashes to
   1.013 bara. Below -56.6 C the CO2 passes its triple point and dry ice
   forms; Peng-Robinson has no solid phase, so the real temperature stays
   near the triple point while solid forms.
6. **Well.** NeqSim `CO2InjectionWellAnalyzer` (wellbore Beggs and Brill,
   phase boundary scan, impurity enrichment, shutdown and choke checks) from
   the pipeline arrival conditions and mass flow.

## Python Usage Pattern

```python
from ccs_transport_chain import (
    ChainLimits, Co2Pipeline, Co2Stream, InjectionWell, assess_transport_chain,
)

stream = Co2Stream({"CO2": 0.955, "nitrogen": 0.02, "argon": 0.005,
                    "hydrogen": 0.005, "methane": 0.015, "water": 0.00005})
pipe = Co2Pipeline(length_m=80000.0, inner_diameter_m=0.38,
                   mass_flow_kg_h=200000.0, inlet_pressure_bara=150.0,
                   inlet_temperature_c=35.0, segments=10)
well = InjectionWell(depth_m=1300.0, tubing_inner_diameter_m=0.157,
                     reservoir_pressure_bara=120.0, fracture_pressure_bara=210.0)
report = assess_transport_chain(stream, pipe, well, ChainLimits(maop_bara=180.0))
print(report.to_markdown())
```

`examples/ccs_pipeline_to_injector.py` runs the full chain in about 20 s.

## Validation Checklist

- [ ] Composition is on a molar basis with NeqSim names; water is the
      delivered, dissolved water.
- [ ] The lowest single-phase margin and its location are reported.
- [ ] The water margin factor at the coldest, lowest-pressure station meets
      the project basis.
- [ ] Depressurisation results are read with the dry-ice caveat.
- [ ] Bottom-hole pressure was compared with reservoir and fracture pressure
      for the full arrival-pressure range, not one point.
- [ ] For design, the composition-specific phase boundary is verified
      against measured data or a reference EoS (e.g. GERG-2008).

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| "this chain is for CO2-rich streams" | Less than 80 mol % CO2 | Use gas pipeline tools for CO2-rich natural gas |
| Two-phase flow at the outlet | Light impurities raise the bubble pressure | Higher operating pressure or tighter N2/H2/Ar/CH4 limits |
| Bottom-hole pressure above fracture | Dense CO2 column adds roughly 100 bar per 1000 m | Choke at the wellhead (check JT cooling) or operate the line lower |
| Depressurisation at -90 C | Peng-Robinson has no solid CO2 | Read it as dry-ice formation near -56.6 C |
| Slow run | Many stations; each needs a flash scan | Fewer `segments` for screening |

## Limitations

- Peng-Robinson with default interaction parameters; impure-CO2 phase
  boundaries can be off by several bar. Verify for design (DNV-RP-F104).
- Free water is from equilibrium only; hydrates and acid formation from
  SO2/NOx/O2 reactions are not modelled. `DensePhaseCO2Corrosion` is a
  screening heuristic, not DNV-RP-F104 conformity evidence.
- Depressurisation is an end-state calculation, not a transient blowdown.
- No running-ductile-fracture or dispersion assessment.
- Screening only; it does not replace a CO2 pipeline design basis, safety
  studies or engineering judgement.

## Related NeqSim Functionality

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills`.
- `neqsim.process.equipment.pipeline.CO2InjectionWellAnalyzer`.
- `neqsim.process.corrosion.DensePhaseCO2Corrosion`.
- `ThermodynamicOperations#TPflash()`, `#PHflash(double)`, `#PSflash(double)`,
  `#bubblePointPressureFlash(boolean)`.
- `DnvRpF104Co2PipelineEnvelopeScreeningKernel` (core NeqSim) for the
  DNV-RP-F104 envelope with project-verified inputs; see the core skill
  `neqsim-ccs-hydrogen`.
- Related community skills: `neqsim-co2-corrosion-profile` (dense-phase mode),
  `neqsim-active-learning-surrogate` (operating window over uncertain
  impurities and pressures).

## References

- DNV-RP-F104 (2021). Design and operation of carbon dioxide pipelines.
- ISO 27913:2016. Carbon dioxide capture, transportation and geological
  storage - Pipeline transportation systems.
- NeqSim repository: https://github.com/equinor/neqsim
