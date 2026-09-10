---
name: neqsim-reservoir-model-builder
calculation_basis: "screening"
version: "0.4.0"
description: "Set up a screening-level reservoir model from whatever data exists, on a data-maturity ladder from a single public headline volume up to a full static-model parameter set, and refine it as data arrives. Enforces a data-first workflow: six modelling ingredients (geometry, petrophysics, fluid, SCAL, contacts, volumes) each have a ranked source ladder, every rung above the one in use must carry a recorded outcome of used/blocked/absent before the model may be built, a blocked source is reported as an access request rather than an acquisition programme, and any downgrade is surfaced with what it gave up so recovery factor can be decomposed into displacement times sweep. USE WHEN: a task needs a reservoir model for a field where only open data is available (for example an NCS field on public resource pages), needs a best-guess structural model when there is NO seismic, log or contact data at all (assumed play-typical trap style, layered stratigraphy, fluid contact and culmination solved to honour published volumes, structure-aware well placement, and a full assumption register), needs volumetrics from area/net pay/porosity/Sw, needs hydrostatic pressure and geothermal temperature defaults from depth, needs a recovery factor and drive mechanism from analogues, needs a well count and productivity index from permeability, needs to turn an ALREADY-BUILT static model (retrieved grid dimensions plus PORO/PERMX/NTG/SATNUM/EQLNUM cell arrays) into validated OPM Flow GRID and PROPS include files while catching the failure modes that produce a deck which runs and is wrong (array length mismatch, zero-based region arrays, fractions stored in percent, PERMZ left equal to PERMX, undefined sentinels) and reconciling the rebuilt in-place volume against a reported P90/P50/P10, or needs a NeqSim SimpleReservoir/WellFlow specification with a provenance trail and a ranked data-acquisition plan."
last_verified: "2026-09-10"
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
- **There is no subsurface data at all** and a model still has to be built: no
  seismic, no logs, no contacts, only a published resource number and a
  development description. See "Building a model when there is no subsurface
  data at all" below — assume the play-typical structure, solve the contact and
  the compartment split against the published numbers, place the wells on the
  structure, and publish the assumption register.
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

### Handing the model to OPM Flow on Windows

When a tank model must become a gridded reservoir simulation, chain to
`neqsim-near-well-and-injectivity`. OPM Flow is a Linux simulator; on Windows the
verified local pattern is the Docker image `opm-flow:2026.04`, not a host
`flow.exe`:

```powershell
docker run --rm opm-flow:2026.04 --version
docker run --rm -v "${PWD}/deck:/data" opm-flow:2026.04 `
  CASE.DATA --output-dir=/data/out
```

The image uses `LANG=C.UTF-8` and `LC_ALL=C.UTF-8`; Flow can otherwise abort
silently under a non-English locale. Treat a missing host `flow` command as
expected when Docker is available. Record the image tag with the results and
keep the deck directory mounted at `/data` so include files resolve.

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

## Search for everything first — simplify only when it is recorded

A screening model is allowed to be simple. It is not allowed to be simple *by
accident*. Two studies produce the same deck:

- legitimate: "the published grid is behind an entitlement we do not have, so
  we built a play-typical block and the forecast is an upper bound"
- illegitimate: "we built a play-typical block"

Only the first is a study. On Omega Sør an assumed homogeneous block
over-predicted recovery by **62 %** against the operator's own recoverable
range — not because the fluid or the in-place volume was wrong (both were
matched) but because a single unfaulted block cannot do worse than near-piston
displacement. The geology was never checked for; it was simply replaced.

`reservoir_model_builder.data_first` makes that impossible to do silently.

```python
from reservoir_model_builder import data_first_gate, acquisition_plan

