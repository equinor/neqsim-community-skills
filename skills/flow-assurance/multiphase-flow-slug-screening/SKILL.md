---
name: neqsim-multiphase-flow-slug-screening
version: "0.1.0"
description: "Educational multiphase slug-flow regime and slug-catcher volume screening. USE WHEN: a task needs a public, screening-level indicator of whether a multiphase line is in an intermittent/slug regime and a first-pass slug-catcher volume estimate before validated multiphase flow analysis."
last_verified: "2026-06-19"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Multiphase Flow Slug Screening

Use this skill for public, educational multiphase slug-flow screening. It gives a coarse flow-regime indicator from superficial gas and liquid velocities and a first-pass slug-catcher volume estimate from slug geometry, so an agent can flag slug risk before moving to validated multiphase flow analysis.

## When to Use

- When a user asks whether a multiphase line is likely to be in a slug regime.
- When an agent needs a quick slug-catcher volume order-of-magnitude to scope a flow-assurance study.
- When examples must run without confidential pipeline geometry, project flow-assurance reports, or company multiphase guidelines.

## Inputs

- `superficial_gas_velocity`: superficial gas velocity in m/s.
- `superficial_liquid_velocity`: superficial liquid velocity in m/s.
- `pipe_internal_diameter`: pipe inside diameter in m.
- `slug_length_to_diameter`: slug length expressed as a multiple of the diameter, default 30.0.
- `liquid_holdup_in_slug`: liquid holdup in the slug body, dimensionless in (0, 1], default 0.8.
- `surge_factor`: surge/safety factor on slug-catcher volume, default 1.2.
- `available_slug_catcher_volume`: optional available slug-catcher volume in m3 for a capacity check.

## Outputs

- `mixture_velocity_m_per_s`: sum of the superficial gas and liquid velocities.
- `froude_number`: mixture Froude number using the pipe inside diameter.
- `liquid_fraction`: liquid superficial velocity divided by the mixture velocity.
- `flow_regime_indicator`: coarse public regime label (gas-dominated, slug, liquid-dominated, transition).
- `estimated_slug_volume_m3`: screening slug volume from slug geometry and holdup.
- `recommended_slug_catcher_volume_m3`: slug volume scaled by the surge factor.
- `capacity_ratio`: recommended over available slug-catcher volume when an available volume is given.
- `slug_warning`: `ok`, `watch`, or `high`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `SlugScreeningModel` uses open, published concepts only:

- the mixture velocity is the sum of the superficial gas and liquid velocities, and the Froude number uses the pipe inside diameter as the length scale.
- the flow-regime indicator is a coarse public heuristic over Froude number and liquid fraction. It is not a validated flow-pattern map.
- the slug volume is slug length times pipe area times liquid holdup, with a surge factor giving the recommended slug-catcher volume.
- when an available slug-catcher volume is provided, the capacity ratio drives rule-based warnings; otherwise a slug regime is flagged as `watch`.

This is educational and screening-only logic. It is not a validated flow-pattern map, not a slug-catcher design method, and not a replacement for validated multiphase flow analysis and a qualified flow-assurance review.

## Python Usage Pattern

```python
from multiphase_flow_slug_screening import SlugScreeningModel

model = SlugScreeningModel()
result = model.evaluate(
    superficial_gas_velocity=4.0,
    superficial_liquid_velocity=1.0,
    pipe_internal_diameter=0.3,
    available_slug_catcher_volume=1.0,
)

print(result.flow_regime_indicator)
print(result.recommended_slug_catcher_volume_m3)
print(result.slug_warning)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim multiphase pipe flow analysis. If it is not installed, the example still runs with public placeholder logic.

## Validation Checklist

- [ ] Velocities and diameter are in SI units.
- [ ] Example inputs are public and synthetic.
- [ ] Tests cover slug, capacity, and invalid-input cases.
- [ ] Results are described as educational screening indicators.
- [ ] Real slug-catcher sizing is redirected to validated multiphase flow methods and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Regime label looks wrong | Superficial velocities taken at the wrong conditions | Evaluate superficial velocities at line pressure and temperature |
| Slug volume too small | Slug length-to-diameter set too low for terrain slugging | Use a length-to-diameter consistent with the line profile and terrain |
| Capacity check missing | No available slug-catcher volume provided | Pass `available_slug_catcher_volume` for a capacity ratio |

## Limitations

- No validated flow-pattern map (Beggs and Brill, Taitel-Dukler) is applied.
- No terrain, severe, or hydrodynamic slugging dynamics are modelled.
- No transient slug tracking or slug frequency is computed.
- Not suitable for safety-critical, design, guarantee, or standards-compliance work.

## Related NeqSim Functionality

This educational screening corresponds to validated, rigorous functionality in the NeqSim Java library that a qualified engineer should use for design-grade work:

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — rigorous multiphase pressure drop, holdup, and flow-regime evaluation.
- `neqsim.process.equipment.separator.ThreePhaseSeparator` — slug-catcher / inlet-separation modelling for liquid handling.

In Python the same classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Public multiphase flow references such as the Beggs and Brill correlation, the Taitel-Dukler flow-pattern map, and NORSOK P-001/P-002 for general multiphase line concepts.
