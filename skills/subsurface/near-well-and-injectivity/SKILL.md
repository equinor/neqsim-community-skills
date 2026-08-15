---
name: neqsim-near-well-and-injectivity
version: "0.2.0"
description: "Derive what the rock will give and take, and hand it to NeqSim: productivity and injectivity indices, their evolution as saturation fronts develop, and the SCAL basis behind them. Standardises on OPM Flow as the reservoir simulator, pyscal for relative permeability and resdata for output, and covers converting a NeqSim compositional fluid into a black-oil PVT table that OPM Flow will actually accept. USE WHEN: a productivity or injectivity index is about to be assumed, injectors must be checked against a voidage requirement, productivity decay through the bubble point matters, a NeqSim fluid must become a PVTO/PVDG/PVTW deck section, or an Eclipse-format reservoir model must be built and run."
last_verified: "2026-08-12"
requires:
  python_packages: [pyscal, resdata, numpy]
  java_packages: [neqsim]
  env: [opm-flow]
  network: []
---

# Near-Well Simulation, Productivity and Injectivity

NeqSim answers what a well can **lift**. It does not answer what the rock around
the well will **give** or **take**. That gap is where most assumed productivity
and injectivity indices live, and it is where this skill works.

Use this skill when a number like `productivityIndex = 200 Sm3/(day·bar)` or
`injectivity = 450 Sm3/(day·bar)` is about to be typed into a model, and nobody
can say where it came from.

## When to Use

- A productivity or injectivity index is about to be assumed rather than derived.
- Injectors must be checked against a **voidage** requirement, not a rate target.
- Productivity decay through the bubble point, or injectivity change as a water
  bank develops, affects the answer.
- A NeqSim compositional fluid must become a black-oil `PVTO` / `PVDG` / `PVTW`
  deck section.
- An Eclipse-format reservoir model must be built and run in OPM Flow, and its
  inflow relationship handed back to a NeqSim wellbore or process model.

Do **not** use this skill for CFD (see `neqsim-cfd-coupling`), for full-field
development planning, or to publish a reserves number without a qualified
reservoir-engineering review.

## Inputs

- `fluid`: the NeqSim compositional fluid to convert to black-oil PVT.
- `pressure_grid`, `reservoir_temperature`: pressure nodes and temperature for
  the `BlackOilConverter.convert` call; standard conditions default to
  1.01325 bara and 288.15 K.
- `scal_basis`: `pyscal` `WaterOil` / `GasOil` endpoints and Corey exponents —
  `swirr`, `swl`, `sorw`, `sgcr`, `sorg`, `nw`, `now`, `ng`, `nog`, `krwend`,
  `kroend`, `krgend`.
- `rock_and_geometry`: permeability, net pay, porosity, wellbore radius `rw`,
  drainage radius `re`, drain length and completion geometry.
- `grid_definition`: for a radial model, `INRAD`, `DRV`, `DTHETAV`, `DZV`/`DZ`
  and `TOPS` (vector forms only).
- `well_controls`: `WCONPROD` / `WCONINJE` targets and limits, and the group
  controls (`GCONPROD`, `GCONINJE ... 'VREP'`) that set voidage replacement.
- `measured_pvt`: optional laboratory Rs and Bo at initial pressure, used to
  validate the converted table.
- `assumed_index`: the productivity or injectivity index currently in the model,
  for comparison against the derived value.

## Outputs

- `black_oil_table`: `PVTO`, `PVDG`, `PVTW` sections that satisfy Flow's
  monotonicity rules, plus the validation verdict on Rs and Bo.
- `scal_tables`: `SWOF` and `SGOF` written from the `pyscal` tables, with the
  water endpoint reported at `Sw = 1 - Sorw` (not the table maximum).
- `productivity_index`: `WPI` from the Flow SUMMARY section, with `CWPI` per
  connection, read back with `resdata`.
- `injectivity_index`: the **developed** index once the water bank has grown,
  alongside the initial value and the endpoint mobility ratio $M$.
