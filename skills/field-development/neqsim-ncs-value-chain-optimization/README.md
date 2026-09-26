# neqsim-ncs-value-chain-optimization

Capacity-constrained, multi-year value optimisation of the whole Norwegian
Continental Shelf. It runs on the open-data graph from
[neqsim-ncs-infrastructure-network](../neqsim-ncs-infrastructure-network/README.md)
and hands off to NeqSim `ValueChainObjective`, `DebottleneckingAdvisor` and
host process-model optimisation.

## Quick Start

```powershell
C:\appl\neqsim-venv\Scripts\python.exe -m pip install -e ..\neqsim-ncs-infrastructure-network -e ".[test,lp,neqsim]"
C:\appl\neqsim-venv\Scripts\python.exe -m pytest
C:\appl\neqsim-venv\Scripts\python.exe examples\ncs_value_chain_study.py
```

## Layout

| Path | Content |
|------|---------|
| `src/ncs_value_chain_optimization/supply.py` | history + Arps/reserves-capped forecasts, discovery profiles |
| `src/ncs_value_chain_optimization/scenario.py` | `ncs_value_chain_scenario.v1` schema and defaults |
| `src/ncs_value_chain_optimization/optimizer.py` | per-year LP (SciPy HiGHS) with shadow prices |
| `src/ncs_value_chain_optimization/opportunities.py` | bottlenecks, ullage, tie-ins, uplift |
| `src/ncs_value_chain_optimization/neqsim_bridge.py` | NeqSim economics, debottlenecking, process-model targets |

## Attribution

Uses data from the Norwegian Offshore Directorate (NLOD 2.0), norskpetroleum.no and
gassco.eu, via the infrastructure-network snapshot.

## License

Apache-2.0.
