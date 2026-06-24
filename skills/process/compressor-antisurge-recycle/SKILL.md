---
name: neqsim-compressor-antisurge-recycle
version: 0.1.0
description: "Set up anti-surge recycle control for a centrifugal compressor in NeqSim, including auto-generating a compressor chart with surge and stonewall curves when no vendor chart is given. USE WHEN: a task needs to protect a NeqSim compressor from surge with a recycle (spill-back) loop driven by the anti-surge Calculator, and a compressor performance chart (with surge and stonewall curves) is either supplied or must be generated."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages:
    - neqsim
  env: []
  network: false
---

# Compressor Anti-Surge Recycle Setup

This skill explains how to protect a centrifugal compressor against surge in a
NeqSim `ProcessSystem` by adding a recycle (spill-back) loop controlled by the
built-in anti-surge `Calculator`. It also explains how to **auto-generate a
compressor chart with surge and stonewall curves** when no vendor chart is
available, because the anti-surge loop needs a surge limit to act against.

The pure-Python helper (`AntiSurgeRecycleModel`) is an educational planning aid
that mirrors NeqSim's proportional anti-surge step so an agent can pre-estimate
the recycle flow and decide whether a chart must be generated first. Real
control design must use the validated NeqSim equipment classes below and a
qualified rotating-equipment review (API 617 / API 692).

## When to Use

Use this skill when:

- A NeqSim compressor operating point can fall to the left of its surge line at
  low throughput (turndown, start-up, trips) and needs recycle protection.
- You must build the anti-surge recycle topology (surge curve, recycle stream,
  discharge splitter, anti-surge `Calculator`, anti-surge valve, `Recycle`).
- **No vendor compressor chart is provided** and a chart with surge and
  stonewall curves must be generated from the compressor's design point.
- You want a screening estimate of the recycle flow required to keep the
  compressor off surge before running the full simulation.

Do not use this skill as a substitute for vendor performance maps, anti-surge
controller tuning, dynamic surge/transient analysis, or rotating-equipment
design review.

## Inputs

- Compressor inlet (suction) volumetric flow at the operating point (m3/h).
- Surge-limit flow at the operating head and speed (m3/h). When no vendor chart
  is available, this comes from the generated surge curve.
- Whether a vendor compressor chart is provided (`chart_provided`).
- Existing recycle flow, if any (m3/h).
- For chart generation: a design speed, the number of speed lines, and
  optionally impeller diameter / number of stages for advanced corrections.

## Outputs

- `needs_chart_generation` — whether a chart must be generated before control.
- `in_surge` — whether the operating point is at or below the surge flow.
- `surge_margin_fraction` — `(inlet_flow - surge_flow) / surge_flow`.
- `recommended_recycle_flow` — screening recycle flow to add at suction (m3/h).
- `total_suction_flow` — inlet flow plus recommended recycle (m3/h).
- `recycle_warning` — `ok`, `recycle`, or `surge`.
- Assumptions and limitations.

## Engineering Method

A centrifugal compressor surges when the inlet volumetric flow drops below the
surge flow at the current head/speed. Anti-surge control opens a recycle line
from discharge back to suction to keep the **total** suction flow above the
surge limit plus a margin.

NeqSim implements this with a recycle loop and an anti-surge `Calculator`:

1. A **surge curve** on the compressor chart provides the surge flow versus head.
2. A low-flow **recycle stream** is added into the compressor suction.
3. A **splitter** on the compressor discharge creates a forward branch
   (`getSplitStream(0)`) and a recycle branch (`getSplitStream(1)`).
4. An **anti-surge `Calculator`** (its name **must start with**
   `"anti surge calculator"`) reads the compressor and writes the splitter
   recycle flow each iteration. Internally it compares the inlet flow to the
   surge flow: far from surge (`inlet_flow > 1.2 * surge_flow`) it drives recycle
   to a minimum; otherwise it adds a proportional, capped step
   `0.5 * (surge_flow - inlet_flow)` to the recycle branch.
