"""Value-chain optimiser tests: synthetic network (exact LP answers) + bundled NCS snapshot."""

import pytest

from ncs_infrastructure_network import NcsNetwork
from ncs_value_chain_optimization import (NcsValueChainOptimizer, bottlenecks, build_supply, curtailment,
                                          discovery_profile, forecast_series, make_scenario, production_uplift,
                                          tiein_ranking, validate_scenario)
from ncs_value_chain_optimization import neqsim_bridge as vb
from ncs_value_chain_optimization.supply import EntityProfile


def _tiny_network():
    """Two fields share a 10 MSm3/d trunk to market; B also has a 3 MSm3/d bypass."""
    nodes = {k: {"id": k, "name": k, "kind": kind} for k, kind in
             [("A", "field"), ("B", "field"), ("HUB", "hub"), ("T", "terminal"), ("MARKET_DE", "market")]}
    arcs = [
        {"id": "A_HUB", "from": "A", "to": "HUB", "medium": "gas", "capacity": None},
        {"id": "B_HUB", "from": "B", "to": "HUB", "medium": "gas", "capacity": None},
        {"id": "TRUNK", "from": "HUB", "to": "T", "medium": "gas", "capacity": 10.0},
        {"id": "BYPASS", "from": "B", "to": "T", "medium": "gas", "capacity": 3.0},
        {"id": "T_M", "from": "T", "to": "MARKET_DE", "medium": "gas", "capacity": None},
    ]
    fields = {k: {"id": k, "name": k, "production": {}, "reserves": {}} for k in ("A", "B")}
    return NcsNetwork({"schema": "ncs_network_snapshot.v1", "nodes": nodes, "arcs": arcs, "fields": fields,
                       "discoveries": {}, "hosts": [], "generated_utc": "2026-01-01"})


def _profiles(a, b, year=2026):
    return {"A": EntityProfile("A", "field", gas_msm3d={year: a}),
            "B": EntityProfile("B", "field", gas_msm3d={year: b})}


def test_lp_uses_bypass_and_prices_the_trunk():
    pytest.importorskip("scipy")
    net = _tiny_network()
    sc = make_scenario(years=[2026, 2026], include_discoveries=False)
    opt = NcsValueChainOptimizer(net, sc, profiles=_profiles(8.0, 5.0))
    yr = opt.run()["years"][0]
    assert yr["status"] == "optimal"
    shipped = sum(p["gas_msm3d"] for p in yr["produced"].values())
    assert shipped == pytest.approx(13.0, abs=1e-6)  # 10 trunk + 3 bypass
    assert yr["element_flow"]["TRUNK"] == pytest.approx(10.0)
    assert yr["element_flow"]["BYPASS"] == pytest.approx(3.0)
    assert not yr["curtailed"]
    # nothing binds with slack supply -> add supply and the trunk gets a shadow price
    opt2 = NcsValueChainOptimizer(net, sc, profiles=_profiles(9.0, 6.0))
    r2 = opt2.run()
    y2 = r2["years"][0]
    assert sum(v["gas_msm3d"] for v in y2["curtailed"].values()) == pytest.approx(2.0, abs=1e-6)
    netback = (3.0 - 0.12) * 365.0  # MNOK/yr per MSm3/d
    assert y2["shadow_price_mnok_per_unit_yr"]["TRUNK"] == pytest.approx(netback, rel=1e-6)
    assert bottlenecks(r2)[0]["element"] in ("TRUNK", "BYPASS")
    assert curtailment(r2)


def test_field_cost_shifts_curtailment_to_the_costly_field():
    pytest.importorskip("scipy")
    net = _tiny_network()
    sc = make_scenario(years=[2026, 2026], include_discoveries=False,
                       field_cost_nok_per_sm3oe={"A": 1500.0})  # 1.5 NOK/Sm3 gas penalty on A
    net.arcs["BYPASS"]["capacity"] = 0.0
    yr = NcsValueChainOptimizer(net, sc, profiles=_profiles(8.0, 8.0)).run()["years"][0]
    assert yr["produced"]["B"]["u"] == pytest.approx(1.0)
    assert yr["produced"]["A"]["gas_msm3d"] == pytest.approx(2.0, abs=1e-6)


