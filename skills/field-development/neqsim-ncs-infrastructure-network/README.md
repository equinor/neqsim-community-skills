# neqsim-ncs-infrastructure-network

Open-data graph of the Norwegian Continental Shelf export system: fields,
discoveries, host platforms, trunklines, processing plants, receiving terminals
and markets. Includes read-only clients for Sodir, FactPages and ENTSOG, and
hand-offs to NeqSim `TiebackAnalyzer` and `LoopedPipeNetwork`.

## Quick Start

```powershell
C:\appl\neqsim-venv\Scripts\python.exe -m pip install -e ".[test,neqsim]"
C:\appl\neqsim-venv\Scripts\python.exe -m pytest
```

```python
from ncs_infrastructure_network import NcsNetwork
net = NcsNetwork.load()
net.export_routes("Troll")
net.utilization(2025, "gas")["elements"][:5]
net.single_points_of_failure(2025)
```

See [SKILL.md](SKILL.md) for method, validation and limitations, and
[examples/ncs_network_walkthrough.py](examples/ncs_network_walkthrough.py).

## Layout

| Path | Content |
|------|---------|
| `src/ncs_infrastructure_network/network.py` | `NcsNetwork`: routes, utilisation, outages, SPOF, nearest hosts |
| `src/ncs_infrastructure_network/open_api.py` | Sodir DataService / FactPages, ENTSOG, norskpetroleum readers |
| `src/ncs_infrastructure_network/topology.py` | curated plants, terminals, markets, aliases (with sources) |
| `src/ncs_infrastructure_network/transport_parser.py` | route extraction from Sodir "Transport" text |
| `src/ncs_infrastructure_network/build.py` | snapshot builder (pure, testable) |
| `src/ncs_infrastructure_network/neqsim_bridge.py` | NeqSim tie-back and trunkline hand-offs |
| `src/ncs_infrastructure_network/sources.py` | open + enterprise source registry |
| `scripts/build_snapshot.py` | live rebuild of the bundled snapshot |

## Attribution

Contains data from the Norwegian Offshore Directorate (Sodir), licensed under the
Norwegian Licence for Open Government Data (NLOD) 2.0. Pipeline capacities are from
norskpetroleum.no, and plant capacities are from gassco.eu. Both are reused with
attribution; see `source_url` on every record.

## License

Apache-2.0 for the code. Data remains under its source licences.
