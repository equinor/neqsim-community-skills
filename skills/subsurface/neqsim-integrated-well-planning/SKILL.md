---
name: neqsim-integrated-well-planning
calculation_basis: "hybrid"
version: "0.1.0"
description: "Integrated well planning for oil, gas-condensate, water- and gas-injection wells (onshore, platform, subsea): provenance-tracked basis, NeqSim reservoir-well-facility chain (IPR, drift-flux VLP, injectivity, hydrate, annulus pressure, tubing movement), operating envelopes, barrier schematics, alternatives, A3 drawings, hand-off schemas, report and capability ledger. USE WHEN: a well must be sized, compared or documented from reservoir, fluid, host and completion data."
last_verified: "2026-10-31"
required_skills:
  - neqsim-well-design-study
  - neqsim-near-well-and-injectivity
  - neqsim-agent-handoff
requires:
  python_packages: ["numpy", "PyYAML", "jsonschema", "matplotlib", "python-docx", "jpype1"]
  optional_python_packages: ["pyvista", "pandas", "Pillow"]
  java_packages: ["neqsim (wellplanning classes: WellboreThermalModel, DriftFluxWellboreHydraulics, GasCondensateInflowModel, AnnularPressureBuildup, TubingMovementCalculator, WellChemicalTreatment, InjectionWellHydraulics, NodalAnalysis)"]
  env: ["IWP_NEQSIM_CLASSPATH (optional)", "NEQSIM_PROJECT_ROOT (optional)"]
  network: []
tags: [wells, well-planning, nodal-analysis, injectivity, operating-envelope, barriers, flow-assurance, integrity, drawings, report]
min_neqsim_version: "3.7.0"
---

# Integrated Well Planning

One repeatable workflow that turns reservoir information, fluid data, well requirements and facility constraints into a **traceable well-design proposal**, executable models, professional drawings and a well-planning report. It supports oil producers, gas and gas-condensate producers, water injectors and gas injectors, onshore, on platforms and subsea. The agent `well-planning-engineer` coordinates the study; this skill defines the schemas, methods, calculation tools, checks, drawing templates and report structure. The drilling and casing design module is the required skill `neqsim-well-design-study`.

The skill separates three things that must never be mixed up: **implemented calculations** (NeqSim classes with tests), **screening estimates** (executable but approximate or uncalibrated) and **assessments not performed** (they need an external tool or specialist; the skill then produces an interface specification, never a number). That separation is the *capability ledger* below and is printed in every report.

## When to Use

- A well concept must be sized or compared: tubing size, wellhead/host back pressure, gas lift, completion arrangement, injection pressure and duty.
- A reservoir fluid and an IPR/injectivity basis exist and the question is deliverability, injectivity, temperatures, phase behaviour, hydrate margin and the operating envelope.
- A study needs a source/assumption register, a standards register, barrier schematics, A3 drawings, a decision/action log and a report that states what was and was not calculated.
- A hand-off to or from another agent is needed (VFP tables, trajectory, host constraints, PVT, cost/profile, flow-assurance requirements, integrity inputs).
- Do **not** use it for final design, rig-ready programmes, relief-well work, regulatory compliance statements or reservoir recovery/value estimates.

## Inputs

The planning basis (`iwp_planning_basis.v1`, YAML or JSON, template: `templates/planning_basis_template.yaml`). Ranges are `{low, base, high}`; `low` is the pessimistic outcome, `high` the optimistic one (skin, water cut and host pressure are therefore taken from the opposite end of their range in the low case).

1. **Purpose and targets:** study purpose, maturity (`concept`, `selection`, `detailed_engineering_support`, `operating_well_evaluation`), rate or injection target with range.
2. **Location and environment:** onshore, platform or subsea; water depth; reference elevation; surface or seabed temperature.
3. **Datums:** depth reference, MD/TVD/TVDSS convention, coordinate system, pressure reference (bara), standard conditions (15 C, 1.01325 bara).
4. **Reservoir:** pressure, temperature, permeability, thickness, skin, drainage radius, depletion, water cut, fracture gradient (injectors), uncertainty ranges.
5. **Fluid:** EOS, components, PVT measurements, water chemistry, contaminants (CO2, H2S), wax appearance temperature. Missing items are data gaps with a stated consequence.
6. **Trajectory and completion:** survey description or stations, casing programme, tubing (ID, grade, weight), packer, safety valve, mandrels, perforations, lift type, tree, formations and contacts.
7. **Facility:** host pressure range, flowline description, choke drop, supply pressure, pump/compressor efficiency, power and rate limits, fluid-quality limits.
8. **Operations:** life, intervention strategy, abandonment requirement.
9. **Limits and design factors:** approved limits with a source and a `limit_basis` (`APPROVED`, `SYNTHETIC`, `ASSUMED`, `NONE`). Design factors are only used when supplied with a source.
10. **Provenance map:** per dotted path, class `SUPPLIED`, `MEASURED`, `FITTED`, `CALCULATED` or `ASSUMED`, plus source. A synthetic study can never contain `MEASURED` values.

