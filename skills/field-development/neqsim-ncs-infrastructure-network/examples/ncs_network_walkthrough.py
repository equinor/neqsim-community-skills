"""Walk through the NCS network: routes, utilisation, outages, tie-back and hydraulics.

Run with the shared NeqSim environment:
    C:\\appl\\neqsim-venv\\Scripts\\python.exe examples/ncs_network_walkthrough.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncs_infrastructure_network import NcsNetwork  # noqa: E402
from ncs_infrastructure_network import neqsim_bridge as nb  # noqa: E402

net = NcsNetwork.load()
print(json.dumps(net.summary(), indent=1))

for field in ("Johan Sverdrup", "Troll", "Aasta Hansteen"):
    gas = net.export_routes(field)["routes"]["gas"][0]
    print(f"{field}: {' -> '.join(gas['nodes'])} (bottleneck {gas['bottleneck_arc']} {gas['bottleneck_capacity']})")

u = net.utilization(2025, "gas")
print("\nMost loaded gas elements 2025:")
for e in u["elements"][:8]:
    print(f"  {e['name']:<32} {e['flow']:>7.1f} / {e['capacity']} MSm3/d  ({e['utilization']:.0%})")

print("\nSingle points of failure (gas, 2025):")
for s in net.single_points_of_failure(2025, "gas", top=5):
    print(f"  {s['element']:<40} strands {s['stranded_rate']:.1f} MSm3/d  ({', '.join(s['fields'][:4])})")

try:
    spec = nb.tieback_screen_spec(net, "7324/8-1 (Wisting)", n_hosts=3, max_km=400)
    print("\nTie-back screening (NeqSim TiebackAnalyzer):")
    for r in nb.run_tieback_screening(spec, max_distance_km=400):
        print(f"  {r['host']:<24} passed={r['passed']} {r['distance_km']:.0f} km NPV {r['npv_musd']:.0f} MUSD")
    hyd = nb.run_trunk_hydraulics(nb.trunk_hydraulics_spec(net, "TROLL", terminal_pressure_bar=90.0),
                                  inlet_pressure_bar=160.0)
    print(f"\nKollsnes->Easington at 160 bar inlet: {hyd['deliverable_rate_msm3d']} MSm3/d "
          f"(NeqSim LoopedPipeNetwork, converged={hyd['converged']})")
except RuntimeError as exc:  # neqsim not installed
    print("NeqSim bridge skipped:", exc)
