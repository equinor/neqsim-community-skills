---
name: neqsim-acoustic-induced-vibration-screening
version: "0.1.0"
description: "Educational acoustic-induced-vibration (AIV) screening using the public Energy Institute likelihood-of-failure form for gas pressure-reducing devices. USE WHEN: a task needs a public, screening-level estimate of sound power level, pipe diameter-to-thickness ratio, allowable sound power level, and an AIV likelihood-of-failure index for a control valve, relief valve, or restriction orifice before detailed vibration assessment."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Acoustic-Induced Vibration Screening

Use this skill for public, educational acoustic-induced-vibration (AIV) screening of gas pressure-reducing devices. It estimates the generated sound power level, the pipe diameter-to-thickness ratio, an allowable sound power level, and a likelihood-of-failure (LOF) index so an agent can scope an AIV study before a detailed piping-vibration assessment. It complements the `flow-induced-vibration-screening` skill, which covers gas flow-induced vibration through a kinetic-energy index.

## When to Use

- When a user asks whether a control valve, relief valve, or restriction orifice creates an AIV risk.
- When an agent needs a quick sound-power-level and LOF estimate downstream of a high pressure drop.
- When examples must run without confidential valve data, vendor noise curves, or company specs.

## Inputs

- `mass_flow_kg_s`: gas mass flow through the device in kg/s.
- `upstream_pressure_bar`: upstream pressure `P1` in bar absolute.
- `downstream_pressure_bar`: downstream pressure `P2` in bar absolute.
- `pipe_outside_diameter_mm`: downstream pipe outside diameter in mm.
- `wall_thickness_mm`: downstream pipe wall thickness in mm.
- `molecular_weight`: gas molecular weight, default 19.
- `temperature_k`: gas temperature in kelvin, default 313.15.
- `downstream_pipe_length_m`: downstream pipe length in m, default 10.
- `sound_power_level_db`: optional measured/known sound power level; if omitted it is computed.

## Outputs

- `pressure_drop_ratio`: `(P1 - P2) / P1`.
- `sound_power_level_db`: supplied or computed sound power level in dB.
- `diameter_thickness_ratio`: pipe `D / t`.
- `allowable_sound_power_level_db`: allowable sound power level from the `D / t` correlation.
- `likelihood_of_failure`: dimensionless AIV LOF index.
- `downstream_pipe_length_m`: echoed downstream pipe length.
- `risk_warning`: `low-risk`, `medium-risk`, or `high-risk`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `AcousticInducedVibrationModel` uses the open Energy Institute / Carucci-Mueller AIV screening form only:

- sound power level uses `PWL = 10 log10[(dP/P1)^3.6 * mdot^2 * (T/MW)^1.2] + constant`.
- diameter-to-thickness ratio uses `D / t`.
- allowable sound power level uses `PWL_allow = reference - slope * (D / t)`, so higher `D / t` lowers the limit.
- likelihood of failure uses `LOF = 1 + (PWL - PWL_allow) / spread`, clamped at zero, so higher `PWL` and higher `D / t` both raise the LOF.

This is educational and screening-only logic. The correlation constants are documented screening approximations, not certified AIV limits. It assumes a single gas pressure-reducing device, ignores branch-connection geometry, weld type, and downstream fitting layout, and is not a replacement for a validated AIV assessment or qualified piping-vibration review.

## Python Usage Pattern

```python
from acoustic_induced_vibration_screening import AcousticInducedVibrationModel

model = AcousticInducedVibrationModel()
result = model.evaluate(
    mass_flow_kg_s=12.0,
    upstream_pressure_bar=90.0,
    downstream_pressure_bar=20.0,
    pipe_outside_diameter_mm=323.9,
    wall_thickness_mm=9.5,
)

print(result.sound_power_level_db)
print(result.likelihood_of_failure)
print(result.risk_warning)
```

## Related NeqSim Functionality

For validated vibration screening, redirect to NeqSim classes:

- `neqsim.process.safety.vibration.AcousticInducedVibrationLOF` — proposed AIV likelihood-of-failure model (PWL, D/t, allowable-PWL correlation); candidate NeqSim gap.
- `neqsim.process.safety.vibration.FlowInducedVibrationLOF` — proposed flow-induced-vibration model; candidate NeqSim gap.
- The `flow-induced-vibration-screening` community skill — gas flow-induced vibration through a kinetic-energy index.

This skill is a public triage layer that decides when to invoke a validated AIV assessment.

## Validation Checklist

- [ ] Upstream and downstream pressures are positive and `P1 > P2`.
- [ ] Pipe outside diameter exceeds twice the wall thickness.
- [ ] Tests cover sound-power-level computation, a supplied sound-power-level path, a high-risk case, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real assessment is redirected to validated NeqSim vibration classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| LOF unexpectedly high | Large `D / t` thin-wall pipe | Use a thicker wall or smaller diameter |
| LOF always zero | Very low sound power level | Confirm the pressure-drop and flow inputs |
| Computed PWL ignored | `sound_power_level_db` supplied | Omit it to let the correlation compute PWL |

## Limitations

- No proprietary valve data, vendor noise curves, or company specs are included.
- Branch-connection geometry, weld type, and downstream fitting layout are not modelled.
- The correlation constants are documented screening approximations only.

## References

- Energy Institute, Guidelines for the Avoidance of Vibration Induced Fatigue Failure in Process Pipework, 2nd Edition.
- Carucci, V. A., and Mueller, R. T., Acoustically Induced Piping Vibration in High Capacity Pressure Reducing Systems, ASME 82-WA/PVP-8.
- NeqSim repository: https://github.com/equinor/neqsim