## Outputs

- `results/model_results.json` (low/base/high operating points, profiles, integrity, flow assurance, trajectory, barriers, interface specifications, envelope) and `models/rerun_model.py` to re-run the numbers.
- `results/operating_envelope.{json,csv,md}`, `results/alternatives.json` (scorecard, Pareto front, tornado, deliverability profile), `results/risk_register.json`.
- Outbound hand-off messages in `results/handoffs/` (`iwp_*.v1`, envelope `iwp_handoff_envelope.v1`).
- `drawings/`: A3 well schematic and barrier sheets (PNG 300 dpi + vector PDF/SVG), 17 chart types as 300 dpi PNG, `drawings_register.csv`, a JSON provenance sidecar for every figure.
- `report/well_planning_report.{docx,md}` with executive summary and recommended concept, design basis, reservoir and fluid, alternatives, performance and envelopes, interfaces, flow assurance, risks and gaps, cost and schedule, validation and records, appendices (ledger, drawings register, decision/action log, hand-offs) and revision control.
- `registers/` and `decisions/`: source register, data gaps, standards register, capability ledger, decision log, action log.

## Engineering Method

**Workflow (agent-driven, reproducible):** `<python> -m integrated_well_planning init-study | validate-basis | run-model | envelope | alternatives | drawings | report | all` (see Python Usage Pattern). Study folder: `basis/ registers/ models/ results/ drawings/ report/ decisions/`.

