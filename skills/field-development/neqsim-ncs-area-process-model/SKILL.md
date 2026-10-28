---
name: neqsim-ncs-area-process-model
calculation_basis: "screening"
version: "0.1.0"
description: "Assemble one common NeqSim ProcessModel for an NCS catchment: all field/platform models that deliver to one terminal (Kollsnes, Kaarstoe, Nyhamna, Mongstad) plus shared structures and export pipelines, with back-pressure coupling, common fluid basis and verification against terminal flow. USE WHEN: field models exist and a value-chain model to a terminal is wanted, or a shared export line couples several platforms."
last_verified: "2026-10-19"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# NCS Area Process Model (terminal-anchored value chain)

Turns a set of finished field or platform models into one coupled model of everything that
delivers to a terminal. The result answers questions no single-field model can: how one field's
rate changes another field's back-pressure through a shared line, what arrives at the terminal
(rate, P, T, composition, liquid load), and which structure, line or terminal limit binds first.

It is a model-assembly method. The physics stays in the per-field models and in NeqSim pipe and
network classes. Connectivity and nameplate capacity come from `neqsim-ncs-infrastructure-network`;
shelf-wide optimisation stays in `neqsim-ncs-value-chain-optimization`.

## When to Use

- "Make one model for everything that produces to Kollsnes (or Kaarstoe, Nyhamna, Mongstad, Sture)."
- Several platforms share an export line or a riser platform and the back-pressure interaction matters.
- A tie-in or rate change must be tested against the whole route, not one platform.
- Arrival conditions at a terminal are needed as one consistent set (rate, P, T, composition).

Do not use for a single field (use the process-model skills) or for a shelf-wide nomination
optimum (use `neqsim-ncs-value-chain-optimization`).

## Inputs

- The terminal or plant and the product (gas, rich gas, oil, condensate).
- The finished per-field or per-platform models, with boundary stream, fluid basis, rate basis and status.
- Geometry of each export line and shared structure: length, ID, wall, roughness, elevation profile, U-value.
- Measured rate, pressure and temperature at both ends of every line and at the terminal, for at
  least two windows (calibration and hold-out).
- Operating routing evidence: valve states, historian flows, metered terminal flows.

## Outputs

- Catchment table per product, with every override of the open topology and its source.
- The coupled `ProcessModel`: field areas, line areas, junction areas, terminal area.
- Rate, P, T and composition at every node; terminal arrival profile.
- Binding-constraint ranking (equipment constraints, line velocity, pressure, erosional limits).
- Verification table (mass balance, arrival conditions, line pressure drop, coupling response).
- List of boundaries that were imposed instead of computed, and the assumptions and data gaps.

## Engineering Method

### Step 1 - Discover the catchment

Run the open-graph queries in the Python Usage Pattern section below.
Snapshot of 2026-09 for Kollsnes: Troll (A, B, C), Kvitebjoern, Visund, Fram, Fram H-Nord, Byrding.
Trunk elements: Troll A - Kollsnes, Kvitebjoern gas pipeline to Kollsnes, Zeepipe IIA/IIB and Vestprosess
out of Kollsnes. The liquid legs are separate: Troll B/C oil to Mongstad (Troll Oil Pipeline I/II),
Kvitebjoern condensate to Kollsnes then Vestprosess to Mongstad, Gjoea oil to Troll C.
Always list gas and liquid catchments separately, because a field can reach different terminals
with each product.

**Treat the open graph as the first draft, not the truth.** Open topology is built from Sodir transport
text and can lag operations. Example: the snapshot routes Valemon gas to Heimdal, while the
operator's model and historian show all Valemon gas and condensate going to Kvitebjoern since 2023
(crossover valve open, Heimdal riser pig-launcher valve closed). Check every member against
operating evidence (P&ID valve states, historian flows, metered terminal flows) and record the
override with its source. Never leave a member out because the open graph misses it.

### Step 2 - Inventory the per-field models

For every platform in the catchment, record in one table:

