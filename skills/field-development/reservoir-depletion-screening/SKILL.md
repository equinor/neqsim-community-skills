---
name: neqsim-reservoir-depletion-screening
version: "0.1.0"
description: "Educational reservoir tank-depletion vs time screening with gas/oil and water-cut evolution. USE WHEN: a task needs a public, screening-level pressure-decline and production profile over time from a recoverable volume and offtake rate before detailed NeqSim SimpleReservoir or reservoir-engineering modelling."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reservoir Depletion Screening

Use this skill for a quick, public screening of how a reservoir develops with
time. Given a recoverable volume, an offtake rate, and an initial and
abandonment pressure, it produces a year-by-year profile of reservoir pressure,
cumulative production, recovery factor, water cut, and hydrocarbon/water rates.
It is intentionally simple and should guide users toward the validated NeqSim
`SimpleReservoir` tank model (`runTransient`) and the NeqSim MCP `runReservoir`
workflow for real depletion behaviour.

## When to Use

- When a user wants a first look at how reservoir pressure declines over field life.
- When an early production/decline profile is needed before a reservoir model exists.
- When an agent needs an upstream "reservoir vs time" feed for a production-routing
  or arrival-pressure screening chain.

## Inputs

- `fluid_type`: `gas` or `oil`.
- `initial_pressure_bara`: reservoir pressure at start of production.
- `abandonment_pressure_bara`: pressure at which production stops (screening).
- `recoverable_volume_sm3`: recoverable hydrocarbon volume at standard conditions.
- `offtake_rate_sm3_per_day`: constant screening offtake (hydrocarbon) rate.
- `years`: number of years to simulate.
- `time_step_years`: time-step size (default 1.0 year).
- `initial_water_cut_fraction`: water cut at start (default 0).
- `water_cut_rise_per_year`: linear water-cut rise per year (default 0).

## Outputs

- `steps`: per-step `year`, `pressure_bara`, `cumulative_production_sm3`,
  `recovery_factor`, `water_cut_fraction`, `hydrocarbon_rate_sm3_per_day`,
  `water_rate_sm3_per_day`, and `depleted` flag.
- `final_pressure_bara`, `final_recovery_factor`.
- `plateau_years`: years before production can no longer be sustained (or `None`).
- `years_to_abandonment`: first year the reservoir reaches abandonment (or `None`).
- `depletion_warning`: `ok`, `watch`, or `high`.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

Reservoir pressure declines linearly with recovery factor between the initial
and abandonment pressure: `P = Pi - (Pi - Pabn) * (Gp / Vrec)`. Cumulative
production `Gp` accrues at the constant offtake rate each step until the
recoverable volume is reached or the abandonment pressure is hit. Water cut
follows a supplied linear trend, and the water rate is derived from the
hydrocarbon rate and the water-cut fraction. The verdict is `high` once the
reservoir is depleted, `watch` past a configurable recovery-factor threshold,
otherwise `ok`.

This skill performs no PVT, aquifer, injection, or coning physics. It is a
transparent placeholder that must be replaced by a validated NeqSim reservoir
tank model for any quantitative use.

## Python Usage Pattern

```python
from reservoir_depletion_screening import ReservoirDepletionModel

model = ReservoirDepletionModel()
result = model.evaluate(
    fluid_type="gas",
    initial_pressure_bara=300.0,
    abandonment_pressure_bara=80.0,
    recoverable_volume_sm3=20.0e9,
    offtake_rate_sm3_per_day=8.0e6,
    years=15,
    initial_water_cut_fraction=0.05,
    water_cut_rise_per_year=0.03,
)

for step in result.steps:
    print(step.year, step.pressure_bara, step.recovery_factor, step.water_cut_fraction)
print(result.depletion_warning)
```

## Validated NeqSim Path

This screening is a placeholder. For real reservoir-vs-time behaviour use:

- NeqSim `SimpleReservoir` with `addGasProducer` / `addOilProducer` /
  `addWaterInjector` / `addGasInjector` and a `runTransient(deltat)` time loop.
- NeqSim MCP `runReservoir` for an orchestrated reservoir tank simulation.
- The enterprise `well-production-routing-agent` for live-data, IPR + tubing,
  and Beggs & Brills arrival modelling.

## Escalation

Escalate any `watch` or `high` verdict, and any quantitative use, to a validated
NeqSim reservoir model and qualified reservoir-engineering review.

## Validation Checklist

- [ ] Inputs are validated and within stated ranges.
- [ ] Examples use public data only.
- [ ] Screening assumptions are stated explicitly.
- [ ] Limitations are respected.
- [ ] Quantitative use is escalated to validated NeqSim models.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Unrealistic result | Inputs outside the screening range | Keep inputs within the stated bounds |
| Misused for design | Screening output taken as final | Escalate to validated NeqSim models |

## Limitations

- Educational screening only; not a validated design method.
- No confidential data or proprietary methods are included.
- Escalate any quantitative or design use to validated NeqSim workflows.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
