---
name: neqsim-ncs-value-chain-optimization
calculation_basis: "screening"
version: "0.1.0"
description: "Multi-year, capacity-constrained value-chain optimisation of the whole Norwegian Continental Shelf: forecasts every field from Sodir history (Arps decline capped by remaining reserves) and phases in discoveries by maturity, routes all oil and gas through the real trunklines, processing plants and receiving terminals of neqsim-ncs-infrastructure-network with a linear programme (SciPy HiGHS), and returns production per field, curtailment, shadow prices of every pipeline and plant, ullage timelines, tie-in rankings and production-uplift lists, then hands them to NeqSim ValueChainObjective, DebottleneckingAdvisor and process-model optimisation. USE WHEN: a task asks how to maximise value or production across the NCS, which pipeline/plant is the binding constraint and what an extra unit of capacity is worth, how an outage or new tie-in changes the whole system, which discoveries fit best into spare capacity, or where fields could produce more."
last_verified: "2026-09-26"
requires:
  python_packages: ["scipy"]
  java_packages: []
  env: []
  network: []
---

# NCS Value-Chain Optimisation

This skill optimises the Norwegian Continental Shelf as one system. It takes the
open-data export graph from `neqsim-ncs-infrastructure-network`, puts supply on
it for every year, and answers:

- how much each field and discovery should produce each year to maximise value
  when all fields share the same trunklines, plants and terminals;
- which elements bind, and what one more MSm3/d or Sm3/d of capacity is worth
  there (shadow price);
- how an outage, capacity change, price shift or new tie-in propagates;
- where spare capacity (ullage) opens up over time, and which discoveries use
  it best;
- which producing fields could ship more, and whether the field or the network
  limits them.

Everything is public screening data. Governed inputs (RNB forecasts, Gassled
tariffs, gas-quality specs, metered flows) enter through a scenario JSON
produced by the enterprise binding skill
`enterprise-ncs-value-chain-data-binding`. This skill never reads company
systems.

## When to Use

- "Maximise NCS production/value for 2026–2040 given the pipeline system."
- "What is the most valuable debottleneck on the NCS, and when does it bind?"
- "If Kollsnes runs at 70% in 2027, what is lost and where does gas reroute?"
- "Which discoveries should be tied in first, into which host, and is there
  ullage?"
- "Which fields could produce more today, and what limits them?"
- Before a detailed NeqSim host process-model study: to get the rate targets
  the host must handle, including tie-ins.

## Inputs

- An `NcsNetwork` (bundled snapshot or a live rebuild).
- A scenario (`ncs_value_chain_scenario.v1`, see `scenario.py`) with these keys:
  - `years`;
  - `prices` (gas NOK/Sm3, liquid NOK/Sm3, exit-market factors);
  - `tariffs` (default and per arc);
  - `discount_rate`;
  - `capacity_overrides`;
  - `outages` (element, years, available fraction);
  - `forecast_overrides` (e.g. RNB per field);
  - `include_discoveries`, `tieback_max_km`, `max_paths_per_entity`.
  All have stated public defaults.

## Outputs

`NcsValueChainOptimizer(network, scenario).run()` returns
`ncs_value_chain_result.v1`. For each year it holds:

- `produced` per entity (`u`, gas MSm3/d, liquid Sm3/d);
- `curtailed`, `element_flow` and `utilization`;
- `shadow_price_mnok_per_unit_yr`, and `exits` by market;
- `unsold` (production without a sales route, e.g. reinjection) and
  `unconnected` entities.

It also carries the horizon NPV, the tie-back host of each discovery, the
supply profiles with their method, and the stated assumptions.

`opportunities.py` turns this into:

- `bottlenecks`: elements ranked by discounted shadow value;
- `ullage_timeline`: spare capacity per element and year;
- `curtailment`: lost production by year and entity;
- `tiein_ranking`: discoveries by accepted discounted revenue, with host and
  distance;
- `stranded_discoveries`: no host within the tie-back radius;
- `production_uplift`: extra rate per field, limited by route headroom or
  demonstrated capability.

## Engineering Method

1. **Supply.** Sodir yearly net production up to the base year.
   - **Forecast:** an Arps decline fitted from peak, using
     `norwegian_continental_shelf_data.fit_arps_decline` (built-in exponential
     fallback), with a 4 %/yr minimum decline. Fields still on plateau hold their
     rate until about 60 % of remaining reserves are produced, then decline at
     12 %/yr.
   - **Cap:** cumulative future volume is capped at Sodir remaining reserves.
   - **Discoveries:** sized from Sodir recoverable volumes. Start year = base
     year + 2 (decided/approved), + 4 (clarification), + 7 (likely); not
     evaluated and unlikely are excluded by default. Profile: 50 % build-up
     year, then 12 %/yr of recoverable on plateau for 4 years, then 15 %/yr
     decline.
2. **Routing.** Up to 20 loop-free paths per entity and medium to markets. A
   discovery ties back to the nearest in-service processing host within
   `tieback_max_km` that has an export route.
3. **LP per year.**

   $$\max \sum_{e,p} \left(P_m f_{exit} - T_p\right) x_{e,p} \quad \text{s.t.} \quad \sum_p x^{m}_{e,p} = u_e R^{m}_e,\; \sum_{(e,p) \ni c} x_{e,p} \le C_c,\; 0 \le u_e \le 1$$

   Here $u_e$ couples a field's oil and gas, and $C_c$ is every trunkline and
   plant capacity after overrides and outages. Solved with SciPy HiGHS. Duals
   of the capacity rows are shadow prices in MNOK/yr per MSm3/d (gas) or per
   Sm3/d (liquid).