1. **Planning basis and registers.** Fill the basis, run `validate-basis` (fail-closed: missing required inputs, composition not summing to 1, Kelvin given as Celsius, TVD above MD, MEASURED in a synthetic study, SUPPLIED without a source). Gaps carry a consequence. Standards register starts `TO_VERIFY` (NORSOK D-010, ISO 16530-1, ISO/TR 10400 and casing/tubing specifications, ISO 15156, drilling/wellhead/subsea requirements, company requirements): edition, amendments, applicability and exclusions are verified by the study lead; **no design factor, rating or acceptance limit is invented** and no compliance statement is generated.
2. **Single calculations first (MCP).** For one flash, saturation pressure, standards lookup or sizing use the curated `mcp_neqsim_*` tools (`runCapability`: `search` -> `inspectApi` -> invoke) before writing code. Use this package for the chain, loops, sweeps, drawings and the report.
3. **Fluid model.** `model_chain.build_fluid` builds the NeqSim fluid (SRK, PR or CPA, mixing rule always set). Water for hydraulics is added with the classic mixing rule (no mutual solubility); hydrate work uses a CPA fluid. Stock-tank and standard-volume factors come from one TP flash at 15 C and 1.01325 bara (no separator train): record it as a model choice. Uncalibrated EOS is a data gap until PVT is supplied (`neqsim-eos-regression`, `neqsim-pvt-fluid-study-report`).
4. **Producers.** IPR: Darcy productivity index with NeqSim viscosity and volume factor (Standing composite: linear above, Vogel below the bubble point) for oil; `GasCondensateInflowModel` (pseudo-pressure, condensate banking, optional Forchheimer) for gas and gas-condensate. VLP: `DriftFluxWellboreHydraulics` with a `WellboreThermalModel` (Ramey) temperature profile, segment flashes, Turner and erosional ratios. Wellhead back pressure: host pressure plus a NeqSim `PipeBeggsAndBrills` flowline (5-point table) plus a supplied choke drop. Nodal solve at the bottom-hole node: all intersections, stable branch = highest-rate stable crossing, loading branch left of the VLP minimum. Sensitivities: tubing ID, host pressure, water cut, depletion, skin, lift gas.
5. **Injectors.** Water: `InjectionWellHydraulics` (matrix operating point, tubing column, injection temperature, thermal fracture-pressure reduction = full-cooling upper bound), required BHP then required WHP by bisection, fracture margin, pump duty (efficiency is an input). Gas: radial pseudo-pressure injectivity with NeqSim Z and viscosity, tubing column, isentropic compression duty from a NeqSim PS flash. Intentional-fracture injection is *not* modelled (ledger L26).
6. **Integrity and barriers.** Load cases (production or injection, shut-in, evacuated tubing, optional supplied test pressure); tubular formula ratings (API TR 5C3 via `neqsim-well-design-study`); utilisation = load / formula rating; design-factor status only against supplied factors (otherwise `NEEDS_REVIEW`); annular pressure build-up (`AnnularPressureBuildup`); tubing movement, packer force, buckling (`TubingMovementCalculator`); proposed barrier schematics per well state (production/injection, shut-in, intervention, abandonment) with primary and secondary envelopes, verification method and unresolved dependencies, all `UNVERIFIED`.
7. **Operating envelope.** One row per parameter and condition: limit min/max, limit source and basis, design margin (only when its source is given), predicted value, margin, status, required action. Rules: no source => `NEEDS_REVIEW`; SYNTHETIC/ASSUMED limit => `NEEDS_REVIEW` with an indicative status; no prediction => `NOT_ASSESSED`. Calculated conditions are kept separate from verified ratings and approved limits.
8. **Flow assurance.** Hydrate temperature and margin along the well (CPA), MEG/methanol dose and injection basis (`WellChemicalTreatment`), shut-in cooldown to the hydrate line, Turner (gas wells) and erosional ratios, wax margin only with a laboratory WAT, CO2/H2S partial pressures for the materials engineer. Scale and compatibility are `NOT_PERFORMED` without water chemistry; transient start-up, unloading and slugging are `EXTERNAL_TOOL_REQUIRED` - a steady-state result is never called transient validation.
9. **Alternatives.** Tubing size, lift (gas lift screening), wellhead pressure, completion variants through the same chain for low/base/high; scorecard (weights are ASSUMED equal unless supplied; criteria without data are excluded, not scored zero), non-dominated front, binding constraint, tornado and sensitivity grid, deliverability versus time with linear depletion. Recovery and project value are not inferred from deliverability. Cost enters only if supplied with currency and source.
10. **Drilling and completion interfaces.** Minimum-curvature geometry and DLS check, casing formula ratings and a pore/mud/fracture arithmetic check are implemented; anti-collision, geomechanics, drilling hydraulics, cementing and detailed mechanical design become `iwp_interface_spec.v1` documents with inputs available/missing, receiver and expected return, status `UNRESOLVED`.
11. **Drawings and report.** `drawings` renders every chart from the results with provenance; `report` builds the Word and Markdown report with a readiness label (`NOT READY` or `SCREENING - FOR REVIEW`, never an approval).

### Capability ledger