5. An **anti-surge valve** on the recycle branch drops the discharge pressure
   back to suction pressure.
6. A **`Recycle`** unit closes the loop, feeding the valve outlet back into the
   placeholder suction recycle stream.

### Generating a Compressor Chart When None Is Given

The anti-surge loop needs a surge limit, so if no vendor chart exists a chart
must be generated first. NeqSim builds a chart from the compressor's design
operating point and **automatically populates both the surge curve and the
stonewall curve**:

- `Compressor.generateCompressorChart("normal curves", numberOfSpeeds)` builds a
  multi-speed chart whose lowest-flow points form the surge curve and whose
  highest-flow points form the stonewall curve.
- `CompressorChartGenerator` gives finer control (chart type, Reynolds/Mach
  corrections, multistage surge correction, impeller diameter) and also returns
  a chart with surge and stonewall curves attached.

After generation, the surge flow at the operating head is available through
`Compressor.getSurgeFlowRate()` and the distance to surge through
`Compressor.getDistanceToSurge()`.

The `AntiSurgeRecycleModel` mirrors step 4 so you can estimate the recycle flow
and flag whether chart generation (`needs_chart_generation`) is required before
wiring the loop.

## Python Usage Pattern

Screening estimate of the recycle flow (no NeqSim required):

```python
from compressor_antisurge_recycle import AntiSurgeRecycleModel

model = AntiSurgeRecycleModel()
plan = model.plan(
    inlet_flow=4200.0,   # m3/h at suction
    surge_flow=5000.0,   # m3/h surge limit at operating head
    chart_provided=True,
    current_recycle=0.0,
)
print(plan.recommended_recycle_flow, plan.recycle_warning)
```

Generate a compressor chart (with surge and stonewall curves) when none is
given, using NeqSim through the `neqsim` package:

```python
from neqsim import jneqsim

# `compressor` is an existing neqsim.process.equipment.compressor.Compressor
compressor.setSpeed(8000.0)   # design speed (rpm)
compressor.run()              # solve the design point first
compressor.generateCompressorChart("normal curves", 5)  # 5 speed lines

# Surge and stonewall curves are now populated automatically.
chart = compressor.getCompressorChart()
surge_flow = compressor.getSurgeFlowRate()
distance_to_surge = compressor.getDistanceToSurge()
```

Finer control with the generator (optional corrections):

```python
from neqsim import jneqsim

generator = jneqsim.process.equipment.compressor.CompressorChartGenerator(compressor)
generator.setChartType("interpolate and extrapolate")
generator.enableAdvancedCorrections(numberOfStages)  # Reynolds + Mach + multistage
chart = generator.generateCompressorChart("normal curves", 5)
compressor.setCompressorChart(chart)
```

Wire the anti-surge recycle loop (generic data, after a chart exists):

```python
from neqsim import jneqsim

splitter_pkg = jneqsim.process.equipment.splitter
valve_pkg = jneqsim.process.equipment.valve
util_pkg = jneqsim.process.equipment.util

suction_pressure = compressor.getInletStream().getPressure("bara")

# 2. Low-flow placeholder recycle stream into the compressor suction.
recycle_gas = compressor.getInletStream().clone()
recycle_gas.setName("anti surge recycle gas")
recycle_gas.setFlowRate(1.0, "kg/hr")
recycle_gas.run()
process.add(recycle_gas)

# 3. Splitter on the compressor discharge: branch 0 forward, branch 1 recycle.
gas_splitter = splitter_pkg.Splitter("anti surge splitter", compressor.getOutletStream(), 2)
gas_splitter.run()
process.add(gas_splitter)

# 4. Anti-surge Calculator (name MUST start with "anti surge calculator").
anti_surge_calc = util_pkg.Calculator("anti surge calculator 1")
anti_surge_calc.addInputVariable(compressor)
anti_surge_calc.setOutputVariable(gas_splitter)
process.add(anti_surge_calc)

# 5. Anti-surge valve on the recycle branch back to suction pressure.
anti_surge_valve = valve_pkg.ThrottlingValve("anti surge valve", gas_splitter.getSplitStream(1))
anti_surge_valve.setOutletPressure(suction_pressure, "bara")
anti_surge_valve.run()
process.add(anti_surge_valve)

# 6. Recycle unit closes the loop into the placeholder suction stream.
recycle = util_pkg.Recycle("recycle anti surge")
recycle.addStream(anti_surge_valve.getOutletStream())
recycle.setOutletStream(recycle_gas)
recycle.setTolerance(1e-2)
process.add(recycle)

process.run()
```

