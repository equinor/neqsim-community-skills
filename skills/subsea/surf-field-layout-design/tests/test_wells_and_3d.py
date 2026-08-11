import os

import pytest

from surf_field_layout_design import (
    MAX_SCREENING_DOGLEG_DEG_PER_30M,
    build_well_paths,
    design_surf_layout,
    plot_reservoir_3d,
    trajectory_warnings,
)

matplotlib = pytest.importorskip("matplotlib")


@pytest.fixture()
def layout():
    return design_surf_layout(
        field_name="Test field",
        centre_latitude_deg=73.375,
        centre_longitude_deg=25.0,
        water_depth_m=400.0,
        producers=8,
        water_injectors=6,
        gas_injectors=2,
        reservoir_length_km=6.0,
        reservoir_width_km=3.1,
        field_axis_bearing_deg=30.0,
        design_liquid_rate_m3_per_s=0.33,
    )


@pytest.fixture()
def paths(layout):
    return build_well_paths(
        layout,
        reservoir_depth_m_tvdmsl=650.0,
        net_pay_m=45.0,
        field_axis_bearing_deg=30.0,
    )


class TestWellPaths:
    def test_one_trajectory_per_well(self, layout, paths):
        assert len(paths) == len(layout.nodes_of_kind("well"))

    def test_trajectory_starts_at_the_tree_and_ends_in_the_reservoir(self, layout, paths):
        for well_path in paths:
            well = layout.node(well_path.well_tag)
            start = well_path.points[0]
            end = well_path.points[-1]
            assert start[0] == pytest.approx(well.east_m)
            assert start[2] == pytest.approx(well.water_depth_m)
            assert 650.0 <= end[2] <= 650.0 + 45.0

    def test_depth_increases_monotonically_down_the_hole(self, paths):
        for well_path in paths:
            depths = [point[2] for point in well_path.points]
            assert all(b >= a - 1e-6 for a, b in zip(depths, depths[1:]))

    def test_measured_depth_exceeds_the_vertical_depth(self, paths):
        for well_path in paths:
            assert well_path.measured_depth_m > well_path.reservoir_target_tvd_m

    def test_the_whole_drain_stays_inside_the_reservoir_footprint(self, layout, paths):
        from math import cos, radians, sin

        angle = radians(layout.summary["field_axis_bearing_deg"])
        half_length = layout.summary["reservoir_length_km"] * 500.0
        for well_path in paths:
            for east, north, _ in well_path.points[-2:]:
                along = east * sin(angle) + north * cos(angle)
                assert abs(along) <= half_length + 1.0

    def test_geographic_track_matches_the_local_track(self, layout, paths):
        well_path = paths[0]
        latitude, longitude, tvd = well_path.geographic[0]
        east, north = layout.frame.to_local(latitude, longitude)
        assert east == pytest.approx(well_path.points[0][0], abs=1.0)
        assert north == pytest.approx(well_path.points[0][1], abs=1.0)
        assert tvd == pytest.approx(well_path.points[0][2])

    def test_services_keep_their_across_axis_band(self, paths):
        production = [p for p in paths if p.service == "production"]
        water = [p for p in paths if p.service == "water_injection"]
        gas = [p for p in paths if p.service == "gas_injection"]
        assert production and water and gas
        # the injector bands sit on opposite sides of the producer band
        def mean_across(group):
            return sum(p.points[-2][0] for p in group) / len(group)

        assert mean_across(water) != pytest.approx(mean_across(gas), abs=100.0)

    def test_a_tight_build_is_flagged_as_undrillable(self, layout):
        paths = build_well_paths(
            layout,
            reservoir_depth_m_tvdmsl=430.0,  # only 30 m below the seabed
            net_pay_m=20.0,
            kick_off_below_seabed_m=10.0,
            field_axis_bearing_deg=30.0,
        )
        assert any(not p.drillable for p in paths)
        warnings = trajectory_warnings(paths)
        assert warnings
        assert any(str(int(MAX_SCREENING_DOGLEG_DEG_PER_30M)) in w for w in warnings)

    def test_rejects_an_impossible_reservoir_depth(self, layout):
        with pytest.raises(ValueError):
            build_well_paths(layout, reservoir_depth_m_tvdmsl=0.0)

    def test_path_dict_is_reportable(self, paths):
        payload = paths[0].to_dict()
        for key in ("well", "service", "measured_depth_m", "build_rate_deg_per_30m", "drillable"):
            assert key in payload


class TestReservoir3D:
    def test_figure_is_written(self, tmp_path, layout, paths):
        target = str(tmp_path / "reservoir3d.png")
        plot_reservoir_3d(
            layout, paths, target, reservoir_depth_m_tvdmsl=650.0, net_pay_m=45.0
        )
        assert os.path.exists(target)
        assert os.path.getsize(target) > 10000

    def test_accepts_a_custom_view_and_title(self, tmp_path, layout, paths):
        target = str(tmp_path / "reservoir3d_view.png")
        plot_reservoir_3d(
            layout,
            paths,
            target,
            reservoir_depth_m_tvdmsl=650.0,
            title="Custom",
            elevation_deg=35.0,
            azimuth_deg=120.0,
        )
        assert os.path.exists(target)