| ID | Calculation | Status | Class or tool |
|---|---|---|---|
| L01 | Wellbore temperature profile (Ramey) and shut-in cooldown | IMPLEMENTED_VALIDATED | `WellboreThermalModel` |
| L02 | Drift-flux tubing hydraulics, regime, Turner, erosional ratio | IMPLEMENTED_VALIDATED | `DriftFluxWellboreHydraulics` |
| L03 | Gas-condensate inflow, banking (banking is screening), non-Darcy | IMPLEMENTED_VALIDATED | `GasCondensateInflowModel` |
| L04 | Oil/gas IPR from Darcy, composite IPR, nodal solve in Python | SCREENING | `producers`, `nodal` |
| L05 | Nodal intersections, stability, loading onset | IMPLEMENTED_VALIDATED | `NodalAnalysis` (cross-check) + `nodal` |
| L06 | Injection hydraulics, matrix point, thermal fracture reduction | IMPLEMENTED_VALIDATED | `InjectionWellHydraulics` |
| L07 | Gas injectivity and compression duty | SCREENING | `injectors` |
| L08 | Hydrate inhibitor dose and injection basis | IMPLEMENTED_VALIDATED | `WellChemicalTreatment` |
| L09 | Annular pressure build-up | IMPLEMENTED_VALIDATED | `AnnularPressureBuildup` |
| L10 | Tubing movement, packer load, buckling, von Mises | IMPLEMENTED_VALIDATED | `TubingMovementCalculator` |
| L11 | Tubular formula ratings and utilisation | SCREENING | `well_design_study.casing_design` |
| L12 | Pressure window, seats, kick tolerance, torque and drag, ECD, time and cost | SCREENING | `well_design_study` |
| L13 | Barrier schematics (data model, drawings) | SCREENING | `barriers` |
| L14 | Operating-envelope table (fail-closed) | IMPLEMENTED_VALIDATED | `envelope` |
| L15 | Alternatives, scorecard, Pareto | SCREENING | `alternatives` |
| L16 | Gas-lift screening | SCREENING | `producers` (lift gas at the shoe) |
| L17 | ESP and other artificial lift design | EXTERNAL_TOOL_REQUIRED | `ArtificialLiftScreener`, vendor tool |
| L18 | Scale prediction, injection-water compatibility | EXTERNAL_TOOL_REQUIRED | water-chemistry tools, laboratory test |
| L19 | CO2 corrosion, sour-service screening | SCREENING | `CO2CorrosionAnalyzer`, `SourServiceAssessment` |
| L20 | Wax | SCREENING | supplied WAT only |
| L21 | Transient start-up, unloading, slugging | EXTERNAL_TOOL_REQUIRED | `TwoFluidPipe` / OLGA-class |
| L22 | Anti-collision and survey uncertainty | EXTERNAL_TOOL_REQUIRED | `well-trajectory-anticollision-agent`, Compass-class tool |
| L23 | Geomechanics and borehole stability | EXTERNAL_TOOL_REQUIRED | specialist |
| L24 | Drilling hydraulics, cement placement, detailed mechanical design | EXTERNAL_TOOL_REQUIRED | operator software |
| L25 | Recovery, depletion forecast, project value | NOT_PERFORMED | other agents |
| L26 | Velocity-dependent kr, CVD, stratified wellbore, fracture-injection dynamics, ISO 13679 load-case matrix | NOT_PERFORMED | Java follow-ups |

`IMPLEMENTED_VALIDATED` means checked against an analytic limit, textbook formula or cross-correlation in the NeqSim test suite - **not field-calibrated**. `python -m integrated_well_planning ledger --json` prints the ledger with `available` set from the runtime probe, plus the Java follow-ups.

### Java follow-ups recorded (not done here)

Expose the wellplanning classes through the automation/MCP layer; variable solution GOR and emulsion viscosity in the drift-flux class; NodalAnalysis adapters for the composite IPR and a choke/flowline node; a life-cycle `WellLoadCaseMatrix` (ISO 13679 style); velocity-dependent kr in `GasCondensateInflowModel`; a barrier-schematic data class next to `WellBarrierSchematic`.

### Hand-off schemas (`schemas/`, versioned `iwp_*.v1`)

| Schema | Direction | Counterpart (community) |
|---|---|---|
| `iwp_planning_basis.v1` | in | reservoir-simulator-agent, fluid-characterization-agent, field-development |
| `iwp_vfp_request.v1` | out | vfp-lift-curve-agent |
| `iwp_trajectory.v1` | in and out | well-trajectory-anticollision-agent |
| `iwp_host_constraints.v1` | in | tie-in-screening-agent, debottlenecking-agent, production-optimization-agent |
| `iwp_fluid_basis.v1` | in | fluid-characterization-agent, pvt-agent, e300-fluid-agent |
| `iwp_cost_profile.v1` | out | asset-economics-agent, field-development, concept-selection-agent |
| `iwp_flow_assurance_requirements.v1` | out and in | flow-assurance-study-agent, flow-assurance-engineer-agent |
| `iwp_integrity_inputs.v1` | out and in | well-integrity review (process-safety-agent) |
| `iwp_well_model.v1`, `iwp_operating_envelope.v1` | out | field-development, production-optimization-agent |
| `iwp_interface_spec.v1` | out | specialist tools and agents |
| `iwp_handoff_envelope.v1` | wrapper | all |

Inbound values are merged with provenance `SUPPLIED` and the message source (`handoff.apply_host_constraints`, `apply_fluid_basis`, `apply_trajectory`); they are never relabelled as calculated.

### Visual design system (`iwp_style.py`, `iwp_graphics.py`, `iwp_drawings.py`)

