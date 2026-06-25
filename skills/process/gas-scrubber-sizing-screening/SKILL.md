---
name: neqsim-gas-scrubber-sizing-screening
version: "0.1.0"
description: "Educational gas-scrubber sizing screening using the public Souders-Brown / K-factor relation for vertical separators with a mist-eliminator gas-load check. USE WHEN: a task needs a public, screening-level estimate of the Souders-Brown velocity, required vessel diameter, velocity utilisation, and mist-eliminator load for a vertical gas scrubber before detailed separator design."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Gas Scrubber Sizing Screening

Use this skill for public, educational gas-scrubber (vertical separator) sizing screening. It estimates the Souders-Brown maximum gas velocity, the required vessel diameter, the velocity utilisation against an existing diameter, and a mist-eliminator gas-load check so an agent can scope a separator-sizing study before detailed design.

## When to Use

- When a user asks what diameter a vertical gas scrubber needs or whether an existing vessel is large enough.
- When an agent needs a quick Souders-Brown velocity and mist-eliminator load estimate.
- When examples must run without confidential vessel data, vendor internals data, or company specs.

## Inputs

- `gas_mass_flow_kg_s`: gas mass flow in kg/s.
- `gas_density_kg_m3`: gas density in kg/m3.
- `liquid_density_kg_m3`: liquid density in kg/m3.
- `k_factor_m_s`: Souders-Brown K-factor in m/s, default 0.107.
- `vessel_inside_diameter_m`: optional existing vessel inside diameter; if given it is checked, otherwise the required diameter is sized.
- `mist_eliminator_k_factor`: mist-eliminator K-factor in m/s, default 0.12.
- `demister_present`: whether a mist eliminator is installed, default `True`.

## Outputs

- `souders_brown_velocity_m_s`: maximum gas velocity `v_max`.
- `gas_volumetric_flow_m3_s`: actual gas volumetric flow `Q`.
- `required_area_m2`: required cross-sectional area `Q / v_max`.
- `required_diameter_m`: required vessel inside diameter.
- `actual_velocity_m_s`: actual gas velocity at the given diameter, or `null`.
- `velocity_utilisation`: actual velocity divided by `v_max`, or `null`.
- `gas_load_factor`: effective K-factor from the actual velocity, or `null`.
- `demister_velocity_limit_m_s`: mist-eliminator Souders-Brown limit.
- `demister_utilisation`: gas velocity divided by the demister limit, or `null`.
- `sizing_warning`: `ok`, `watch`, `undersized`, or `oversized`.
- `demister_warning`: `ok`, `watch`, `mist-eliminator-overloaded`, or `no-demister`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `GasScrubberSizingModel` uses open separator-sizing relations only:

- Souders-Brown velocity uses `v_max = K sqrt((rho_l - rho_g) / rho_g)`.
- gas volumetric flow uses `Q = mdot / rho_g`.
- required area uses `A = Q / v_max` and required diameter uses `D = sqrt(4 A / pi)`.
- when a diameter is given, actual velocity uses `v = Q / (pi/4 * D^2)`, velocity utilisation uses `v / v_max`, and the effective K-factor uses `v / sqrt((rho_l - rho_g) / rho_g)`.
- the demister limit uses `v_demister = K_mist sqrt((rho_l - rho_g) / rho_g)`, and demister utilisation uses `v / v_demister`.

This is educational and screening-only logic. It assumes a vertical vessel with uniform gas velocity, ignores inlet-device performance, liquid handling, and settling-section detail, and is not a replacement for validated separator sizing or qualified review.

## Python Usage Pattern

```python
from gas_scrubber_sizing_screening import GasScrubberSizingModel

model = GasScrubberSizingModel()
result = model.evaluate(
    gas_mass_flow_kg_s=8.0,
    gas_density_kg_m3=45.0,
    liquid_density_kg_m3=700.0,
    vessel_inside_diameter_m=1.2,
)

print(result.souders_brown_velocity_m_s)
print(result.velocity_utilisation)
print(result.sizing_warning)
print(result.demister_warning)
```

## Related NeqSim Functionality

For validated separator sizing, redirect to NeqSim classes:

- `neqsim.process.equipment.separator.Separator` — process separator with gas/liquid split and performance.
- `neqsim.process.mechanicaldesign.separator.SeparatorMechanicalDesign` — separator mechanical design, gas-load factor, and retention time.
- `neqsim.process.mechanicaldesign.separator.internals.DemistingInternal` — mist-eliminator Souders-Brown limit and carry-over model.
- `neqsim.process.equipment.separator.GasScrubberDesign` — proposed dedicated gas-scrubber sizing model; candidate NeqSim gap.

This skill is a public triage layer that decides when to invoke a validated separator-sizing model.

## Validation Checklist

- [ ] Gas and liquid densities are positive and `rho_l > rho_g`.
- [ ] K-factors and mass flow are positive.
- [ ] Tests cover sizing without a diameter, an undersized vessel, a demister-overload case, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real sizing is redirected to validated NeqSim separator classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Velocity utilisation above 1 | Vessel diameter too small | Increase the diameter or reduce throughput |
| Mist eliminator overloaded | Demister K-factor exceeded | Add a larger demister or reduce velocity |
| Utilisation missing | No `vessel_inside_diameter_m` supplied | Use `required_diameter_m` as the size |

## Limitations

- No proprietary vessel data, vendor internals data, or company specs are included.
- Inlet-device performance, liquid handling, and settling-section detail are not modelled.
- A single Souders-Brown K-factor is used for the gas-capacity check.

## References

- GPSA Engineering Data Book, Section 7, Separators and Filters.
- API Recommended Practice 12J, Specification for Oil and Gas Separators.
- NeqSim repository: https://github.com/equinor/neqsim
