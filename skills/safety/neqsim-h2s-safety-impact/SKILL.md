---
name: neqsim-h2s-safety-impact
calculation_basis: "screening"
version: "0.1.0"
description: "Screening workflow and helpers for the safety impact of H2S in produced gas: partial pressure and sour-service flag per location, toxic reach of the release scenarios, detector equivalence, SO2 from flare and fuel gas, export-gas blending, scavenger demand and vapour over produced water, with an evidence gate. USE WHEN: a tie-in, SURF or process safety study must say what the H2S content (estimated or measured) changes in materials, detection, consequence and gas quality."
last_verified: "2026-11-22"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# H2S Safety Impact

H2S in produced gas is often a trace (1 to 20 ppm) in a gas that is dominated by hydrocarbons and CO2. At that level it rarely changes the flammable consequence, but it can decide sour-service material classes, the detection philosophy, the export-gas specification, the scavenger demand and the exposure at drains, vents and sample points. This skill is the repeatable "what does H2S change" workflow that follows an H2S estimate. It does not estimate H2S itself.

## When to Use

- A safety study or concept design has a screened or measured H2S value and needs its effect on materials, detection, release consequence, flare and fuel gas, export gas and chemicals.
- A previous study assumed "no H2S" and the rev A conclusions must be re-checked with a range.
- Sampling recommendations for the next test are needed to close the main uncertainty.

Not for: estimating H2S (use `neqsim-reservoir-h2s-estimation`), souring time (use `neqsim-reservoir-souring-correlation`), splitting H2S between gas, oil and water (use `neqsim-h2s-phase-partitioning`), plume modelling (use `neqsim-gas-dispersion-distance-screening` or NeqSim `GaussianPlume`), personnel exposure limits as legal compliance.

## Inputs

- H2S in gas as P10/P50/P90 (or a measurement) per year and per location, each with its basis (ppm mole or weight, dry or wet, test separator, wellhead, arrival), temperature and pressure.
- Evidence class: `measured`, `analogue`, `estimate` or `none`.
- Pressure and temperature of every location: reservoir, shut-in tubing head, flowing tree, riser base, arrival, vent and drain.
- Release scenarios from the consequence study: release rate, state, stability and wind, flammable reach (LFL).
- Limits with their source: sour-service partial-pressure threshold, detector alarm points, toxic thresholds, export-gas H2S limit. Pass the value from the document you read; say so in `source`.

## Outputs

- Per location: H2S partial pressure, ratio to the threshold, flag below, borderline or sour, and the H2S ppm that would reach the threshold.
- Toxic distances for named thresholds beside the flammable distance, and the H2S ppm in the gas at which each toxic contour reaches the LFL contour.
- Detector equivalence: H2S in air at the hydrocarbon alarm, and the %LEL at which an H2S alarm would trip.
- SO2 rate from flare and fuel gas; blended export-gas H2S against the limit; removal and scavenger demand; H2S vapour over water.
- `evidence_gate`: status UNVERIFIED_SCREENING unless H2S is measured with sample point and basis, plus the data gaps.

## Engineering Method

1. **Gate the evidence.** Call `evidence_gate`. No measurement means UNVERIFIED_SCREENING and a data gap "measured H2S"; never write "compliant" or "no H2S" for an unmeasured reservoir.
2. **Get H2S per year and location** with the three upstream skills; convert separator-gas ppm to the location basis by the partitioning skill (or by the dilute relation `y_gas = h / (n_gas + n_oil/K_go + n_water/K_gw)` with K from a NeqSim flash). Keep P10/P50/P90 and the souring option (injection water source) as separate cases.
3. **Partial pressure and materials.** `sour_service_screen` per location: reservoir, shut-in tubing head, flowing tree, riser base, arrival. Test the design conditions and a P99 value, not only the normal case. If a document sets a lower trigger (for example sour-grade armour wires in flexible pipe), run the screen again with that threshold and name it.
4. **Release consequence.** Reuse the flammable scenarios unchanged. For each, compute the H2S mass fraction of the released stream and call `toxic_reach` with a plume function. Report the toxic contour beside the LFL contour and the break-even H2S ppm (threshold divided by the LFL fraction).
5. **Detection and exposure.** `detector_equivalence` for the process-area detection philosophy; `vapour_ppm_over_water` and a flash of the oil for drains, tanks, vents and sample points, which are the realistic exposure route at trace levels.
6. **Flare, fuel gas, export and chemicals.** `so2_emission_kg_h`, `export_blend_ppm`, `removal_and_scavenger`.
7. **Thermodynamic checks.** Re-flash one case with the H2S range to show that hydrate temperature, density and depressurisation temperatures do not change (a few hundredths of a kelvin at 50 ppm in tests of a lean gas).
8. **Revision table and sampling plan.** List every earlier result that changes, by how much, and what to sample at the next test.