Okabe-Ito based colour-blind-safe palette with fixed semantic colours (pressure blue, temperature vermillion, gas orange, oil green, water sky blue, hydrate purple, traffic lights always paired with a text label, primary barrier blue, secondary barrier red); fonts that exist on the machine (Segoe UI, Calibri, Arial, DejaVu Sans fallbacks), TrueType embedded in PDF; direct labels instead of legends; shaded low/base/high bands; A3 sheets with border, title block, revision block, drawing number, SYNTHETIC stamp, optional scale bar and north arrow; PDF/SVG vector plus 300 dpi PNG; provenance sidecar per figure. Library: well schematic with depth tracks, barrier schematics, nodal analysis, wellbore profiles, operating-envelope chart and table, scorecard, radar, Pareto, waterfall, tornado, sensitivity heat-map, deliverability bands, Gantt with whiskers, risk matrix, risk register, decision tree, time-depth, trajectory plan/section with separation fans, 3D trajectory (PyVista off-screen, matplotlib fallback).

## Python Usage Pattern

Use the shared NeqSim Python interpreter (active environment or `NEQSIM_PYTHON`; `sys.executable` for child processes); never activate or create environments.

```python
from pathlib import Path
from integrated_well_planning import study, examples_data
from integrated_well_planning.drawings_run import make_drawings
from integrated_well_planning.report import build_report
from integrated_well_planning.runtime import ensure_runtime

print(ensure_runtime().to_dict())                       # which wellplanning classes exist; reason when they do not
root = Path("studies/A-1")
study.init_study(root, basis=examples_data.oil_producer_platform())   # or well_type/environment template
print(study.validate(root)["status"])                    # fail-closed: FAIL blocks run_model
res = study.run_model(root)                              # low/base/high, integrity, flow assurance, barriers, envelope, hand-offs
alt = study.alternatives(root, profile_years=[0, 5, 10]) # scorecard, Pareto, tornado, deliverability profile
study.envelope(root)                                     # re-evaluate after approved limits are added to the basis
make_drawings(root); print(build_report(root)["readiness"])
```

Command line (same steps): `<python> -m integrated_well_planning init-study FOLDER --well-type gas_injector --environment platform`, then `validate-basis FOLDER`, `run-model FOLDER`, `alternatives FOLDER --profile-years 0,5,10`, `envelope FOLDER`, `drawings FOLDER`, `report FOLDER`, or `all FOLDER`; `ledger --json`; `runtime`; `list-cases`.

NeqSim runtime: `ensure_runtime()` starts the JVM once from `IWP_NEQSIM_CLASSPATH`, a NeqSim checkout (`NEQSIM_PROJECT_ROOT` or a sibling `neqsim` folder: `target/classes` plus the shaded jar of the installed `neqsim` package for dependencies) or the installed package. When the wellplanning classes are absent the chain raises `ModelUnavailable` with the reason, `run_model` stops with that reason, the ledger shows `available=False` and nothing is fabricated.

## Validation Checklist

- [ ] Basis validates (`PASS` or `WARN`, no errors); provenance recorded for every required input; synthetic studies are stamped as such.
- [ ] MD, TVD, TVDSS, pressure reference (bara) and standard conditions stated; survey TVD agrees with the basis.
- [ ] Rate target met in base, low and high cases or the shortfall is reported with the binding constraint.
- [ ] Stable operating point identified; VLP minimum / loading branch shown; nodal result cross-checked against `NodalAnalysis` for a linear case (tests do this).
- [ ] Fracture margin positive for matrix injection, or the intentional-fracture basis is declared `EXTERNAL_TOOL_REQUIRED`.
- [ ] Every envelope row has a limit source, or is `NEEDS_REVIEW`; no design factor appears without a source.
- [ ] Barrier elements are `UNVERIFIED` unless evidence is attached; no compliance statement in the report.
- [ ] Ledger printed; every `EXTERNAL_TOOL_REQUIRED` item has a route; Java follow-ups listed.
- [ ] Figures carry provenance sidecars; flow diagrams pass the PFD layout review where used.
- [ ] Alternatives compare like with like; weights and missing criteria are stated; no recovery or value claim.

## Common Mistakes

- Treating a steady-state drift-flux result as a transient or slugging validation.
- Reading `low` as "low value" of every parameter: here `low` is the pessimistic outcome (high skin, high water cut, high host pressure).
- Mixing gauge and absolute pressure, or MD and TVD, or RKB and MSL (TVDSS) without the datum record.
- Using the oil-well Turner flag: it is a gas-well criterion and is not applied to oil producers.
- Reporting a formula rating as a manufacturer rating, or a design factor that nobody supplied.
- Putting the wellhead rating in as an approved limit when it is a placeholder (`limit_basis` SYNTHETIC makes the row `NEEDS_REVIEW`).
- Forgetting `initProperties()` after a flash when writing new NeqSim code against transport properties.
- Inferring recovery or project value from a deliverability curve.

