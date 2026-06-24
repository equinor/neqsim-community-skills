---
name: neqsim-noise-screening
version: "0.1.0"
description: "Educational valve and line aerodynamic-noise indicator that estimates a screening sound-pressure level from gas mass flow, pressure drop, and density using a public IEC 60534-8 style energy approach. USE WHEN: a task needs a public, screening-level noise indicator and an action/high flag for a gas valve or restriction before detailed IEC 60534-8 noise prediction."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Noise Screening

Use this skill for public, educational aerodynamic-noise screening of a gas valve or line restriction. It estimates a sound-pressure-level indicator from the mass flow, pressure drop, and density using an open energy-based approach, so an agent can flag a potential noise problem before detailed IEC 60534-8 prediction.

## When to Use

- When a user asks whether a gas valve or restriction is likely to be noisy.
- When an agent needs a quick action/high noise flag for screening.
- When examples must run without confidential valve trim or vendor noise data.

## Inputs

- `mass_flow`: gas mass flow in kg/s.
- `pressure_drop`: pressure drop across the restriction in bar.
- `inlet_density`: inlet gas density in kg/m3.
- `sound_speed`: speed of sound in m/s (provide this, or temperature and molar mass).
- `specific_heat_ratio`: ratio of specific heats `k`, default 1.3.
- `temperature`: gas temperature in K (used to estimate sound speed).
- `molar_mass`: gas molar mass in g/mol (used to estimate sound speed).

## Outputs

- `vena_contracta_velocity_m_s`: estimated velocity at the restriction.
- `mach_number`: velocity divided by the speed of sound.
- `internal_sound_power_level_db`: internal sound power level (re 1 pW).
- `estimated_spl_1m_dba`: screening sound-pressure level at 1 m.
- `noise_warning`: `ok`, `action`, or `high`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `ValveNoiseModel` uses a public energy-based aerodynamic-noise approach:

- the vena-contracta velocity uses `v = sqrt(2 * dP / rho)`.
- the speed of sound uses the provided value or `c = sqrt(k * R * T / M)`.
- the mechanical stream power uses `W_m = 0.5 * mdot * v^2`.
- the acoustic power uses `W_a = min(0.01, eta_f * Mach^3) * W_m`.
- the sound power level uses `L_W = 10 log10(W_a / 1 pW)` and a fixed transmission loss converts it to a 1 m sound-pressure level.

This is an educational screening indicator, not a full IEC 60534-8-3 prediction. It uses a generic acoustic efficiency and a fixed transmission loss with no valve style, trim, pipe schedule, distance correction, or frequency weighting. It is not a replacement for validated noise prediction, vendor noise data, and qualified acoustic review.

## Python Usage Pattern

```python
from noise_screening import ValveNoiseModel

model = ValveNoiseModel()
result = model.evaluate(
    mass_flow=12.0,
    pressure_drop=40.0,
    inlet_density=35.0,
    temperature=310.0,
    molar_mass=19.0,
)

print(result.mach_number)
print(result.estimated_spl_1m_dba)
print(result.noise_warning)
```

## Related NeqSim Functionality

For validated valve behaviour, redirect to existing NeqSim classes:

- `neqsim.process.equipment.valve.ThrottlingValve` — flow-vs-Cv valve and pressure-drop response that defines the noise duty.
- `neqsim.process.equipment.valve.ControlValve` — control valve with characteristic and controller coupling.

Full aerodynamic-noise prediction follows IEC 60534-8-3. This skill is a public noise triage layer that decides when to invoke detailed valve and noise tools.

## Validation Checklist

- [ ] Mass flow, pressure drop, and density are positive.
- [ ] Either a sound speed or temperature and molar mass are supplied.
- [ ] The result is treated as a screening indicator, not a certified noise level.
- [ ] Tests cover the basic indicator, a high-noise case, sound-speed estimation, and invalid input.
- [ ] Real noise prediction is redirected to validated tools and qualified acoustic review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| SPL looks too precise | Treated indicator as IEC result | Use it only for screening |
| Mach off | Sound speed from wrong gas | Provide molar mass and temperature |
| Wrong magnitude | Mass flow in kg/h not kg/s | Use kg/s |

## Limitations

- Screening indicator only, not IEC 60534-8-3 prediction.
- No valve style, trim, pipe schedule, or frequency content.
- Fixed transmission loss and generic acoustic efficiency.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
