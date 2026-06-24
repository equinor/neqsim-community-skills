---
name: neqsim-production-network-routing
version: "0.1.0"
description: "Educational production-network routing screening that routes wells through manifolds and flowlines/risers to a host and rolls up an arrival pressure. USE WHEN: a task needs a public, screening-level inflow rate per well, aggregated manifold rates, and a platform arrival-pressure roll-up before detailed NeqSim inflow and multiphase-hydraulics design."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Production Network Routing

Use this skill for a quick, public screening of a "reservoir-to-facility"
production network: wells flowing through manifolds and flowlines/risers to a
host. Given wells with a productivity index and a manifold/flowline layout, it
estimates a screening rate per well, aggregates rates by manifold, and rolls up
an arrival pressure at the host with a simple pressure-drop gradient. It is
intentionally simple and should guide users toward validated NeqSim inflow and
multiphase-hydraulics workflows.

## When to Use

- When wells, a manifold layout, and a required arrival pressure are available and
  a first network roll-up is needed.
- When an agent needs to chain reservoir-vs-time screening to a platform
  arrival-pressure check.
- Before detailed IPR, tubing, and multiphase flowline modelling.

## Inputs

- `wells`: rows of `{name, manifold, reservoir_pressure_bara,
  flowing_bottomhole_pressure_bara, productivity_index_sm3_per_day_bar,
  tubing_head_pressure_bara}`.
- `manifolds`: rows of `{name, flowline_length_km, pressure_gradient_bar_per_km,
  riser_dp_bar}` (`riser_dp_bar` optional, default 0).
- `host_name`: name of the receiving host/platform (default `HOST`).
- `required_arrival_pressure_bara`: minimum required arrival pressure at the host.

## Outputs

- `wells`: per-well `drawdown_bar`, `rate_sm3_per_day`, and `flow_warning`.
- `manifolds`: per-manifold `total_rate_sm3_per_day`, `manifold_pressure_bara`,
  `flowline_dp_bar`, `riser_dp_bar`, `arrival_pressure_bara`,
  `arrival_margin_bar`, and `arrival_warning`.
- `total_rate_sm3_per_day`: aggregated network rate.
- `min_arrival_pressure_bara`: lowest manifold arrival pressure.
- `overall_warning`: worst of the well and manifold warnings.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

Each well rate is a linear productivity-index inflow:
`q = PI * max(0, P_res - P_bhp)`. A well with no drawdown flags `high`. Wells are
grouped by manifold; the manifold collection pressure is the lowest routed well
tubing-head pressure (the most-constrained well). The arrival pressure is the
manifold pressure minus a screening flowline pressure drop
(`gradient * length`) and an optional riser pressure drop. The arrival margin is
the arrival pressure minus the required arrival pressure: negative is `high`,
below 10 % of the requirement is `watch`, otherwise `ok`. The overall warning is
the most severe across wells and manifolds.

This skill performs no real IPR, multiphase hydraulics, phase split, or thermal
calculation. It applies simple algebra to supplied values and must be replaced
by validated NeqSim tools for any quantitative use.

## Python Usage Pattern

```python
from production_network_routing import ProductionNetworkModel

wells = [
    {"name": "WELL-A", "manifold": "MANIFOLD-1", "reservoir_pressure_bara": 300.0,
     "flowing_bottomhole_pressure_bara": 250.0,
     "productivity_index_sm3_per_day_bar": 1.0e5, "tubing_head_pressure_bara": 140.0},
    {"name": "WELL-B", "manifold": "MANIFOLD-1", "reservoir_pressure_bara": 295.0,
     "flowing_bottomhole_pressure_bara": 240.0,
     "productivity_index_sm3_per_day_bar": 0.9e5, "tubing_head_pressure_bara": 135.0},
]
manifolds = [
    {"name": "MANIFOLD-1", "flowline_length_km": 8.0,
     "pressure_gradient_bar_per_km": 1.5, "riser_dp_bar": 20.0},
]

result = ProductionNetworkModel().evaluate(
    wells=wells, manifolds=manifolds, host_name="HOST",
    required_arrival_pressure_bara=90.0,
)
print(result.min_arrival_pressure_bara, result.overall_warning)
```

## Validated NeqSim Path

This screening is a placeholder. For real reservoir-to-facility behaviour use:

- NeqSim `SimpleReservoir` (`runTransient`) for reservoir-vs-time inflow.
- NeqSim `PipeBeggsAndBrills` for multiphase flowline/riser pressure drop and
  temperature with gas/oil/water.
- NeqSim MCP `runPipeline`, `runProcess`, and `runFlowAssurance` for arrival
  conditions and flow-assurance checks.
- The enterprise `well-production-routing-agent` for live-data, IPR + tubing,
  choke, and Beggs & Brills arrival modelling.

## Escalation

Escalate any `watch` or `high` verdict, and any quantitative use, to validated
NeqSim inflow and multiphase-hydraulics models and qualified production-technology
review.