gate = data_first_gate({
    "geometry": [
        {"source": "published_grid",      "outcome": "blocked", "detail": "401"},
        {"source": "horizons_and_faults", "outcome": "blocked"},
        {"source": "structure_map",       "outcome": "absent"},
        {"source": "well_tops",           "outcome": "absent"},
        {"source": "assumed_block",       "outcome": "used"},
    ],
    "petrophysics": [...], "fluid": [...], "scal": [...],
    "contacts": [...],     "volumes": [...],
})
# gate["decision"]     'proceed' | 'blocked'
# gate["mustDisclose"] what the downgrade gave up, per ingredient
# gate["downgraded"]   ingredients not built from their best source

acquisition_plan(gate)
# ranked by how much each gap is currently being guessed, and it separates
#   "access request -- the data exists and is catalogued"   (an ACL)
# from
#   "acquisition -- nothing of this kind was found"          (a programme)
```

Six ingredients have a ladder: `geometry`, `petrophysics`, `fluid`, `scal`,
`contacts`, `volumes`. Three rules:

1. **Every rung above the one in use needs a recorded outcome** — `used`,
   `blocked` or `absent`. `not_attempted` is a blocker, because an unattempted
   rung and an absent one yield the same model and opposite recommendations.
2. **`blocked` ≠ `absent`.** Blocked is an entitlement finding and the fix is an
   access request. Reporting it as missing data invents an acquisition
   programme that nobody needs.
3. **Any downgrade must be disclosed**, not only the bottom rung. Dropping from
   the published grid to well tops still discards the faults.

When the gate reports a downgrade on `geometry` or `scal`, the report must
decompose recovery factor into displacement × sweep, so the reader can see
which half is assumed:

```
RF = E_d (displacement, set by SCAL endpoints) × E_v (sweep, set by geometry)
```

That decomposition is what localised the Omega Sør disagreement to sweep alone,
and it is what turned "the benchmark failed" into an actionable finding.

## Building a model when there is no subsurface data at all

Sometimes there is no seismic, no log, no contact and no PVT sample — only a
published resource number and a development description. The choice then is not
between building a model and not building one; it is between an implicit guess
buried in a spreadsheet and an explicit, labelled one. **Make the guess, then
state it.** `reservoir_model_builder.structure` exists to do exactly that.

The rule is: *assume the geology, derive everything that can be derived, and put
every remaining assumption in a register that says what would replace it.*

### 1. Assume the structural style from the play, not from nothing

A rectangular tank is a guess too — just an unlabelled one that happens to be
geologically impossible. Assume instead the trap style that dominates the play,
so the guess is at least the most likely guess:

```python
from reservoir_model_builder import assume_structure, assumption_register

structure = assume_structure(sea_area="north_sea", gross_thickness_m=60.0)
print(structure.play)            # tampen_brent
print(structure.style["trap"])   # three-way dip closure sealed against a N-S normal fault
for row in assumption_register(structure):
    print(row["element"], "|", row["value"], "|", row["provenance"])
```

`assume_structure` returns the dip, the structural relief, the bounding-fault
throw and seal multiplier, a screening cell size, and a layered stratigraphy for
the play. Every parameter comes back with provenance `analogue` or `default` —
never `measured` — and every assumption records `would_be_replaced_by`, which
becomes the data-acquisition request in the report.

Pass `gross_thickness_m` and the register will additionally flag a bounding
fault whose throw is smaller than the reservoir interval: such a fault is
self-juxtaposed and cannot be assumed to seal, which silently invalidates any
two-compartment story built on it.

Available styles: `tampen_brent`, `north_sea_horst`, `north_sea_salt_dome`,
`halten_terrace`, `barents_platform`, `generic_anticline`. Passing only a
`sea_area` picks the dominant style for that area; passing nothing gives a
generic anticline.

### 2. Layer the reservoir, do not average it

`STRATIGRAPHY` gives a per-formation porosity, net-to-gross, permeability and
kv/kh for each play — Brent as Tarbert / Ness / Etive-Rannoch, Halten as Garn /
Not / Ile / Tofte-Tilje, chalk as Tor / Hod. Use it even at screening level.

A single-permeability tank cannot tell you whether a horizontal drain drains the
whole interval or only the layer it sits in, and that is usually the question the
model is being asked. The property *contrast* matters more than the absolute
values, which is why the layering is worth carrying even when the numbers are
analogues.

Modulate the properties by structural position as well — crestal rock is
normally better — because on a structural closure every well is crestal, so the
trend and the well locations are correlated.

### 3. Solve what can be solved instead of guessing it

Two geometric numbers are usually free, and two constraints are usually public.
Invert rather than assume:

```python
from reservoir_model_builder import (
    solve_contact_for_volume,
    solve_amplitude_for_split,
)