def test_outage_reduces_capacity():
    pytest.importorskip("scipy")
    net = _tiny_network()
    sc = make_scenario(years=[2026, 2026], include_discoveries=False,
                       outages=[{"element": "TRUNK", "years": [2026], "available_fraction": 0.5}])
    yr = NcsValueChainOptimizer(net, sc, profiles=_profiles(8.0, 5.0)).run()["years"][0]
    assert sum(p["gas_msm3d"] for p in yr["produced"].values()) == pytest.approx(8.0, abs=1e-6)


def test_forecast_is_capped_by_reserves_and_declines():
    hist = {2016 + i: 10.0 * (0.9 ** i) for i in range(10)}  # MSm3/d, declining
    out, method, capped = forecast_series(hist, last_year=2025, end_year=2060, remaining=5.0, volume_factor=1000.0)
    assert sum(out.values()) * 365.0 <= 5.0 * 1000.0 + 1e-6  # rate-days <= remaining (5 GSm3 = 5000 MSm3)
    assert out[2026] < hist[2025]
    assert capped or min(out.values()) > 0


def test_discovery_profile_integrates_to_recoverable():
    prof = discovery_profile(2.0, volume_factor=1000.0, start_year=2030, end_year=2080)
    assert min(prof) == 2030
    assert sum(prof.values()) * 365.0 == pytest.approx(2000.0, rel=0.03)  # 2 GSm3 = 2000 MSm3


def test_scenario_validation():
    assert validate_scenario(make_scenario()) == []
    assert validate_scenario(make_scenario(years=[2030, 2020]))


@pytest.fixture(scope="module")
def ncs():
    pytest.importorskip("scipy")
    net = NcsNetwork.load()
    sc = make_scenario(years=[2026, 2032])
    opt = NcsValueChainOptimizer(net, sc)
    return net, sc, opt, opt.run()


def test_full_ncs_solves(ncs):
    net, sc, opt, r = ncs
    assert all(y["status"] == "optimal" for y in r["years"])
    first = r["years"][0]
    shipped = sum(p["gas_msm3d"] for p in first["produced"].values())
    assert 250 < shipped < 400
    assert max(first["utilization"].values()) <= 1.0 + 1e-6
    assert r["npv_mnok"] > 0


def test_supply_starts_from_history():
    net = NcsNetwork.load()
    supply = build_supply(net, reference_year=2025, end_year=2030)
    assert supply["TROLL"].rate(2025, "gas") > 50  # history
    assert 0 < supply["TROLL"].rate(2030, "gas") <= supply["TROLL"].rate(2025, "gas") * 1.01


def test_opportunities_on_ncs(ncs):
    net, sc, opt, r = ncs
    ranking = tiein_ranking(r, gas_price=3.0, liquid_price=4500.0)
    assert ranking and ranking[0]["host"]
    uplift = production_uplift(opt, r, 2026)
    assert all(u["uplift"] <= u["capability_gap"] + 1e-9 for u in uplift)


def test_neqsim_value_chain_handoffs(ncs):
    pytest.importorskip("neqsim")
    net, sc, opt, r = ncs
    check = vb.value_objective_check(r, sc, 2026)
    assert check["relative_difference"] < 1e-6
    specs = vb.debottleneck_specs(opt, r, [{"element": "KOLLSNES", "added_capacity": 5, "capex_mnok": 1000}])
    ranked = vb.run_debottlenecking(specs, sc)
    assert ranked[0]["neqsim_class"].endswith("DebottleneckingAdvisor")
    targets = vb.process_model_targets(r, net, "TROLL", years=[2026])
    assert targets["years"][0]["host_gas_msm3d"] > 0
