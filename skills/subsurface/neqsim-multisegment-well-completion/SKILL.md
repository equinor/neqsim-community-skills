---
name: neqsim-multisegment-well-completion
calculation_basis: "hybrid"
version: "0.1.0"
description: "Multi-segment well completions with inflow-control devices: adds plain WELSEGS/COMPSEGS to standard wells, writes the completor case (AICD, spiral ICD, nozzle valve, DAR/density) and runs equinor/completor to an OPM/Eclipse deck; OPM device equations with NeqSim phase properties; zonal water and gas change at equal oil. USE WHEN: screening AICD/ICD/DAR completions or building a multi-segment deck."
last_verified: "2026-11-15"
requires:
  python_packages: [completor, matplotlib, neqsim]
  java_packages: []
  env: []
  network: []
---

# Multi-Segment Well Completion (AICD, ICD, Valve, DAR)

Use this skill to put inflow-control devices into a reservoir simulation deck and to screen what they do. It wraps [completor](https://github.com/equinor/completor) (LGPL-3.0), which turns a completion description and an Eclipse/OPM schedule into a multi-segment well with tubing, device and annulus layers. It evaluates the devices with the same equations OPM Flow uses, taking phase properties from NeqSim.

Three things it does that completor does not:
- It gives standard wells (WELSPECS and COMPDAT only) a plain multi-segment description first, because completor needs WELSEGS and COMPSEGS.
- It checks the design before completor runs: undefined device numbers, bad annulus codes, zero-length intervals.
- It tells you what the devices do to oil, water and gas before you spend a simulation run on them.

## When to Use

- Capacity-increase or production-acceleration screening of AICD, AICV-like, ICD or DAR completions on oil-rim, gas-cap or water-coning wells.
- Building an OPM Flow or Eclipse multi-segment deck with devices for a reservoir-simulation comparison, bare well against devices.
- Checking a vendor or inflow-control-team device parameter set: does it choke gas or water relative to oil at the expected rate per device?
- Converting a screening deck's standard wells to multi-segment wells.

Do not use it to qualify a device or to choose a vendor; device parameters must come from the vendor or the inflow-control team.

## Inputs

Config for `<python> -m msw_completion run config.json`:

- `deck`: the `.DATA` file or a schedule file (read only; outputs go to `out_dir`). Only the SCHEDULE section is processed; RUNSPEC gets a WSEGDIMS entry when needed.
- `add_plain_msw`: `auto` (default; only when the deck has no WELSEGS), `true` or `false`. `msw`: `wells`, `diameter_m`, `roughness_m`. Supported grids are block-centred cartesian (DXV/DYV/DZV or DX/DY/DZ with TOPS). For corner-point grids, call `add_plain_msw(..., cell_centres=f)` with cell centres from the grid file.
- `design`: the completion.
  - `completion` rows: `well`, `branch`, `start_md`, `end_md`, `screen_diameter_m`, `casing_diameter_m`, `roughness_m`, `annulus` (`GP` gravel pack or no annular flow, `OA` open annulus, `PA` packer with zero length), `devices_per_joint`, `device_type` (`PERF`, `AICD`, `ICD`, `VALVE`, `DENSITY`), `device_number`.
  - Device tables with `number` and fields:
    - `aicd`: `strength` (completor alpha), `x`, `y`, `a`–`f`, `rho_cal`, `mu_cal`, `z`;
    - `icd` (spiral): `strength`, `rho_cal`, `mu_cal`, `critical_value`;
    - `valve`: `cv`, `ac`, `ac_max`;
    - `density` (DAR): `cv`, `ac_oil`, `ac_gas`, `ac_water`, `wvf_low`, `wvf_high`, `gvf_low`, `gvf_high`.
  - Optional `joint_length_m` (default 12), `segment_length`, `use_strict`, `gp_perf_devicelayer`.
- `parameter_source` (required): where the device parameters come from, for example a vendor datasheet and revision, or `illustrative`. Without it the run is blocked; with `illustrative` every result carries a do-not-plan warning.
- Phase properties at device conditions:
  - `phase_properties` (oil, water and gas density in kg/m3 and viscosity in cP), or
  - `fluid` for NeqSim: `components` or `e300`, `temperature_c`, `pressure_bara`, optional `fallback` for a phase that does not form, and optional `water` (brine density and viscosity).
- `calibrate` (optional): `device`, `design_rate_rm3_day`, `design_dp_bar`. This scales the AICD or ICD strength to a design point and keeps the exponents.
- `check_rate_rm3_day`: rate per device for the single-phase check.
- `zones` and `screening` (optional): zones with `productivity_index` (rm3/day/bar, total reservoir rate), `water_fraction`, `gas_fraction`, `devices`; screening with `device`, `bare_drawdown_bar` and `max_drawdown_bar`.

## Outputs

`well_completion_evidence.v1` (`completion_evidence.json`), always `unverified`:
- `status` (`ok` or `blocked`), `missing`, `warnings`, `parameter_source`, sources and the phase properties used;
- `plain_msw`: connections and MD range per converted well;
- `device_layer` per well: segments, branches, device segments by type, and per device segment the MD, strength, exponents and the number of devices (from completor's scale factor `-1/N`; valves report the segment Cv, which completor multiplies by N);
- `device_check`: pressure drop for pure oil, water and gas at the check rate, and the water/oil and gas/oil ratios;
- `screening`: bare and device inflow per zone, the extra drawdown for the same oil, and the water and gas change. It warns when devices push more flow into a gas or water zone;
- `calibration`, `required_checks`.

Files in `out_dir`: `<deck>_MSW.DATA` (plain multi-segment), `completor.case`, `<deck>_COMPLETOR.DATA` (devices), `device_curves.png`.

## Engineering Method

1. **Plain multi-segment well.** One tubing segment per connection, in COMPDAT order. Measured depth runs along the connection cell centres. A horizontal first connection starts at its centre depth; a vertical one starts at its top. Segment bounds are the midpoints between centres. WSEGDIMS is set to 4 segments and 3 branches per connection plus margin, because the device and annulus layers multiply both.
2. **completor** runs in-process (`completor.main.create`) on the SCHEDULE section; its log messages are collected as warnings and not printed. completor applies `devices_per_joint × segment length / joint length` devices to each segment.
3. **Device equations** (OPM Flow `MultisegmentWellSegments`, METRIC units, rate q per device in rm3/day, dP in bar):
   - AICD: `dP = S rho_mix (rho_mix/rho_cal)^z (mu_cal/mu_mix)^y q^x`, with `rho_mix = fo^a rho_o + fw^b rho_w + fg^c rho_g` and `mu_mix = fo^d mu_o + fw^e mu_w + fg^f mu_g`.
   - Spiral ICD: `dP = S (rho/rho_cal)^0.75 (mu/mu_cal)^0.25 q^2`, where the liquid viscosity is OPM's water-in-oil / oil-in-water emulsion viscosity around `critical_value` (transition width 0.05, viscosity ratio capped at 5).
   - Valve: `dP = rho v^2 / (2 Cv^2)`, `v = q/Ac`; pipe friction is excluded.
   - DAR / density device: a valve with the oil, water or gas area, switched at `wvf_high` and `gvf_high`. completor writes this as ACTIONX switches with hysteresis between the low and high thresholds; the steady screening uses the closing thresholds.
4. **Phase properties.** Oil and gas come from a NeqSim TP flash of the hydrocarbon fluid with multiphase check and `initProperties()`. Water comes from a pure-water CPA flash, because cubic EOS without volume correction underpredicts liquid water density by about 20 %. Pass `water` for brine.
5. **Zonal screening.** Each zone has packers and its own devices. The zone rate solves `drawdown = q/PI + dP_device(q/N)`, and the drawdown with devices is raised until the oil rate matches the bare completion. Phase fractions per zone are fixed, so the result is the immediate re-allocation between zones, not delayed breakthrough.

## Python Usage Pattern

```python
from msw_completion import Aicd, PhaseProperties, Zone, compare_at_same_oil, single_phase_drops

props = PhaseProperties(oil_density=690, water_density=980, gas_density=230,
                        oil_viscosity=0.29, water_viscosity=0.25, gas_viscosity=0.028)
aicd = Aicd(strength=5.7e-6, x=3.0, y=1.2)          # from the vendor, not from this example
print(single_phase_drops(aicd, 7.5, props))          # gas/oil and water/oil choking ratios
zones = [Zone("heel", 40, 0.0, 0.6, devices=60), Zone("toe", 40, 0.5, 0.0, devices=60)]
print(compare_at_same_oil(zones, aicd, props, bare_drawdown_bar=6, max_drawdown_bar=60)["gas_change_fraction"])
```

Deck route: `<python> -m msw_completion run config.json` prints `status`, device segments per well and the water and gas change; it exits with 2 when blocked. `<python> -m msw_completion devices <deck>` summarises the device layer of any completor deck.

## Validation Checklist

- [ ] `parameter_source` names a vendor or inflow-control-team source; `illustrative` results are not used for decisions.
- [ ] `device_check`: the gas/oil and water/oil ratios are above 1 for an AICD meant to choke gas or water. If not, the parameters do not do what the design intends.
- [ ] `device_layer`: device count per segment is consistent with joint length and `devices_per_joint`.
- [ ] No WSEGDIMS warning; the deck runs in OPM Flow or Eclipse, and the bare multi-segment deck reproduces the standard-well deck before devices are compared.
- [ ] Plain-MSW measured depths are replaced by the planned trajectory where one exists.
- [ ] Water properties are brine values when salinity matters.

## Common Mistakes

- Comparing the device deck with the standard-well deck. Compare it with the plain multi-segment deck instead, so that the segment hydraulics are the same in both.
- Reading completor's `STRENGTH` as per segment. It is per device; the scale factor `-1/N` divides the segment rate by N devices.
- Taking `a`–`f` = 1 because they are defaults. With linear mixing, a gas-oil mixture can see a lower drop than oil, so the AICD does not choke a coning zone. Use the vendor exponents.
- Using a cubic-EOS aqueous density for water (around 20 % low; enters squared in the AICD drop).
- Treating the zonal screening as a forecast. It holds phase split fixed; run the decks.
- Letting `add_plain_msw` chain the laterals of a multilateral well. It makes one tubing path through all COMPDAT cells in listed order, so lateral 2 flows through lateral 1. For multilaterals write one branch per lateral (WELSEGS with branch numbers, all outlets at a shared node, COMPSEGS with the branch number) and give each branch its own `COMPLETION` row (the Grimsnes task did this in a task script, `61_msw_build.py`).
- Reading a device gain from a homogeneous model. In flat homogeneous layers the inflow along a lateral is already even and devices only add drawdown (Grimsnes: -0.2 to -0.5 RF points); the gain appears only with permeability streaks, so run the device and the bare multi-segment well in the same streak field (lognormal multipliers per block and row) before drawing a conclusion.
- Valuing devices on a short horizon. Devices defer gas (and add water); a 10-year NPV that sells gas penalises them, the 20-year NPV does not. Rerun the key cases on the full horizon.
- Calling completor from an interpreter that lacks it. In the Grimsnes setup it lived in the user site-packages of the system Python; append that folder to `sys.path` rather than installing at run time.

## Limitations

- Screening: device parameters, zone productivity and phase fractions are inputs; there is no device qualification.
- Plain multi-segment conversion supports cartesian block-centred grids; corner-point grids need cell centres from the grid file.
- Steady screening ignores the hysteresis of density-switched devices, pipe friction in valves, and the maximum-rate limits.
- completor features not exposed in the config (ICV control, dual-RCP, injection valves, lateral routing) can be used by writing the case file directly.

## References

- equinor/completor (LGPL-3.0), documentation "Configuration" (COMPLETION, JOINTLENGTH, SEGMENTLENGTH and device keywords): https://equinor.github.io/completor/
- OPM Flow source, `opm/simulators/wells/MultisegmentWellSegments.cpp` (`pressureDropAutoICD`, `pressureDropSpiralICD`) and `MSWellHelpers.cpp` (emulsion viscosity); OPM keyword definitions WSEGAICD and WSEGSICD (item order and units): https://github.com/OPM
- Related skills:
  - `neqsim-capacity-increase-screening`: lever ranking; NeqSim's `InflowControlCompletion` gives the same-oil comparison inside a process model.
  - `neqsim-opm-open-reservoir-decks` and `neqsim-near-well-and-injectivity`: running OPM Flow and the inflow basis.
  - `neqsim-vfp-lift-curves`: lift curves for the same wells.
  - `neqsim-reservoir-model-builder`: the deck the wells sit in.
