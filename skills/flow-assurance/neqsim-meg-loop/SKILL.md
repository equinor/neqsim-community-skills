---
name: neqsim-meg-loop
calculation_basis: "hybrid"
version: "0.1.0"
description: "MEG hydrate-inhibition loop screening with NeqSim (SRK-CPA): lean MEG rate to meet a hydrate margin at the design pressure and coldest temperature, rich MEG and Hammerschmidt cross-check, MEG losses, regeneration water, reboiler temperature and duty, salt build-up and reclaimer slipstream, and lean-quality trade-off. USE WHEN: sizing MEG injection or regeneration for a gas tie-back."
last_verified: "2026-11-22"
requires:
  python_packages: [neqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# MEG Loop

A gas tie-back inhibited with MEG is a closed loop: lean MEG goes subsea,
rich MEG comes back with the produced water, the water is boiled off and the
lean MEG is reused. Sizing it needs three linked answers: how much lean MEG
keeps the coldest point out of hydrates, how much heat the regenerator needs,
and whether formation-water salts will build up in the loop. This skill gets
all three from one NeqSim SRK-CPA model of the well stream.

## When to Use

- Sizing lean MEG injection for a new well or a tie-in to an existing MEG
  system (is the existing pump and regeneration capacity enough?).
- Checking how formation-water breakthrough changes regeneration duty and
  salt handling.
- Comparing lean MEG concentrations (80, 85, 90 wt %).
- Not for continuous kinetic or anti-agglomerant inhibitors, or methanol.

## Inputs

- `WellStream(components, flow_rate, flow_unit="MSm3/day",
  pseudo_components=[], formation_water_m3_d=0, formation_water_tds_mg_l=0)`:
  NeqSim component names on a molar basis, without MEG. Include condensed
  water as `water` (saturated gas). C7+ as `(name, amount, kg/mol, g/cm3)`.
- `HydrateDesign(pressure_bara, min_temperature_c, margin_c=3,
  arrival_pressure_bara=50, arrival_temperature_c=20)`: the coldest
  high-pressure point (often settle-out after shut-in at seabed temperature)
  and the arrival separator.
- `Regeneration(lean_meg_wt=0.90, regenerator_pressure_bara=1.2,
  rich_feed_temperature_c=80, reclaimer_slipstream=0, salt_limit_wt=0.05,
  loop_inventory_m3=100, lean_alternatives=(0.80, 0.85))`. The 5 wt % salt
  limit is a screening value; use the project limit.

## Outputs

`MegReport` with `results`:

- `uninhibited_hydrate_c`, `inhibited_hydrate_c`, `required_depression_c`.
- `free_water_kg_h` (condensed plus formation water), `lean_meg_kg_h`,
  `lean_meg_m3_d`.
- `rich_meg_wt_pct` and `hammerschmidt_wt_pct` (cross-check),
  `meg_loss_kg_d` (dissolved in gas and hydrocarbon liquid).
- `water_evaporated_kg_h`, `reboiler_temperature_c`, `reboiler_duty_kw`.
- `salt_in_kg_d`, `steady_salt_wt_pct`, `min_slipstream_pct`,
  `days_to_salt_limit`.

`alternatives` holds the injection, rich MEG and duty for each other lean
concentration. `findings` codes: `no-inhibition-needed`,
`target-not-reached`, `hammerschmidt-deviation`, `high-rich-meg`,
`salt-accumulation`, `divalent-salts`, `meg-losses`. `to_markdown()` and
`to_dict()` give a report and JSON.

## Engineering Method

1. **Well stream.** A NeqSim `Stream` converts the rate to component molar
   rates; formation water is added as pure water.
2. **Injection rate.** SRK-CPA (Statoil, mixing rule 10) system with the
   whole stream plus lean MEG; `hydrateFormationTemperature()` at the design
   pressure; bisection on the lean MEG rate until the hydrate temperature
   equals the coldest temperature minus the margin.
3. **Rich MEG and losses.** Multiphase TP flash at arrival; the aqueous
   phase gives rich MEG wt %, MEG in the other phases is the loss.
   Hammerschmidt (K = 1297, M = 62.07) for the same depression is the
   cross-check.
4. **Regeneration.** Water boiled off = rich water minus lean water. The
   reboiler temperature is the CPA bubble point of lean MEG at the
   regenerator pressure; the duty is the NeqSim enthalpy difference between
   rich feed and lean product plus water vapour at reboiler temperature.
   Reflux, condenser and pump work are not included.
5. **Salts.** Salt in = formation water x TDS (all salts assumed to stay in
   the loop). With a fraction `f` of lean MEG through a reclaimer that
   removes all salt, steady-state salt = salt in / (f x lean rate). The
   minimum `f` keeps it under the limit; without reclaiming the inventory
   reaches the limit after limit x inventory / salt in.

## Python Usage Pattern

```python
from meg_loop import HydrateDesign, Regeneration, WellStream, assess_meg_loop

stream = WellStream(
    {"methane": 85, "ethane": 6, "propane": 3, "n-butane": 1,
     "CO2": 2, "nitrogen": 1, "water": 0.6},
    flow_rate=8.0, formation_water_m3_d=20.0, formation_water_tds_mg_l=60000.0)
design = HydrateDesign(pressure_bara=150.0, min_temperature_c=4.0, margin_c=3.0,
                       arrival_pressure_bara=60.0, arrival_temperature_c=15.0)
report = assess_meg_loop(stream, design, Regeneration(reclaimer_slipstream=0.3))
print(report.to_markdown())
```

`examples/gas_tieback_meg_loop.py` runs a full case in about 25 s.

## Validation Checklist

- [ ] The design point is the coldest point at the highest pressure it can
      see (shut-in, settle-out, restart), not normal operation.
- [ ] Water includes condensed water and the formation-water forecast.
- [ ] Rich MEG is within a few wt % of Hammerschmidt below about 50 wt %;
      larger gaps were understood.
- [ ] The salt limit and slipstream come from the project basis.
- [ ] Reboiler duty was compared with the regeneration package (add reflux
      and losses).

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| No MEG needed for a wet gas | `water` missing from the stream | Add condensed water (saturated gas) and formation water |
| `target-not-reached` | Margin too large or lean MEG too weak | Raise lean concentration, combine with insulation or heating |
| Duty does not change with lean wt % | It is set by the water to evaporate, which is the produced water | Expected; lean wt % changes pump rate and inventory |
| Salt limit reached in days | High-TDS formation water with no reclaiming | Full or partial reclaimer, or water management |
| `MEG` in the well stream raises an error | MEG is the injected inhibitor | Give the stream without MEG |

## Limitations

- Thermodynamic hydrate equilibrium only; no kinetics, no salt effect on
  the hydrate curve (conservative), no hydrate plug risk analysis.
- Salt balance assumes all salts stay dissolved and the reclaimer removes
  all salt in its feed; divalent-ion scaling and pH stabilisation are not
  modelled.
- Regenerator is an enthalpy balance, not a column model.
- Screening only; does not replace a flow assurance design basis or a
  vendor regeneration design.

## Related NeqSim Functionality

- `SystemSrkCPAstatoil`, `ThermodynamicOperations#hydrateFormationTemperature()`,
  `#bubblePointTemperatureFlash()`.
- Core skill `neqsim-flow-assurance` for hydrate curves and inhibitor
  checks; community skills `neqsim-hydrate-margin-check`,
  `neqsim-co2-corrosion-profile` (MEG lowers the CO2 corrosion rate),
  `neqsim-active-learning-surrogate` (MEG rate over uncertain water and
  temperature).

## References

- Hammerschmidt, E.G. (1934). Formation of gas hydrates in natural gas
  transmission lines. Ind. Eng. Chem. 26, 851-855.
- Sloan, E.D., Koh, C.A. (2008). Clathrate Hydrates of Natural Gases, 3rd ed.
- NORSOK P-002 Process system design.
- NeqSim repository: https://github.com/equinor/neqsim
