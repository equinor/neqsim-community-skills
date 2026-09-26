---
name: neqsim-ncs-infrastructure-network
calculation_basis: "screening"
version: "0.1.0"
description: "Open-data graph of the whole Norwegian Continental Shelf export system - every field, discovery, host platform, trunkline, processing plant (Kårstø, Kollsnes, Nyhamna, Melkøya), receiving terminal (Emden, Dornum, Zeebrugge, Dunkerque, St Fergus, Easington, Nybro) and market - built live from the Sodir DataService, norskpetroleum.no capacity tables and Gassco plant pages, with read-only Sodir/FactPages/ENTSOG clients and NeqSim hand-offs (TiebackAnalyzer, HostFacility, LoopedPipeNetwork). USE WHEN: a task must know how NCS fields connect to the market, which fields share a pipeline or plant, how loaded each trunkline and plant is in a year, what an outage strands or reroutes, which elements are single points of failure, which host a discovery can tie into, or needs live open data (Sodir, ENTSOG flows) for an NCS value-chain study."
last_verified: "2026-09-26"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# NCS Infrastructure Network

This skill gives an agent a working model of how the Norwegian Continental Shelf
(NCS) is connected. It covers the physical chain from each field through host
platforms and trunklines to the onshore processing plants, the receiving
terminals in the UK and continental Europe, and the markets. The graph is
built from open data only:

| Source | What it provides | Access |
|--------|------------------|--------|
| Sodir DataService (ArcGIS REST) | fields, discoveries, facilities, pipelines, reserves, yearly profiles, field "Transport" descriptions | open API, NLOD 2.0 |
| Sodir FactPages CSV | the same tables as flat CSV | open API |
| norskpetroleum.no | pipeline capacity tables (gas MSm3/d, oil Sm3/d) | open download |
| gassco.eu plant pages | Kollsnes, Nyhamna capacities; Kårstø product rates; terminal list | open web |
| ENTSOG Transparency | daily physical flow at every Norwegian entry point | open API |

A bundled snapshot (`data/ncs_network_snapshot.json`) makes the skill work
offline. `scripts/build_snapshot.py` rebuilds it from the live APIs in a minute.

It is a screening model of connectivity and nameplate capacity. It is not a
hydraulic model of Gassled, not the Gassco nomination system, and not a booking
tool. Hydraulic checks are handed to NeqSim `LoopedPipeNetwork`.

## When to Use

- A task asks where a field's gas or oil goes, and through which pipelines,
  plants and terminals.
- A task needs the fields that share a trunkline, plant or terminal, e.g.
  before a tie-in, a shutdown or a capacity study.
- A task needs trunkline and plant utilisation for a historical year, or for
  forecast rates from `neqsim-ncs-value-chain-optimization`.
- A task asks what an outage of a pipeline, riser platform or plant strands or
  reroutes, or which elements are single points of failure.
- A discovery needs its nearest in-service processing hosts and a NeqSim
  `TiebackAnalyzer` screening against them.
- A study needs live open data: Sodir tables through `SodirDataService` /
  `SodirFactPages`, or observed terminal entry flows from ENTSOG to calibrate
  the model.

## Inputs

- Nothing to load the bundled snapshot: `NcsNetwork.load()`.
- Names resolve loosely: `"Troll"`, `"TROLL"`, `"Kårstø"`, `"KARSTO"` and
  discovery names such as `"7324/8-1 (Wisting)"` all work.
- `utilization(year, medium, rates=None)`: `medium` is `"gas"` (MSm3/d) or
  `"liquid"` (oil + condensate, Sm3/d); `rates` overrides history with
  `{field_id: rate}`.
- Open-API clients take an injectable `fetch(url, timeout) -> bytes`, which
  makes them testable offline.

## Outputs

- `export_routes(field)`: gas and liquid paths to market with the bottleneck
  arc and its capacity.
- `utilization(year, medium)`: flow, capacity and utilisation per trunkline and
  plant, plus overloaded elements and unrouted fields.
- `outage_impact(element, year)`: stranded rate and fields; rerouted fields with
  their new exit.
- `single_points_of_failure(year)`: elements ranked by stranded production.
- `nearest_hosts(discovery)`: in-service processing hosts with distance, water
  depth, operator and facility kind.
- NeqSim bridge results: `TiebackAnalyzer` pass/fail, CAPEX and NPV per host;
  `LoopedPipeNetwork` node pressures, velocities and deliverable rate along an
  export path.

