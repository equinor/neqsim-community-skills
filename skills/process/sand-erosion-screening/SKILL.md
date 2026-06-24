---
name: neqsim-sand-erosion-screening
version: "0.1.0"
description: "Educational sand-erosion and remaining-wall-life screening for solids-bearing lines. USE WHEN: a task needs a public, screening-level estimate of sand erosion rate, cumulative wall loss, and remaining wall life from a sand production rate before detailed DNV RP O501 erosion analysis."
last_verified: "2026-05-20"
requires:
  python: ">=3.10"
  neqsim: optional
---

# Sand Erosion Screening

Educational screening of solids (sand) erosion for production and flowline piping.
The skill estimates an erosional-velocity ratio, a simplified sand erosion rate,
the cumulative wall loss over a design life, the remaining wall thickness, and a
remaining-life indicator. It is a public, screening-level placeholder for learning
and workflow scaffolding only — it does not implement the validated DNV RP O501
erosion model.

## When to Use

- Early sand-management screening when a sand production rate is known or assumed.
- Triaging whether a solids-bearing line warrants a detailed DNV RP O501 erosion study.
- Teaching the link between sand rate, flow velocity, and remaining wall life.
- Building agent or notebook scaffolding before validated erosion calculations.

Do not use this skill for design, fitness-for-service, integrity, or sand-rate
allowable decisions. Use the validated NeqSim `ErosionPredictionCalculator`
(DNV RP O501) and qualified engineering review for those.

## Inputs

| Input | Unit | Notes |
| --- | --- | --- |
| `fluid_velocity` | m/s | Mixture flow velocity at line conditions |
| `mixture_density` | kg/m3 | Flowing mixture density at line pressure and temperature |
| `pipe_diameter` | m | Internal diameter of the line |
| `wall_thickness` | mm | Nominal wall thickness |
| `sand_rate` | kg/day | Solids (sand) production rate; defaults to 0 (no sand) |
| `corrosion_allowance` | mm | Wall reserved for corrosion; default 3.0 |
| `material_factor` | – | Relative material erosion resistance; default 1.0 (carbon steel) |
| `design_life_years` | yr | Design life used for cumulative loss; default 25 |
| `c_factor` | – | API RP 14E SI C constant; default 122 |

## Outputs

| Output | Unit | Meaning |
| --- | --- | --- |
| `erosional_velocity_m_per_s` | m/s | API RP 14E erosional velocity `Ve = C / sqrt(rho)` |
| `velocity_ratio` | – | `fluid_velocity / erosional_velocity` |
| `erosion_rate_mm_per_yr` | mm/yr | Screening sand erosion rate |
| `cumulative_erosion_mm` | mm | Erosion rate times design life |
| `usable_wall_mm` | mm | Wall thickness minus corrosion allowance |
| `remaining_wall_mm` | mm | Usable wall minus cumulative erosion |
| `remaining_life_years` | yr | Usable wall divided by erosion rate (None when no sand) |
| `erosion_warning` | – | `ok`, `watch`, or `high` |

## Engineering Method

1. Erosional velocity is estimated from the public API RP 14E form
   `Ve = C / sqrt(rho)`, with the SI continuous-service constant near 122.
2. The velocity ratio compares the flowing velocity to the erosional velocity.
3. A transparent screening proportionality estimates the sand erosion rate:

   $$
   \dot{e} = k \, f_\mathrm{mat} \, \frac{\dot{m}_\mathrm{sand} \, v^2}{D^2}
   $$

   where $k$ is a public screening coefficient (not a DNV RP O501 constant),
   $f_\mathrm{mat}$ is a material factor, $\dot{m}_\mathrm{sand}$ is the sand
   rate, $v$ the velocity, and $D$ the pipe diameter.
4. Cumulative erosion is the erosion rate times the design life; the remaining
   wall is the usable wall (thickness minus corrosion allowance) minus the
   cumulative erosion.
5. Remaining life is the usable wall divided by the erosion rate.
6. The warning is the more severe of a velocity-ratio band (watch above 0.8,
   high above 1.0) and a remaining-life band (watch below the design life, high
   below half the design life).

## Python Usage Pattern

```python
from sand_erosion_screening import SandErosionModel

result = SandErosionModel().evaluate(
    fluid_velocity=12.0,
    mixture_density=120.0,
    pipe_diameter=0.1524,
    wall_thickness=12.7,
    sand_rate=50.0,
    corrosion_allowance=3.0,
    material_factor=1.0,
    design_life_years=25.0,
)

print(result.erosion_rate_mm_per_yr)
print(result.remaining_wall_mm)
print(result.remaining_life_years)
print(result.erosion_warning)
```

## Validation Checklist

- [ ] Mixture density is evaluated at the flowing line pressure and temperature.
- [ ] The sand rate reflects a realistic or conservative solids production estimate.
- [ ] The corrosion allowance is consistent with the line specification.
- [ ] The material factor reflects the actual pipe material.
- [ ] Screening results are confirmed with the NeqSim `ErosionPredictionCalculator`.
- [ ] A qualified engineer reviews any integrity or sand-allowable conclusion.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Erosion rate looks too high or low | Velocity or density at the wrong conditions | Use flowing velocity and density at line conditions |
| Remaining life is `None` | Sand rate is zero | Provide a non-zero sand rate for an erosion estimate |
| Warning never triggers | Sand rate or velocity unrealistically low | Use a conservative sand rate and design velocity |
| Results treated as design values | Screening coefficient is educational | Use DNV RP O501 via NeqSim for design |

## Limitations

- No proprietary erosion models, sand-monitoring data, or company integrity specs.
- The erosion coefficient is a transparent public placeholder, not DNV RP O501.
- No particle-size, geometry-specific (elbow, tee, choke), or impact-angle effects.
- No transient, slug, or intermittent sand-burst behaviour is captured.
- Not suitable for safety-critical, design, guarantee, or standards-compliance work.

## Related NeqSim Functionality

This educational screening corresponds to validated, rigorous functionality in the
NeqSim Java library that a qualified engineer should use for design-grade work:

- `neqsim.pvtsimulation.flowassurance.ErosionPredictionCalculator` — validated
  API RP 14E and DNV RP O501 erosion model with sand rate, erosion rate,
  cumulative erosion, remaining wall thickness, and risk level.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — rigorous multiphase
  pressure drop and velocity profile to source the erosional velocity inputs.

In Python the same classes are reachable through the `neqsim` package (for example
`from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Public erosion references such as API RP 14E and DNV RP O501 for general sand-erosion concepts.