## Sampling recommendation (what closes the uncertainty)

At the next drill-stem or well test, per flow period: H2S in separator gas by detector tube and by laboratory analysis of an inert-coated cylinder (steel bottles lose H2S), with the GOR, separator pressure and temperature, water cut, and H2S in oil (ppm weight) and water (mg/L) with pH and alkalinity. From downhole samples: H2S, sulphide and mercury analysis in coated containers on the rig. In the water: sulphate, volatile fatty acids, Cl, Mg, Br. Core and cuttings: pyrite and siderite by XRD. For injection water: source, sulphate, treatment, nitrate and biocide plan, temperature at the sand face.

## Validation Checklist

- [ ] Evidence class stated; status UNVERIFIED_SCREENING unless measured at a stated sample point and basis.
- [ ] Every threshold has a named source; standards not read are labelled "convention".
- [ ] P10, P50, P90 and a tail (P99) shown for partial pressure and toxic reach.
- [ ] Toxic reach compared with the flammable reach of the same scenario.
- [ ] Souring source, water treatment and thermal assumptions listed separately.
- [ ] Hand calculations in the tests agree with the helpers.

## Limitations

- Screening only: ground-level passive plume, no jet rise, no wake, no ionisation of H2S in water, no re-oxidation, no kinetics.
- Thresholds are inputs; the library does not contain licensed standard text.
- The Henry constants for water are recalled from the literature and must be verified before design use.

## Python Usage Pattern

```python
from h2s_safety_impact import sour_service_screen, detector_equivalence, export_blend_ppm, evidence_gate

gate = evidence_gate("estimate", {"y_h2s_ppm": 4.7, "basis": "gas at host inlet", "temperature_c": 119.0, "pressure_bara": 13.0})
print(gate["status"], [g["gap"] for g in gate["data_gaps"]])
print(sour_service_screen(4.5, 258.4)["flag"])          # borderline at the shut-in tubing head
print(detector_equivalence(20.0, 0.04)["dedicated_h2s_detection_required"])
print(export_blend_ppm([(1.0e6, 4.7), (2.5e6, 1.0)]))   # ppm in the blended gas
```

Tested in `tests/test_h2s_safety_impact.py`, including a worked example for a generic oil-rim field.

## Common Mistakes

- Treating a low reading as zero: H2S is lost to steel and mud; a non-detect is a detection limit.
- Reading ppm weight as ppm mole: for a gas of molar mass 21 the ratio is 1.6.
- Using normal-case partial pressure for material selection when the design case is the shut-in tubing head.
- Forgetting that the water phase takes up H2S, so gas ppm at low pressure is higher than at the test separator.
- Calling a trace-H2S gas "sweet" without the evidence gate.

## References

- Sander, R. (2015). Compilation of Henry's law constants (version 4.0) for water as solvent. Atmos. Chem. Phys. 15, 4399-4981.
- CCPS (2000). Guidelines for Chemical Process Quantitative Risk Analysis, 2nd ed. (H2S probit).
- Companion skills: `neqsim-reservoir-h2s-estimation`, `neqsim-reservoir-souring-correlation`, `neqsim-h2s-phase-partitioning`, `neqsim-gas-dispersion-distance-screening`, `neqsim-flare-helideck-dispersion`.