The forward process continues on `gas_splitter.getSplitStream(0)`.

## Validation Checklist

- The compressor has a chart with an active surge curve before the loop runs;
  if not, generate one and confirm `getSurgeCurve().isActive()` is true.
- The anti-surge `Calculator` name starts with `"anti surge calculator"`.
- The `Calculator` input is the `Compressor` and the output is the discharge
  `Splitter`.
- The anti-surge valve sits on `getSplitStream(1)` and drops to suction pressure.
- The `Recycle` outlet stream is the placeholder suction recycle stream.
- After `process.run()`, the total suction flow exceeds the surge flow plus the
  intended margin (`getDistanceToSurge()` is positive).
- Recycle convergence tolerance is set (for example `setTolerance(1e-2)`).

## Common Mistakes

- Naming the calculator anything that does not start with
  `"anti surge calculator"` — the anti-surge logic then never triggers.
- Wiring the anti-surge valve to the forward branch `getSplitStream(0)` instead
  of the recycle branch `getSplitStream(1)`.
- Running the loop without a surge curve, so there is no surge flow to compare
  against (generate a chart first when no vendor chart is given).
- Using a zero or negative placeholder recycle flow that the `Recycle` cannot
  converge from; start from a small positive flow (for example 1 kg/hr).
- Reading the surge flow at the wrong head or speed — the surge flow must match
  the operating head and speed.
- Treating the generated chart as a vendor-validated map; generated charts are
  estimates for modelling, not design certification.

## Limitations

- Screening logic only; it does not tune an anti-surge controller or set
  recycle valve `Cv`, response time, or surge control line offset.
- It does not perform dynamic surge, ESD, or transient recycle analysis.
- Generated compressor charts are model estimates, not vendor performance maps.
- It does not replace API 617 / API 692 rotating-equipment design and review.
- Results require qualified human review before any design or operating use.

## Related NeqSim Functionality

- `neqsim.process.equipment.compressor.Compressor` —
  `generateCompressorChart(...)`, `getCompressorChart()`,
  `getSurgeFlowRate()`, `getDistanceToSurge()`, `setSpeed(...)`.
- `neqsim.process.equipment.compressor.CompressorChart` —
  `getSurgeCurve()`, `getStoneWallCurve()`, `generateSurgeCurve()`,
  `generateStoneWallCurve()`, `checkStoneWall(...)`.
- `neqsim.process.equipment.compressor.CompressorChartGenerator` —
  `setChartType(...)`, `enableAdvancedCorrections(...)`,
  `generateCompressorChart(...)`.
- `neqsim.process.equipment.splitter.Splitter` — discharge split into forward
  and recycle branches.
- `neqsim.process.equipment.util.Calculator` — anti-surge engine
  (`runAntiSurgeCalc`) triggered by the `"anti surge calculator"` name prefix.
- `neqsim.process.equipment.valve.ThrottlingValve` — anti-surge recycle valve.
- `neqsim.process.equipment.util.Recycle` — closes the recycle loop.

In Python these classes are reachable through the `neqsim` package (for example
`from neqsim import jneqsim`).

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- API Standard 617 — Axial and Centrifugal Compressors.
- API Standard 692 — Surge Control for Centrifugal Compressors.
