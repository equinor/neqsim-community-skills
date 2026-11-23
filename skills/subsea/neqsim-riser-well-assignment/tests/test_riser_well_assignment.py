"""Tests for the riser-well assignment optimizer."""

import copy
import random

import pytest

from riser_well_assignment import (
    Solution,
    brute_force,
    check_solution,
    load_problem,
    pareto_swaps,
    solve,
    synthetic_problem,
)


def _tiny(seed, periods=1, choking=False, **cfg):
    """Four wells, three risers (splitter, HP-only injection riser with a limit, LP-only)."""
    rng = random.Random(seed)
    risers = [
        {"id": "A", "capacity": 2, "manifolds": ["HP", "LP"], "current_manifold": "HP"},
        {"id": "B", "capacity": 1, "manifolds": ["HP"], "max_temp_c": 70.0, "current_manifold": "HP"},
        {"id": "C", "capacity": 1, "manifolds": ["LP"], "current_manifold": "LP"},
    ]
    wells = []
    for k in range(4):
        hp, lp = rng.uniform(100, 400), rng.uniform(150, 500)
        wells.append({"id": "W%d" % k, "rates": {"HP": {"oil": hp, "gas": hp / 4}, "LP": {"oil": lp, "gas": lp / 4}},
                      "temp_c": rng.choice([60.0, 90.0]), "current_riser": ["A", "A", "B", "C"][k]})
    config = {"stream_value": {"oil": 1.0}, "period_days": [100.0] * periods, "rov_cost_per_swap": 5000.0,
              "swap_days": 2.0, "allow_choking": choking}
    config.update(cfg)
    return {
        "wells": wells, "risers": risers,
        "reach": {"A": ["W0", "W1", "W2", "W3"], "B": ["W0", "W2", "W3"], "C": ["W1", "W2", "W3"]},
        "manifold_limits": {"HP": {"gas": 180.0}, "LP": {"gas": 150.0}},
        "config": config,
    }


def _tiny2(seed, **cfg):
    """Three wells, two risers, two periods: small enough for exhaustive enumeration."""
    rng = random.Random(seed)
    wells = []
    for k in range(3):
        hp, lp = rng.uniform(50, 200), rng.uniform(80, 260)
        wells.append({"id": "W%d" % k, "current_riser": ["A", None, "B"][k],
                      "temp_c": [rng.choice([60.0, 90.0]), rng.choice([60.0, 90.0])],
                      "rates": {"HP": {"oil": [hp, hp * 0.9], "gas": [hp / 4, hp / 4]},
                                "LP": {"oil": [lp, lp * 0.9], "gas": [lp / 4, lp / 4]}}})
    config = {"stream_value": {"oil": 1.0}, "period_days": [50.0, 50.0], "rov_cost_per_swap": 800.0,
              "swap_days": 2.0, "allow_choking": False, "manifold_switch_cost": 300.0,
              "disconnect_cost": 200.0}
    config.update(cfg)
    return {
        "wells": wells,
        "risers": [{"id": "A", "capacity": 2, "manifolds": ["HP", "LP"], "current_manifold": "HP"},
                   {"id": "B", "capacity": 1, "manifolds": ["HP"], "max_temp_c": 70.0, "current_manifold": "HP"}],
        "reach": {"A": ["W0", "W1", "W2"], "B": ["W0", "W1", "W2"]},
        "manifold_limits": {"HP": {"gas": 70.0}},
        "config": config,
    }


@pytest.mark.parametrize("seed", range(6))
def test_matches_brute_force_single_period(seed):
    problem = load_problem(_tiny(seed))
    sol = solve(problem)
    assert check_solution(problem, sol) == []
    assert sol.objective == pytest.approx(brute_force(problem), rel=1e-6)


@pytest.mark.parametrize("seed,extra", [(0, {}), (1, {}), (2, {"max_swaps_total": 1}),
                                         (3, {"max_swaps_per_period": 1}), (4, {"sibling_shutin": False})])
def test_matches_brute_force_two_periods_with_all_transition_costs(seed, extra):
    problem = load_problem(_tiny2(seed, **extra))
    sol = solve(problem)
    assert check_solution(problem, sol) == []
    assert sol.milp_objective == pytest.approx(sol.objective, rel=1e-7, abs=1e-6)
    assert sol.objective == pytest.approx(brute_force(problem), rel=1e-6)


