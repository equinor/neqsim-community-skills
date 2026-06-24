---
name: neqsim-surf-cooldown-screening
version: "0.1.0"
description: "Educational SURF flowline/riser cooldown and no-touch-time screening placeholder with public assumptions. USE WHEN: a task needs a quick, public estimate of how long an insulated subsea flowline stays above its hydrate formation temperature after shutdown, and should be directed to validated NeqSim methods for real cooldown and hydrate calculations."
last_verified: "2026-07-04"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# SURF Cooldown Screening

Use this skill for a quick, public estimate of the **no-touch time** of an
insulated subsea flowline or riser after a shutdown: how long the trapped fluid
stays above its hydrate formation temperature (plus a safety margin) before
remedial action (depressurization or inhibitor injection) is required. It is
intentionally simple and should guide users toward validated NeqSim cooldown and
hydrate workflows for real work.

## When to Use

- When a user asks roughly how long a subsea line can be left after shutdown
  before reaching the hydrate region.
- When a validated NeqSim hydrate equilibrium temperature and a lumped thermal
  time constant (or the data to estimate one) are already available.
- When an agent should explain that validated NeqSim methods are required for
  real cooldown, no-touch-time, and inhibitor design.

## Inputs

- `initial_temperature`: fluid temperature at shutdown in C.
- `seabed_temperature`: ambient seabed (sink) temperature in C.
- `hydrate_equilibrium_temperature`: hydrate formation temperature in C from a
  validated NeqSim calculation.
- `time_constant_hours`: lumped exponential cooldown time constant in hours.
- `hydrate_margin`: configurable margin above the hydrate temperature in C
  (constructor, default 3.0).
- `required_no_touch_time`: optional operational target in hours (constructor).

A helper, `time_constant_from_lumped_mass`, estimates `time_constant_hours` from
fluid density, specific heat, internal diameter, and an overall U-value using the
public lumped relation `tau = rho * cp * D / (4 * U)`.

## Outputs

- `no_touch_time_hours`: time to cool to the hydrate target temperature.
- `target_temperature_c`: hydrate equilibrium temperature plus the margin.
- `verdict`: `ok`, `marginal`, `critical`, or `no_hydrate_risk`.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

The placeholder uses a single-node (lumped) exponential cooldown:

`T(t) = T_seabed + (T_initial - T_seabed) * exp(-t / tau)`

Solving for the time to reach the hydrate target temperature
`T_target = T_hydrate + margin`:

`t_no_touch = -tau * ln((T_target - T_seabed) / (T_initial - T_seabed))`

If the hydrate temperature is at or below the seabed temperature (or no value is
supplied), the line never enters the hydrate region and the verdict is
`no_hydrate_risk`. Verdict bands: with a required no-touch time, `ok` at or above
the requirement, `marginal` at or above 75% of it, otherwise `critical`. Without
a requirement, `ok` at 12 h or more, `marginal` at 6 h or more, otherwise
`critical`.

This is not a distributed thermal-hydraulic model. The hydrate equilibrium
temperature and the thermal time constant must come from validated NeqSim
calculations with a defined fluid composition, water content, geometry, and
insulation basis.

## Python Usage Pattern

```python
from surf_cooldown_screening import SurfCooldownModel

model = SurfCooldownModel(hydrate_margin=3.0, required_no_touch_time=8.0)

tau = SurfCooldownModel.time_constant_from_lumped_mass(
    fluid_density=180.0,        # kg/m3 (dense gas)
    specific_heat=2600.0,       # J/kg.K
    internal_diameter=0.254,    # m
    overall_u_value=2.5,        # W/m2.K
)

result = model.evaluate(
    initial_temperature=65.0,
    seabed_temperature=4.0,
    hydrate_equilibrium_temperature=20.0,
    time_constant_hours=tau,
)

print(result.no_touch_time_hours)
print(result.verdict)
print(result.assumptions)
```

If the optional `neqsim` Python package is available, the result records that
fact so an agent can recommend moving to validated NeqSim cooldown workflows. If
not, the example still runs with fallback placeholder logic.

## Validation Checklist

- [ ] Initial, seabed, and hydrate temperatures are finite.
- [ ] The hydrate equilibrium temperature came from a validated NeqSim calculation.
- [ ] The time constant came from a validated lumped or distributed model.
- [ ] No-hydrate-risk and in-region cases are tested.
- [ ] The hydrate margin and verdict bands are documented as configurable public
      guidelines only.
- [ ] Results are not used as a design no-touch time or an operating limit.
- [ ] Real cooldown work is redirected to validated NeqSim methods and qualified
      flow assurance review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| No-touch time looks generous but hydrates form early | Time constant underestimated (insulation too optimistic) | Use a validated U-value and lumped/distributed cooldown model |
| Verdict always `no_hydrate_risk` | Hydrate temperature below seabed or omitted | Supply a validated NeqSim hydrate equilibrium temperature |
| No-touch time negative or undefined | Initial temperature already at or below the hydrate target | Confirm the operating point and recompute with NeqSim |

## Limitations

- Single-node lumped model only; no axial profile, no transient depressurization.
- No hydrate phase equilibrium, salinity, methanol, MEG, or kinetics here.
- No proprietary insulation data or company cooldown specifications.
- Not suitable for design no-touch time, inhibitor dosage, or operating-limit
  decisions.

## Related NeqSim Functionality

This educational screening corresponds to validated, rigorous functionality in
the NeqSim Java library that a qualified engineer should use for design-grade
work:

- `neqsim.pvtsimulation.flowassurance.SurfCooldownAnalyzer` — couples a live
  fluid to a lumped cooldown engine, auto-extracts density, specific heat, and
  the hydrate equilibrium temperature, and reports the no-touch time and verdict.
- `neqsim.pvtsimulation.flowassurance.PipelineCooldownCalculator` — lumped
  layer/U-value cooldown engine with time-to-temperature and time-constant
  outputs.
- `neqsim.thermodynamicoperations.ThermodynamicOperations#hydrateFormationTemperature()`
  — rigorous hydrate equilibrium temperature.

In Python the same classes are reachable through the `neqsim` package (for
example `from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- DNV-RP-F109, On-bottom stability / thermal design background (public guidance).
- API RP 17A, Subsea production systems (public scope background).
