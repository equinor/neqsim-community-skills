---
name: neqsim-two-phase-flow-regime-screening
version: "0.1.0"
description: "Educational two-phase flow-regime screening that classifies a horizontal gas-liquid flow pattern from superficial velocities using a simplified public Mandhane-style map and flags slug risk. USE WHEN: a task needs a public, screening-level flow-regime flag (stratified, slug, annular, bubble) and slug-risk triage to pair with slug-flow and flow-induced-vibration work."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Two-Phase Flow Regime Screening

Use this skill for public, educational two-phase flow-regime screening. It classifies a horizontal gas-liquid flow pattern from the superficial gas and liquid velocities using a simplified Mandhane-style decision tree and flags slug risk so an agent can decide whether to invoke validated NeqSim multiphase pipe-flow modelling.

## When to Use

- When a user asks what flow regime a horizontal line is likely in.
- When an agent needs a quick slug-risk flag before slug or vibration work.
- When examples must run without confidential pipeline models or field data.

## Inputs

Provide either the superficial velocities directly, or enough data to compute them:

- `superficial_gas_velocity`: gas superficial velocity `Vsg` in m/s.
- `superficial_liquid_velocity`: liquid superficial velocity `Vsl` in m/s.

or

- `pipe_inner_diameter`: pipe inner diameter in m.
- `gas_mass_flow`: gas mass flow in kg/s.
- `liquid_mass_flow`: liquid mass flow in kg/s.
- `gas_density`: gas density in kg/m3.
- `liquid_density`: liquid density in kg/m3.

## Outputs

- `superficial_gas_velocity_m_s`: gas superficial velocity used.
- `superficial_liquid_velocity_m_s`: liquid superficial velocity used.
- `mixture_velocity_m_s`: `Vsg + Vsl`.
- `flow_regime`: `stratified-smooth`, `stratified-wavy`, `elongated-bubble`, `slug`, `dispersed-bubble`, or `annular-mist`.
- `slug_risk`: `true` when the regime is slug or elongated-bubble.
- `regime_warning`: `ok`, `slug-risk`, or `high-velocity`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `TwoPhaseRegimeModel` uses a simplified public Mandhane-style classifier for horizontal flow:

- superficial velocities use `Vs = (mdot / rho) / (pi/4 * D^2)` when computed from flows.
- the regime is selected from public approximate boundaries: annular-mist above `Vsg = 10 m/s`, dispersed-bubble above `Vsl = 2 m/s`, stratified below `Vsl = 0.1 m/s`, elongated-bubble for low gas velocity, otherwise slug.
- `slug_risk` is flagged for the slug and elongated-bubble regimes.

This is educational and screening-only logic. The boundaries are public approximations, not the digitized Mandhane chart or a mechanistic model. It ignores pipe inclination, surface tension, viscosity, entrainment, and transient slugging. It is not a replacement for validated multiphase flow modelling and qualified flow assurance review.

## Python Usage Pattern

```python
from two_phase_flow_regime_screening import TwoPhaseRegimeModel

model = TwoPhaseRegimeModel()
result = model.evaluate(
    superficial_gas_velocity=3.0,
    superficial_liquid_velocity=0.5,
)

print(result.flow_regime)
print(result.slug_risk)
print(result.regime_warning)
```

## Related NeqSim Functionality

For validated multiphase flow behaviour, redirect to existing NeqSim classes:

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — Beggs and Brills multiphase pressure drop and holdup with internal regime determination.
- `neqsim.process.equipment.pipeline.TwoFluidPipe` — two-fluid transient pipe flow.
- `neqsim.process.equipment.pipeline.AdiabaticTwoPhasePipe` — adiabatic two-phase line modelling.

This skill is a public flow-regime triage layer that decides when to invoke those validated pipe-flow classes.

## Validation Checklist

- [ ] Either superficial velocities or full flow/density/diameter data are supplied.
- [ ] Velocities are non-negative and finite.
- [ ] The regime and slug-risk flag are reported as screening indicators.
- [ ] Tests cover stratified, slug, annular, computed velocities, and invalid input.
- [ ] Real regime analysis is redirected to validated NeqSim pipe-flow classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Regime looks wrong | Used vertical or inclined line | This map is for horizontal flow only |
| Velocities too high | Mass flow given in kg/h not kg/s | Use kg/s, or pass velocities directly |
| Slug missed | Operating near a public boundary | Use a mechanistic NeqSim model near boundaries |

## Limitations

- Horizontal flow only; no inclination or terrain slugging.
- Public approximate boundaries, not the digitized Mandhane chart.
- No surface-tension, viscosity, or entrainment effects.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
