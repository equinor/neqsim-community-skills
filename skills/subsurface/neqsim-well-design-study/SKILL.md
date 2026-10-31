---
name: neqsim-well-design-study
calculation_basis: "screening"
version: "0.2.0"
description: "Screening well design study and report: pore/fracture window, casing seats and kick tolerance, casing and tubing design (API TR 5C3), erosional-velocity screening, torque and drag, ECD, offset-well calibration, time and cost P10/P50/P90, fail-closed validation and a Word report. USE WHEN: a concept or pre-FEED well design, casing or kick-tolerance review, or well time and cost range is needed, especially with offset wells."
last_verified: "2026-10-31"
requires:
  python_packages: ["numpy"]
  optional_python_packages: ["matplotlib", "python-docx", "pandas"]
  java_packages: []
  env: []
  network: []
---

# Well Design Study

A reusable, offset-well-aware workflow for a **screening** well design study and its report. It turns a pressure basis, a planned (or proposed) casing programme and offset-well evidence into a checked design: window and seats, casing strings, completion screening, drilling feasibility, time and cost range, a standards register and a validation list. Detailed design stays in the operator's well-design and casing-design software; this skill frames the concept, checks a design that already exists in those tools, and prepares the evidence and the report.

## When to Use

- Exploration, appraisal or development well at concept or pre-FEED stage needs a casing programme, kick-tolerance check, time and cost range or a design report.
- A planned programme (for example a "dry case" and a "discovery case" design) must be sanity-checked against offset-well strength tests and mud weights.
- A reservoir fluid and well deliverability model needs a tubing, wellhead and barrier basis (see `neqsim-subsea-and-wells`, `neqsim-near-well-and-injectivity`).
- Do **not** use it for final design, rig selection, safety-critical or regulatory work, relief-well or HPHT qualification.

## Inputs

1. **Reference**: RKB elevation (air gap), water depth, TD (MD, TVD), vertical or deviated path, target and fluids.
2. **Pressure basis**: pore (low/base/high) and fracture (low/base/high) EMW curves against TVD. Build them from the prospect estimate (reservoir pressure, depth, regional trend) and calibrate to offset wells (`calibration_points`, `envelope`).
3. **Planned programme**: sections with hole size, casing OD, top and shoe TVD/MD, mud weight, top of cement, grades to try.
4. **Kick basis**: kick intensity (sg), influx density (sg), required kick tolerance (m3).
5. **Offset evidence tables** (CSV in one folder, filled from public regulator data and well reports or by hand): `offset_casing_lot.csv`, `offset_mud_weight.csv`, `offset_pressure_temp.csv`, `offset_time_depth.csv`, `offset_problems.csv`, `offset_documents.csv`.
6. **Completion basis** (producer): shut-in wellhead pressure from the NeqSim fluid and reservoir pressure, tubing candidates, rates, packer fluid, maximum temperature.

## Outputs

- Mud-weight window versus depth with planned mud weights, shoes and offset points (`window_plot`).
- Kick tolerance per section; bottom-up seat proposal (`propose_seats_bottom_up`).
- Casing-string selection with burst, collapse, tension and triaxial design factors and the governing load case (`select_string`).
- Wellhead pressure class, tubing velocity versus erosional and Turner limits (`tubing_table`).
- Torque and drag envelope and ECD versus flow (`torque_drag_envelope`, `circulation`).
- Time and cost P10/P50/P90 with the contributors (`monte_carlo`).
- Validation checks, standards register and a Word report (`run_well_study`, `report.WellReport`).

## Engineering Method

1. **Evidence first.** Collect offset data (LOT/FIT at each shoe, mud weight versus depth, pressure tests, kicks, losses, stuck pipe, days per section). Tag each datum with a tier (public regulator data, final well report, internal system, analyst estimate). Empty tables are a result: record them as data gaps.
2. **Pressure model.** Pore curves from the prospect estimate and offsets (low/base/high); fracture curves from LOT points (LOT = estimate, FIT = lower bound) with a matrix-stress (Eaton) fallback and an overburden trend. Window = [pore high + trip margin, fracture low - margin].
3. **Seats and kick tolerance.** Single-bubble gas kick with the shoe at the fracture pressure; formation pressure = (mud + kick intensity) hydrostatic at the section bottom. Bottom-up seat proposal, and a section-by-section check of the planned programme.
4. **Casing design.** API TR 5C3 collapse (yield, plastic, transition, elastic), Barlow burst, body yield; load cases gas kick (gas to surface, capped at shoe fracture), tubing leak, pressure test, evacuation; triaxial von Mises with Lame stresses; temperature derating of yield (assumption). Lightest catalogue pipe that passes all design factors.
5. **Completion screening.** Erosional velocity (API RP 14E, C factor), Turner unloading, tubing thermal force and ballooning checks, wellhead class from the maximum surface pressure.
6. **Drilling feasibility.** Soft-string torque and drag with friction ranges, sinusoidal buckling margin, Bingham ECD and pump pressure.
7. **Time and cost.** Section times and NPT events as lognormal P10/P50/P90 from offsets (or planned days), rate and materials uncertainty, Monte Carlo with reported correlations.
8. **Fail-closed validation.** Published-rating cross-check, geometry, window, kick tolerance and design-factor checks; any failed check blocks a ready label.
9. **Report.** Answer first; basis; offsets used and not used; window and seats; casing; completion; drilling; time and cost; risks; assumptions and gaps; standards register; validation; every figure with provenance.

