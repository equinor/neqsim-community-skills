import json
import math

import pytest

from seabed_protection_screening import (
    PipeBasis,
    RouteSegment,
    ScreeningAssumptions,
    SeabedProtectionScreener,
    TrencherCapability,
    assemble_segments,
    build_route,
    buried_thermal_resistance_k_m_per_w,
    find_line_crossings,
    plan_protection_data_package,
    read_geojson,
    required_uplift_rock_thickness_m,
    rock_section_area_m2,
    sample_polygon_layer,
    to_neqsim_burial_segments,
)

# A west-east route of roughly 11 km at 60 N.
ROUTE = [(2.00, 60.0), (2.10, 60.0), (2.20, 60.0)]


def _box(west, south, east, north, **props):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def _collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def test_route_has_monotonic_kp_and_expected_length():
    route = build_route(ROUTE, spacing_m=500.0)
    kps = [p.kp_m for p in route]
    assert kps == sorted(kps)
    assert route[-1].kp_m == pytest.approx(2 * 5558.0, rel=0.01)
    assert max(b - a for a, b in zip(kps, kps[1:])) <= 500.0 + 1e-6


def test_polygon_sampling_honours_holes_and_rank_order():
    route = build_route(ROUTE, spacing_m=500.0)
    outer = {"type": "Feature", "properties": {"v": "low"}, "geometry": {"type": "Polygon", "coordinates": [
        [[1.9, 59.9], [2.3, 59.9], [2.3, 60.1], [1.9, 60.1], [1.9, 59.9]],
        [[2.08, 59.95], [2.12, 59.95], [2.12, 60.05], [2.08, 60.05], [2.08, 59.95]],
    ]}}
    overlap = _box(2.15, 59.9, 2.3, 60.1, v="high")
    values = sample_polygon_layer(route, _collection(outer, overlap), "v", default="none", rank_order=["none", "low", "high"])
    by_kp = {round(p.kp_m): v for p, v in zip(route, values)}
    assert by_kp[0] == "low"
    assert by_kp[round(route[len(route) // 2].kp_m)] == "none"  # inside the hole
    assert values[-1] == "high"  # overlap resolved to the most onerous


def test_line_crossings_report_kp_angle_and_diameter():
    route = build_route(ROUTE, spacing_m=500.0)
    pipeline = {"type": "Feature", "properties": {"name": "EXPORT-1", "od_in": 20}, "geometry": {
        "type": "LineString", "coordinates": [[2.05, 59.95], [2.05, 60.05]]}}
    found = find_line_crossings(route, _collection(pipeline), outer_diameter_attribute="od_in", outer_diameter_unit_m=0.0254)
    assert len(found) == 1
    assert found[0].feature_id == "EXPORT-1"
    assert found[0].kp_m == pytest.approx(5558.0 / 2, rel=0.01)
    assert found[0].crossing_angle_deg == pytest.approx(90.0, abs=0.5)
    assert found[0].crossed_outer_diameter_m == pytest.approx(0.508)


def test_assemble_segments_merges_equal_stations_and_covers_route():
    route = build_route(ROUTE, spacing_m=500.0)
    fishing = ["high" if p.kp_m > 5558.0 else "none" for p in route]
    segments = assemble_segments(route, {"fishing_intensity": fishing})
    assert len(segments) == 2
    assert segments[0].start_kp_m == 0.0
    assert segments[-1].end_kp_m == pytest.approx(route[-1].kp_m)
    assert segments[0].end_kp_m == segments[1].start_kp_m
    with pytest.raises(ValueError):
        assemble_segments(route, {"fishing_intensity": ["none"]})


def test_data_plan_is_offline_and_validates_bounds():
    plan = plan_protection_data_package(1.9, 59.9, 2.3, 60.1, sodir_pipeline_layer_id=7)
    assert [r.source_key for r in plan] == ["emodnet_seabed_substrate", "emodnet_human_activities", "sodir_factmaps"]
    assert plan[2].url.startswith("https://factmaps.sodir.no/") and "/7/query?" in plan[2].url
    with pytest.raises(ValueError):
        plan_protection_data_package(2.3, 59.9, 1.9, 60.1)


def test_uplift_thickness_satisfies_the_force_balance():
    a = ScreeningAssumptions()
    od = 0.4
    force = 15000.0
    t = required_uplift_rock_thickness_m(force, od, a)
    height = od + t
    weight = a.rock_submerged_unit_weight_n_m3 * (
        (a.rock_crest_width_m + a.rock_side_slope * height) * height - (a.rock_crest_width_m + a.rock_side_slope * od) * od
    )
    assert weight == pytest.approx(force * a.uplift_safety_factor, rel=1e-6)
    assert required_uplift_rock_thickness_m(0.0, od, a) == 0.0


def test_rock_area_surface_laid_matches_trapezoid_less_pipe():
    a = ScreeningAssumptions()
    od, t = 0.4, 0.6
    area = rock_section_area_m2(od, t, 0.0, True, a)
    expected = (a.rock_crest_width_m + a.rock_side_slope * (od + t)) * (od + t) - math.pi * od * od / 4.0
    assert area == pytest.approx(expected)


def test_buried_resistance_matches_neqsim_shape_factor():
    r = buried_thermal_resistance_k_m_per_w(0.6, 0.4, 1.5)
    radius, depth = 0.2, 0.8
    ratio = depth / radius
    assert r == pytest.approx(math.log(2 * ratio + math.sqrt(4 * ratio**2 - 1)) / (2 * math.pi * 1.5))
    with pytest.raises(ValueError):
        buried_thermal_resistance_k_m_per_w(0.0, 0.4, 1.5)


def _screener():
    return SeabedProtectionScreener(PipeBasis(0.4, "flowline"))


def test_sand_with_heavy_fishing_is_trenched_with_cover_to_requirement():
    seg = RouteSegment(0.0, 3000.0, {"fishing_intensity": "high", "soil_class": "sand"})
    plan = _screener().assess([seg], existing_cover_intervals=[])
    s = plan.segments[0]
    assert s.strategy == "trench" and s.trench_method == "jetting"
    assert s.required_cover_m == 1.0 and s.controlling_hazard.startswith("trawl")
    assert s.trench_depth_m == pytest.approx(0.4 + 1.0 + 0.1)
    assert s.rock_volume_m3 == 0.0
    assert s.trench_days == pytest.approx(3000.0 / 3000.0)
    assert plan.buried_length_fraction == 1.0


def test_rock_substrate_forces_rock_dump_and_flags_no_rock_zone():
    seg = RouteSegment(0.0, 1000.0, {"fishing_intensity": "medium", "soil_class": "rock", "no_rock": True})
    plan = _screener().assess([seg], existing_cover_intervals=[])
    s = plan.segments[0]
    assert s.strategy == "rock_dump" and s.trench_method is None
    assert s.rock_volume_m3 > 0.0 and s.rock_tonnes > s.rock_volume_m3
    assert any("no_rock" in w for w in plan.warnings)
    assert s.thermal_condition == "rock_covered"


def test_stiff_clay_falls_back_to_a_capable_method_or_partial_trench_plus_rock():
    seg = RouteSegment(0.0, 1000.0, {"fishing_intensity": "high", "soil_class": "firm_clay", "undrained_shear_strength_kpa": 250.0})
    s = _screener().assess([seg], existing_cover_intervals=[]).segments[0]
    assert s.trench_method == "mechanical_cutter"
    limited = ScreeningAssumptions(trenchers={"mechanical_cutter": TrencherCapability(300.0, 1.0, 1200.0, True, True)}, method_preference=("mechanical_cutter",))
    s2 = SeabedProtectionScreener(PipeBasis(0.4), limited).assess([seg], existing_cover_intervals=[]).segments[0]
    assert s2.strategy == "trench_and_rock" and s2.rock_volume_m3 > 0.0
    assert s2.trench_depth_m == pytest.approx(1.0)


def test_existing_survey_cover_avoids_intervention_only_when_fully_covering():
    seg = RouteSegment(1000.0, 2000.0, {"fishing_intensity": "medium", "soil_class": "sand"})
    full = [{"start_kp_m": 900.0, "end_kp_m": 2100.0, "min_cover_m": 0.8}]
    partial = [{"start_kp_m": 900.0, "end_kp_m": 1500.0, "min_cover_m": 0.8}]
    assert _screener().assess([seg], existing_cover_intervals=full).segments[0].strategy == "adequate_existing_cover"
    assert _screener().assess([seg], existing_cover_intervals=partial).segments[0].strategy == "trench"


def test_rock_only_hazards_override_burial_and_uplift_drives_thickness():
    seg = RouteSegment(0.0, 500.0, {"soil_class": "sand", "uplift_force_n_per_m": 12000.0, "fishing_intensity": "low"})
    plan = _screener().assess([seg], existing_cover_intervals=[])
    s = plan.segments[0]
    assert s.strategy == "rock_dump"
    assert s.controlling_hazard == "upheaval buckling"
    assert s.rock_thickness_m == pytest.approx(required_uplift_rock_thickness_m(12000.0, 0.4, ScreeningAssumptions()))


def test_crossings_and_span_supports_add_rock_and_report_gaps():
    route = build_route(ROUTE, spacing_m=500.0)
    pipeline = {"type": "Feature", "properties": {"name": "X"}, "geometry": {"type": "LineString", "coordinates": [[2.05, 59.95], [2.05, 60.05]]}}
    crossings = find_line_crossings(route, _collection(pipeline))
    seg = RouteSegment(0.0, route[-1].kp_m, {})
    spans = [{"start_kp_m": 100.0, "end_kp_m": 180.0, "length_m": 80.0, "max_gap_m": 0.8}]
    plan = _screener().assess([seg], crossings=crossings, span_candidates=spans, allowable_span_m=30.0, existing_cover_intervals=[])
    assert plan.crossings[0].rock_volume_m3 > 0.0
    assert plan.span_supports[0].supports == 2
    assert plan.rock_tonnes == pytest.approx(plan.crossings[0].rock_tonnes + plan.span_supports[0].rock_tonnes)
    assert any("Crossed outer diameter missing" in g for g in plan.data_gaps)
    no_allowable = _screener().assess([seg], span_candidates=spans, existing_cover_intervals=[])
    assert not no_allowable.span_supports and any("allowable span" in g for g in no_allowable.data_gaps)


def test_thermal_handoff_merges_sections_and_marks_exposed():
    segs = [
        RouteSegment(0.0, 1000.0, {}),
        RouteSegment(1000.0, 2000.0, {"fishing_intensity": "high", "soil_class": "sand"}),
        RouteSegment(2000.0, 3000.0, {"fishing_intensity": "high", "soil_class": "sand"}),
    ]
    plan = _screener().assess(segs, existing_cover_intervals=[])
    sections = to_neqsim_burial_segments(plan, 0.4)
    assert [s["buried"] for s in sections] == [False, True]
    assert sections[1]["start_kp_m"] == 1000.0 and sections[1]["end_kp_m"] == 3000.0
    assert sections[1]["burial_depth_m"] == pytest.approx(1.0 + 0.1 + 0.2)  # required + trench allowance + radius
    assert plan.exposed_length_m == pytest.approx(1000.0)


def test_unknown_soil_and_missing_inputs_are_reported_not_guessed():
    seg = RouteSegment(0.0, 1000.0, {"fishing_intensity": "high", "mystery": 1})
    plan = _screener().assess([seg])
    assert plan.segments[0].strategy == "rock_dump"
    assert any("no recognised soil class" in g for g in plan.data_gaps)
    assert any("No surveyed cover" in g for g in plan.data_gaps)
    assert any("rock placement rate" in g for g in plan.data_gaps)
    assert any("mystery" in w for w in plan.warnings)
    assert plan.rock_days is None


def test_rock_days_when_rate_supplied_and_plan_serialises(tmp_path):
    a = ScreeningAssumptions(rock_rate_tonnes_per_day=5000.0)
    seg = RouteSegment(0.0, 1000.0, {"soil_class": "rock", "fishing_intensity": "high"})
    plan = SeabedProtectionScreener(PipeBasis(0.4), a).assess([seg], existing_cover_intervals=[])
    assert plan.rock_days == pytest.approx(plan.rock_tonnes / 5000.0)
    json.dumps(plan.to_dict())
    path = tmp_path / "layer.geojson"
    path.write_text(json.dumps(_box(0, 0, 1, 1, v=1)), encoding="utf-8")
    assert read_geojson(path)["type"] == "FeatureCollection"


def test_input_validation():
    with pytest.raises(ValueError):
        SeabedProtectionScreener(PipeBasis(0.0))
    with pytest.raises(ValueError):
        _screener().assess([])
    with pytest.raises(ValueError):
        build_route([(0, 0)])
