---
name: neqsim-artificial-lift-screening
version: "0.1.0"
description: "Educational artificial-lift screening that compares a simple straight-line IPR natural deliverability against a target rate and screens gas lift and ESP feasibility from a required bottomhole-pressure reduction. USE WHEN: a task needs a public, screening-level recommendation of natural flow, gas lift, or ESP for a well before detailed inflow/outflow (nodal) analysis and lift design."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Artificial Lift Screening

Use this skill for public, educational artificial-lift triage. It estimates natural deliverability from a straight-line inflow performance relationship (IPR), checks it against a target rate, and screens gas lift and electric submersible pump (ESP) feasibility from the bottomhole-pressure reduction required to meet the target.

## When to Use

- When a user asks whether a well can flow naturally or needs artificial lift to hit a target rate.
- When an agent needs a quick gas-lift vs ESP recommendation before nodal analysis.
- When the reservoir may be unable to deliver the target even at zero bottomhole pressure.
- When examples must run without proprietary well models, vendor pump curves, or field data.

## Inputs

- `reservoir_pressure_bar`: average reservoir pressure in bar.
- `bottomhole_flowing_pressure_bar`: current flowing bottomhole pressure in bar.
- `productivity_index_sm3_d_bar`: straight-line productivity index in Sm3/d per bar drawdown.
- `target_rate_sm3_d`: required production rate in Sm3/d.
- `water_cut`: produced water fraction in [0, 1), default 0.0.
- `gas_lift_available`: whether gas lift injection is available, default `True`.
- `max_injection_gas_sm3_d`: optional available lift-gas injection rate in Sm3/d.
- `esp_max_head_m`: optional maximum ESP head in metres.
- `fluid_gradient_bar_per_m`: hydrocarbon fluid gradient in bar/m, default 0.09.
- `well_depth_m`: producing depth in metres, default 2000.

## Outputs

- `natural_rate_sm3_d`: deliverability from the straight-line IPR at the current bottomhole pressure.
- `required_pwf_bar`: bottomhole pressure required to deliver the target rate.
- `required_pressure_reduction_bar`: bottomhole-pressure reduction needed beyond the current flowing pressure.
- `esp_required_head_m`: ESP head needed for the pressure reduction, or `null`.
- `gas_lift_feasible`: `True`/`False` gas-lift feasibility flag.
- `esp_feasible`: `True`/`False` ESP feasibility flag.
- `recommended_method`: `natural-flow`, `gas-lift`, `esp`, or `infeasible`.
- `warning`: same value as `recommended_method` for quick triage.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `ArtificialLiftModel` uses open well relations only:

- natural deliverability uses a straight-line IPR: `q = PI * (Pr - Pwf)`.
- the bottomhole pressure for the target rate is `Pwf_req = Pr - target / PI`; if `Pwf_req <= 0` the reservoir cannot deliver the target and the result is `infeasible`.
- the required pressure reduction is `dP = Pwf_current - Pwf_req` (zero when natural flow already meets the target).
- an effective gradient blends fluid and water gradients: `grad = fluid_gradient * (1 - water_cut) + 0.0981 * water_cut` (bar/m).
- ESP head uses `H = dP / grad`, feasible when `esp_max_head_m` is supplied and `H <= esp_max_head_m`.
- gas lift can lighten the column up to about half the hydrostatic head, `dP_max = 0.5 * grad * well_depth`, feasible when lift gas is available and `dP <= dP_max`.

This is educational and screening-only logic. It assumes a straight-line IPR (no turbulence or saturation effects), a static effective gradient, and a fixed gas-lift lightening fraction. It is not a replacement for validated nodal analysis or qualified lift design.

## Python Usage Pattern

```python
from artificial_lift_screening import ArtificialLiftModel

model = ArtificialLiftModel()
result = model.evaluate(
    reservoir_pressure_bar=250.0,
    bottomhole_flowing_pressure_bar=200.0,
    productivity_index_sm3_d_bar=8.0,
    target_rate_sm3_d=800.0,
    esp_max_head_m=2500.0,
)

print(result.natural_rate_sm3_d)
print(result.required_pressure_reduction_bar)
print(result.recommended_method)
```

## Related NeqSim Functionality

For validated inflow/outflow and lift modelling, redirect to NeqSim resources:

- `neqsim.process.equipment.reservoir.WellFlow` — well inflow with a productivity-index based IPR.
- `neqsim.process.equipment.reservoir.SimpleReservoir` — material-balance reservoir for production forecasting.
- the `neqsim-production-optimization` skill — gas lift allocation and bottleneck analysis guidance.

This skill is a public triage layer that decides when to invoke validated nodal analysis.

## Validation Checklist

- [ ] Reservoir and flowing pressures, productivity index, and target rate are positive.
- [ ] Water cut is in [0, 1) and depth and gradient are positive.
- [ ] An infeasible reservoir (required Pwf at or below zero) is reported as `infeasible`.
- [ ] Tests cover natural flow, gas-lift, ESP, infeasible, and invalid input.
- [ ] Real lift selection is redirected to validated NeqSim resources and qualified design.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Always `esp` never `gas-lift` | `gas_lift_available` left False | Set gas lift availability to True |
| ESP feasibility always False | `esp_max_head_m` not supplied | Provide a maximum ESP head |
| Recommendation `infeasible` | Target rate exceeds PI x reservoir pressure | Lower the target or revisit PI |

## Limitations

- No proprietary well models, vendor pump curves, or field data are included.
- A straight-line IPR is used; no bubble-point or turbulence effects are modelled.
- Gas-lift and ESP feasibility use single fixed-fraction screening rules.

## References

- Beggs, H. D., Production Optimization Using Nodal Analysis.
- Economides, M. J. et al., Petroleum Production Systems.
- API RP 11S, Recommended Practice for the Operation, Maintenance, and Troubleshooting of Electric Submersible Pump Installations.
- NeqSim repository: https://github.com/equinor/neqsim
