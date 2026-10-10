---
name: neqsim-erd-reach-screening
calculation_basis: "screening"
version: "0.1.0"
description: "Educational extended-reach well screening: build-and-hold path and Johancsik soft-string torque and drag, torque-limited reach versus friction and drill string, calibrated to a rig's longest historic well. USE WHEN: a task asks whether a platform or fixed-rig well can reach a target at a given horizontal departure and TVD, how reach depends on friction factor or drill-string torque rating, or how a new long-reach keeper or infill well compares with the rig's history before detailed well design."
last_verified: "2026-10-09"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# ERD Reach Screening

Use this skill for a public, screening-level answer to "can this rig reach that far?". It builds a build-and-hold well path, integrates a soft-string torque and drag model with Coulomb friction, and returns the torque-limited reach for a drill string and friction case. It is meant to be calibrated to the longest well already drilled from the same rig before any reach number is quoted.

## When to Use

- A keeper, exploration or infill well is proposed from an existing platform or fixed rig and the horizontal departure is large compared with the rig's history.
- A reach-versus-friction-factor curve is needed to turn friction uncertainty into a probability that the well can be drilled.
- A team wants to know whether a heavier or higher-torque drill string (for example 6-5/8 in) moves the reach limit enough to matter.

## Inputs

- `tvd`, `departure` in metres below the rig floor and horizontally from the slot.
- `WellEnvironment`: kick-off point, build rate (deg per 30 m), mud specific gravity, cased and open-hole friction factors, casing shoe fraction.
- `DrillString`: drill pipe, HWDP and BHA weights per metre, tool-joint radius, torque limit.

## Outputs

- `ReachResult`: measured depth, hold inclination, ERD ratio (departure over TVD), pick-up and slack-off hook load, torque on bottom, which limit binds (`torque` or `slack-off (lock-up)`).
- `reach_limit(...)`: the largest departure that keeps torque within the limit and slack-off positive.

## Method

1. Build-and-hold path from the kick-off point at a constant build rate; the hold inclination follows from the target departure.
2. Johancsik soft-string integration from the bit up: axial load changes by the buoyed weight component plus or minus friction times the contact force; torque accumulates friction times contact force times tool-joint radius.
3. Calibrate the friction factors so the model just allows the rig's longest historic well (for Njord A on the Norwegian shelf this gave 0.15 cased and 0.20 open hole, a limit about 20 percent above the 5.1 km actually drilled), then scale friction to express uncertainty.

```python
from erd_reach_screening import DrillString, WellEnvironment, reach_limit, screen_reach

env = WellEnvironment(ff_cased=0.15, ff_open=0.20)
erd_string = DrillString(name="6-5/8 in", dp_kg_per_m=49.0, tool_joint_radius_m=0.0953, torque_limit_knm=85.0)
print(reach_limit(3500.0, erd_string, env))            # torque-limited reach in metres
print(screen_reach(3500.0, 8000.0, erd_string, env).limiting)
```

## Validation Checklist

- [ ] Path closes on the target TVD and departure within 0.2 percent.
- [ ] Vertical hook load equals buoyed weight; horizontal drag equals friction times weight; weightless arc follows the capstan equation.
- [ ] Friction factors are calibrated to a real well from the same rig, not taken from a textbook.
- [ ] The result is reported as a reach envelope with a friction range, not as a single number.
- [ ] Hole cleaning, ECD, buckling, casing wear and riser limits are listed as not modelled.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Reach looks far too short or too long | Textbook friction factors used without calibration | Calibrate to the longest historic well on the rig |
| Torque limit ignored | Only slack-off checked | Report both limits; torque binds first for 5-7/8 in drill pipe |
| ERD ratio quoted as capability | Ratio taken from shallow-TVD record wells | Compare reach at the same TVD and rig, not the ratio |
| Departure from MD and TVD only | Straight-line assumption | Invert the build-and-hold path instead (`sqrt(MD^2-TVD^2)` overstates departure) |

## Limitations

- No hole cleaning, ECD, hydraulics, buckling, casing wear, vibration or riser tension.
- No rig data, vendor string data or company well design basis is included; torque limits are generic.
- Not suitable for well design, rig selection, safety-critical or regulatory work.

## Related NeqSim Functionality

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` for the long-reach tubing and riser hydraulics that decide the producing rate once the well is drilled.
- Skill `neqsim-near-well-and-injectivity` for inflow and VFP tables; `neqsim-subsea-and-wells` for well design and cost rollups.

## References

- Johancsik, C.A., Friesen, D.B., Dawson, R. (1984), Torque and drag in directional wells, SPE 11380.
- Public extended-reach records, for example the Sakhalin-1 wells reaching 11 to 12 km departure, for context on what tailored rigs achieve.