| Item | Why it matters |
|---|---|
| Boundary: last modelled stream (platform export valve, export compressor discharge, line end, riser top) | the coupling point; a line that is already inside a field model must not be added twice |
| Boundary pressure and temperature: imposed or computed | imposed boundaries must become computed ones at the coupling point |
| Fluid basis: EOS, component list, pseudo-component method, mixing rule | components must match to mix streams |
| Rate basis: standard or actual, MSm3/d or kg/h, gauge or absolute | the most common source of a 1 atm / 15 C error |
| Operating window, calibration date, status | a hold-out-verified model is not a design model |
| Utilisation and capacity constraints exposed | needed for the area bottleneck ranking |

Models built on one shared characterisation (for example a common PR78 component set with a
common pseudo-component split) mix directly. Where bases differ, re-map each fluid onto one
component list first; mixing streams of different bases silently loses mass or composition.

### Step 3 - Lay out the areas

One `ProcessSystem` per area, all in one `ProcessModel` (`plant.add("area", ps)`). Never nest a
`ProcessModel` or `ProcessModule` inside a `ProcessSystem`.

| Area type | Contents |
|---|---|
| Field area | the existing platform model, unchanged internally |
| Line area | one `PipeBeggsAndBrills` (or equivalent) per physical segment: riser, seabed line, riser, with length, ID, roughness, elevation profile, U-value |
| Junction area | shared riser platform, tie-in manifold, SSIV station or mixer where streams meet |
| Terminal area | slug catcher / inlet separator, with the terminal pressure as the single downstream boundary |

Rules: pass cross-area streams by object reference; a stream belongs to one area; split a shared
line at every tie-in so each segment has one flow; keep gas, rich gas and liquid lines as separate
networks that share only the platforms; keep one terminal pressure per product.

### Step 4 - Couple pressure and rate

Platforms set rate, the network sets pressure. Back-pressure propagates upstream:

1. Fix the terminal pressure (the only imposed pressure in the model).
2. Solve each line from the terminal backwards for the arrival pressure it needs at its upstream end.
3. Use that arrival pressure as the downstream boundary of the platform model (export pressure
   controller set-point, separator pressure or compressor discharge target).
4. Re-solve the platforms; iterate until the junction pressures stop changing. Use
   `ProcessModel` `runUntilConverged` and let NeqSim choose the tolerances; prefer
   `makeRecycles()` / automatic recycles over hand-written tears.

Where a platform controls separator pressure to follow the line pressure (as Valemon does against
the Kvitebjoern line), model that controller or set the separator pressure from the line result;
do not impose both.

For a shared looped or branched gas network use `LoopedPipeNetwork` / `NetworkOptimizer`
(see `neqsim-pipeline-and-terminal-networks`); for transient linepack `TransientGasNetwork`.

### Step 5 - Keep it fast: platform interface models

A full well-to-export model of every platform in one solve is slow. Use two levels:

- **Detailed**: every platform in full, for verification and bottleneck work.
- **Interface**: each platform reduced to a table or surrogate of export rate, P, T and composition
  versus back-pressure, built from sweeps of the detailed model (`copy()` the model and sweep the
  boundary). Use the interface level for network, scenario and optimisation loops and refresh it
  when a platform model changes.

Record the sweep range; never extrapolate an interface beyond it.

## Python Usage Pattern

```python
from ncs_infrastructure_network import NcsNetwork
net = NcsNetwork.load()
net.upstream_fields("KOLLSNES")     # fields whose preferred route passes the node
net.export_routes("Visund")          # ordered nodes and bottleneck arc, gas and liquid
net.outage_impact("KOLLSNES", 2025)  # what the terminal strands
```