- `voidage_check`: injected volume versus the reservoir voidage requirement.
- `fidelity_statement`: which level (analytic, radial/sector, full field) was
  used and why.
- `neqsim_handoff`: the inflow relationship passed to `InflowPerformance` for the
  NeqSim wellbore and process model.

## Engineering Method

The chain is fixed, and each link is checkable:

1. **Choose the fidelity first** — analytic (Joshi, Peaceman/Darcy radial,
   two-region Buckley-Leverett), OPM Flow radial or sector model, or full field.
   Most near-well questions never need a grid.
2. **Convert the fluid** — `BlackOilConverter` turns the NeqSim EOS fluid into
   Rs, Bo and Bg tables, which are then validated for monotonicity, continuity
   and agreement with measured PVT before they reach the deck.
3. **Build the SCAL basis explicitly** with `pyscal`, because the water
   relative-permeability endpoint governs injectivity far more strongly than
   absolute permeability.
4. **Grid logarithmically** in the near-well region, since half the drawdown in a
   radial system occurs within a few metres of the wellbore.
5. **Run OPM Flow** on the Eclipse-format deck and read `WPI` / `CWPI` and the
   rates back with `resdata`.
6. **Evaluate injectivity on the endpoint mobility ratio**
   $M = [k_{rw}(S_{or})/\mu_w] / [k_{ro}(S_{wi})/\mu_o]$, at the **injected-water**
   temperature, and size injectors on the developed index.
7. **Hand the inflow relationship to NeqSim** rather than duplicating the
   reservoir physics in the process model.

## One simulator: OPM Flow

Reservoir simulation in this stack is **OPM Flow**. Do not mix in a second
simulator unless the task genuinely cannot be done in Flow — a model that runs in
one simulator is worth more than two half-built ones, and the Eclipse deck format
is the interchange format the rest of the industry reads.

| Tool | Version verified | Use it for |
|---|---|---|
| **OPM Flow** | 2026.04 | the reservoir simulator: black-oil, three-phase, Eclipse-format decks |
| `pyscal` | 0.17.0 | relative permeability and capillary pressure; writes the SWOF/SGOF tables the deck needs |
| `resdata` | 6.3.2 | read the EGRID, INIT, UNRST and SMSPEC output Flow writes |
| NeqSim `BlackOilConverter` | 3.17.0 | compositional EOS fluid → black-oil PVT |

`OpenFOAM` is CFD and is **not** a reservoir simulator — no black-oil PVT, no
well models, no relative permeability. Keep it for the CFD work in
`neqsim-cfd-coupling`.

### Getting Flow to run

Flow is Linux software. On Windows use WSL2 or a container:

```dockerfile
FROM ubuntu:24.04
# Flow aborts with no error message under a non-English locale.
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common ca-certificates gnupg \
 && apt-add-repository -y ppa:opm/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      mpi-default-bin libopm-simulators-bin python3-opm-common \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /data
ENTRYPOINT ["flow"]
```

```powershell
docker build -t opm-flow:2026.04 .
docker run --rm -v "${PWD}/deck:/data" opm-flow:2026.04 CASE.DATA --output-dir=/data/out
```

`mpi-default-bin` is required even for a serial run, because the OPM binaries
link against the MPI libraries.

## NeqSim compositional fluid → black-oil table

This is the join between the two halves of the stack, and it is where the silent
errors live.

```python
result = jneqsim.blackoil.BlackOilConverter.convert(
    fluid, 273.15 + T_C, pressure_grid, 1.01325, 288.15)
```

### Validate the table before it reaches the deck

A black-oil conversion can fail *quietly* — it returns a table, the table looks
plausible in a plot, and every downstream number is wrong. Check all four:

1. **Rs strictly increasing with pressure up to the bubble point**, and non-zero
   everywhere above a couple of bara. A live oil with `Rs = 0` at 40 bara is a
   failed flash, not a dead oil.
2. **Rs continuous.** A step change — say `0 → 40 Sm3/Sm3` across one bar — is the
   signature of a flash that converged to the trivial single-phase solution at the
   lower pressures.