## Python Usage Pattern

```python
from well_design_study import (run_well_study, load_evidence, calibration_points, monte_carlo, SectionTime, NptEvent, CostBasis,
                               normalise_casing_rows, normalise_wellbore_rows, write_table, check_tubing)

rows = normalise_casing_rows(raw_rows, well_info, source="regulator table", date_text="2026-10-31")   # fractional inches, none/LOT/FIT, TVD basis
write_table(rows, "casing_lot", "offset_wells")
evidence = load_evidence("offset_wells")             # CSV tables, empty list when a file is missing
points = calibration_points(evidence, well_refs, {"rkb_m": 25.0, "water_depth_m": 300.0})   # rebased to equal depth below the seabed
results = run_well_study(spec)                        # window, plan, strings, checks, standards register
mc = monte_carlo([SectionTime("17.5 in", 6, 9, 16)], [NptEvent("losses", 0.3, 1, 3, 8)], CostBasis(3.2, 140.0, 110.0), common_sigma=0.3)
```

Study spec options that matter on a real case:

* Sections: `casing_od_in: None` for the final open-hole section; `riserless: true` for conductor and top-hole (no kick tolerance, window in mud weight below the seabed); `shoe_strength_sg` for a planned or measured FIT/LOT; `production: true` for the string that carries the shut-in wellhead pressure; `fixed_pipe` to check an existing design; `string_top_tvd_m` for a liner hanger; `evacuation_basis` (`fraction` or `pore_balance`) and `evacuation_external` (`mud_or_pore` or `set_cement`).
* Kick: `kick.basis` is `"pore"` (formation pressure = pore + intensity, recommended when mud is well above pore pressure) or `"mud"` (legacy: mud + intensity, very conservative with heavy mud). Report both when the basis of a planned design is unknown.
* Pore curves: build from pressure points with `hydrostatic_pressure_bar` and `emw_curve_from_pressure_points` (pressure builds from mean sea level, not from the rotary table).
* Tubing: `check_tubing` (shut-in and evacuated cases, annulus fluid outside); casing strings use `check_string` / `select_string`.
* Drilling: `torque_and_drag(..., tortuosity_deg_per_30m=0.3)` so that a vertical well does not return zero torque.
* Time: calibrate `common_sigma` so that the productive-time P10-P90 spread equals the offsets; use only offsets without recorded NPT for productive time and the event frequency for NPT; exclude sidetrack rows (days after kick-off only).

Figures: `well_design_study.figures` (`window_plot` with `extras`, `schematic`, `design_factor_plot`, `time_depth_plot`, `histogram_plot(units=...)`, `line_plot`). Report: `well_design_study.report.WellReport` (title page, table of contents, numbered tables and figures, provenance lines, `callout`, `landscape`/`portrait`, `appendix`, coloured status labels such as `[VERIFIED]`, `[DERIVED]`, `[ASSUMED]`).

## Validation Checklist

