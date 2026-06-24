# Production Network Routing

Educational, dependency-free screening that routes wells through manifolds and
flowlines/risers to a host and rolls up an arrival pressure. Produces a
screening rate per well (productivity-index inflow), aggregated manifold rates,
and a platform arrival-pressure check.

This is a transparent placeholder only. For real inflow and multiphase
hydraulics use NeqSim `PipeBeggsAndBrills`, `SimpleReservoir`, and the NeqSim MCP
`runPipeline` / `runProcess` / `runFlowAssurance` workflows. See `SKILL.md` for
the full method and the validated NeqSim path.

## Quick Start

```bash
cd skills/subsea/production-network-routing
python -m pytest          # run tests from inside the skill folder
python examples/basic_production_network.py
```

## Layout

- `src/production_network_routing/model.py` — screening model.
- `examples/basic_production_network.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
