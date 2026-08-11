---
name: neqsim-reservoir-model-builder
version: "0.1.0"
description: "Set up a screening-level reservoir model from whatever data exists, on a data-maturity ladder from a single public headline volume up to a full static-model parameter set, and refine it as data arrives. USE WHEN: a task needs a reservoir model for a field where only open data is available (for example an NCS field on public resource pages), needs volumetrics from area/net pay/porosity/Sw, needs hydrostatic pressure and geothermal temperature defaults from depth, needs a recovery factor and drive mechanism from analogues, needs a well count and productivity index from permeability, or needs a NeqSim SimpleReservoir/WellFlow specification with a provenance trail and a ranked data-acquisition plan."
last_verified: "2026-08-11"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reservoir Model Builder

Use this skill to turn whatever reservoir data is available — from a single
public headline volume to a full static-model parameter set — into a coherent,
runnable screening reservoir model, and to refine that model as better data
arrives without losing track of what came from where.

The central idea is a **data-maturity ladder**. Every number in the model carries
a provenance label, so the model can always answer three questions:

1. What did we actually know?
2. What did the builder assume on our behalf, and from what basis?
3. Which missing measurement would most reduce the uncertainty?

## When to Use

- A reservoir model is needed for a field where only open data exists (public
  resource pages, an approved development plan summary, a discovery
  announcement).
- Volumetrics must be built from area, net pay, porosity and water saturation,
  or an in-place volume must be back-calculated from a reported recoverable
  volume.
- Reservoir pressure and temperature are unknown and must be defaulted from
  depth using a hydrostatic gradient and a geothermal gradient.
- A recovery factor and a drive mechanism must be inferred from fluid type,
  aquifer strength and injection plan.
- A well count and a productivity index must be estimated from permeability and
  net pay before any well test exists.
- An existing screening model must be refined with new logs, a well test or a
  PVT report, with an auditable record of what changed.
- A NeqSim `SimpleReservoir` / `WellFlow` set-up or an MCP `runReservoir` payload
  is needed as the next step.

## Inputs

All inputs are optional except the field name and enough information to size the
reservoir and set its conditions.

| Group | Fields |
| --- | --- |
| Identity | `field_name`, `fluid_type` (`gas`, `oil`, `gas_condensate`), `sea_area` |
| Structure and rock | `area_km2`, `gross_thickness_m`, `net_pay_m`, `net_to_gross`, `porosity`, `water_saturation`, `permeability_mD` |
| Conditions | `datum_depth_m_tvdmsl`, `water_depth_m`, `initial_pressure_bara`, `reservoir_temperature_C`, `abandonment_pressure_bara` |
| Fluid | `fluid_composition`, `oil_formation_volume_factor`, `gas_compressibility_factor`, `solution_gas_oil_ratio_Sm3_per_Sm3`, `oil_viscosity_cP`, `gas_viscosity_cP` |
| Volumes | `stoiip_Sm3`, `giip_Sm3`, `recoverable_oil_Sm3`, `recoverable_gas_Sm3`, `recovery_factor` |
| Drive | `drive_mechanism`, `aquifer_strength` (`none`/`weak`/`moderate`/`strong`), `has_gas_cap`, `injection_plan` |
| Wells | `producer_count`, `injector_count`, `productivity_index_Sm3_per_day_bar`, `target_plateau_rate_Sm3_per_day`, `drainage_radius_m`, `wellbore_radius_m`, `skin_factor`, `drawdown_fraction` |
| Provenance | `provenance`, `reference`, `field_provenance`, `field_reference` |

At minimum the builder needs:

- one of `initial_pressure_bara` or `datum_depth_m_tvdmsl`, and
- one of `initial_pressure_bara`/`reservoir_temperature_C` or `datum_depth_m_tvdmsl`, and
- one way to size the reservoir: an in-place volume, a recoverable volume, or
  `area_km2` together with `net_pay_m` or `gross_thickness_m`.

