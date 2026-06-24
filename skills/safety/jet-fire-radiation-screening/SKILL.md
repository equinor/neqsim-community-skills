---
name: neqsim-jet-fire-radiation-screening
version: "0.1.0"
description: "Educational jet-fire thermal-radiation screening that estimates the radiative flux at a distance, or the distance to a target flux, using the public single-point-source flame radiation model. USE WHEN: a task needs a public, screening-level jet-fire radiation flux or a distance to a personnel/equipment thermal limit before detailed fire-consequence analysis."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Jet Fire Radiation Screening

Use this skill for public, educational jet-fire thermal-radiation screening. It estimates the radiative heat flux at a given distance, or the distance to a target flux, from an ignited gas release using the open single-point-source flame model, so an agent can scope a fire hazard zone before detailed consequence analysis.

## When to Use

- When a user asks roughly what radiation flux reaches a target distance.
- When an agent needs a quick distance to a personnel or equipment thermal limit.
- When examples must run without confidential plant layout or fire-tool data.

## Inputs

- `release_rate`: burning mass release rate `mdot` in kg/s.
- `heat_of_combustion`: lower heat of combustion `Hc` in J/kg, default 50e6.
- `radiant_fraction`: fraction of heat released as radiation `Xr`, default 0.2.
- `transmissivity`: atmospheric transmissivity `tau`, default 1.0.
- `distance`: distance to the target in m (for flux), optional.
- `target_flux`: target radiation flux in kW/m2 (for distance), optional.

## Outputs

- `total_radiative_power_kw`: total radiative power emitted by the flame.
- `radiation_flux_kw_m2`: flux at `distance`, or `null` if no distance given.
- `distance_to_target_m`: distance to `target_flux`, or `null` if no target given.
- `radiation_warning`: `ok`, `watch`, `high`, `severe`, or `no-distance`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `JetFireRadiationModel` uses the public single-point-source flame model:

- the radiative power uses `Q_rad = tau * Xr * mdot * Hc`.
- the flux at a distance uses `q = Q_rad / (4 pi r^2)`.
- the distance to a target flux inverts the same relation: `r = sqrt(Q_rad / (4 pi q_target))`.
- the warning compares the flux to public thermal limits: a personnel limit (default 4.7 kW/m2), an equipment limit (default 12.5 kW/m2), and a 37.5 kW/m2 severe limit.

This is educational and screening-only logic. It assumes full combustion of the released mass, isotropic emission with no view factor, and no flame shape, length, or wind tilt. It is not a replacement for validated fire modelling, solid-flame or CFD radiation tools, and qualified safety review.

## Python Usage Pattern

```python
from jet_fire_radiation_screening import JetFireRadiationModel

model = JetFireRadiationModel()
result = model.evaluate(
    release_rate=10.0,
    target_flux=12.5,
)

print(result.total_radiative_power_kw)
print(result.distance_to_target_m)
print(result.radiation_warning)
```

## Related NeqSim Functionality

For validated fire-consequence behaviour, redirect to existing NeqSim classes:

- `neqsim.process.safety.fire.JetFireModel` — jet-fire flame and radiation modelling.
- `neqsim.process.safety.fire.PoolFireModel` — pool-fire radiation modelling.
- `neqsim.process.safety.fire.BLEVECalculator` — BLEVE fireball thermal dose.

This skill is a public radiation triage layer that decides when to invoke those validated fire classes.

## Validation Checklist

- [ ] Release rate and heat of combustion are positive.
- [ ] Radiant fraction and transmissivity are in `(0, 1]`.
- [ ] At least one of `distance` or `target_flux` is supplied for a useful result.
- [ ] Tests cover radiative power, flux at distance, distance to target, and invalid input.
- [ ] Real fire analysis is redirected to validated NeqSim fire classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Flux too high near source | Point source over-predicts close in | Use a solid-flame NeqSim model near the flame |
| No flux reported | `distance` not supplied | Pass `distance` or `target_flux` |
| Wrong power | `Hc` given per mole not per kg | Use J/kg for the heat of combustion |

## Limitations

- Point-source emission; no flame length, shape, or view factor.
- No wind tilt, lift-off, or partial combustion.
- No transient or impinging-fire effects.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
