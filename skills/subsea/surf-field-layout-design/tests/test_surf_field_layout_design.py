import math

import pytest

from surf_field_layout_design import (
    OPEN_DATA_SOURCES,
    LocalFrame,
    block_bounds,
    design_surf_layout,
    erosional_velocity_m_per_s,
    execute,
    haversine_m,
    plan_bathymetry_request,
    plan_layout_data_package,
    quadrant_bounds,
    select_line_size,
)


def _layout(**overrides):
    kwargs = dict(
        field_name="Test field",
        centre_latitude_deg=73.375,
        centre_longitude_deg=25.0,
        water_depth_m=400.0,
        producers=8,
        water_injectors=6,
        gas_injectors=2,
        slots_per_template=4,
        reservoir_length_km=6.0,
        reservoir_width_km=3.0,
        design_liquid_rate_m3_per_s=0.33,
        design_water_injection_rate_m3_per_s=0.23,
        design_gas_injection_rate_am3_per_s=0.09,
    )
    kwargs.update(overrides)
    return design_surf_layout(**kwargs)


class TestLocalFrame:
    def test_round_trip_is_metre_accurate(self):
        frame = LocalFrame(73.375, 25.0)
        latitude, longitude = frame.to_geographic(5000.0, -3000.0)
        east, north = frame.to_local(latitude, longitude)
        assert east == pytest.approx(5000.0, abs=0.1)
        assert north == pytest.approx(-3000.0, abs=0.1)

    def test_local_offset_matches_great_circle_distance(self):
        frame = LocalFrame(73.375, 25.0)
        latitude, longitude = frame.to_geographic(4000.0, 3000.0)
        distance = haversine_m(73.375, 25.0, latitude, longitude)
        assert distance == pytest.approx(5000.0, rel=0.01)

    def test_rejects_impossible_origin(self):
        with pytest.raises(ValueError):
            LocalFrame(120.0, 0.0)


class TestNorwegianGrid:
    def test_quadrant_spans_one_by_two_degrees(self):
        bounds = quadrant_bounds("7324")
        assert bounds["south_latitude_deg"] == 73.0
        assert bounds["north_latitude_deg"] == 74.0
        assert bounds["west_longitude_deg"] == 24.0
        assert bounds["east_longitude_deg"] == 26.0

    def test_block_is_fifteen_by_forty_minutes(self):
        bounds = block_bounds("7324/8")
        assert bounds["north_latitude_deg"] - bounds["south_latitude_deg"] == pytest.approx(0.25)
        assert bounds["east_longitude_deg"] - bounds["west_longitude_deg"] == pytest.approx(2.0 / 3.0)
        assert bounds["quadrant"] == "7324"

    def test_block_bounds_carry_a_verification_flag(self):
        assert "verification" in block_bounds("7324/8")

    def test_southern_quadrants_are_rejected(self):
        with pytest.raises(ValueError):
            quadrant_bounds("1525")

    def test_block_number_is_range_checked(self):
        with pytest.raises(ValueError):
            block_bounds("7324/13")


class TestLineSizing:
    def test_erosional_velocity_matches_api_rp_14e(self):
        # 100 / sqrt(50 lb/ft3) = 14.1 ft/s = 4.31 m/s
        assert erosional_velocity_m_per_s(800.9) == pytest.approx(4.31, rel=0.02)

    def test_selects_the_smallest_size_that_meets_the_target(self):
        size = select_line_size(0.165, 850.0, target_velocity_m_per_s=3.0)
        assert size.velocity_m_per_s <= 3.0
        smaller = [s for s in (4.0, 6.0, 8.0, 10.0, 12.0) if s < size.nominal_inch]
        for nominal in smaller:
            area = math.pi / 4.0 * (nominal * 0.0254 * 0.9) ** 2
            assert 0.165 / area > 3.0

    def test_flags_a_line_above_the_erosional_limit(self):
        size = select_line_size(50.0, 850.0, target_velocity_m_per_s=3.0)
        assert size.erosional_ratio > 1.0
        assert "erosional" in size.verdict

    def test_rejects_a_non_positive_flow(self):
        with pytest.raises(ValueError):
            select_line_size(0.0, 850.0)