## Outputs

- `parameters` — every resolved parameter with value, unit, provenance,
  reference, low/high range and derived-from basis.
- `volumetrics` — hydrocarbon pore volume, STOIIP/GIIP, recoverable volumes, and
  the corresponding in-situ reservoir volumes plus connate water and aquifer.
- `drive_mechanism` — inferred or supplied.
- `data_tier` — `tier-0-headline`, `tier-1-public-volumetric`,
  `tier-2-well-and-pvt` or `tier-3-static-model`.
- `completeness` — weighted fraction of the model that rests on real data.
- `derivations` — the arithmetic behind every derived number, written out.
- `warnings` — physics and consistency flags (cold or shallow reservoir,
  over/under-pressure, double-counted net-to-gross, a reported recoverable volume
  that disagrees with the geometry-derived in-place volume).
- `refinement_plan` — data items ranked by weight times remaining uncertainty,
  each with the acquisition route that would deliver it.
- `neqsim_spec` — a NeqSim-ready specification for `SimpleReservoir`, `WellFlow`
  and the MCP `runReservoir` tool.

## Engineering Method

The skill uses transparent, public, screening-level relations only.

**Volumetrics.** The hydrocarbon pore volume is
`A x h x NTG x phi x (1 - Sw)`. If `net_pay_m` is supplied it is used directly and
net-to-gross is *not* applied again; if `gross_thickness_m` is supplied,
net-to-gross is applied. Supplying both raises a warning. Oil in place is
`HCPV / Bo`; gas in place is `HCPV / Bg`.

**Gas formation volume factor.** `Bg = (Psc x Z x T) / (Tsc x P)` with
`Psc = 1.01325 bara` and `Tsc = 288.15 K`, so the model is explicit about the
standard conditions behind every Sm3.

**Pressure and temperature defaults.** Initial pressure defaults to a normal
hydrostatic gradient of 0.105 bar/m of true vertical depth. Temperature defaults
to a sea-area seabed temperature plus a geothermal gradient applied over the
interval below the seabed. Both are labelled `derived` and both raise a warning
when the resulting model is pressure-sensitive.

**Recovery factor.** Screening low/base/high ranges are tabulated per fluid type
and drive mechanism (depletion, water drive, solution gas, gas cap, water or gas
injection) and labelled `analogue`. They are placeholders for reservoir
simulation or analogue field performance.

**Drive mechanism.** Inferred from the injection plan first, then aquifer
strength, then the presence of a gas cap, then the fluid type.

**Well inflow.** The productivity index is either supplied, or estimated from
pseudo-steady radial Darcy inflow in practical metric units:

$$
J = \frac{0.05357\,k\,h}{\mu\,B\,\bigl(\ln(r_e/r_w) - 0.75 + S\bigr)}
$$

with `J` in Sm3/day/bar, `k` in mD, `h` in m, `mu` in cP. The well count follows
from the plateau target divided by the per-well rate at the design drawdown. If
neither a productivity index nor a permeability is available, the skill reports
zero and warns rather than inventing deliverability.

**Consistency check.** When the in-place volume comes from geometry *and* a
recoverable volume was reported independently, the implied recovery factor is
computed and a warning is raised if it disagrees with the assumed recovery factor
by more than 25 %.

This is not reservoir simulation. There is no gridding, no relative permeability,
no saturation-height modelling, no history matching and no aquifer influx solver.

## Python Usage Pattern

