"""Synthetic demonstration instance (NOT field data).

The numbers are invented to exercise every constraint type in the optimizer:
splitter risers, an LP-only riser, temperature-limited HP-only injection risers,
reach limited by riser length and slot position, back-pressure dependent well
rates and shared HP/LP manifold limits. Replace it with real wells, risers and
rates for an actual study.
"""

from __future__ import annotations

import random
from typing import Any, Dict


def synthetic_problem(seed: int = 7, n_wells: int = 26, n_periods: int = 4) -> Dict[str, Any]:
    """Return a problem dictionary with 17 risers (3 splitters, 1 LP-only, 4 injection).

    Args:
        seed: random seed, for reproducible demonstrations.
        n_wells: number of wells (slots) to generate.
        n_periods: number of yearly planning periods.

    Returns:
        A dictionary accepted by :func:`riser_well_assignment.load_problem`.
    """
    rng = random.Random(seed)
    p_hp, p_lp = 40.0, 15.0
    risers = []
    for i in range(1, 18):
        r: Dict[str, Any] = {"id": "R%02d" % i, "capacity": 1, "manifolds": ["HP", "LP"],
                             "max_reach_m": 1800.0 + 150.0 * (i % 5)}
        if i in (5, 9, 13):
            r["capacity"] = 3
        if i in (1, 2, 3, 4):
            r["manifolds"] = ["HP"]
            r["max_temp_c"] = 80.0
        if i == 15:
            r["manifolds"] = ["LP"]
        risers.append(r)
    risers_by_id = {r["id"]: r for r in risers}

    wells, distance = [], {}
    for k in range(1, n_wells + 1):
        wid = "W%02d" % k
        pi = rng.uniform(80.0, 400.0)
        p_res0 = rng.uniform(260.0, 330.0)
        decline = rng.uniform(6.0, 22.0)
        dp_line = rng.uniform(8.0, 30.0)
        wc0 = rng.uniform(0.05, 0.4)
        gor = rng.uniform(80.0, 400.0)
        t_flow = rng.uniform(55.0, 120.0)
        rates: Dict[str, Dict[str, list]] = {}
        for m, p_man in (("HP", p_hp), ("LP", p_lp)):
            oil, gas, wat = [], [], []
            for t in range(n_periods):
                p_res = p_res0 - decline * t
                q = max(0.0, pi * (p_res - 180.0 - dp_line - p_man) / 10.0)
                wc = min(0.9, wc0 + 0.08 * t)
                q_oil = q * (1.0 - wc)
                oil.append(round(q_oil, 1))
                wat.append(round(q * wc, 1))
                gas.append(round(q_oil * gor / 1000.0, 1))
            rates[m] = {"oil": oil, "gas": gas, "water": wat}
        wells.append({"id": wid, "slot": "S%02d" % k, "rates": rates,
                      "temp_c": [round(t_flow - 1.5 * t, 1) for t in range(n_periods)]})
        distance[wid] = {r["id"]: round(rng.uniform(600.0, 2600.0), 0) for r in risers}

    # Plausible but suboptimal current state: first feasible riser by greedy order.
    used: Dict[str, int] = {}
    lined: Dict[str, str] = {}
    order = [r["id"] for r in risers if r["id"] not in ("R01", "R02", "R03", "R04")]
    order += ["R01", "R02", "R03", "R04"]
    for w in wells:
        for rid in order:
            r = risers_by_id[rid]
            if distance[w["id"]][rid] > r["max_reach_m"] or used.get(rid, 0) >= r["capacity"]:
                continue
            man = lined.get(rid) or r["manifolds"][0]
            if man not in w["rates"] or (r.get("max_temp_c") and w["temp_c"][0] > r["max_temp_c"]):
                continue
            used[rid] = used.get(rid, 0) + 1
            lined[rid] = man
            w["current_riser"] = rid
            break
    for r in risers:
        if r["id"] in lined:
            r["current_manifold"] = lined[r["id"]]

    return {
        "wells": wells,
        "risers": risers,
        "distance_m": distance,
        "manifold_limits": {"HP": {"gas": 2400.0, "water": 6000.0},
                            "LP": {"gas": 1500.0, "water": 3500.0}},
        "total_limits": {"oil": 30000.0, "water": 8500.0},
        "config": {
            "period_days": [365.0] * n_periods,
            "stream_value": {"oil": 60.0},
            "swap_days": 4.0,
            "rov_cost_per_swap": 250000.0,
            "manifold_switch_cost": 0.0,
            "max_swaps_per_period": 4,
            "allow_choking": True,
            "time_limit_s": 60.0,
        },
    }
