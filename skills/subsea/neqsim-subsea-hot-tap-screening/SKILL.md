---
name: neqsim-subsea-hot-tap-screening
calculation_basis: "screening"
version: "1.0.0"
description: "Educational screening of a mechanical-clamp hot tap on a live subsea pipeline: branch-to-run ratio, tee pressure and temperature rating, remaining wall against a hoop minimum, line velocity during cutting, hydrate margin and branch bending moment, with missing evidence reported as data gaps. USE WHEN: a tie-in concept proposes tapping an existing flowline or pipeline instead of a planned tie-in spool and needs a first go/no-go screen before a hot-tap contractor study."
last_verified: "2026-11-20"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Subsea Hot-Tap Screening

Simpler hot tapping is attractive for tie-in and clustering: a new field connects
to an existing pipeline without shutting it down or pre-installing a tee. The
decision still depends on a short list of conditions at the tap location. This
skill checks them once, with the evidence trail, so a concept can be accepted for
a contractor study or dropped early.

It addresses mechanical-clamp subsea hot taps. It is not a hot-tap procedure and
does not treat welded (topside) hot taps, where burn-through and hydrogen
cracking dominate.

## When to Use

- A tie-in or clustering concept proposes connecting into an existing live line.
- Compare candidate tap locations by pressure, temperature, wall and velocity.
- Check whether a candidate clamp rating and branch size fit the host line.
- Collect the data gaps a hot-tap contractor must close before a study starts.

## When *Not* to Use

- As a hot-tap design, procedure or qualification. These belong to the contractor,
  the clamp vendor and the governing standard.
- For welded hot taps on live hydrocarbon lines (burn-through, heat input).
- To decide on isolation, blinding or personnel safety.
- With confidential line data in a public workspace.

## Inputs

| Input | Meaning |
|---|---|
| `RunPipe` | `outer_diameter_m`, `wall_m`, `smys_mpa`, `corrosion_allowance_m`, `design_factor` |
| `HotTapTee` | `cutter_diameter_m`, `pressure_rating_bar` vs temperature table, `max_temperature_c`, `max_branch_ratio`, optional `allowable_branch_moment_knm` |
| `HotTapCase` | operating pressure and temperature, actual flow, optional cutting velocity limit, hydrate temperature and margin, cutter feed, branch weight, lever arm |

## Outputs

| Output | Contents |
|---|---|
| `HotTapResult.checks` | `branch_ratio`, `pressure_rating`, `temperature`, `remaining_wall`, `cutting_velocity`, `hydrate_margin`, `branch_moment`, `cutting_time` (info) |
| `Check` | `status` (`pass`, `fail`, `info`, `data_gap`), value, limit, unit, utilisation |
| `data_gaps`, `assumptions` | Evidence still needed, and the screening assumptions used |
| `overall` | `fail`, `incomplete` (only data gaps), or `pass` |

## Engineering Method

**Branch ratio.** Cutter diameter over run outer diameter against the clamp limit.
The default 0.5 is a screening value and is listed in the assumptions; replace it
with the vendor limit.

**Pressure and temperature.** Operating pressure against the tee rating
interpolated at the operating temperature; a table that does not cover the
temperature is a data gap. Maximum temperature is checked separately.

**Remaining wall.** Hoop minimum `t_min = P D / (2 SMYS F)` against the nominal
wall less the corrosion allowance, using the maximum pressure at the tap during
the whole operation.

**Cutting velocity.** Mean velocity from the actual volumetric flow and inner
diameter, against the vendor limit for cutting under flow.

**Hydrate margin.** Operating temperature minus the hydrate temperature at the
tap pressure (from a NeqSim flash or hydrate calculation) against a minimum
margin. Local cooling at the cutter is not modelled.

**Branch moment.** Submerged branch weight times lever arm against the allowable
moment of the tap.

**Cutting time.** Wall thickness over cutter feed rate, reported as information.

**Evidence discipline.** A check without its inputs returns `data_gap`, and the
overall verdict becomes `incomplete`, never `pass`.

## Python Usage Pattern

```python
from subsea_hot_tap_screening import HotTapCase, HotTapTee, RunPipe, screen

pipe = RunPipe(0.4064, 0.0143, 415.0, corrosion_allowance_m=0.003, design_factor=0.72)
tee = HotTapTee(
    cutter_diameter_m=0.15,
    pressure_rating_bar=((0.0, 250.0), (100.0, 200.0)),   # vendor rating vs C
    max_temperature_c=120.0,
    allowable_branch_moment_knm=30.0,
)
case = HotTapCase(
    operating_pressure_bar=100.0, temperature_c=40.0, flow_rate_m3_h=200.0,
    max_cutting_velocity_ms=3.0,
    hydrate_temperature_c=15.0,            # from a NeqSim hydrate calculation
    cutter_feed_mm_min=2.0, branch_weight_kn=10.0, lever_arm_m=1.5,
)

result = screen(pipe, tee, case)
print(result.overall, result.data_gaps)
for name, check in result.checks.items():
    print(name, check.status, check.value, check.limit, check.unit)
```

## Validation Checklist

- Wall, SMYS and corrosion allowance come from the as-built and latest inspection,
  not from the original design.
- The maximum pressure over the whole operation is used, including shut-in.
- Clamp rating table and branch limit come from the vendor, replacing the defaults.
- Hydrate temperature comes from a NeqSim calculation at the tap pressure and the
  actual fluid and inhibitor.
- Velocity is the actual flow at the tap, not the design rate.
- All `data_gaps` are closed or carried into the study as open items.
- Results are handed to the hot-tap contractor and reviewed by a qualified engineer.

## Common Mistakes

- Using the original nominal wall when the line has corroded or been inspected thinner.
- Reading the clamp rating at ambient temperature for a hot line.
- Using design flow instead of the current flow, or the shut-in pressure of the wrong case.
- Treating a missing hydrate temperature as no risk.
- Using a branch ratio limit from memory rather than the clamp vendor.
- Reading `pass` as approval to tap.

## Limitations

- Screening only; it is not a hot-tap design, procedure or qualification.
- Mechanical-clamp subsea taps only; no welding, burn-through or heat-input model.
- No area-replacement or stress analysis of the opening and clamp.
- No cutter-induced cooling, coupon retention, debris or sealing assessment.
- No dynamic loads, current loads or ROV and diver operational constraints.
- Branch moment is a static cantilever; no soil or support interaction.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Companion skills: `neqsim-flow-assurance`, `neqsim-pipeline-survey-processing`,
  `neqsim-marine-operations-weather-window`, `neqsim-open-marine-constraints`
- Public references for the downstream work: ASME B31.4 and B31.8 (pipeline
  design factors), API 1104 (welding of pipelines), DNV-ST-F101 (submarine pipeline
  systems), API 2201 (safe hot tapping practices).