```python
from reservoir_model_builder import build_reservoir_model, summarize

# Stage 1 - a public headline entry and a depth is enough to start.
model = build_reservoir_model(
    field_name="Example NCS oil field",
    fluid_type="oil",
    sea_area="barents_sea",
    water_depth_m=400.0,
    datum_depth_m_tvdmsl=650.0,
    recoverable_oil_Sm3=79.5e6,
    provenance="public-reported",
    reference="public resource reporting",
)
print(summarize(model))
print(model.data_tier, model.completeness)

# Stage 2 - borrow rock properties from the play, clearly labelled as analogue.
model = model.refine(
    {"porosity": 0.28, "water_saturation": 0.25, "aquifer_strength": "moderate"},
    provenance="analogue",
    reference="analogue field in the same play",
)

# Stage 3 - replace the analogues with appraisal-well and PVT data.
model = model.refine(
    {
        "area_km2": 21.0,
        "net_pay_m": 45.0,
        "porosity": 0.30,
        "water_saturation": 0.20,
        "permeability_mD": 2000.0,
        "initial_pressure_bara": 76.0,
        "reservoir_temperature_C": 18.0,
        "oil_formation_volume_factor": 1.12,
    },
    provenance="measured",
    reference="appraisal well logs, DST and PVT report",
)

for change in model.changes:
    print(change["parameter"], change["provenance_before"], "->", change["provenance_after"])

spec = model.neqsim_spec          # feeds SimpleReservoir / WellFlow / runReservoir
plan = model.refinement_plan      # ranked data-acquisition plan
```

Each `refine` call carries its own provenance, so values from an earlier source
keep their original label. `model.to_dict()` returns the whole model, provenance
trail included, as JSON for a task `results.json`.

### Handing the model to NeqSim

`neqsim_spec` is aligned with the MCP `runReservoir` payload and with
`SimpleReservoir.setReservoirFluid(system, gasVolume, oilVolume, waterVolume)`.

**Volume basis gotcha.** `setReservoirFluid` takes *in-situ reservoir* volumes at
the fluid's temperature and pressure, even though the MCP keys are named
`gasVolume_Sm3` / `oilVolume_Sm3` / `waterVolume_Sm3`. The skill therefore emits
reservoir m3 in those keys and repeats the standard-condition volumes separately
under `standardConditionVolumes`, with `volumeBasis` stating which is which.

**Aquifer.** The aquifer volume is reported separately as `aquiferVolume_rm3` and
is *not* folded into `waterVolume_Sm3`. A 12-times-HCPV aquifer added to a tank
model dominates the depletion behaviour, so including it must be a deliberate
choice.

**Productivity index unit.** `WellFlow.setWellProductionIndex(double)` expects the
quadratic form in MSm3/day/bar^2 (`q = PI x (Pr^2 - Pwf^2)`), not a linear
Sm3/day/bar index. The skill emits both:
`wellModel.productivityIndex_Sm3_per_day_bar` for reporting and
`wellModel.neqsimWellProductionIndex_MSm3_per_day_bar2` for the NeqSim call,
matched at the design drawdown.

### Turning the compositional fluid into a black-oil description

When the model must produce a rate profile rather than only volumes, convert the
compositional fluid to a black-oil table with
`neqsim.blackoil.BlackOilConverter.convert(fluid, Tref_K, pGrid_bara, Pstd_bara,
Tstd_K)`. Three things go wrong routinely:

- **Volume shift.** `Phase.getDensity()` and `Phase.getVolume()` return the *raw
  EOS* values; `Phase.getDensity("kg/m3")` and `Phase.getCorrectedVolume()` apply
  the Peneloux volume translation. Any tuned reservoir fluid has a volume shift,
  so mixing the two conventions in one balance biases the stock-tank density, Bo
  and Rs by the size of the shift (a few percent). Use the corrected accessors
  everywhere, including in your own separator-test and GOR scripts.
- **Bubble point on the grid.** The converter snaps the bubble point to the
  highest grid pressure that still shows free gas and clamps Rs above it. Put a
  point immediately below the EOS saturation pressure (for example
  `psat - 0.02` bar) in `pGrid`, or Rs at and above the bubble point comes out
  low.
