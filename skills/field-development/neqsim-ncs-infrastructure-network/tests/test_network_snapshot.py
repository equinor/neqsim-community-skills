"""Behaviour of the bundled snapshot (open Sodir / norskpetroleum / Gassco data)."""

import pytest

from ncs_infrastructure_network import NcsNetwork
from ncs_infrastructure_network import neqsim_bridge as nb


@pytest.fixture(scope="module")
def net():
    return NcsNetwork.load()


def test_snapshot_has_the_ncs(net):
    s = net.summary()
    assert s["fields"] >= 120 and s["candidate_discoveries"] >= 100 and s["hosts"] >= 50
    for plant in ("KOLLSNES", "KARSTO", "NYHAMNA", "HAMMERFEST_LNG"):
        assert net.nodes[plant]["kind"] == "plant"
    for terminal in ("EMDEN", "DORNUM", "ZEEBRUGGE", "DUNKERQUE", "ST_FERGUS", "EASINGTON", "NYBRO"):
        assert net.nodes[terminal]["kind"] == "terminal"


def test_troll_gas_goes_through_kollsnes(net):
    routes = net.export_routes("Troll")["routes"]["gas"]
    assert routes and all("KOLLSNES" in r["nodes"] for r in routes)


def test_johan_sverdrup_gas_uses_statpipe_rich_gas(net):
    path = net.preferred_path("JOHAN SVERDRUP", "gas")
    assert path.nodes[1:3] == ["STATPIPE_RICH_GAS", "KARSTO"]


def test_recent_year_is_routed_without_overload(net):
    u = net.utilization(2025, "gas")
    assert u["routed_rate"] / u["total_rate"] > 0.99
    assert 250 < u["total_rate"] < 400  # NCS sales gas ~ 120 GSm3/yr
    assert not u["overloaded"]


def test_kollsnes_is_a_single_point_of_failure(net):
    spof = net.single_points_of_failure(2025, "gas", top=5)
    assert "KOLLSNES" in [s["element"] for s in spof]
    assert net.outage_impact("KOLLSNES", 2025)["stranded_rate"] > 100


def test_nearest_hosts_are_sorted(net):
    disc = next(d for d in net.discoveries.values() if d.get("lat"))
    hosts = net.nearest_hosts(disc["id"], n=3)
    assert len(hosts) == 3 and hosts[0]["distance_km"] <= hosts[-1]["distance_km"]


def test_bridge_specs_offline(net):
    disc = max((d for d in net.discoveries.values() if d.get("lat") and d["reserves"].get("oe_msm3")),
               key=lambda d: d["reserves"]["oe_msm3"])
    spec = nb.tieback_screen_spec(net, disc["id"], n_hosts=3, max_km=500)
    assert spec["reserves_mmboe"] > 0 and len(spec["hosts"]) == 3
    hyd = nb.trunk_hydraulics_spec(net, "TROLL", rate_msm3d=40.0)
    assert hyd["pipes"] and all(p["inner_diameter_m"] > 0.3 for p in hyd["pipes"])


def test_bridge_runs_neqsim_when_available(net):
    pytest.importorskip("neqsim")
    disc = max((d for d in net.discoveries.values() if d.get("lat") and d["reserves"].get("oe_msm3")),
               key=lambda d: d["reserves"]["oe_msm3"])
    spec = nb.tieback_screen_spec(net, disc["id"], n_hosts=2, max_km=500)
    results = nb.run_tieback_screening(spec, max_distance_km=500)
    assert results and all("TiebackAnalyzer" in r["neqsim_class"] for r in results)
    hyd = nb.run_trunk_hydraulics(nb.trunk_hydraulics_spec(net, "TROLL", terminal_pressure_bar=90.0),
                                  inlet_pressure_bar=160.0)
    assert hyd["converged"] and hyd["deliverable_rate_msm3d"] > 5
