---
name: neqsim-dry-gas-seal-screening
version: "0.1.0"
description: "Educational dry gas seal supply and condensation screening for centrifugal compressors. USE WHEN: a task needs a public, screening-level estimate of seal-gas and separation-gas supply demand and a seal-gas condensation-margin check (cavity temperature versus hydrocarbon dew point) before detailed dry gas seal system design per API 692."
last_verified: "2026-06-19"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Dry Gas Seal Screening

Use this skill for public, educational dry gas seal screening on centrifugal compressors. It estimates the seal-gas and separation-gas supply demand from the primary seal leakage rate and flags retrograde-condensation risk by comparing the seal cavity temperature against a hydrocarbon dew point at the seal/vent reference condition.

## When to Use

- When a user asks whether a compressor dry gas seal has adequate seal-gas supply margin.
- When an agent needs a quick condensation-risk triage for the primary vent / standpipe dead-leg before a detailed seal study.
- When examples must run without confidential seal vendor data, machine line lists, or project seal-gas conditioning specifications.

## Inputs

- `seal_leakage_rate_nl_per_min`: primary seal leakage rate at standard conditions in NL/min per seal.
- `seal_cavity_temperature_c`: seal cavity (process-side) temperature in degrees C.
- `hydrocarbon_dew_point_c`: hydrocarbon dew point at the seal/vent reference condition in degrees C.
- `seal_count`: number of seals supplied (default 2: drive end and non-drive end).
- `supply_margin`: seal-gas supply margin over leakage, dimensionless, default 1.25.
- `separation_gas_rate_nl_per_min`: separation (secondary) gas rate per seal in NL/min, default 0.0.

## Outputs

- `total_seal_gas_supply_nl_per_min`: screening seal-gas supply demand.
- `separation_gas_supply_nl_per_min`: screening separation-gas supply demand.
- `seal_gas_supply_margin_ratio`: the applied supply margin over leakage.
- `condensation_margin_c`: seal cavity temperature minus the hydrocarbon dew point.
- `condensation_warning`: `ok`, `watch`, or `high` (a small or negative margin means higher condensation risk).
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `DryGasSealModel` uses open, public concepts only:

- seal-gas supply demand is the primary seal leakage multiplied by the seal count and a supply margin, reflecting the API 692 intent that supply must exceed leakage to keep the seal faces clean.
- separation-gas supply demand scales with the seal count.
- the condensation margin compares the seal cavity temperature against a hydrocarbon dew point at the seal/vent reference condition. A small or negative margin flags retrograde condensation risk in the primary vent piping and standpipe dead-legs, which is the failure mode that seal-gas conditioning units exist to prevent.

This is educational and screening-only logic. It is not a seal vendor method, not a seal-gas conditioning design, and not a replacement for validated dry gas seal analysis and a qualified rotating-equipment review.

## Python Usage Pattern

```python
from dry_gas_seal_screening import DryGasSealModel

model = DryGasSealModel()
result = model.evaluate(
    seal_leakage_rate_nl_per_min=280.0,
    seal_cavity_temperature_c=44.0,
    hydrocarbon_dew_point_c=40.0,
    seal_count=2,
    supply_margin=1.25,
    separation_gas_rate_nl_per_min=120.0,
)

print(result.condensation_warning)
print(result.total_seal_gas_supply_nl_per_min)
print(result.condensation_margin_c)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim seal-gas dew-point and condensation analysis. If it is not installed, the example still runs with public placeholder logic.

## Validation Checklist

- [ ] Inputs are in the documented units (NL/min, degrees C).
- [ ] Example inputs are public and synthetic.
- [ ] Tests cover ok, watch, high, and invalid-input cases.
- [ ] Results are described as educational screening indicators.
- [ ] Real seal system design is redirected to validated methods, API 692, and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Condensation never flagged | Dew point taken at cavity pressure instead of the vent/expanded condition | Use the hydrocarbon dew point at the seal/vent reference condition |
| Supply demand looks low | Supply margin set to 1.0 | Use a supply margin above 1.0 consistent with the seal-gas control philosophy |
| Wrong total supply | Seal count not matching the machine arrangement | Set `seal_count` to the actual number of seals supplied |

## Limitations

- No seal vendor leakage curves, clearance models, or qualification data are included.
- No isenthalpic (Joule-Thomson) expansion or transient standpipe cooldown is modelled.
- No seal-gas conditioning unit (heater/separator) sizing is performed.
- Not suitable for safety-critical, design, guarantee, or standards-compliance work.

## Related NeqSim Functionality

This educational screening corresponds to validated, rigorous functionality in the NeqSim Java library that a qualified engineer should use for design-grade work:

- `neqsim.process.equipment.compressor.DryGasSealAnalyzer` — isenthalpic seal-gap expansion, retrograde condensation mapping, dead-leg cooldown, condensate accumulation, and seal-gas conditioning unit sizing per API 692.
- `neqsim.process.measurementdevice.HydrocarbonDewPointAnalyser` — hydrocarbon dew-point evaluation for the seal-gas stream.
- `neqsim.process.equipment.valve.ThrottlingValve` — Joule-Thomson expansion modelling across the seal gap.

In Python the same classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Public rotating-equipment references such as API 692 (Dry Gas Sealing Systems) and API 614 (Lubrication, Shaft-Sealing, and Oil-Control Systems) for general seal-gas concepts.