- [ ] 9-5/8 in 47 ppf N80 reproduces the published 4 760 psi collapse and 6 870 psi burst within 2 percent (built-in check).
- [ ] Depth references stated (RKB, TVDSS, MSL) and EMW computed against RKB TVD consistently with the offset tables.
- [ ] Every planned mud weight lies in the window of its section, or the section is flagged.
- [ ] Kick tolerance meets the requirement at every riser-connected shoe.
- [ ] Every casing string has a passing catalogue pipe, with the governing load case named.
- [ ] Offset data labelled by tier; LOT and FIT not mixed; unverified numbers marked.
- [ ] Assumption register and data-gap register filled; no number without a status label.
- [ ] Report states what was not modelled and who must confirm each item.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Window looks too wide | Offset LOT at a different datum or in a different mud system | Convert all EMW to the same RKB TVD reference; use FIT as a lower bound only |
| Kick tolerance negative | Shoe too shallow for the section pore pressure | Move the seat down, reduce kick intensity only with evidence, or add a liner |
| Casing selection changes with the temperature | Yield derating is an assumption | Use vendor high-temperature derating or HPHT qualification data |
| Burst governed by gas to surface | Shoe fracture cap not applied to the last string | Set `cap_gas_at_frac` only where the shoe is at a leak-off limit; the production string sees reservoir pressure |
| Time estimate too narrow | Offset NPT not included, or sections treated as independent | Add NPT events from offset problem frequency and a common performance factor (`common_sigma`) calibrated to the offset spread |
| Kick tolerance far below a planned design | Legacy mud-based kick convention with mud well above pore pressure, or a different hole section assumed per table row | Use `kick.basis = "pore"`, report both conventions, state the reading of the planned design's rows and do not tune to agree |
| Riserless window or kick tolerance fails at the conductor | Window judged as EMW at RKB depth; kick tolerance asked where no shut-in exists | Flag the section `riserless`; the window is converted to mud weight below the seabed under a seawater head |
| Hydrostatic pore EMW looks too high near the seabed | Normal gradient applied from the rotary table | Build pore curves with `hydrostatic_pressure_bar` (pressure from mean sea level) |
| Liner collapse fails by a wide margin | Fixed 50 percent evacuation with the mud column outside | Use `evacuation_basis = "pore_balance"` and compare `evacuation_external = "set_cement"`; confirm in the company casing tool |
| Zero torque in a vertical well | Perfectly straight survey | Add a tortuosity allowance (0.2 - 0.5 deg per 30 m) |
| Days per 1000 m of 5 | Sidetrack row (days after kick-off only) mixed with full wells | Exclude sidetracks from time statistics |
| Strength trend scattered | Offsets at different RKB and water depth, FIT mixed with LOT, wells with a different overpressure regime | Rebase to equal depth below the seabed, keep FIT as lower bound, exclude other regimes (state it) |

## Limitations

- Screening level: vertical or near-vertical string loads, no wear, no cyclic or thermal-transient well-bore analysis, no wellhead growth or annular pressure build-up, no relief-well design, no cementing hydraulics, no geomechanical stability model.
- The pipe catalogue holds nominal API sizes; confirm against the vendor list. Design factors are operator-practice defaults, not code values. API TR 5C3 collapse is checked on three published ratings only; thin-wall large-diameter pipe (D/t above about 35, elastic regime) is sensitive to ovality and wall tolerance that the formula omits.
- Kick tolerance is a single gas bubble without choke-line friction or gas expansion; conventions differ between tools (pore or mud basis, kick size, pipe size) and must be stated.
- Pore and fracture curves are inputs; the skill does not interpret seismic or logs. Mud weights are never pore pressures. Eaton gradients can lie well below measured leak-off values at depth.
- Time and cost parameters are assumptions unless an offset or rig contract supplies them.

## Related NeqSim Functionality

- `neqsim.process.mechanicaldesign.subsea.WellDesignCalculator`, `WellMechanicalDesign`, `WellIntegrityScreening` and `WellCostEstimator` for casing and cost roll-ups inside process models; this skill adds offset calibration, kick tolerance, torque and drag, time/cost ranges and the report.
- Skills `neqsim-erd-reach-screening`, `neqsim-well-trajectory-anticollision` for reach and collision checks; `neqsim-near-well-and-injectivity` and `neqsim-subsea-and-wells` for inflow and production wells; `neqsim-flow-assurance` for hydrate and CO2 corrosion of the well fluid.
- NeqSim gas density at wellhead and shoe conditions gives the influx density and the shut-in wellhead pressure that load the casing.
- Companion community agent: `well-design-study-agent`.

## References

- API TR 5C3 / ISO 10400, performance properties of casing and tubing. API Spec 5CT / ISO 11960.
- NORSOK D-010, well integrity in drilling and well operations (design basis and barriers; verify the revision).
- Johancsik, Friesen, Dawson (1984), SPE 11380, torque and drag. Dawson and Paslay (1984), SPE 11167, buckling.
- Bourgoyne et al., Applied Drilling Engineering (SPE), hydraulics and well control (kick tolerance).
- Turner, Hubbard, Dukler (1969), SPE 2198, liquid loading. API RP 14E, erosional velocity.