## Limitations

Screening and early-design support only; human review is required. All NeqSim physics here is validated against analytic limits and cross-correlations, **not calibrated to field or laboratory data**. No well-control, borehole-stability, cementing, anti-collision, scale, sand, MIC, ESP design or transient assessment is performed (ledger). The standards register contains topics and sources to verify; it contains no requirement values. Annulus and movement calculations assume a vertical free-standing string; deviated-well friction and bending, cement/formation compliance and the ISO 13679 load-case matrix are not modelled. Constant GOR in the producer VLP, single bottom-hole node, no layered reservoir, no skin growth or scaling, linear depletion in the deliverability profile.

## Related NeqSim Functionality

Skills: `neqsim-well-design-study` (drilling/casing module, required), `neqsim-near-well-and-injectivity`, `neqsim-vfp-lift-curves`, `neqsim-erd-reach-screening`, `neqsim-well-trajectory-anticollision`, `neqsim-reservoir-depletion-screening`, `neqsim-reservoir-model-builder`, `neqsim-reservoir-history-match-forecast`, `neqsim-production-network-routing`, `neqsim-tight-reservoir-test-design`, `neqsim-reservoir-souring-correlation`, `neqsim-flow-assurance`, `neqsim-production-chemistry`, `neqsim-electrolyte-systems`, `neqsim-eos-regression`, `neqsim-pvt-fluid-study-report`, `neqsim-optimization-and-doe`, `neqsim-agentic-process-optimization`, `neqsim-professional-reporting`, `neqsim-report-design-and-visual-qa`, `neqsim-surf-design-study`, `neqsim-depressurization-mdmt`, `neqsim-capacity-and-utilization-analysis`, `neqsim-equipment-cost-estimation`, `neqsim-field-economics`, `neqsim-agent-handoff`.

Agents: `well-planning-engineer` (coordinator), `field-development`, `flow-assurance-study-agent`, `flow-assurance-engineer-agent`, `near-well-injectivity-agent`, `vfp-lift-curve-agent`, `well-trajectory-anticollision-agent`, `artificial-lift-agent`, `gas-lift-allocation-agent`, `reservoir-simulator-agent`, `reservoir-history-match-agent`, `fluid-characterization-agent`, `pvt-agent`, `e300-fluid-agent`, `production-optimization-agent`, `reservoir-to-facility-screening-agent`, `concept-selection-agent`, `process-safety-agent`, `energy-emissions-agent`, `asset-economics-agent`.

Java: `WellSystem`, `WellFlow`, `TubingPerformance`, `TransientWellbore`, `TwoFluidPipe`, `PipeBeggsAndBrills`, `LoopedPipeNetwork`, `FieldWellNetworkCoupler`, `InjectionWellModel`, `ArtificialLiftScreener`, `GasLiftPerformanceCurve`, `InhibitorInjectionPoint`, `WellDesignCalculator`, `WellMechanicalDesign`, `WellIntegrityScreening`, `WellBarrierSchematic`, `ShutInPressureEstimator`, `WellCostEstimator`, `VfpTableBuilder`, hydrate/wax/scale/corrosion classes, and the `neqsim.process.fielddevelopment.wellplanning` package (docs: `docs/fielddevelopment/WELL_PLANNING_PHYSICS.md` in the NeqSim repository).

## References

- API TR 5C3 / ISO/TR 10400 (tubular performance formulas), API RP 14E (erosional velocity ratio), NORSOK D-010, ISO 16530-1, ISO 15156 (editions and applicability to be verified by the study lead; none of their requirement values are encoded here).
- Ramey, H. J. (1962), wellbore heat transmission; Hasan and Kabir (drift-flux and transient heat transfer); Turner et al. (1969), liquid loading; Standing / Vogel composite IPR; Fevang and Whitson (1996), gas-condensate well deliverability; Hammerschmidt (hydrate inhibition).
- NeqSim documentation: `docs/fielddevelopment/WELL_PLANNING_PHYSICS.md`; examples `examples/`; schemas `schemas/`; templates `templates/`.