- **Sm3 convention.** The converter uses the real EOS gas volume at standard
  conditions. Scripts that define Sm3 with the ideal-gas molar volume
  (`R T / P = 0.023645` Sm3/mol) read roughly half a percent higher GOR.

Export the result with
`neqsim.blackoil.io.EclipseEOSExporter.toFile(pvt, rhoOilSc, rhoGasSc,
rhoWaterSc, path)` for a PVTO/PVTG/PVTW/DENSITY include file.

### Driving the tank with injection

`SimpleReservoir` takes `addOilProducer`, `addWaterProducer`, `addGasInjector`
and `addWaterInjector`. Two practical points:

- The injector stream is cloned from a *reservoir* phase, so for an
  undersaturated oil the gas-injection stream is meaningless until you set it
  explicitly: flash the reservoir fluid to standard conditions, take the gas
  phase and `stream.setFluid(...)` with the same component set as the tank.
- Set every rate in `kg/day` using the black-oil stock-tank densities. The
  reservoir-oil mass rate that yields `q_o` Sm3/day of stock-tank oil is
  `q_o * (rho_o_sc + Rs * rho_g_sc)`; volumetric `Sm3/day` on a liquid stream is
  ambiguous and should be avoided.
- For a voidage-replacement concept, size the water injection from what the
  reinjected gas does not cover:
  `q_wi = (VRR * (q_o Bo + q_w Bw) - q_gi Bg) / Bw`.
- `SimpleReservoir` closes its own balance on the **raw** EOS volume
  (`setReservoirFluid` scales phases with `getVolume()`, `runTransient` calls
  `TVflash(reservoirVolume, "m3")`), while the black-oil factors above are
  volume-shift corrected. For a translated fluid the two bases differ by the
  size of the shift, so an open-loop voidage balance drifts and the tank
  pressure runs away. Scale the feed-forward by
  `raw_volume / sum(phase.getCorrectedVolume())` and put the water injection on
  a velocity-form PI controller on reservoir pressure. Rate-limit the oil rate
  as well, or the deliverability constraint chatters against the pressure loop.
- Every producer and injector needs a non-zero flow rate; a zero-flow stream
  makes `runTransient` throw `setMolarComposition - Input totalFlow must be
  larger than 0`.

## Validation Checklist

- [ ] The sizing basis is stated: geometry, in-place volume, or a back-calculated
      recoverable volume.
- [ ] Net pay and net-to-gross are not applied twice.
- [ ] Pressure and temperature are either measured or explicitly labelled as
      gradient defaults.
- [ ] The recovery factor is labelled `analogue` unless it comes from simulation
      or analogue field performance.
- [ ] Geometry-derived in-place volume and any reported recoverable volume are
      reconciled, or the divergence is explained.
- [ ] Well count and plateau rate rest on a productivity index or a permeability,
      or are declared unconstrained.
- [ ] The volume basis handed to NeqSim is reservoir m3, not Sm3.
- [ ] The refinement plan is recorded and the top items are turned into data
      requests.
- [ ] A qualified reservoir engineer has reviewed the model before any decision.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| In-place volume is roughly half of the expected value | `net_pay_m` supplied together with `net_to_gross`, expecting both to apply | Supply `gross_thickness_m` with `net_to_gross`, or `net_pay_m` alone |
| Reservoir gas volume looks far too small | Standard-condition GIIP passed straight into `setReservoirFluid` | Use `gasVolume_Sm3` from `neqsim_spec`, which is already `GIIP x Bg` |
| Depletion barely moves the pressure | The aquifer volume was added to the tank water volume | Keep `aquiferVolume_rm3` separate and model influx deliberately |
| Well count is 1 for a large field | No productivity index and no permeability | Supply a well-test PI, or a permeability with net pay |
| Implied recovery factor is far below the assumed one | The mapped area or net pay is too generous for the reported recoverable volume | Reconcile geometry, reported volume and recovery factor |
| Temperature looks too high for a shallow Barents Sea reservoir | Default geothermal gradient applied from sea level rather than the seabed | Supply `water_depth_m` so the gradient starts at the seabed |
| Stock-tank oil density is a few percent off the PVT report | Raw EOS `getVolume()`/`getDensity()` used instead of the volume-shift corrected accessors | Use `getCorrectedVolume()` and `getDensity("kg/m3")` |
| Design drawdown puts the flowing bottomhole pressure below the bubble point | The plateau was set from facility capacity, not from the undersaturation | Limit drawdown to the undersaturation, or add producers |

