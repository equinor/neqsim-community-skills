---
name: neqsim-gas-turbine-performance-screening
version: "0.1.0"
description: "Educational gas-turbine performance screening using open ISO 3977 / GL1029 style derate factors. USE WHEN: a task needs a public, screening-level estimate of site-rated shaft power, site heat rate, thermal efficiency, fuel heat input, exhaust mass flow, and exhaust temperature for a gas-turbine driver before detailed package selection."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Gas Turbine Performance Screening

Use this skill for public, educational gas-turbine performance screening. It corrects an ISO base rating for ambient temperature, site elevation, and inlet/exhaust pressure losses to estimate site-rated shaft power, site heat rate, thermal efficiency, fuel heat input, exhaust mass flow, and exhaust temperature so an agent can scope a driver-selection study before detailed package review.

## When to Use

- When a user asks how much power a gas-turbine driver makes at site conditions versus its ISO rating.
- When an agent needs a quick site heat rate, fuel heat input, or exhaust mass flow estimate for waste-heat or HRSG scoping.
- When examples must run without confidential vendor performance maps or company package specs.

## Inputs

- `iso_base_power_kw`: ISO base-load shaft power rating in kW.
- `iso_heat_rate_kj_kwh`: ISO base-load heat rate in kJ/kWh.
- `ambient_temperature_k`: site ambient temperature in kelvin, default 288.15 (ISO reference).
- `site_elevation_m`: site elevation above sea level in m, default 0.
- `relative_humidity`: site relative humidity fraction, default 0.6 (small effect).
- `inlet_pressure_loss_mbar`: inlet system pressure loss in mbar, default 10.
- `exhaust_pressure_loss_mbar`: exhaust system pressure loss in mbar, default 10.
- `required_shaft_power_kw`: optional driven-equipment shaft power in kW for the margin check.

## Outputs

- `site_power_kw`: derated site shaft power.
- `ambient_derate_factor`: ambient-temperature power factor.
- `altitude_derate_factor`: site-elevation power factor.
- `pressure_loss_derate_factor`: combined inlet/exhaust pressure-loss power factor.
- `total_derate_factor`: product of all derate factors.
- `site_heat_rate_kj_kwh`: site heat rate after efficiency degradation.
- `thermal_efficiency`: shaft thermal efficiency from the site heat rate.
- `fuel_heat_input_kw`: fuel lower-heating-value heat input.
- `exhaust_mass_flow_kg_s`: screening exhaust mass flow.
- `exhaust_temperature_k`: screening exhaust temperature.
- `power_margin_ratio`: site power divided by required shaft power, or `null`.
- `power_warning`: `ok`, `watch`, `insufficient-power`, or `no-rating`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `GasTurbinePerformanceModel` uses open performance-derate relations only:

- ambient derate uses `f_amb = 1 - 0.007 (T_amb - 288.15)`, clamped at zero.
- altitude derate uses `f_alt = 1 - 1.1e-4 * elevation`, from reduced barometric pressure.
- pressure-loss derate uses `f_inlet = 1 - 0.002 * dP_inlet` and `f_exhaust = 1 - 0.001 * dP_exhaust`.
- site power uses `P_site = P_iso * f_amb * f_alt * f_inlet * f_exhaust * f_humidity`.
- site heat rate uses `HR_site = HR_iso (1 + 0.5 (1 - f_total))` so efficiency falls with derate.
- fuel heat input uses `Q_fuel = P_site * HR_site / 3600`.
- exhaust mass flow uses a fixed specific-flow factor `m_exh = P_site * 0.003`.

This is educational and screening-only logic. It assumes linear derates, a fixed specific exhaust flow, and a typical exhaust temperature. It is not a replacement for validated gas-turbine performance models or qualified package review.

## Python Usage Pattern

```python
from gas_turbine_performance_screening import GasTurbinePerformanceModel

model = GasTurbinePerformanceModel()
result = model.evaluate(
    iso_base_power_kw=30000.0,
    iso_heat_rate_kj_kwh=9500.0,
    ambient_temperature_k=303.15,
    site_elevation_m=50.0,
    required_shaft_power_kw=26000.0,
)

print(result.site_power_kw)
print(result.site_heat_rate_kj_kwh)
print(result.power_warning)
```

## Related NeqSim Functionality

For validated power-generation calculations, redirect to NeqSim classes:

- `neqsim.process.equipment.powergeneration.GasTurbine` — gas-turbine driver model with fuel and exhaust calculations.
- `neqsim.process.equipment.powergeneration.HRSG` — heat-recovery steam generator using turbine exhaust.
- `neqsim.process.equipment.powergeneration.CombinedCycleSystem` — combined-cycle integration of turbine and steam systems.

This skill is a public triage layer that decides when to invoke a validated gas-turbine model.

## Validation Checklist

- [ ] ISO base power and heat rate are positive.
- [ ] Ambient temperature is positive and elevation is non-negative.
- [ ] Tests cover ambient derate, the power margin, the fuel/efficiency estimate, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real driver selection is redirected to validated NeqSim power-generation classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Site power above ISO rating | Ambient below 288.15 K | Screening caps uprate; treat sub-ISO gains conservatively |
| Power margin missing | No required shaft power supplied | Provide `required_shaft_power_kw` for the margin check |
| Exhaust flow looks flat | Fixed specific-flow factor used | Use a validated gas-turbine model for HRSG sizing |

## Limitations

- No proprietary vendor performance maps, fuel composition effects, or company specs are included.
- Derates are linear screening factors; part-load, water injection, and DLE effects are not modelled.
- Exhaust mass flow and temperature use fixed screening assumptions, not a heat-and-mass balance.

## References

- ISO 3977, Gas turbines — Procurement.
- ISO 2314, Gas turbines — Acceptance tests.
- NeqSim repository: https://github.com/equinor/neqsim
