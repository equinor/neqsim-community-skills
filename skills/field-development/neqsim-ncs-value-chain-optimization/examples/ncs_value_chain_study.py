"""NCS value-chain study: optimise 2026-2040, stress Kollsnes, rank tie-ins and debottlenecks.

    C:\\appl\\neqsim-venv\\Scripts\\python.exe examples/ncs_value_chain_study.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE.parent / "neqsim-ncs-infrastructure-network" / "src"))

from ncs_infrastructure_network import NcsNetwork  # noqa: E402
from ncs_value_chain_optimization import (NcsValueChainOptimizer, bottlenecks, curtailment,  # noqa: E402
                                          make_scenario, production_uplift, tiein_ranking)
from ncs_value_chain_optimization import neqsim_bridge as vb  # noqa: E402

net = NcsNetwork.load()
scenario = make_scenario(years=[2026, 2040],
                         outages=[{"element": "KOLLSNES", "years": [2027], "available_fraction": 0.7}])
opt = NcsValueChainOptimizer(net, scenario)
res = opt.run()
print(f"NPV 2026-2040 (gross netback, {scenario['discount_rate']:.0%}): {res['npv_mnok']:,.0f} MNOK")

for y in res["years"][::3]:
    gas = sum(p["gas_msm3d"] for p in y["produced"].values())
    print(f"  {y['year']}: {gas:6.1f} MSm3/d gas shipped, value {y['objective_mnok']:,.0f} MNOK/yr")

print("\nBinding elements:")
for b in bottlenecks(res)[:5]:
    print(f"  {b['element']:<40} years {b['binding_years']}  PV {b['pv_mnok_per_unit_capacity']:.0f} MNOK per unit")
print("\nCurtailment:", curtailment(res)[:3])

print("\nTop tie-ins (network-accepted discounted revenue):")
for t in tiein_ranking(res, gas_price=3.0, liquid_price=4500.0)[:5]:
    print(f"  {t['discovery']:<32} -> {t['host']:<14} {t['distance_km']} km  from {t['first_year']}  "
          f"PV {t['pv_gross_revenue_mnok']:,.0f} MNOK")

print("\nWhere could fields ship more in 2026:")
for u in production_uplift(opt, res, 2026)[:5]:
    print(f"  {u['entity']:<18} +{u['uplift']} {u['unit']} ({u['limited_by']})")

try:
    print("\nNeqSim ValueChainObjective check:", vb.value_objective_check(res, scenario, 2026)["relative_difference"])
    specs = vb.debottleneck_specs(opt, res, [{"element": "KOLLSNES", "added_capacity": 10, "capex_mnok": 3000}])
    for r in vb.run_debottlenecking(specs, scenario):
        print(f"NeqSim DebottleneckingAdvisor: {r['name']} NPV {r['npv_mnok']:.0f} MNOK, B/C {r['benefit_cost_ratio']}")
except RuntimeError as exc:
    print("NeqSim hand-offs skipped:", exc)
