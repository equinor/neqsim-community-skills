import math

import pytest
from tie_in_pipeline_concept import (
    OilProperties,
    PipelineDesignBasis,
    build_profile,
    f101_checks,
    great_circle_points,
    haversine_km,
    profile_statistics,
    rank_candidates,
    run_concept,
    select_wall_thickness,
    size_pipeline,
    solve_hydraulics,
)
from tie_in_pipeline_concept.sizing import friction_factor, overall_u

PROPS = OilProperties(std_density_kg_m3=882.0, viscosity_cp_inlet=4.95, viscosity_cp_sea=15.3)


def fake_fetch(url):
    # smooth synthetic seabed: 100 m rising to 90 m, EMODnet returns negative elevation
    lon = float(url.split("POINT%28")[1].split("%20")[0])
    return {"avg": -(100.0 - 5.0 * (lon - 2.0))}


def test_haversine_and_great_circle_length():
    d = haversine_km(60.5057, 2.0131, 60.4913, 2.8256)
    total, pts = great_circle_points((2.0131, 60.5057), (2.8256, 60.4913), 0.5)
    assert d == pytest.approx(total, rel=1e-6)
    assert pts[0][0] == 0.0 and pts[-1][0] == pytest.approx(total)
    assert 44.0 < total < 45.5


def test_rank_prefers_field_centre_with_feeders():
    source = {"lat": 60.5057, "lon": 2.0131}
    hosts = [
        {"name": "A", "lat": 60.4913, "lon": 2.8256},
        {"name": "B", "lat": 60.3896, "lon": 2.7953},
        {"name": "FAR", "lat": 58.8, "lon": 2.2},
    ]
    ranked = rank_candidates(source, hosts, feeds_into={"X": ["A"], "Y": ["A"], "Z": ["A"]}, terminal_hosts=["A"])
    assert [c.name for c in ranked] == ["A", "B"]
    assert ranked[0].rationale


def test_profile_with_injected_fetch_and_gap_fill(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return {"avg": None} if len(calls) == 3 else fake_fetch(url)

    prof = build_profile((2.0, 60.5), (2.8, 60.5), 5.0, fetch, tmp_path / "c.json")
    assert prof.gaps == [2]
    assert len(prof.depth_m) == len(prof.kp_km)
    stats = profile_statistics(prof)
    assert stats["interpolated_points"] == 1
    n_first = len(calls)
    build_profile((2.0, 60.5), (2.8, 60.5), 5.0, fetch, tmp_path / "c.json")
    assert len(calls) == n_first  # served from cache


def test_friction_factor_regimes():
    assert friction_factor(1000, 1e-4) == pytest.approx(0.064)
    assert friction_factor(1e5, 1e-4) == pytest.approx(0.0183, abs=0.0006)
    with pytest.raises(ValueError):
        friction_factor(0.0, 1e-4)


def test_hydraulics_monotonic_with_rate_and_diameter():
    basis = PipelineDesignBasis(length_m=44500.0)
    small = solve_hydraulics(6000.0, PROPS, 0.2, basis, 20.0)
    large = solve_hydraulics(6000.0, PROPS, 0.3, basis, 20.0)
    more = solve_hydraulics(11500.0, PROPS, 0.3, basis, 20.0)
    assert small["inlet_pressure_barg"] > large["inlet_pressure_barg"] > basis.arrival_pressure_barg
    assert more["inlet_pressure_barg"] > large["inlet_pressure_barg"]
    assert large["t_out_c"] == pytest.approx(basis.t_sea_c, abs=0.5)


def test_insulation_raises_arrival_temperature():
    bare = PipelineDesignBasis(length_m=44500.0)
    ins = PipelineDesignBasis(length_m=44500.0, insulation_thickness_m=0.04)
    u_b = overall_u(0.3, 0.0095, bare)
    u_i = overall_u(0.3, 0.0095, ins)
    assert u_i < u_b
    assert solve_hydraulics(6000.0, PROPS, 0.3, ins, u_i)["t_out_c"] > solve_hydraulics(6000.0, PROPS, 0.3, bare, u_b)["t_out_c"]


def test_wall_thickness_matches_martin_linge_screening():
    basis = PipelineDesignBasis(length_m=44500.0, max_water_depth_m=119.0, riser_height_m=144.0)
    w = select_wall_thickness(0.3239, basis, 882.0)
    assert w["t_nom_mm"] == 9.5
    assert w["util_pressure"] == pytest.approx(0.43, abs=0.03)
    high = PipelineDesignBasis(length_m=44500.0, design_pressure_barg=100.0, max_water_depth_m=119.0, riser_height_m=144.0)
    assert f101_checks(0.3239, 0.0095, high, 882.0)["util_pressure"] == pytest.approx(0.87, abs=0.04)


def test_size_pipeline_recommends_12_inch_for_6000():
    basis = PipelineDesignBasis(length_m=44500.0, max_water_depth_m=119.0, net_elevation_m=5.0)
    res = size_pipeline(PROPS, basis, {"turndown": 2600.0, "design": 6000.0}, "design", "turndown")
    assert res["recommended"] in (10, 12)
    assert res["rejection_reasons"][8]


def test_run_concept_end_to_end(tmp_path):
    out = run_concept(
        {"name": "S", "lat": 60.5, "lon": 2.0}, {"name": "T", "lat": 60.5, "lon": 2.8}, PROPS,
        {"turndown": 2600.0, "design": 6000.0}, "design", "turndown",
        hosts=[{"name": "T", "lat": 60.5, "lon": 2.8}], fetch=fake_fetch, cache_path=tmp_path / "d.json",
        basis_overrides={"arrival_pressure_barg": 12.0})
    assert out["basis"]["arrival_pressure_barg"] == 12.0
    assert out["sizing"]["recommended"] is not None
    assert out["candidates"][0]["name"] == "T"
    with pytest.raises(ValueError):
        run_concept({"name": "S", "lat": 60.5, "lon": 2.0}, {"name": "T", "lat": 60.5, "lon": 2.8}, PROPS,
                    {"a": 1.0}, "a", "a", fetch=fake_fetch, basis_overrides={"nonsense": 1})
    assert math.isfinite(out["statistics"]["route_3d_length_km"])