## Engineering Method

1. **Nodes.** Fields (142), candidate discoveries (266), plants, receiving
   terminals, junctions and markets. Curated nodes and aliases live in
   `topology.py`, each with a `source_url` and `basis`.
2. **Capacitated arcs.** Every norskpetroleum table row becomes a directed arc
   with capacity, diameter, length and start year. A range such as Tampen Link
   `10–27` uses the conservative low value and keeps the range.
   Two shared trunks are split at their tie-ins:
   - Statpipe rich gas at a junction, so Johan Sverdrup, Balder and Brage only
     share the section to Kårstø;
   - Europipe II at the Baltic Pipe tie-in (27.4 MSm3/d to Nybro).
3. **Field routes from prose.** The English Sodir "Transport" text of every
   field is parsed:
   - clauses are split and each is assigned gas, liquid or both ("well stream");
   - proper names that contain commodity words ("Shell-Esso Gas and Liquid")
     are masked before classification;
   - gazetteer mentions become ordered arcs.
   Text arcs are dropped when they would bypass a capacitated table path, or
   when they would leave a plant or terminal (those outlets come from the
   tables). Each route carries `confidence` and `needs_review`.
4. **Volumes.** Sodir yearly net production: gas GSm3/yr × 1000/365 gives
   MSm3/d, and oil + condensate MSm3/yr × 10^6/365 gives Sm3/d.
5. **Utilisation.** Capacity-aware greedy routing: fields are routed largest
   first, each on the path with most headroom, splitting across paths as they
   fill. It is a feasibility screen, not a nomination optimum; use the value-chain
   optimiser for that. The 2025 snapshot routes 333.8 MSm3/d (about 122 GSm3/yr,
   in line with published NCS sales gas) with no element above capacity.
6. **Resilience.** An element is removed and every affected field is rerouted.
   Fields with no remaining path to market count as stranded.

## Python Usage Pattern

```python
from ncs_infrastructure_network import NcsNetwork
from ncs_infrastructure_network import neqsim_bridge as nb

net = NcsNetwork.load()
net.export_routes("Johan Sverdrup")["routes"]["gas"][0]["nodes"]
# ['JOHAN_SVERDRUP', 'STATPIPE_RICH_GAS', 'KARSTO', 'EUROPIPE_II_BALTIC_TIE_IN', 'DORNUM', 'MARKET_DE']

u = net.utilization(2025, "gas")                 # trunkline/plant loading
spof = net.single_points_of_failure(2025, "gas")  # KOLLSNES, TROLL A, KARSTO, SLEIPNER ...
net.outage_impact("NYHAMNA", 2025)                # stranded Ormen Lange + Aasta Hansteen gas

# NeqSim: tie-back screening of a discovery against the nearest real hosts
spec = nb.tieback_screen_spec(net, "7324/8-1 (Wisting)", n_hosts=3, max_km=400)
nb.run_tieback_screening(spec, max_distance_km=400)       # TiebackAnalyzer.quickScreen per host

# NeqSim: hydraulic check of an export path (LoopedPipeNetwork, pressure-pressure)
hyd = nb.trunk_hydraulics_spec(net, "TROLL", terminal_pressure_bar=90.0)
nb.run_trunk_hydraulics(hyd, inlet_pressure_bar=160.0)    # deliverable MSm3/d, node pressures
```

Live open data:

```python
from ncs_infrastructure_network import SodirDataService, EntsogTransparency, summarise_entry_flows

fields = SodirDataService().query("field")                             # layer 7100, paged
reserves = SodirDataService().query("field_reserves")                  # 7113, all versions
flows = EntsogTransparency().norwegian_entry_flows("2026-09-01", "2026-09-07")
summarise_entry_flows(flows)   # mean/max MSm3/d per terminal (GCV 11 kWh/Sm3 default)
```

## Data Refresh

```powershell
C:\appl\neqsim-venv\Scripts\python.exe scripts\build_snapshot.py                 # live rebuild
C:\appl\neqsim-venv\Scripts\python.exe scripts\build_snapshot.py --raw-cache raw.json
C:\appl\neqsim-venv\Scripts\python.exe scripts\build_snapshot.py --from-raw raw.json   # offline
```

Sodir updates daily. norskpetroleum reissues the capacity tables irregularly, and
the file name carries a date: update `NORSKPETROLEUM_TABLES` in `open_api.py`
when it changes. After a rebuild, run the tests. They check routing coverage and
that the recent year has no overloaded element.