3. **Bo rises with pressure below Pb and falls above it.** A Bo sitting at ~1.00
   below Pb is reporting *dead* oil.
4. **Rs and Bo at the initial pressure match the measured PVT** to a few per cent.
   If there is no measured PVT, say so and treat every derived index as analogue.

> **Known trap (fixed in NeqSim 3.17.0, PR #2976).** Building a phase's standalone
> system with `setMolarComposition()` leaves the stale phase and K-value state from
> the parent flash in place, and the next flash can converge to the trivial
> single-phase solution — reporting `Rs = 0` for a live oil. Build from
> `setEmptyFluid()` + `addComponent()` instead. On an older NeqSim, a table whose
> Rs collapses below some pressure has hit exactly this.

### Writing PVTO, PVDG and PVTW that Flow will accept

Flow enforces monotonicity that converter output will not satisfy on its own.

**PVTO** — within each undersaturated branch, `Bo` must be **strictly
decreasing** with pressure. You cannot reuse the saturated rows as the branch:
along the saturated curve Bo *rises*. Build each branch from the oil
compressibility fitted to the genuinely undersaturated rows:

$$
c_o = -\frac{1}{\Delta p}\,\ln\frac{B_o(p_2)}{B_o(p_1)}
\qquad
B_o(p) = B_o(p_b)\,e^{-c_o\,(p - p_b)}
$$

and the same shape, opposite sign, for viscosity.

**PVDG** — `Bg` must be strictly decreasing. Converters typically *clamp* Bg
above the bubble point, which produces repeated values and a rejected deck. Keep
the computed saturated branch and extrapolate the dry-gas branch as
$B_g \propto 1/p$.

### Initialising an undersaturated oil

With `DISGAS` active and no `RSVD` table, Flow requires the EQUIL datum depth to
sit exactly at the gas–oil contact. An undersaturated reservoir has no GOC in the
model, so supply a constant-Rs `RSVD` table and point EQUIL item 9 at it:

```
EQLDIMS
  1 100 /
...
EQUIL
-- datum  Pdatum  OWC  Pcow  GOC  Pcog  Rsvd Rvvd N
  695.8 70.680 718.3 0.0 623.3 0.0 1 1* 0 /

RSVD
  653.3 47.47901
  738.3 47.47901 /
```

## Common Mistakes

Deck traps that cost a run each:

| Symptom | Cause | Fix |
|---|---|---|
| `String 'P2' / not formatted as valid keyword` | one slash per well in a SUMMARY well list | a well list is **one** record: `WBHP` then `'P1' 'P2' ... /` |
| `Could not convert string RATE to bool` | wrong item index in `GCONPROD` | item 7 is the exceed procedure — `'FIELD' 'ORAT' <q> 3* 'RATE' /` |
| horizontal well drains one cell | `COMPDAT` ranges over **K only** | emit one record per cell along the drain, with the `'Y'` (or `'X'`) direction flag |
| injectors run away to the fracture limit | an explicit well target overrides group control | put the wells on `'GRUP'` in `WCONINJE` and set `GCONINJE ... 'VREP' 3* 1.0 /` |
| absurd produced-water rates | no liquid limit on the producers | set `WCONPROD` item 7 to the tubing or ESP capacity |
| Flow exits silently, no message | non-English locale | `LANG=C.UTF-8 LC_ALL=C.UTF-8` |

## Near-well radial models

Flow **does** support cylindrical grids, but the implementation is narrower than
the Eclipse specification: `RADIAL` in RUNSPEC, then `INRAD`, `DRV`, `DTHETAV`,
`DZV` or `DZ`, and `TOPS`. `DR` and `DTHETA` are *not* accepted — it must be the
vector forms. `TOPS` takes exactly `NX*NY` values, the angles must not sum to more
than 360°, and `CIRCLE` applies only when they sum to exactly 360°.

Flow reports the productivity index directly: request `WPI` (and `CWPI` for the
per-connection value) in the SUMMARY section and read it back with `resdata`.

## Decide the fidelity before you build anything

Most near-well questions do not need a grid.

**Analytic** — Joshi for a drain, Peaceman/Darcy radial for a vertical well, and a
two-region Buckley-Leverett estimate for injectivity. Milliseconds. Start here,
and often finish here.

**OPM Flow radial or sector model** — when the saturation front itself is the
question: gravity override, cross-flow between layers, or a real completion
geometry.

**Full field** — when well count, pattern and voidage interact, which is exactly
when an injector count is being decided.

Say which you chose and why.

## Grid the near-well region logarithmically

Half the drawdown in a radial system happens within a few metres of the
wellbore. A uniform grid puts nearly all its cells where nothing is happening.

```python
import numpy as np, math
edges = np.logspace(math.log10(0.108), math.log10(800.0), 41)   # rw to re
drv = np.diff(edges)
```

## Make the SCAL basis explicit with pyscal

Injectivity is governed by the water relative-permeability **endpoint** far more
than by absolute permeability. A Darcy-range reservoir with `krwend = 0.1` is a
poor injector; a 200 mD reservoir with `krwend = 0.5` is a good one.

```python
from pyscal import WaterOil, GasOil

wo = WaterOil(swirr=0.20, swl=0.20, sorw=0.25, h=0.02)
wo.add_corey_water(nw=2.5, krwend=0.35)
wo.add_corey_oil(now=3.0, kroend=0.90)

go = GasOil(swirr=0.20, swl=0.20, sgcr=0.05, sorg=0.25, h=0.02)
go.add_corey_gas(ng=2.0, krgend=0.85)
go.add_corey_oil(nog=3.0, kroend=0.90)
```

Write `wo.table[["SW","KRW","KROW"]]` straight out as `SWOF` and the GasOil table
as `SGOF`. Vary `krwend` and `sorw` before varying permeability. That is where
the answer moves.

> `wo.table["KRW"].max()` is **1.0**, at `Sw = 1`. The endpoint you want is `krw`
> at `Sw = 1 - Sorw`. Reporting the maximum instead silently overstates
> injectivity by a factor of three.

## Injectivity does not always decline

The common assumption is that injectivity falls as water replaces oil. Whether
it does depends on the **endpoint mobility ratio**:

$$
M = \frac{k_{rw}(S_{or}) / \mu_w}{k_{ro}(S_{wi}) / \mu_o}
$$

- $M > 1$ — water is more mobile than the oil it replaces, and injectivity
  **improves** as the bank grows. Common in viscous-oil fields.
- $M < 1$ — injectivity declines, and the injector count must be set on the
  developed value, not the initial one.

Cold seawater into a warm reservoir raises $\mu_w$ and can flip $M$ below 1 on
its own. Evaluate at the **injected-water** temperature, not the reservoir
temperature. Size injectors on the **developed** index either way — sizing on the
initial value is how a waterflood ends up short of injectors five years in.

## Python Usage Pattern

End to end: NeqSim fluid → black-oil table → deck → Flow → index → NeqSim.

```python
import numpy as np, math
from pyscal import WaterOil
from resdata.summary import Summary

# 1. Compositional fluid -> black-oil PVT, then validate before it reaches the deck.
pressure_grid = np.linspace(400.0, 10.0, 40)
table = jneqsim.blackoil.BlackOilConverter.convert(
    fluid, 273.15 + 82.0, pressure_grid, 1.01325, 288.15)

# 2. SCAL basis - the water endpoint, not the table maximum.
wo = WaterOil(swirr=0.20, swl=0.20, sorw=0.25, h=0.02)
wo.add_corey_water(nw=2.5, krwend=0.35)
wo.add_corey_oil(now=3.0, kroend=0.90)
krw_end = float(wo.table.loc[wo.table["SW"] <= 1.0 - 0.25, "KRW"].iloc[-1])

# 3. Logarithmic near-well grid from rw to re.
edges = np.logspace(math.log10(0.108), math.log10(800.0), 41)
drv = np.diff(edges)

# 4. Run Flow on the deck (Linux / WSL2 / container), then read the index back.
#    docker run --rm -v "${PWD}/deck:/data" opm-flow:2026.04 CASE.DATA --output-dir=/data/out
summary = Summary("out/CASE.SMSPEC")
productivity_index = summary["WPI:P1"].values[-1]      # Sm3/(day*bar)

# 5. Hand the inflow relationship to NeqSim - do not duplicate it there.
from neqsim.process.equipment.reservoir import InflowPerformance
ipr = InflowPerformance.composite(productivity_index, reservoir_pressure, bubble_point)
```

Use `InflowPerformance.joshiHorizontal(...)` when the drain geometry is the
question and `radialProductivityIndex(...)` as a sanity check on any assumed
index. If the two differ by more than a factor of two, one of them describes a
different well.

## Validation Checklist

- **Compare against the assumed index.** A derived index more than 2× the
  assumed one means the wells are not the constraint, and adding producers buys
  far less than the assumed value implies.
- **Check the injectors against the voidage requirement**, not against a rate
  target. If the injectors cannot take the water the reservoir needs, pressure
  support fails and both rate and recovery fall.
- **Sanity-check simulated rates against the voidage demand.** Water injection an
  order of magnitude above voidage means the wells are on the wrong control, not
  that the rock is good.
- **Watch the units.** `pyscal` is dimensionless; the Darcy constant that gives
  Sm3/(day·bar) from mD, m and cP is `0.053577`, equivalent to the field-unit
  `0.00708` with net pay in feet.
- **Never read an injectivity index off a producer's PI.** Different fluid,
  different mobility, different direction.

## Limitations

- OPM Flow is a **black-oil** simulator here. Compositional effects — gas
  injection with condensate dropout, miscible displacement, CO2 solubility in
  brine — are outside what this chain represents.
- The black-oil conversion is only as good as the EOS fluid behind it. Without
  measured PVT to check Rs and Bo against, every derived index is an analogue.
- `pyscal` Corey curves are a parameterisation, not measured SCAL. Endpoints
  drive injectivity, so an unmeasured `krwend` is the dominant uncertainty.
- Flow's cylindrical-grid support is narrower than the Eclipse specification
  (vector keyword forms only, `TOPS` of exactly `NX*NY`, angles summing to no
  more than 360°).
- Flow is Linux software; on Windows it needs WSL2 or a container, and it aborts
  silently under a non-English locale.
- Near-well models say nothing about aquifer support, pattern interference or
  field-wide voidage once the question outgrows the drainage region.
- Screening and engineering support only — not a substitute for a qualified
  reservoir-engineering review or a formal reserves estimate.

## References

- OPM Flow (Open Porous Media), reservoir simulator, version 2026.04 —
  https://opm-project.org
- `pyscal` 0.17.0, relative permeability and capillary pressure —
  https://equinor.github.io/pyscal
- `resdata` 6.3.2, Eclipse-format output reader —
  https://github.com/equinor/resdata
- Joshi, S. D. (1988). *Augmentation of Well Productivity With Slant and
  Horizontal Wells.* JPT 40(6), 729-739.
- Peaceman, D. W. (1978). *Interpretation of Well-Block Pressures in Numerical
  Reservoir Simulation.* SPE Journal 18(3), 183-194.
- Buckley, S. E. and Leverett, M. C. (1942). *Mechanism of Fluid Displacement in
  Sands.* Transactions of the AIME 146(1), 107-116.
- NeqSim `BlackOilConverter` 3.17.0 (PR #2976) —
  https://github.com/equinor/neqsim

## Chain to

- `neqsim-api-patterns` — building the NeqSim wellbore and process model that
  consumes the inflow relationship
- `neqsim-subsea-and-wells` — completion, casing and barrier design
- `neqsim-reservoir-modelling` — when the question outgrows the near-well region
- `neqsim-benchmark-reference-data` — validating a derived index against
  published field data
- `neqsim-input-validation` — before any of it
