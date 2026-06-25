---
name: neqsim-reciprocating-compressor-screening
version: "0.1.0"
description: "Educational reciprocating-compressor screening using the public clearance volumetric-efficiency relation (API 618 / API 619 style). USE WHEN: a task needs a public, screening-level estimate of volumetric efficiency, actual inlet capacity, staging, discharge temperature, and rod-load utilisation for a reciprocating compressor before detailed selection."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reciprocating Compressor Screening

Use this skill for public, educational reciprocating-compressor screening. It estimates clearance volumetric efficiency, actual inlet capacity, the required number of stages, discharge temperature, and a rod-load utilisation ratio so an agent can scope a reciprocating-compression study before detailed selection.

## When to Use

- When a user asks how many stages a reciprocating compressor needs or what its volumetric efficiency is.
- When an agent needs a quick actual-capacity and discharge-temperature estimate for a positive-displacement machine.
- When examples must run without confidential compressor data, vendor curves, or company specs.

## Inputs

- `suction_pressure`: stage suction pressure `P1` in bar absolute.
- `discharge_pressure`: final discharge pressure `P2` in bar absolute.
- `suction_temperature`: suction temperature `T1` in kelvin.
- `swept_volume_rate_m3_h`: geometric (swept) volume rate in m3/h.
- `clearance_fraction`: cylinder clearance fraction `C`, default 0.12.
- `specific_heat_ratio`: ratio of specific heats `k`, default 1.3.
- `leakage_allowance`: leakage/loss allowance `L`, default 0.03.
- `rated_rod_load_kn`: optional rated rod load in kN for the rod-load comparison.
- `piston_area_m2`: optional piston area in m2 for the rod-load comparison.

## Outputs

- `pressure_ratio`: overall `P2 / P1`.
- `stages`: integer number of stages keeping each stage below `max_stage_ratio`.
- `stage_pressure_ratio`: per-stage pressure ratio.
- `volumetric_efficiency`: clearance volumetric efficiency.
- `actual_inlet_capacity_m3_h`: swept rate multiplied by volumetric efficiency.
- `discharge_temperature_k`: first-stage isentropic discharge temperature.
- `rod_load_ratio`: gas rod load divided by rated rod load, or `null`.
- `capacity_warning`: `ok`, `watch`, `low-volumetric-efficiency`, or `discharge-temp-high`.
- `rod_load_warning`: `ok`, `watch`, `rod-load-exceeded`, or `no-rating`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `ReciprocatingCompressorModel` uses open positive-displacement relations only:

- staging splits the overall ratio so `stage_ratio = (P2 / P1)^(1/stages)` stays below `max_stage_ratio` (default 4.0).
- volumetric efficiency uses `VE = 1 - C (r^(1/k) - 1) - L`.
- actual inlet capacity uses `Q_actual = swept_rate * VE`.
- discharge temperature uses `T2 = T1 r^((k-1)/k)`.
- gas rod load uses `F = dP * piston_area`, compared to the rated rod load.

This is educational and screening-only logic. It assumes constant `k`, ideal staging, no valve or pulsation losses, and gas-only rod load. It is not a replacement for validated reciprocating-compressor sizing or qualified rotating-equipment review.

## Python Usage Pattern

```python
from reciprocating_compressor_screening import ReciprocatingCompressorModel

model = ReciprocatingCompressorModel()
result = model.evaluate(
    suction_pressure=2.0,
    discharge_pressure=120.0,
    suction_temperature=313.15,
    swept_volume_rate_m3_h=800.0,
    rated_rod_load_kn=120.0,
    piston_area_m2=0.04,
)

print(result.stages)
print(result.volumetric_efficiency)
print(result.rod_load_warning)
```

## Related NeqSim Functionality

For validated compression calculations, redirect to NeqSim classes:

- `neqsim.process.equipment.compressor.Compressor` — rigorous polytropic compression with real-gas properties.
- `neqsim.process.equipment.compressor.ReciprocatingCompressor` — proposed reciprocating-compressor model (volumetric efficiency, valve losses, rod load); candidate NeqSim gap.
- `neqsim.process.mechanicaldesign.compressor.CompressorMechanicalDesign` — compressor mechanical design and feasibility.

This skill is a public triage layer that decides when to invoke a validated reciprocating-compressor model.

## Validation Checklist

- [ ] Suction and discharge pressures are positive and `P2 > P1`.
- [ ] Clearance fraction is in `(0, 1)` and leakage allowance in `[0, 1)`.
- [ ] Tests cover staging, volumetric efficiency, a rod-load comparison, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real selection is redirected to validated NeqSim compressor classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Volumetric efficiency near zero | Single high-ratio stage | Let the staging logic add stages |
| Discharge temperature too high | High stage ratio | Add stages or intercooling |
| Rod-load ratio missing | No rated rod load or piston area supplied | Provide both for the comparison |

## Limitations

- No proprietary compressor data, vendor curves, or company specs are included.
- No valve losses, pulsation, or real-gas property variation are modelled.
- Rod load uses gas load only; inertia and load reversal are not included.

## References

- API Standard 618, Reciprocating Compressors for Petroleum, Chemical, and Gas Industry Services.
- API Standard 619, Rotary-Type Positive-Displacement Compressors.
- NeqSim repository: https://github.com/equinor/neqsim