The model itself is built with the NeqSim Java API (through the project's Python bridge): one
`ProcessSystem` per area, combined with `plant.add("area", ps)`, cross-area streams passed by
object reference, then `plant.runUntilConverged(...)`.

## Validation Checklist

### Step 6 - Verify

| Check | Acceptance |
|---|---|
| Mass balance: sum of platform exports minus line holdup change minus terminal arrival | closes within the metering uncertainty |
| Terminal arrival rate, P, T and gas quality against metered or historian values | state error per variable; do not tune one platform to hide a line error |
| Each line's pressure drop against its own measurements | roughness and U-value fitted on one window, checked on another |
| Shared line: rate of field A moved, field B's pressure responds in the expected direction | sign and magnitude plausible |
| Boundary pressure at every coupling: computed upstream equals imposed downstream | no residual jump |

Use at least two operating windows (calibration and hold-out). Report which platform models were
only verified on their own boundary and not in the coupled state.

### Step 7 - Report

Per product (gas, rich gas, oil, condensate): the table of fields, lines, junctions and terminal
with rate, P and T at every node; the binding constraint ranking from the equipment capacity
constraints plus line velocity, pressure and erosional limits; the terminal arrival profile; the
list of model boundaries that were imposed instead of computed; the override log from Step 1.

### Step 8 - Show it on a map

A catchment result is read faster on a map than in a table. Draw four figures from open data: (1) base state, (2) margin to the pressure the
system needs and the scenario deltas, (3) a zoom on any corridor where lines run in parallel, (4) pressure and temperature against distance
to the terminal. Conventions that worked on the Kollsnes catchment:

- Lines from Sodir FactMaps layer 6100 (as-laid polylines, open data), platforms from layer 6000, coast from Natural Earth (public domain).
- Colour each gas line by the modelled pressure from `PipeBeggsAndBrills.getPressureProfile()` (bara; `getTemperatureProfile()` is Kelvin),
  mapped on distance along the drawn polyline; one colour scale for the whole chain.
- Put the number on the figure: rate (MSm3/d), pressure (bara), temperature, margin (bar), scenario delta (bar and MW), first binding machine.
- Margin colours: below 2 bar binding, 2 to 6 bar watch, above 6 bar comfortable. Draw assumed objects ringed or dashed and say "assumed".
- Keep gas and liquid legs apart; keep every callout inside the axes; open each image before using it.

## Common Mistakes

- Adding an export line that is already inside the platform model (double pressure drop).
- Imposing a pressure at both ends of a line.
- Mixing standard and actual rates, or gauge and absolute pressure, between models.
- Treating open-data nameplate capacity as spare capacity.
- Using a field's historical export route when operations changed it.
- Mixing fluids of different component bases without re-mapping.
- Letting one platform's calibration absorb a line or terminal error.

## Limitations

Screening and system-level analysis. Liquid-loaded multiphase export lines need a transient or
multiphase simulator for slugging and ramp-up; steady-state `PipeBeggsAndBrills` gives pressure
drop and holdup only. Platform capacity beyond what the per-field models expose is not known.
Not an allocation, nomination or tariff model.

## Related Functionality

- `neqsim-ncs-infrastructure-network` - catchment, routes, outage, nameplate capacity.
- `neqsim-ncs-value-chain-optimization` - shelf-wide capacity-constrained optimum.
- `neqsim-pipeline-and-terminal-networks` - `LoopedPipeNetwork`, `TransientGasNetwork`, terminal tanks.
- `neqsim-capacity-and-utilization-analysis` - bottleneck tracking on the combined model.
- `neqsim-agentic-process-optimization` - closed-loop optimisation of a large `ProcessModel`.
- `neqsim-production-network-routing` - well-to-host routing.
- `neqsim-norwegian-continental-shelf-data` - Sodir and Gassco data access.
- `neqsim-process-modeling` (reference `multi-platform-complex`) and `neqsim-future-operation-study` - multi-platform package layout, and per-year strategy / modification register on a finished model.

## References

- Norwegian Offshore Directorate (Sodir) FactPages / FactMaps - https://factpages.sodir.no, https://factmaps.sodir.no
- Gassco, Kollsnes and the Gassled system - https://www.gassco.no/en/
- Norwegian Petroleum, "The oil and gas pipeline system" - https://www.norskpetroleum.no/en/production-and-exports/the-oil-and-gas-pipeline-system/