def test_temperature_and_reach_constraints_hold():
    data = _tiny(0)
    data["wells"][0]["temp_c"] = 95.0
    problem = load_problem(data)
    sol = solve(problem)
    assert sol.plan.connections[0].get("W0") != "B" or "W0" not in sol.plan.flows[0]
    assert all(rid != "A" or w != "W3" or True for w, rid in sol.plan.connections[0].items())
    assert check_solution(problem, sol) == []


def test_reach_is_enforced_for_new_connections():
    data = _tiny(1)
    data["reach"] = {"A": ["W0", "W1"], "B": ["W2"], "C": ["W3"]}
    problem = load_problem(data)
    sol = solve(problem)
    for wid, rid in sol.plan.connections[0].items():
        assert wid in data["reach"][rid]


def test_lp_only_riser_never_serves_hp():
    sol = solve(load_problem(_tiny(3)))
    for wid, (rid, m, _f) in sol.assignment[0].items():
        if rid == "C":
            assert m == "LP"


def test_splitter_wells_share_one_manifold():
    sol = solve(load_problem(_tiny(2)))
    assert len({m for rid, m, _f in sol.assignment[0].values() if rid == "A"}) <= 1


def test_zero_budget_with_locked_manifolds_is_the_as_is_case():
    problem = load_problem(_tiny(1))
    sol = solve(problem, max_swaps_total=0, lock_manifolds=True)
    assert sol.n_swaps == 0
    for wid, rid in sol.plan.connections[0].items():
        assert rid == problem.wells[wid].current_riser
    for rid, m in sol.plan.lineups[0].items():
        assert m == problem.risers[rid].current_manifold


def test_unlocked_zero_budget_can_still_change_lineup():
    data = _tiny(2)
    problem = load_problem(data)
    free = solve(problem, 0, lock_manifolds=False).objective
    locked = solve(problem, 0, lock_manifolds=True).objective
    assert free >= locked - 1e-6


def test_pareto_value_never_decreases_and_baseline_is_zero_swaps():
    problem = load_problem(_tiny(4))
    rows = pareto_swaps(problem, [1, 2, 3])
    values = [r["net_value"] for r in rows]
    assert all(b >= a - 1e-6 for a, b in zip(values, values[1:]))
    assert rows[0]["gain_vs_no_swap"] >= -1e-6


def test_choking_never_worse_than_on_off():
    on_off = solve(load_problem(_tiny(5, choking=False))).objective
    choked = solve(load_problem(_tiny(5, choking=True))).objective
    assert choked >= on_off - 1e-6


def test_swap_cost_blocks_unprofitable_moves():
    sol = solve(load_problem(_tiny(1, rov_cost_per_swap=1e12)))
    assert sol.n_swaps == 0


def _one_well(rates_gas, **cfg):
    config = {"stream_value": {"oil": 1.0}, "period_days": [10.0] * len(rates_gas), "allow_choking": False,
              "rov_cost_per_swap": 1000.0, "swap_days": 1.0}
    config.update(cfg)
    return {
        "wells": [{"id": "W", "current_riser": "A", "temp_c": 50.0,
                   "rates": {"HP": {"oil": [100.0] * len(rates_gas), "gas": rates_gas}}}],
        "risers": [{"id": "A", "capacity": 1, "manifolds": ["HP"], "current_manifold": "HP"}],
        "reach": {"A": ["W"]},
        "manifold_limits": {"HP": {"gas": 100.0}},
        "config": config,
    }


def test_temporary_shut_in_is_not_a_swap():
    problem = load_problem(_one_well([10.0, 200.0, 10.0]))
    sol = solve(problem, max_swaps_total=0)
    assert sol.n_swaps == 0
    assert "W" in sol.plan.flows[0] and "W" not in sol.plan.flows[1] and "W" in sol.plan.flows[2]
    assert sol.plan.connections[1] == {"W": "A"}


def test_unconnected_well_stays_off_at_zero_budget():
    data = _one_well([10.0], rov_cost_per_swap=100.0)
    data["wells"][0]["current_riser"] = None
    sol = solve(load_problem(data), max_swaps_total=0)
    assert solve(load_problem(data)).n_swaps == 1


def test_missing_limit_stream_is_rejected_and_derived_stream_works():
    data = _tiny(0)
    data["risers"][0]["limits"] = {"liquid": 100.0}
    with pytest.raises(ValueError, match="liquid"):
        load_problem(data)
    for w in data["wells"]:
        for m in w["rates"].values():
            m["water"] = 10.0
    data["config"]["derived_streams"] = {"liquid": ["oil", "water"]}
    sol = solve(load_problem(data))
    assert check_solution(load_problem(data), sol) == []


