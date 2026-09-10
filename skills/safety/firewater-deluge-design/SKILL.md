---
name: neqsim-firewater-deluge-design
calculation_basis: "screening"
version: "0.1.0"
description: "Educational fire-water and deluge coverage screening: area versus dedicated object demand, deluge nozzle-net sizing from both the flow and the spacing criterion, and fire-monitor screening with wind drift. USE WHEN: a task asks whether a process area has adequate fire-water coverage, how many deluge nozzles are needed, or whether monitors or passive fire protection can substitute for a fixed system."
last_verified: "2026-09-10"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Fire-water and Deluge Coverage Design

Use this skill for public, educational fire-water coverage screening. It turns a protected
area and an application rate into a water demand, a nozzle count and a grid pitch, and it
tests the two alternatives that get proposed whenever a fixed deluge net is inconvenient:
protecting the individual items instead of the area, and using fire monitors instead of a
fixed system.

## When to Use

- A verification finding says an area lacks active fire protection and the demand must be scoped.
- A modification adds hydrocarbon-bearing equipment to an area and the fire-water demand changes.
- Somebody proposes fire monitors, or passive fire protection, in place of deluge.
- You need a first nozzle count and grid pitch before a hydraulic network calculation.

## Inputs

- `protected_area_m2`: plan area for general area coverage, m².
- `area_rate_lpm_per_m2`: application rate, (l/min)/m². Public minima are 10 for process
  areas and equipment surfaces and 20 for wellhead areas and riser balconies.
- `objects`: tuple of `(tag, surface_area_m2, rate_lpm_per_m2)` for dedicated protection.
- `duration_min`, `foam_concentrate_percent`, `simultaneous_area_factor`.
- Nozzle: `nozzle_k_lpm_per_sqrt_bar`, `nozzle_min_pressure_barg`, `max_spacing_m`,
  `operating_pressure_barg`, `coverage_efficiency`.
- Monitor: `monitor_count`, `monitor_flow_lpm`, `wind_speed_m_s`, `fall_height_m`,
  `characteristic_dimension_m`, `line_of_sight_obstructed`.

## Outputs

- `area_demand_lpm`, `object_demand_lpm`, `total_demand_lpm`, `total_demand_m3_per_h`,
  `water_volume_m3`, `foam_concentrate_m3`, `object_to_area_ratio`.
- `nozzle_count_from_flow`, `nozzle_count_from_coverage`, `nozzle_count`,
  `governing_criterion`, `grid_spacing_m`, `delivered_density_lpm_per_m2`,
  `pressure_adequate`, `density_met`.
- `nominal_density_lpm_per_m2`, `drift_displacement_m`, `wind_coverage_fraction`,
  `effective_density_lpm_per_m2`, `verdict`.
- `assumptions` on every result.

## Engineering Method

The Python class `FireWaterCoverageModel` uses open, published relations only.

- Demand is the application rate times the protected area, plus the sum of dedicated
  object surfaces times their rates, times a simultaneous-release factor.
- Nozzle discharge follows the orifice law $Q = K\sqrt{p}$ with $K$ in
  $(\mathrm{l/min})/\sqrt{\mathrm{bar}}$.
- The nozzle count is the **larger** of the flow criterion (total discharge must meet the
  density) and the coverage criterion (area divided by the square of the maximum permitted
  spacing). Sizing on flow alone is the classic error: it gives too few, too widely spaced
  nozzles that meet the average density but leave dry patches.
- Monitor droplets are drifted downwind by $\Delta x = h\,u_{\mathrm{wind}}/v_t$, and the
  coverage loss is taken as linear in the drift over the characteristic target dimension.
- Shadowing is a flag, not a model: a monitor cannot wet a surface it cannot see.

## Interpretation

- `object_to_area_ratio` well below 1 means selective protection of the hydrocarbon-bearing
  items is far cheaper in water than blanket coverage. Whether it is *permitted* is a
  requirement question, not a hydraulic one — the area-coverage requirement in NORSOK S-001
  and ISO 13702 is written against the area.
- `governing_criterion == "coverage"` means the nozzle net is set by spray overlap, so a
  higher-K nozzle will not reduce the count.
- `verdict == "marginal_wind_limited"` means the monitor concept only works in still air.

## Limitations

- Screening only. It performs no network hydraulics, no trajectory modelling and no CFD.
- It does not decide compliance. Application rates, durations and the acceptability of
  selective protection come from the governing project standard and the accepted deviations.
- It gives no credit for, and takes no credit from, passive fire protection. Fire water and
  passive fire protection are complementary barriers, and the regulatory rule runs one way:
  passive protection may not be reduced because active protection exists.

## Related Skills

- `neqsim-jet-fire-radiation-screening` and `neqsim-relief-load-screening` — the fire side.
- `neqsim-depressurization-screening` — inventory removal, the primary barrier for a
  pressurised system.
- `neqsim-safety-function-coverage-screening` — whether the protective functions exist at all.
