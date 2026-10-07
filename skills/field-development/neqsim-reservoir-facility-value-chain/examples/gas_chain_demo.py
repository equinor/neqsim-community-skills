"""Minimal reservoir -> wells -> facility chain: yearly rate with separator pressure chosen at the supply/capacity crossing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reservoir_facility_value_chain import Gas, GasTank, PressureCapacityCurve, RSDeliverability, flow_balance, maximise_rate

gas = Gas({"C1": 0.93, "C2": 0.04, "C3": 0.01, "N2": 0.02})
tank = GasTank(gas, 343.15, pz_i=171.6, giip=1000.0, cum=700.0)  # GSm3
law = RSDeliverability(0.0089, 0.705)  # per-well law fitted on choke-open rows
wells = 39.0
capacity = PressureCapacityCurve([31.0, 35.0], [43.2, 62.3])  # MSm3/d vs separator barg, from a process-model sweep

for year in range(2027, 2036):
    pr = tank.pressure()

    def supply(ps):
        return wells * flow_balance(lambda whp: law.rate(pr, whp), ps, 4.4, 1.5)

    ps, q, binding = maximise_rate(supply, capacity, 31.0, 36.0)
    tank.produce(q * 365.0 / 1e3)
    print(f"{year} pr={pr:5.1f} bara  Ps={ps:4.1f} barg  q={q:5.1f} MSm3/d  limited by {binding}")