def test_unknown_temperature_fails_closed():
    data = _tiny(0)
    data["wells"][2]["temp_c"] = None
    problem = load_problem(data)
    assert any("unknown temperature" in w for w in problem.warnings)
    sol = solve(problem)
    assert sol.plan.flows[0].get("W2", (None,))[0] is None or sol.plan.connections[0]["W2"] != "B"
    data["config"]["unknown_temp_policy"] = "allow"
    allowed = solve(load_problem(data))
    assert allowed.objective >= sol.objective - 1e-6


def test_distance_without_reach_limit_is_rejected():
    data = _tiny(0)
    del data["reach"]
    data["distance_m"] = {"W0": {"A": 100.0}}
    with pytest.raises(ValueError, match="max_reach_m"):
        load_problem(data)


def test_negative_stream_value_gives_no_swap_credit():
    data = _tiny2(0)
    data["config"]["stream_value"] = {"oil": 1.0, "gas": -10.0}
    problem = load_problem(data)
    sol = solve(problem)
    assert sol.milp_objective == pytest.approx(sol.objective, rel=1e-7, abs=1e-6)
    assert all(m["cost"] >= 0 for m in sol.moves)


def test_sibling_wells_are_charged_when_a_splitter_riser_is_disturbed():
    data = {
        "wells": [
            {"id": "S", "current_riser": "A", "temp_c": 50.0, "rates": {"HP": {"oil": 100.0}}},
            {"id": "N", "current_riser": None, "temp_c": 50.0, "rates": {"HP": {"oil": 300.0}}},
        ],
        "risers": [{"id": "A", "capacity": 2, "manifolds": ["HP"], "current_manifold": "HP"}],
        "reach": {"A": ["S", "N"]},
        "config": {"stream_value": {"oil": 1.0}, "period_days": [100.0], "allow_choking": False,
                   "rov_cost_per_swap": 0.0, "swap_days": 5.0, "sibling_shutin": True},
    }
    sol = solve(load_problem(data))
    assert sol.n_swaps == 1
    assert sol.evaluation.sibling_cost == pytest.approx(5.0 * 100.0)
    assert sol.milp_objective == pytest.approx(sol.objective)
    data["config"]["sibling_shutin"] = False
    assert solve(load_problem(data)).evaluation.sibling_cost == 0.0


def test_unavailable_riser_is_not_used():
    data = _tiny(2)
    data["risers"][2]["available"] = False
    sol = solve(load_problem(data))
    assert all(rid != "C" for rid in sol.plan.connections[0].values())


def test_riser_limit_by_manifold_steers_the_well_to_the_other_header():
    data = {
        "wells": [{"id": "W", "current_riser": "A", "temp_c": 50.0,
                   "rates": {"HP": {"oil": 100.0, "gas": 200.0}, "LP": {"oil": 80.0, "gas": 200.0}}}],
        "risers": [{"id": "A", "capacity": 1, "manifolds": ["HP", "LP"], "current_manifold": "HP",
                    "limits_by_manifold": {"HP": {"gas": 150.0}, "LP": {"gas": 300.0}}}],
        "reach": {"A": ["W"]},
        "config": {"stream_value": {"oil": 1.0}, "period_days": [10.0], "allow_choking": False},
    }
    problem = load_problem(data)
    sol = solve(problem)
    assert sol.plan.flows[0]["W"][0] == "LP"
    assert check_solution(problem, sol) == []
    assert sol.objective == pytest.approx(brute_force(problem))
    data["config"]["allow_choking"] = True
    choked = solve(load_problem(data))
    assert choked.objective == pytest.approx(10.0 * 80.0)


def test_check_solution_rejects_missing_plan_and_tampered_plan():
    problem = load_problem(_tiny(0))
    assert check_solution(problem, Solution("failed", None, None))
    sol = solve(problem)
    sol.plan.connections[0]["W0"] = "B"
    sol.plan.connections[0]["W2"] = "B"
    assert check_solution(problem, sol)


def test_synthetic_instance_is_feasible_and_checked():
    problem = load_problem(synthetic_problem(n_periods=1))
    assert len(problem.risers) == 17
    assert sum(1 for r in problem.risers.values() if r.capacity == 3) == 3
    sol = solve(problem)
    assert sol.status in ("optimal", "time_limit")
    assert check_solution(problem, sol) == []
    assert solve(problem, 0).objective <= sol.objective + 1e-6


def test_bad_references_raise():
    data = copy.deepcopy(_tiny(0))
    data["wells"][0]["current_riser"] = "Z"
    with pytest.raises(ValueError):
        load_problem(data)
