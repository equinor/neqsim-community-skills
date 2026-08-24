---
name: neqsim-noise-screening
version: "0.2.0"
description: "Standards-based gas-valve and restriction noise screening at a stated receiver distance using either a current measured A-weighted level or a conservative pressure-drop energy model. USE WHEN: a task needs noise triage, receiver/workplace assessment, or routing to detailed IEC 60534-8-3 prediction while keeping acoustic-induced-vibration assessment separate."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Noise Screening

Use this skill to screen gas-valve and restriction noise at a stated receiver distance from either a representative operating measurement or a conservative energy model. Keep source prediction, receiver/workplace assessment, and acoustic-induced-vibration (AIV) screening as separate decisions.

## When to Use

- When a user asks whether a gas valve or restriction is likely to be noisy.
- When current measured noise must be evaluated at a stated operating condition and receiver position.
- When an agent needs a quick action/high noise flag before detailed engineering.
- When examples must run without confidential valve trim or vendor noise data.
- Do not use this skill alone to accept personnel exposure, acoustic fatigue, or AIV.

## Inputs

- `mass_flow`: gas mass flow in kg/s.
- `pressure_drop`: pressure drop across the restriction in bar.
- `inlet_density`: inlet gas density in kg/m3.
- `sound_speed`: speed of sound in m/s (provide this, or temperature and molar mass).
- `distance`: source-to-receiver distance in m, default 1 m.
- `measured_spl_at_distance`: optional representative A-weighted measurement in dBA at `distance`.
- `measured_uncertainty_db`: optional positive measurement uncertainty in dB.
- `specific_heat_ratio`: ratio of specific heats `k`, default 1.3.
- `temperature`: gas temperature in K (used to estimate sound speed).
- `molar_mass`: gas molar mass in g/mol (used to estimate sound speed).
- Constructor overrides for action level, high level, model uncertainty, acoustic efficiency, and transmission loss.

## Outputs

- `vena_contracta_velocity_m_s`: estimated velocity at the restriction.
- `mach_number`: velocity divided by the speed of sound.
- `internal_sound_power_level_db`: internal sound power level (re 1 pW).
- `estimated_spl_1m_dba`: screening sound-pressure level at 1 m.
- `estimated_spl_at_distance_dba`: assessed A-weighted level at the receiver distance.
- `assessment_basis`: `measurement` or `screening-model`.
- `noise_warning`: `ok`, `action`, or `high`.
- `uncertainty_db`, `standards_basis`, and `assumptions` for review and escalation.

## Engineering Method

The Python class `ValveNoiseModel` uses this decision path:

1. Freeze the operating snapshot, source identity, receiver position, and evidence type.
2. Use `measured_spl_at_distance` directly when a representative measurement and uncertainty are available.
3. Otherwise estimate vena-contracta velocity with `v = sqrt(2 * dP / rho)`, mechanical stream power with `W_m = 0.5 * mdot * v^2`, and acoustic power with `W_a = min(0.01, eta_f * Mach^3) * W_m`.
4. Convert sound power to a 1 m level using a configurable transmission loss, then apply free-field spreading `20 log10(r/1 m)` to the receiver.
5. Apply configurable workflow triggers: `ok` below 85 dBA, `action` at or above 85 dBA, and `high` at or above 110 dBA by default.
6. Escalate elevated or uncertain cases to detailed source prediction, a controlled receiver survey, occupational-hygiene review, or separate AIV screening as applicable.

The model is a triage calculation, not a full IEC 60534-8-3 prediction. The default model uncertainty is +/-10 dB. Default thresholds are workflow triggers rather than universal legal exposure limits.

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
  distance=3.0,
)

print(result.mach_number)
print(result.estimated_spl_at_distance_dba)
print(result.assessment_basis)
print(result.noise_warning)
```

For current operating evidence, provide the measured receiver level and its uncertainty:

```python
measured = model.evaluate(
  mass_flow=12.0,
  pressure_drop=40.0,
  inlet_density=35.0,
  sound_speed=410.0,
  distance=3.0,
  measured_spl_at_distance=92.0,
  measured_uncertainty_db=2.0,
)
```

## Related NeqSim Functionality

For detailed valve source prediction, use existing NeqSim classes:

- `neqsim.process.equipment.valve.ThrottlingValve` — flow-vs-Cv valve and pressure-drop response that defines the noise duty.
- `neqsim.process.equipment.valve.ControlValve` — control valve with characteristic and controller coupling.
- `neqsim.process.mechanicaldesign.valve.ControlValveNoise_IEC_60534_8_3` — aerodynamic source prediction with flow regime, mechanical stream power, pipe-wall transmission loss, and external A-weighted level.

For the detailed class, call `setFlowConditions(...)`, `setAcousticProperties(...)`, `setGeometry(...)`, `setValveCoefficients(...)`, and `calcNoise()`. Read `getSoundPressureLevelDbA()`, `getOutletMach()`, `getFlowRegime()`, `getMechanicalStreamPower()`, and `getTransmissionLoss()`. Obtain density, speed of sound, and isentropic exponent from a flashed NeqSim fluid; treat valve coefficients and geometry as controlled vendor/design inputs.

## Validation Checklist

- [ ] Mass flow, pressure drop, and density are positive.
- [ ] Either a sound speed or temperature and molar mass are supplied.
- [ ] Receiver distance, operating timestamp/window, source identity, and evidence basis are recorded.
- [ ] Measurement method, instrument, background correction, and uncertainty are recorded when measured data are used.
- [ ] The result is treated as screening evidence, not universal exposure or AIV acceptance.
- [ ] Detailed source prediction is redirected to NeqSim/vendor tools and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| SPL looks too precise | Treated indicator as IEC result | Use it only for screening |
| Mach off | Sound speed from wrong gas | Provide molar mass and temperature |
| Wrong magnitude | Mass flow in kg/h not kg/s | Use kg/s |
| AIV accepted from dBA | Noise and pipe-vibration criteria were conflated | Run a separate AIV screening |
| Measurement cannot be reproduced | Operating state or receiver position is missing | Record time window, process data, location, and uncertainty |

## Limitations

- The model path is not an IEC 60534-8-3 prediction and has no octave-band content.
- Free-field spreading omits reflections, shielding, multiple sources, directivity, atmospheric absorption, and distributed pipe radiation.
- A single dBA value cannot establish daily exposure dose, hearing protection, acoustic fatigue, or AIV acceptability.
- A measurement applies only to its operating state, receiver position, instrument setup, background correction, and uncertainty.
- Design acceptance requires controlled standards editions, verified valve/vendor data, and competent acoustic review.

## References

- IEC 60534-8-3, control-valve aerodynamic noise prediction method.
- ISO 3744, sound-power determination from sound-pressure measurements.
- ISO 11201, emission sound-pressure measurement at work stations and specified positions.
- ISO 9613-2, engineering prediction of outdoor sound propagation.
- ISO 15664, noise-control design procedures for open plant.
- ISO 1999, estimation of noise-induced hearing loss.
- NeqSim repository: https://github.com/equinor/neqsim
