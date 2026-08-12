---
name: neqsim-near-well-and-injectivity
version: "0.1.0"
description: "Simulate the rock around a well to answer what it will give or take, using the open-source Python subsurface stack: open-DARTS for near-well reservoir simulation, pyscal for the relative-permeability basis, resdata for Eclipse output, welltestpy for well-test interpretation, and opm/ResSimPy for deck handling. Produces productivity and injectivity indices, their evolution as saturation fronts develop, and the skin and completion sensitivities behind them. USE WHEN: a task needs a productivity or injectivity index derived rather than assumed, asks whether injectors can take the voidage water, asks how productivity decays as gas breaks out or water encroaches, needs a SCAL basis made explicit, or needs to hand a defensible inflow relationship to a NeqSim wellbore or process model."
last_verified: "2026-08-12"
requires:
  python_packages: [open-darts, pyscal, resdata, welltestpy, numpy]
  java_packages: []
  env: []
  network: []
---

# Near-Well Simulation, Productivity and Injectivity

NeqSim answers what a well can **lift**. It does not answer what the rock around
the well will **give** or **take**. That gap is where most assumed productivity
and injectivity indices live, and it is where this skill works.

Use this skill when a number like `productivityIndex = 200 Sm3/(day·bar)` or
`injectivity = 450 Sm3/(day·bar)` is about to be typed into a model, and nobody
can say where it came from.

## The tool stack, and what each is actually for

| Tool | Version verified | Use it for |
|---|---|---|
| `open-darts` | 1.5.0 | near-well and full-field reservoir simulation in pure Python; compositional, dead-oil, thermal; operator-based linearisation |
| `pyscal` | 0.17.0 | relative permeability and capillary pressure from Corey or LET parameters; the SCAL basis, made explicit |
| `resdata` | 6.3.2 | read Eclipse/E300 restart, summary and grid output (Equinor; successor to `ecl`) |
| `welltestpy` | 1.2.0 | interpret drawdown and buildup tests for transmissivity and storativity |
| `opm` | 2026.4 | OPM-Common deck parsing and manipulation |
| `ResSimPy` | 2.6.1 | reservoir simulation model and deck manipulation across simulators |
| `flownet` | 0.5.3 | data-driven reduced-physics reservoir models when a full grid is not warranted |

`porepy` and `pyopmnearwell` are **not on PyPI** — install from source if
fractured-media or OPM near-well work is genuinely required.

## Decide the fidelity before you build anything

Most near-well questions do not need a grid. Choose deliberately:

**Analytic two-region** — minutes to write, milliseconds to run. A swept region
at residual oil and an unswept region at connate water, in series. Enough to
size an injector and to show how injectivity moves as the bank grows. Start
here.

**open-DARTS radial model** — minutes to run. Use when the saturation front
itself is the question: gravity override, cross-flow between layers, thermal
fronts, or a genuinely compositional near-well effect.

**Full-field** — a different study. Do not build one to answer an inflow
question.

## Grid the near-well region logarithmically

Half the drawdown in a radial system happens within a few metres of the
wellbore. A uniform grid puts nearly all its cells where nothing is happening.

```python
import numpy as np, math
edges = np.logspace(math.log10(0.108), math.log10(800.0), 41)   # rw to re
```

## Make the SCAL basis explicit with pyscal

Injectivity is governed by the water relative-permeability **endpoint** far more
than by absolute permeability. A Darcy-range reservoir with `krwend = 0.1` is a
poor injector; a 200 mD reservoir with `krwend = 0.5` is a good one.

```python
from pyscal import WaterOil

wo = WaterOil(swirr=0.20, swl=0.20, sorw=0.25, h=0.02)
wo.add_corey_water(nw=2.5, krwend=0.35)
wo.add_corey_oil(now=3.0, kroend=0.90)
table = wo.table[["SW", "KRW", "KROW"]]
```

Vary `krwend` and `sorw` before varying permeability. That is where the answer
moves.

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

Size injectors on the **developed** index either way. Sizing on the initial
value is how a waterflood ends up short of injectors five years in.

## Hand the result to NeqSim, do not duplicate it

The near-well model produces the inflow relationship; NeqSim consumes it.

```python
# near-well study -> productivity index -> NeqSim inflow model
from neqsim.process.equipment.reservoir import InflowPerformance
ipr = InflowPerformance.composite(productivity_index, reservoir_pressure, bubble_point)
```

Use `InflowPerformance.joshiHorizontal(...)` when the drain geometry is the
question and `radialProductivityIndex(...)` as a sanity check on any assumed
index. If the two differ by more than a factor of two, one of them describes a
different well.

## Checks that catch real errors

- **Compare against the assumed index.** A derived index more than 2× the
  assumed one means the wells are not the constraint, and adding producers buys
  far less than the assumed value implies.
- **Check the injectors against the voidage requirement**, not against a rate
  target. If the injectors cannot take the water the reservoir needs, pressure
  support fails and both rate and recovery fall.
- **Watch the units.** `pyscal` is dimensionless; the Darcy constant that gives
  Sm3/(day·bar) from mD, m and cP is `0.053577`, equivalent to the field-unit
  `0.00708` with net pay in feet.
- **Never read an injectivity index off a producer's PI.** Different fluid,
  different mobility, different direction.

## Chain to

- `neqsim-api-patterns` — building the NeqSim wellbore and process model that
  consumes the inflow relationship
- `neqsim-subsea-and-wells` — completion, casing and barrier design
- `neqsim-reservoir-modelling` — when the question outgrows the near-well region
- `neqsim-benchmark-reference-data` — validating a derived index against
  published field data
