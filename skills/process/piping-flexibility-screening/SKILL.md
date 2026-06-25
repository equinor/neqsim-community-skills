---
name: neqsim-piping-flexibility-screening
version: "0.1.0"
description: "Educational piping-flexibility screening using open ASME B31.3 / B16.5 style relations. USE WHEN: a task needs a public, screening-level check of hoop (sustained) stress, thermal expansion, displacement (expansion) stress range, and a flange-rating pressure check for a process pipe run before detailed pipe-stress analysis."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Piping Flexibility Screening

Use this skill for public, educational piping-flexibility screening. It estimates hoop (sustained) stress, free thermal expansion, displacement (expansion) stress range against a simplified allowable, and a flange-rating pressure check so an agent can scope a pipe-flexibility study before detailed pipe-stress analysis.

## When to Use

- When a user asks whether a hot pipe run needs an expansion loop or whether a flange class is adequate.
- When an agent needs a quick hoop-stress and thermal-expansion estimate for a process line.
- When examples must run without confidential isometrics, stress-analysis models, or company piping specs.

## Inputs

- `outside_diameter_mm`: pipe outside diameter in mm.
- `wall_thickness_mm`: pipe wall thickness in mm.
- `design_pressure_bar`: internal design pressure in bar gauge.
- `design_temperature_c`: design (operating) temperature in degrees Celsius.
- `pipe_length_m`: straight run length in m.
- `install_temperature_c`: installation/ambient temperature in degrees Celsius, default 20.
- `anchor_to_anchor`: whether the run is fully restrained anchor-to-anchor, default True.
- `youngs_modulus_mpa`: Young's modulus in MPa, default 200000.
- `thermal_expansion_coeff_per_k`: mean thermal expansion coefficient per K, default 1.2e-5.
- `allowable_stress_mpa`: material allowable stress in MPa, default 138.
- `flange_rating_class`: optional ASME B16.5 flange class (e.g. 150, 300, 600).
- `flange_allowable_pressure_bar`: optional flange allowable pressure at temperature in bar.

## Outputs

- `hoop_stress_mpa`: Barlow hoop (sustained) stress.
- `hoop_stress_ratio`: hoop stress divided by allowable stress.
- `delta_temperature_k`: design minus install temperature difference.
- `free_thermal_expansion_mm`: unrestrained thermal growth of the run.
- `displacement_stress_mpa`: displacement (expansion) stress estimate.
- `allowable_stress_range_mpa`: simplified allowable stress range.
- `displacement_stress_ratio`: displacement stress divided by the allowable range.
- `flange_pressure_ratio`: design pressure divided by flange allowable pressure, or `null`.
- `stress_warning`: `ok`, `watch`, `hoop-stress-exceeded`, or `expansion-stress-exceeded`.
- `flange_warning`: `ok`, `flange-overpressure`, or `no-rating`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `PipingFlexibilityModel` uses open piping relations only:

- hoop stress uses the thin-wall Barlow relation `S_h = P D / (2 t)`.
- thermal strain uses `epsilon = alpha |T_design - T_install|`.
- free thermal expansion uses `dL = epsilon * L`.
- displacement stress uses the fully restrained worst case `S_E = E alpha dT`, with a fixed relief factor when the run is not anchor-to-anchor.
- the allowable stress range uses a simplified `S_A = 1.5 * S_allow` (screening of `f (1.25 S_c + 0.25 S_h)`).
- the flange check compares design pressure to a supplied flange allowable pressure.

This is educational and screening-only logic. It assumes thin-wall pressure stress, a single straight run, constant material properties, and a fully restrained worst-case expansion stress. It is not a replacement for validated pipe-stress/flexibility analysis or qualified piping-engineering review.

## Python Usage Pattern

```python
from piping_flexibility_screening import PipingFlexibilityModel

model = PipingFlexibilityModel()
result = model.evaluate(
    outside_diameter_mm=168.3,
    wall_thickness_mm=7.11,
    design_pressure_bar=50.0,
    design_temperature_c=180.0,
    pipe_length_m=40.0,
    flange_allowable_pressure_bar=49.6,
)

print(result.hoop_stress_mpa)
print(result.displacement_stress_mpa)
print(result.stress_warning)
print(result.flange_warning)
```

## Related NeqSim Functionality

For validated mechanical-design calculations, redirect to NeqSim classes:

- `neqsim.process.mechanicaldesign.pipeline.PipelineMechanicalDesign` — pipeline wall thickness and mechanical design.
- `neqsim.process.mechanicaldesign.pipeline.PipingFlexibilityCalculator` — proposed pipe-stress/flexibility screening (sustained and displacement stress, flange checks); candidate NeqSim gap.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — hydraulic and thermal pipe model for line conditions.

This skill is a public triage layer that decides when to invoke a validated pipe-stress model.

## Validation Checklist

- [ ] Outside diameter and wall thickness are positive and `t < D/2`.
- [ ] Design pressure, length, and material properties are positive.
- [ ] Tests cover hoop stress, displacement stress, the flange check, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real flexibility analysis is redirected to validated NeqSim classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Displacement stress always high | Anchor-to-anchor worst case used | Route an expansion loop or set `anchor_to_anchor=False` |
| Flange ratio missing | No flange allowable pressure supplied | Provide `flange_allowable_pressure_bar` for the check |
| Hoop stress underestimated | Thin-wall Barlow used on thick wall | Use a validated thick-wall pipe-stress model |

## Limitations

- No proprietary isometrics, stress-analysis models, or company piping specs are included.
- A single straight run is modelled; bends, branches, and supports are not analysed.
- Displacement stress uses a fully restrained worst case; real flexibility depends on routing.

## References

- ASME B31.3, Process Piping.
- ASME B16.5, Pipe Flanges and Flanged Fittings.
- NeqSim repository: https://github.com/equinor/neqsim
