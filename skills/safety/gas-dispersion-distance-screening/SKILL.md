---
name: neqsim-gas-dispersion-distance-screening
version: "0.1.0"
description: "Educational Gaussian point-source gas-dispersion screening that estimates the downwind distance to a target concentration (LFL or toxic ppm) using the public Pasquill-Gifford / Briggs rural model. USE WHEN: a task needs a public, screening-level distance-to-LFL or distance-to-ppm estimate for a continuous gas release before detailed dispersion or consequence analysis."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Gas Dispersion Distance Screening

Use this skill for public, educational atmospheric-dispersion screening. It estimates the downwind centerline distance at which a continuous gas release falls to a target concentration using the open Gaussian plume model with Briggs rural dispersion coefficients, so an agent can scope a flammable or toxic hazard zone before detailed dispersion analysis.

## When to Use

- When a user asks roughly how far a gas cloud reaches the LFL or a toxic ppm limit.
- When an agent needs a quick distance-to-target hazard extent for a continuous release.
- When examples must run without confidential plant layout or consequence-tool data.

## Inputs

- `release_rate`: continuous mass release rate `Q` in kg/s.
- `wind_speed`: wind speed `u` in m/s.
- `stability_class`: Pasquill-Gifford stability class `A`-`F`.
- `target_concentration`: target concentration in kg/m3 (use the helper below for vol% or ppm).
- `release_height`: effective release height `He` in m, default 0 (ground level).

Helper: `concentration_from_volume_fraction(volume_fraction, molar_mass, temperature_k, pressure_bara)` converts a gas volume (mole) fraction to kg/m3 using the ideal-gas law.

## Outputs

- `stability_class`: the resolved stability class.
- `target_concentration_kg_m3`: the target concentration used.
- `hazard_distance_m`: farthest downwind distance at or above the target, or `null` if never reached.
- `peak_concentration_kg_m3`: peak centerline concentration over the scan.
- `dispersion_warning`: `hazard-zone`, `no-hazard-distance`, or `beyond-assessment-distance`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `GaussianDispersionModel` uses the open Gaussian plume model:

- the centerline concentration uses `C = Q / (pi * u * sigma_y * sigma_z) * exp(-He^2 / (2 sigma_z^2))`.
- the dispersion coefficients `sigma_y` and `sigma_z` use the Briggs (1973) rural (open-country) formulas for class A-F.
- the hazard distance is the farthest downwind point at or above the target, found by a logarithmic distance scan.

This is educational and screening-only logic. It assumes a continuous point source, constant wind speed, flat open terrain, neutral buoyancy (no dense-gas slumping or plume rise), and no deposition or reaction. It is not a replacement for validated dispersion modelling, dense-gas or CFD tools, and qualified safety review.

## Python Usage Pattern

```python
from gas_dispersion_distance_screening import GaussianDispersionModel

model = GaussianDispersionModel(assessment_distance=500.0)

lfl = GaussianDispersionModel.concentration_from_volume_fraction(
    volume_fraction=0.044,
    molar_mass=16.04,
)
result = model.evaluate(
    release_rate=2.0,
    wind_speed=5.0,
    stability_class="F",
    target_concentration=lfl,
)

print(result.hazard_distance_m)
print(result.dispersion_warning)
```

## Related NeqSim Functionality

For validated dispersion and consequence behaviour, redirect to existing NeqSim classes:

- `neqsim.process.safety.scenario.ReleaseDispersionScenarioGenerator` — release and dispersion scenario generation.
- `neqsim.process.safety.fire.JetFireModel` / `PoolFireModel` — fire consequence models for ignited releases.
- `neqsim.process.safety.fire.VCEModel` — vapour-cloud-explosion overpressure modelling.

This skill is a public dispersion-distance triage layer that decides when to invoke those validated consequence classes.

## Validation Checklist

- [ ] Release rate, wind speed, and target concentration are positive.
- [ ] Stability class is one of A-F.
- [ ] The target is in kg/m3 (use the helper to convert vol% or ppm).
- [ ] Tests cover hazard distance, stability sensitivity, the helper, and invalid input.
- [ ] Real dispersion is redirected to validated NeqSim consequence classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Distance is `null` | Target concentration is too high | Check units; use the vol%/ppm helper |
| Distance too short | Dense gas treated as neutral | Use a dense-gas or CFD model for heavy gases |
| Wrong target | ppm passed as kg/m3 | Convert with `concentration_from_volume_fraction` |

## Limitations

- Neutral-buoyancy Gaussian model only; no dense-gas slumping or plume rise.
- Flat open terrain, constant wind, no obstacles or buildings.
- No deposition, reaction, or time-varying release.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