class TestLayoutDesign:
    def test_every_well_gets_a_tree_and_a_drill_centre(self):
        layout = _layout()
        wells = layout.nodes_of_kind("well")
        trees = layout.nodes_of_kind("xmas_tree")
        assert len(wells) == 16
        assert len(trees) == 16
        assert all(well.parent.endswith("DC01") or "DC" in well.parent for well in wells)

    def test_drill_centre_count_follows_the_slot_count(self):
        layout = _layout(producers=8, slots_per_template=4)
        assert layout.summary["drill_centres"]["production"] == 2
        layout = _layout(producers=9, slots_per_template=4)
        assert layout.summary["drill_centres"]["production"] == 3

    def test_each_drill_centre_has_a_plem_and_an_umbilical(self):
        layout = _layout()
        centres = layout.nodes_of_kind("template")
        plems = [node for node in layout.nodes_of_kind("plem") if node.parent != "HOST"]
        assert len(plems) == len(centres)
        assert len(layout.lines_of_service("umbilical")) == len(centres)

    def test_dual_loop_gives_two_production_legs_per_drill_centre(self):
        layout = _layout(production_architecture="dual_loop")
        production = layout.lines_of_service("production")
        flowlines = [line for line in production if "flowline" in line.line_type]
        assert len(flowlines) == 2 * layout.summary["drill_centres"]["production"]

    def test_single_line_architecture_gives_one_line_per_drill_centre(self):
        layout = _layout(production_architecture="single_line")
        flowlines = [
            line for line in layout.lines_of_service("production") if "flowline" in line.line_type
        ]
        assert len(flowlines) == layout.summary["drill_centres"]["production"]

    def test_host_and_riser_base_are_placed_apart(self):
        layout = _layout(host_offset_km=2.5, riser_base_offset_m=350.0)
        host = layout.node("HOST")
        riser_base = layout.node("RB-PLEM")
        separation = math.hypot(
            host.east_m - riser_base.east_m, host.north_m - riser_base.north_m
        )
        assert separation == pytest.approx(350.0, rel=0.01)

    def test_drill_centres_line_up_on_the_requested_field_axis(self):
        layout = _layout(field_axis_bearing_deg=30.0)
        first, second = [
            node for node in layout.nodes_of_kind("template") if node.tag.startswith("P-DC")
        ][:2]
        axis = math.degrees(
            math.atan2(second.east_m - first.east_m, second.north_m - first.north_m)
        ) % 180.0
        assert axis == pytest.approx(30.0, abs=0.5)

    def test_seabed_slope_deepens_along_the_axis(self):
        layout = _layout(field_axis_bearing_deg=0.0, seabed_slope_deg=1.0)
        centres = [n for n in layout.nodes_of_kind("template") if n.tag.startswith("P-DC")]
        south = min(centres, key=lambda node: node.north_m)
        north = max(centres, key=lambda node: node.north_m)
        assert south.water_depth_m > north.water_depth_m

    def test_risers_are_longer_than_the_water_depth(self):
        layout = _layout(water_depth_m=400.0)
        risers = [line for line in layout.lines if "riser" in line.line_type]
        assert risers
        assert all(line.length_m > 400.0 for line in risers)

    def test_geojson_is_wgs84_and_lists_every_node_and_line(self):
        layout = _layout()
        collection = layout.to_geojson()
        assert collection["type"] == "FeatureCollection"
        points = [f for f in collection["features"] if f["geometry"]["type"] == "Point"]
        lines = [f for f in collection["features"] if f["geometry"]["type"] == "LineString"]
        assert len(points) == len(layout.nodes)
        assert len(lines) == len(layout.lines)
        longitude, latitude = points[0]["geometry"]["coordinates"]
        assert 24.0 < longitude < 26.0
        assert 73.0 < latitude < 74.0

    def test_layout_dict_reports_lengths_and_caveats(self):
        layout = _layout()
        payload = layout.to_dict()
        assert payload["summary"]["flowline_length_km"] > 0.0
        assert payload["summary"]["xmas_trees"] == 16
        assert payload["assumptions"]
        assert layout.total_line_length_km("production") > 0.0

    def test_missing_design_rate_warns_instead_of_guessing(self):
        layout = _layout(design_liquid_rate_m3_per_s=0.0)
        assert any("not sized" in warning for warning in layout.warnings)
        production = [
            line for line in layout.lines_of_service("production") if "flowline" in line.line_type
        ]
        assert all(line.size is None for line in production)

    def test_rejects_an_unknown_architecture(self):
        with pytest.raises(ValueError):
            _layout(production_architecture="spaghetti")

    def test_rejects_a_field_with_no_producers(self):
        with pytest.raises(ValueError):
            _layout(producers=0)


class TestOpenData:
    def test_every_registered_source_is_attributed_and_licensed(self):
        for source in OPEN_DATA_SOURCES.values():
            assert source.licence
            assert source.attribution
            assert source.base_url.startswith("https://")

    def test_bathymetry_request_carries_the_bounding_box(self):
        request = plan_bathymetry_request(24.0, 73.0, 26.0, 74.0)
        assert "24.0" in request.url and "74.0" in request.url
        assert request.method == "GET"

    def test_bounding_box_is_validated(self):
        with pytest.raises(ValueError):
            plan_bathymetry_request(26.0, 73.0, 24.0, 74.0)

    def test_plan_is_offline_until_a_fetch_adapter_is_supplied(self):
        manifest = execute(plan_layout_data_package(24.0, 73.0, 26.0, 74.0))
        assert manifest["executed"] is False
        assert manifest["requests"]
        assert manifest["attribution"]

    def test_a_failing_source_does_not_abort_the_package(self):
        def fetch(url):
            if "sodir" in url:
                raise TimeoutError("no network")
            return {"ok": True}

        manifest = execute(plan_layout_data_package(24.0, 73.0, 26.0, 74.0), fetch=fetch)
        assert manifest["results"]
        assert "sodir_factmaps" in manifest["errors"]