# Contact solved so the closure holds the reported in-place volume.
gwc = solve_contact_for_volume(
    volume_above=lambda depth: giip_above(depth),
    target_volume=reported_giip_Sm3,
    shallow_m=crest_depth, deep_m=deepest_top,
)

# Secondary culmination solved so the volume split matches the reported split.
amplitude = solve_amplitude_for_split(
    split_for_amplitude=lambda amp: secondary_fraction(amp),  # re-solves the contact
    target_fraction=0.23, low_m=20.0, high_m=95.0,
)
```

`solve_contact_for_volume` raises rather than returning a number when the
assumed structure cannot hold the target volume. That is a **result**, not an
error to suppress: it says the assumed relief, area or porosity is inconsistent
with the published volume, and one of them has to move.

`solve_amplitude_for_split` must be given a callable that **re-solves the fluid
contact inside every trial**. Growing a culmination adds pore volume, which
moves the contact, which changes the split. Holding the contact fixed is the
most common reason this loop fails to converge or saturates at a bracket end.

### 4. Place wells on the structure, not on the plan

A nominal well position taken from a tank model is meaningless once there is a
structure: the drain may sit partly or wholly in the water leg, and a gas well
completed below the contact produces nothing. Do not fix this by hand — place
each drain automatically:

```python
from reservoir_model_builder import longest_run_above_contact

start, length = longest_run_above_contact(depths_along_track, gwc)
if length == 0:
    raise ValueError("track is entirely below the contact - move or drop the well")
```

Take the longest contiguous run above the contact and centre the completion on
it. If the run is empty, the well as planned does not work — report that rather
than perforating water.

### 5. Write the assumption register into the deliverable

`assumption_register(structure)` returns one row per assumed element with its
value, provenance, rationale and the measurement that would replace it. Put that
table in the report verbatim. A reader must be able to see, in one place, the
difference between what was known and what was invented.

Label every number in the report with a confidence tier:

| Tier | Meaning |
| --- | --- |
| `Given` | Supplied directly in the task (a profile, a rate, a spec) |
| `Published` | Stated in an operator or authority release |
| `Strong inference` | Follows from a published fact with one clear step |
| `Derived` | Calculated from the above by a stated equation |
| `Analogue` | Taken from a play or field analogue, not from this field |
| `Assumption` | Chosen by the builder; nothing measured touches it |

And state the direction of the inversion explicitly. If the recoverable volume
was an input and the geometry was sized to honour it, then **the model cannot be
used to defend the volume** — only to test whether that volume is deliverable.
Say so in the conclusions, not in a footnote.

### What this does and does not buy you

It buys a geologically coherent model that reproduces the public constraints,
exposes failure modes a tank model hides (wells below the contact, a fault too
small to seal, a closure too small to hold the reported volume), and produces
figures an engineer can argue with.

It does not buy a subsurface interpretation. Everything geometric is a
hypothesis, and the sensitivity of the answer to that hypothesis should be
quoted alongside the answer.

## Reusing a static model somebody already built

The opposite of the sections above: the grid, porosity, permeability and region
arrays already exist — retrieved from a data platform, an RMS export or a CSV —
and the task is to get them into an OPM Flow deck without corrupting them in
transit.

That is a validation problem, not a modelling one. A deck that fails to parse
announces itself; the mistakes that matter here all produce a deck that **runs
and is wrong**:

| Mistake | Why it stays quiet |
| --- | --- |
| array length ≠ `nx*ny*nz` | padded or truncated, so every later cell holds a neighbour's value |
| zero-based region array | Eclipse regions are one-based; a `0` silently falls into region 1 |
| porosity or NTG in percent | initialises fine, pore volume ~100× too large |
| `PERMZ` left equal to `PERMX` | removes the barrier to coning — optimistic, not broken |
| sentinel (`-999`) in an inactive cell | harmless until `ACTNUM` is regenerated elsewhere |

```python
from reservoir_model_builder import (
    GridDimensions, StaticModelArrays, build_static_model_deck_input,
    reconcile_volume,
)