## Validated NeqSim Path

| Question | NeqSim class | Bridge function |
|----------|--------------|-----------------|
| Tie-back of a discovery to a real host | `neqsim.process.fielddevelopment.tieback.TiebackAnalyzer`, `HostFacility` | `tieback_screen_spec`, `run_tieback_screening` |
| Can a trunkline path deliver a rate? | `neqsim.process.equipment.network.LoopedPipeNetwork` | `trunk_hydraulics_spec`, `run_trunk_hydraulics` |
| Economic value of throughput | `neqsim.process.optimization.valuechain.ValueChainObjective` | in `neqsim-ncs-value-chain-optimization` |
| Host process model rate check | `ProcessModel` + `ProcessAutomation.findMaxThroughputJson` | via the `optimize-processmodel` agent |

## Validation Checklist

- [ ] `summary()` shows fields ≥ 120, hosts ≥ 50, the four plants and seven terminals.
- [ ] `utilization(<recent year>, "gas")`: routed/total > 0.99 and `overloaded` empty.
- [ ] Routes flagged `needs_review` were read against the Sodir text before being quoted.
- [ ] Capacities quoted with their `source_url`; estimates and calibrated values
      (`confidence` low/medium, e.g. Melkøya calibrated from observed Snøhvit deliveries) flagged.
- [ ] Any host capacity used in a tie-back came from the caller, never assumed.
- [ ] ENTSOG kWh/d converted with a stated GCV.

## Common Mistakes

- **Reading the Norwegian description row.** Layer 7102 has both `nb` and `en`
  rows per field. Filter `fldCultureCode='en'`, or the parser silently misses
  every route.
- **Treating profiles as a forecast.** Layer 7300 is history only; the current
  year is year-to-date. Forecasts come from `neqsim-ncs-value-chain-optimization`.
- **Mapping "Statpipe" to Statfjord.** Tie-ins join Statpipe rich gas downstream
  of Statfjord. Mapping them to the Statfjord node lets their gas leak out
  through Tampen Link.
- **Shortest-hop routing.** Sending every field on the fewest hops overloads
  Langeled and Zeepipe IIA to 2–3× capacity. Use the capacity-aware
  `utilization`.
- **ENTSOG 404.** A 404 means "no data for the window", not a failure.
- **norskpetroleum "csv" links.** They return xlsx. The data header is the row
  containing Operator/From/To.
- **Gassco UMM.** It sits behind a terms click-through with no API. Never
  automate acceptance; the user exports outage messages and supplies them.

## Limitations

- Nameplate capacities only. Line-pack, pressure-dependent capacity, gas
  quality blending and the Gassco nomination rules are not modelled.
- Kårstø publishes product rates (t/h), not dry-gas throughput. Its export is
  bounded by Statpipe dry gas and Europipe II.
- Host processing capacities are not open data. Tie-back screening uses
  distance and water depth unless the caller supplies capacity.
- Route extraction is text mining of public prose. Treat `needs_review` routes
  as hypotheses.
- UK-side systems (FLAGS, SAGE, FUKA, CATS, Forties) end at an entry node; the
  UK network is not modelled.

## Related NeqSim Functionality

- `neqsim-ncs-value-chain-optimization`: multi-period, capacity-constrained
  optimisation of the whole NCS on this graph.
- `neqsim-norwegian-continental-shelf-data`: headline facts, carbon cost,
  `fit_arps_decline`.
- `neqsim-resource-classification-screening`: maturity of the discoveries
  listed here.
- `neqsim-production-network-routing`, `neqsim-step-out-screening`,
  `neqsim-pipe-route-profile`: detailed tie-back hydraulics.
- NeqSim Java: `TiebackAnalyzer`, `HostFacility`, `LoopedPipeNetwork`,
  `NetworkPlanningHorizon`, `TiebackRouteNetwork`.

## References

- Norwegian Offshore Directorate (Sodir), FactPages and FactMaps DataService — https://factpages.sodir.no, https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer (NLOD 2.0).
- Norwegian Petroleum, "The oil and gas pipeline system" — https://www.norskpetroleum.no/en/production-and-exports/the-oil-and-gas-pipeline-system/
- Gassco, processing plants and receiving terminals — https://gassco.eu/en/about-us/where-we-are/processing-plants/
- ENTSOG Transparency Platform API — https://transparency.entsog.eu/api/v1
- Baltic Pipe project — https://www.baltic-pipe.eu/
