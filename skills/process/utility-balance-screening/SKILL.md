---
name: neqsim-utility-balance-screening
version: "0.1.0"
description: "Educational utility-balance screening for instrument air demand, fuel gas Wobbe index, and cooling water duty/flow with a simple capacity margin roll-up (NORSOK U-001 / ISA-7.0.01 style). USE WHEN: a task needs a public, screening-level estimate of instrument air demand, cooling water flow, fuel gas Wobbe index compliance, and utility capacity utilisation before detailed utility-system design."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Utility Balance Screening

Use this skill for public, educational utility-system screening. It estimates instrument air demand, cooling water flow from a duty and a cooling-water temperature rise, a fuel gas Wobbe index with a band check, and a simple capacity utilisation roll-up so an agent can scope a utility study before detailed design.

## When to Use

- When a user asks how much instrument air a set of consumers needs or whether the air/cooling supply is large enough.
- When an agent needs a quick cooling-water flow estimate from a heat duty and a permitted temperature rise.
- When a fuel gas Wobbe index must be screened against a sales/fuel band without confidential gas data.
- When examples must run without proprietary utility loads, vendor data, or company specs.

## Inputs

- `instrument_air_consumers`: number of instrument air consumers (integer count).
- `air_per_consumer_nm3_h`: average free-air demand per consumer in Nm3/h, default 0.3.
- `cooling_duty_kw`: total cooling duty to reject in kW, default 0.
- `cooling_water_delta_t_c`: permitted cooling-water temperature rise in degrees C, default 10.
- `fuel_gas_lhv_mj_sm3`: optional fuel gas lower heating value in MJ/Sm3.
- `fuel_gas_relative_density`: optional fuel gas relative density (air = 1).
- `wobbe_min`: lower Wobbe index band in MJ/Sm3, default 47.2.
- `wobbe_max`: upper Wobbe index band in MJ/Sm3, default 51.41.
- `instrument_air_capacity_nm3_h`: optional installed instrument air capacity in Nm3/h.
- `cooling_water_capacity_m3_h`: optional installed cooling water capacity in m3/h.

## Outputs

- `instrument_air_demand_nm3_h`: consumer count multiplied by per-consumer demand and a design margin.
- `cooling_water_flow_m3_h`: cooling water flow from the duty and the temperature rise.
- `wobbe_index_mj_sm3`: fuel gas Wobbe index, or `null` if no fuel gas data is supplied.
- `wobbe_in_band`: `True`/`False` if a Wobbe index is computed, otherwise `null`.
- `air_utilisation`: demand divided by installed air capacity, or `null`.
- `cooling_utilisation`: flow divided by installed cooling capacity, or `null`.
- `utility_warning`: `ok`, `watch`, `air-undersized`, or `cooling-undersized`.
- `wobbe_warning`: `ok`, `wobbe-out-of-range`, or `no-fuel-data`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `UtilityBalanceModel` uses open utility relations only:

- instrument air demand uses `Q_air = N * q_consumer * margin` with a 1.3 design margin.
- cooling water flow uses `Q_cw = duty * 3600 / (rho * cp * dT)` with `rho = 1000 kg/m3` and `cp = 4.18 kJ/kg.K`, giving m3/h.
- the Wobbe index uses `W = LHV / sqrt(relative_density)` and is flagged inside or outside `[wobbe_min, wobbe_max]`.
- capacity utilisation uses `demand / capacity` for air and cooling when a capacity is supplied.

This is educational and screening-only logic. It assumes incompressible cooling water with constant properties, a fixed air design margin, and a single fuel gas Wobbe band. It is not a replacement for validated utility-system balances or qualified utility design.

## Python Usage Pattern

```python
from utility_balance_screening import UtilityBalanceModel

model = UtilityBalanceModel()
result = model.evaluate(
    instrument_air_consumers=120,
    cooling_duty_kw=2500.0,
    cooling_water_delta_t_c=10.0,
    fuel_gas_lhv_mj_sm3=39.0,
    fuel_gas_relative_density=0.62,
    instrument_air_capacity_nm3_h=60.0,
    cooling_water_capacity_m3_h=250.0,
)

print(result.instrument_air_demand_nm3_h)
print(result.cooling_water_flow_m3_h)
print(result.wobbe_index_mj_sm3)
print(result.utility_warning)
```

## Related NeqSim Functionality

For validated utility specification and balances, redirect to NeqSim resources:

- the `neqsim-utilities-specification` skill — steam levels, cooling water, instrument air, fuel gas, and nitrogen specification guidance.
- `neqsim.standards.gasquality.Standard_ISO6976` — validated calorific value and Wobbe index per ISO 6976.
- proposed `enterprise-utility-systems-review` — consolidated utility duty roll-up and capacity check; candidate enterprise extension.

This skill is a public triage layer that decides when to invoke a validated utility balance.

## Validation Checklist

- [ ] Consumer count is a non-negative integer and per-consumer demand is positive.
- [ ] Cooling duty is non-negative and the cooling-water temperature rise is positive.
- [ ] Fuel gas LHV and relative density are supplied together or not at all.
- [ ] Tests cover air demand, cooling flow, a Wobbe band check, capacity utilisation, and invalid input.
- [ ] Real utility design is redirected to validated NeqSim resources and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Wobbe index missing | Only one of LHV / relative density supplied | Provide both fuel gas values |
| Cooling flow far too high | Temperature rise set very low | Use a realistic cooling-water `dT` |
| Utilisation is null | No installed capacity supplied | Provide air/cooling capacity to get a ratio |

## Limitations

- No proprietary utility loads, vendor data, or company specifications are included.
- Cooling water uses constant incompressible-water properties; no fouling or approach is modelled.
- A single Wobbe band is used; no full ISO 6976 composition calculation is performed.

## References

- NORSOK U-001, Subsea production systems / utility system requirements.
- ISA-7.0.01, Quality Standard for Instrument Air.
- ISO 6976, Natural gas — Calculation of calorific values, density, relative density and Wobbe indices.
- NeqSim repository: https://github.com/equinor/neqsim