grid = GridDimensions(nx=120, ny=90, nz=24, source="published IJK grid")
model = StaticModelArrays(grid=grid)
model.add("PORO",  poro,  unit="fraction", source="geomodel: poro")
model.add("PERMX", permx, unit="mD",       source="geomodel: KLOGH")
model.add("NTG",   ntg,   unit="fraction", source="geomodel: NTG")
model.add("SATNUM", satnum, unit="index",  source="geomodel: SATNUM")

report = build_static_model_deck_input(model, kv_kh=0.1)
report["deck_writable"], report["blocked_because"]
report["validations"]      # per keyword: count, min, max, issues
report["adjustments"]      # every correction applied, and why
report["include_files"]    # poro.inc, permx.inc, ... only if writable
```

Three refusals are deliberate:

- **No default kv/kh.** Without `kv_kh` the build is blocked rather than writing
  `PERMZ = PERMX`. The assumption has to be stated, because it is the one that
  most changes the recovery.
- **No silent rebasing.** A zero-based region array blocks unless
  `rebase_zero_based_regions=True`, and then the shift appears in `adjustments`
  and in the include-file comment.
- **No geometry invention.** `SPECGRID` carries the dimensions; `COORD` and
  `ZCORN` must come from the source grid and cannot be rebuilt from cell arrays.

Finish with the one check the array validation cannot do — every unit, ordering
and contact error moves the volume:

```python
reconcile_volume(computed_stoiip_m3=stoiip, reported_p50_m3=19.3e6,
                 reported_p90_m3=15.8e6, reported_p10_m3=22.9e6)
# -> ratio, deviation_fraction, within_p90_p10, match, and a ranked diagnosis
#    when it fails: percent vs fraction, m3 vs rm3, TVD vs TVDSS, NTG counted twice
```

Retrieval from a governed platform is a separate concern: on Equinor
infrastructure the enterprise `enterprise-osdu-data-platform` skill resolves the
model in the Reservoir DDMS, maps published property names to Eclipse keywords
and reports dataspace access, then hands the arrays here.

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
- [ ] When the structure was assumed rather than mapped, the assumption register
      is in the deliverable and every row states what would replace it.
- [ ] Any number that was solved for rather than measured (a fluid contact, a
      culmination height) is labelled as an inversion of a published number, and
      the direction of the inversion is stated in the conclusions.
- [ ] Every well drain has been checked against the contact, not just placed at
      a nominal position.
- [ ] A bounding fault relied on for compartmentalisation has a throw larger
      than the reservoir interval.
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
| A well produces nothing, or the solver reports singular well equations | The drain was placed at a nominal position from a tank model and sits below the fluid contact | Place it with `longest_run_above_contact`; if the run is empty, move or drop the well |
| The culmination bisection saturates at a bracket end | The fluid contact was held fixed inside the split solve, so added pore volume never moved the contact | Re-solve the contact inside every amplitude trial |
| The closure runs off the edge of the grid | A regional dip was applied to a block that shallows continuously in one direction, so it never turns over | Make the secondary closure a four-way culmination, or extend the grid past the spill point |
| Two compartments deplete together despite a fault between them | The assumed throw is smaller than the reservoir interval, so the reservoir is self-juxtaposed | Raise the throw above the gross thickness, or model the compartments as connected |
| The assumed structure cannot hold the reported volume | Relief, area or porosity is inconsistent with the published number | Treat the exception from `solve_contact_for_volume` as a result and move one of them |

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
