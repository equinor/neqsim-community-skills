---
name: neqsim-vacuum-collapse-screening
version: "0.1.0"
description: "Educational vacuum-collapse (implosion) screening for a blocked-in vessel that cools down, with vacuum-depth and external-rating flags. USE WHEN: a task needs a public, screening-level check of whether a closed vessel cooldown or steam/vapour condensation can pull a vacuum below the external pressure rating, without proprietary vacuum-collapse design methods."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Vacuum Collapse Screening

Use this skill for public, educational vacuum-collapse (external-pressure implosion) screening examples. When a vessel is blocked in and cools down, the trapped vapour contracts and any condensable vapour (for example steam) condenses, so the internal pressure can fall below atmospheric and pull a vacuum. This skill provides a simple final-pressure estimate, a vacuum-depth indicator, and an external-rating flag that help agents structure early reverse-pressure questions before moving to a validated NeqSim constant-volume cooldown model and a vessel external-pressure (buckling) review.

## When to Use

- When a user asks for a quick, public vacuum-collapse triage for a blocked-in vessel.
- When an agent needs a placeholder estimate of how deep a cooldown or condensation vacuum could be.
- When examples must run without confidential vessel geometry, external-pressure ratings, or company vacuum design bases.

## Inputs

- `initial_pressure`: starting pressure in bara.
- `initial_temperature`: starting temperature in C.
- `cold_end_temperature`: final cooled temperature in C (must be below the initial temperature).
- `condensable_fraction`: fraction of the initial vapour that condenses on cooldown, 0.0 to 1.0, default 0.0.
- `external_pressure_rating`: vessel external-pressure (vacuum) rating in bara, default 0.0 for full vacuum.
- `atmospheric_pressure`: atmospheric pressure in bara, default 1.01325.

## Outputs

- `estimated_final_pressure_bara`: ideal-gas constant-volume final pressure after cooldown and condensation.
- `vacuum_depth_bar`: amount the final pressure sits below atmospheric, in bar (0.0 when no vacuum).
- `margin_to_rating_bar`: final pressure minus the external-pressure rating; negative means the rating is exceeded.
- `vacuum_present`: `True` when the final pressure is below atmospheric.
- `exceeds_rating`: `True` when the final pressure falls below the external-pressure rating.
- `verdict`: `no_vacuum`, `vacuum_within_rating`, or `vacuum_exceeds_rating`.
- `collapse_warning`: `ok`, `watch`, or `high`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `VacuumCollapseModel` uses open placeholder calculations only:

- the non-condensing pressure drop uses the ideal-gas constant-volume relation `P2 = P1 * (T2 / T1)` for a rigid, blocked-in vessel.
- any `condensable_fraction` is removed from the vapour, scaling the final pressure by `(1 - condensable_fraction)` as a screening proxy for steam or vapour condensation.
- the vacuum depth is the atmospheric pressure minus the final pressure, floored at zero.
- the rating margin is the final pressure minus the external-pressure rating, and a negative margin sets the exceeds-rating flag.
- warnings combine a vacuum-present indicator with the exceeds-rating flag.

This is educational and screening-only logic. It is not an external-pressure (buckling) standard, a vessel design method, a vendor method, or a replacement for a validated NeqSim constant-volume cooldown model and a code external-pressure review (for example ASME BPVC Section VIII external pressure).

## Python Usage Pattern

```python
from vacuum_collapse_screening import VacuumCollapseModel

model = VacuumCollapseModel()
result = model.evaluate(
    initial_pressure=1.8,
    initial_temperature=120.0,
    cold_end_temperature=20.0,
    condensable_fraction=0.85,
    external_pressure_rating=0.5,
)

print(result.verdict)
print(result.estimated_final_pressure_bara)
print(result.vacuum_depth_bar)
print(result.margin_to_rating_bar)
print(result.collapse_warning)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to the validated NeqSim `VacuumCollapseAnalyzer`, which performs a real constant-volume (TVflash) cooldown of the actual fluid, tracks condensation, and reports a cooling curve and make-up gas requirement. If it is not installed, the example still runs with public placeholder logic.

## Validation Checklist

- [ ] Pressures and temperatures are positive and the cold-end temperature is below the initial temperature.
- [ ] The condensable fraction is between 0.0 and 1.0.
- [ ] Example inputs are public and synthetic.
- [ ] Tests cover normal, vacuum, exceeds-rating, and invalid-input cases.
- [ ] Results are described as educational screening indicators.
- [ ] Real vacuum-collapse design is redirected to a validated NeqSim constant-volume cooldown model and a code external-pressure review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Treating `estimated_final_pressure_bara` as a design vacuum | Ideal-gas placeholder ignores real-fluid condensation and make-up | Use the NeqSim `VacuumCollapseAnalyzer` constant-volume cooldown model |
| Missing deep vacuum on steam systems | `condensable_fraction` left at 0.0 for a condensing vapour | Set a realistic condensable fraction or use the rigorous model |
| Ignoring external-pressure rating | `external_pressure_rating` not provided | Confirm the vessel external-pressure (vacuum) rating before screening |
| Assuming a vacuum breaker removes the risk | Make-up or vacuum-relief device not credited in screening | Verify vacuum relief sizing in the validated workflow |

## Limitations

- No proprietary vessel geometry, external-pressure rating, or project vacuum design bases are included.
- No real-fluid condensation, multi-phase behaviour, or make-up gas flow is modelled.
- No shell buckling, stiffener, or out-of-roundness external-pressure calculation is performed.
- Not suitable for safety-critical, design, guarantee, or standards-compliance work.

## Related NeqSim Functionality

This educational screening corresponds to validated, rigorous functionality in the NeqSim Java library that a qualified engineer should use for design-grade work:

- `neqsim.process.safety.vacuum.VacuumCollapseAnalyzer` — constant-volume (TVflash) cooldown of a blocked-in vessel, vacuum-depth versus external rating, cooling curve, and make-up gas requirement.
- `neqsim.process.safety.vacuum.VacuumCollapseResult` — structured result with the cooling curve, verdict, and JSON export.

In Python the same classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Public external-pressure references such as ASME BPVC Section VIII Division 1 (external pressure / vacuum) for general vacuum-collapse concepts.