## Limitations

- Screening only. This is a tank-level parameter set, not a reservoir simulation:
  no grid, no relative permeability, no saturation-height model, no aquifer
  influx solver, no history matching.
- Recovery factors, rock defaults and gradients are generic public ranges. They
  are placeholders, not field data, and are labelled as such.
- The productivity index uses a linear pseudo-steady Darcy form. For gas wells at
  large drawdown the pseudo-pressure and non-Darcy terms matter.
- Uncertainty is expressed as low/high ranges, not as a probabilistic
  distribution. Run a Monte Carlo separately if P10/P50/P90 volumes are needed.
- The skill does not produce reserves statements and does not replace qualified
  reservoir engineering or project assurance.
- No proprietary or confidential data is used or included.

## Related NeqSim Functionality

This screening set-up feeds validated, rigorous NeqSim Java functionality that a
qualified engineer should use for design-grade work:

- `neqsim.process.equipment.reservoir.SimpleReservoir#setReservoirFluid(SystemInterface, double, double, double)`
  — tank material balance with gas, oil and water producers and injectors.
- `neqsim.process.equipment.reservoir.WellFlow#setWellProductionIndex(double)`
  and `#setDarcyLawParameters(double, double, double, double, double, double)` —
  inflow performance from a production index or from Darcy parameters.
- `neqsim.process.equipment.reservoir.MultiCompartmentReservoir` — multi-zone
  material balance when the field is compartmentalised.
- `neqsim.process.fielddevelopment.integrated.AquiferDrive` — Fetkovich aquifer
  influx when the aquifer must be modelled explicitly.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — flowline and riser
  hydraulics downstream of the wells.
- The NeqSim MCP `runReservoir`, `runPipeline` and `runFieldEconomics` tools for
  an orchestrated reservoir-to-value analysis.

In Python these classes are reachable through the `neqsim` package (for example
`from neqsim import jneqsim`).

## Related Skills

- `neqsim-norwegian-continental-shelf-data` — run first when the field is on the
  Norwegian Continental Shelf. It supplies the public field, reserves and
  production context, with source attribution, that seeds the inputs here.
- `neqsim-reservoir-depletion-screening` — run after this skill. It turns the
  recoverable volume, initial and abandonment pressure produced here into a
  pressure-and-production profile versus time.
- `neqsim-resource-classification-screening` — places the volumes produced here in
  an SPE-PRMS / NPD maturity category.
- `neqsim-fluid-quality-check` — gate the `fluid_composition` input through this
  check before it is handed to NeqSim.
- `neqsim-pseudocomponent-split-characterization` — characterise the plus fraction
  when only a lumped composition is available.
- `neqsim-production-network-routing` — takes the well count and productivity
  index produced here through manifolds and flowlines to an arrival pressure.
- `neqsim-asset-value-npv-screening` — turns the resulting production profile into
  an NPV screening.

## References

- Norwegian Offshore Directorate FactPages: https://factpages.sodir.no/
- Norwegian Petroleum (public field and resource pages): https://www.norskpetroleum.no/
- SPE Petroleum Resources Management System (SPE-PRMS), public definitions.
- Public reservoir-engineering literature for volumetric, material-balance and
  radial-inflow relations (for example Dake, *Fundamentals of Reservoir
  Engineering*; Craft and Hawkins, *Applied Petroleum Reservoir Engineering*).
- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