4. **Horizon value.** Annual objectives discounted at `discount_rate`. Years
   are independent: curtailed volume is lost, not deferred (conservative).

## Python Usage Pattern

```python
from ncs_infrastructure_network import NcsNetwork
from ncs_value_chain_optimization import (NcsValueChainOptimizer, make_scenario, bottlenecks,
                                          tiein_ranking, production_uplift, ullage_timeline)
from ncs_value_chain_optimization import neqsim_bridge as vb

net = NcsNetwork.load()
sc = make_scenario(years=[2026, 2040],
                   outages=[{"element": "KOLLSNES", "years": [2027], "available_fraction": 0.7}])
opt = NcsValueChainOptimizer(net, sc)
res = opt.run()                           # ~1 s for 15 years, 160 entities

bottlenecks(res)[:5]                      # KOLLSNES binds in 2027 at ~1090 MNOK/yr per MSm3/d
tiein_ranking(res, gas_price=3.0, liquid_price=4500.0)[:10]
production_uplift(opt, res, 2026)
ullage_timeline(res, ["LANGELED_SOUTH__SLEIPNER__EASINGTON", "KOLLSNES"])

# NeqSim hand-offs (pip install neqsim)
vb.value_objective_check(res, sc, 2026)   # ValueChainObjective reproduces the LP gross revenue
specs = vb.debottleneck_specs(opt, res, [{"element": "KOLLSNES", "added_capacity": 10, "capex_mnok": 3000}])
vb.run_debottlenecking(specs, sc)         # DebottleneckingAdvisor: NPV, B/C, payback
vb.process_model_targets(res, net, "GOLIAT")  # rate targets for the optimize-processmodel agent
```

## Validated NeqSim Path

| Step | NeqSim class | Bridge |
|------|--------------|--------|
| Economic basis | `neqsim.process.optimization.valuechain.EconomicParameters` | `economic_parameters` |
| Revenue cross-check | `ValueChainObjective.evaluate(gasSm3/d, oilSm3/d, powerKw)` | `value_objective_check` |
| Debottleneck ranking | `DebottleneckingAdvisor` + `DebottleneckCandidate` (year offsets from base year) | `debottleneck_specs`, `run_debottlenecking` |
| Tie-back screening | `fielddevelopment.tieback.TiebackAnalyzer` | `ncs_infrastructure_network.neqsim_bridge` |
| Trunkline deliverability | `equipment.network.LoopedPipeNetwork` | `ncs_infrastructure_network.neqsim_bridge` |
| Host process capacity | `ProcessAutomation.findMaxThroughputJson`, `AgenticProcessOptimizer` | `process_model_targets` → `optimize-processmodel` agent |
| Field-life investment timing | `LifeOfFieldOptimizer` | take a host's rate targets as its production basis |

## Validation Checklist

- [ ] Every year `status == "optimal"`; first-year shipped gas within a few % of
      the last historical year (the 2026 base case ships ~320 MSm3/d).
- [ ] `max(utilization) <= 1` in every year.
- [ ] `value_objective_check` relative difference below 1e-6 (the NeqSim
      economics and the LP agree).
- [ ] Shadow prices ≈ netback × 365 on binding gas elements (sanity: (3.0 − 0.12)
      × 365 ≈ 1051 MNOK/yr per MSm3/d).
- [ ] Discoveries used in rankings carry status and RC; start years reviewed.
- [ ] Prices and tariffs are labelled public defaults unless bound from
      governed data.

## Common Mistakes

- **Too few paths per entity.** With 8 paths the LP curtailed about
  19 MSm3/d of Troll gas that the network can carry. Keep ≥ 20.
- **Treating DebottleneckCandidate years as calendar years.** They are offsets
  from the base year; 2027 as a year discounts the benefit to zero.
- **Using duals for large capacity steps.** A dual is marginal. The bridge
  re-solves with the added capacity instead.
- **Reading profiles as a forecast.** Sodir layer 7300 is history only; the
  current year is year-to-date.
- **Mistaking zero curtailment for no bottleneck.** When supply declines faster
  than capacity, nothing binds. Check `ullage_timeline` for where tie-ins fit.

## Limitations

- Nameplate capacities; no line-pack, pressure-dependent capacity, gas-quality
  blending, Gassco nomination rules or NGL product constraints at Kårstø.
- Screening supply forecasts (decline + reserves cap). Replace them with RNB or
  operator forecasts through `forecast_overrides` for decisions.
- Tariffs and exit-market factors are placeholders until bound from governed
  commercial data.
- Years are independent (no deferral, storage or reservoir response to
  curtailment).
- Host processing capacity is not open data; the host process model must
  confirm tie-in rates.

## Related NeqSim Functionality

- `neqsim-ncs-infrastructure-network`: the graph, open-API clients, tie-back and
  hydraulics bridges.
- `neqsim-norwegian-continental-shelf-data`: `fit_arps_decline`, headline facts,
  carbon-cost basis.
- `neqsim-resource-classification-screening`: RC maturity behind discovery
  phasing.
- `neqsim-asset-value-npv-screening`, `neqsim-energy-emissions-screening`:
  project-level economics and emissions of a chosen tie-in or debottleneck.
- NeqSim `optimize-processmodel` agent: host plant confirmation of the rate
  targets.

## References

- Norwegian Offshore Directorate FactPages / DataService (NLOD 2.0).
- Norwegian Petroleum, "The oil and gas pipeline system" and "Resource accounts".
- Arps, J.J. (1945). Analysis of decline curves. Trans. AIME 160, 228–247.
- Huangfu, Q., Hall, J.A.J. (2018). Parallelizing the dual revised simplex method. Math. Prog. Comp. 10, 119–142 (HiGHS).
