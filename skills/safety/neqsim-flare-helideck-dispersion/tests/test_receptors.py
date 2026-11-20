import math

import numpy as np
import pytest
from flare_helideck_dispersion import (
    FlightPathSettings,
    PlatformGeometry,
    Receptors,
    Release,
    ReleaseCase,
)
from flare_helideck_dispersion.receptors import angular_difference_deg, grid_to_true


def test_geometry_positions():
    geo = PlatformGeometry()
    deck = geo.helideck_position
    assert math.hypot(deck[0], deck[1]) == pytest.approx(240.0)
    assert deck[2] == pytest.approx(76.0 + 5.0)
    assert geo.vertical_separation_m == pytest.approx(124.0 - 81.0)
    # deck lies WSW of the tip; wind from ENE (060) carries gas from the tip to the deck
    assert geo.azimuth_toward_deck_wind_from_deg == pytest.approx(60.0)
    assert deck[0] < 0.0 and deck[1] < 0.0


def test_grid_conversion_and_from_platform_grid():
    e, n = grid_to_true(100.0, 0.0, 90.0)  # platform north points east
    assert (e, n) == pytest.approx((0.0, -100.0), abs=1e-9)
    geo = PlatformGeometry.from_platform_grid((0.0, 0.0), (0.0, 200.0), 0.0)
    assert geo.helideck_distance_m == pytest.approx(200.0)
    assert geo.helideck_azimuth_from_tip_deg == pytest.approx(0.0, abs=1e-9)


def test_obstacle_free_sector_membership_and_into_wind_logic():
    rec = Receptors(PlatformGeometry())
    assert rec.in_obstacle_free_sector(240.0) and rec.in_obstacle_free_sector(135.0)
    assert not rec.in_obstacle_free_sector(60.0)
    assert rec.into_wind_bearing(200.0) == pytest.approx(200.0)
    # wind from the blocked half: nearest sector edge
    assert rec.into_wind_bearing(100.0) == pytest.approx(135.0)
    assert rec.into_wind_bearing(10.0) == pytest.approx(345.0)
    assert rec.path_bearings[0] == pytest.approx(135.0)
    assert rec.path_bearings[-1] == pytest.approx(345.0)
    assert len(rec.path_bearings) == 43


def test_sector_wrapping_through_north():
    geo = PlatformGeometry(ofs_start_deg=300.0, ofs_end_deg=60.0)
    rec = Receptors(geo)
    assert geo.ofs_width_deg == pytest.approx(120.0)
    assert rec.in_obstacle_free_sector(0.0) and rec.in_obstacle_free_sector(300.0)
    assert not rec.in_obstacle_free_sector(180.0)
    assert rec.path_bearings[0] == pytest.approx(300.0)
    assert rec.path_bearings[-1] == pytest.approx(60.0)
    assert rec.into_wind_bearing(150.0) == pytest.approx(
        60.0
    )  # 150 is nearer to 60 than to 300


def test_climb_profile_and_resolution_warnings():
    rec = Receptors(PlatformGeometry())
    p = rec.path_points(240.0)
    assert p[0, 2] == pytest.approx(rec.deck[2])
    assert p[-1, 2] - p[0, 2] == pytest.approx(
        rec.path_distances[-1] * math.tan(math.radians(5.0))
    )
    coarse = Receptors(
        PlatformGeometry(flight_paths=FlightPathSettings(bearing_step_deg=15.0))
    )
    assert any("under-sampled" in w for w in coarse.warnings())
    assert not any("under-sampled" in w for w in rec.warnings())
    assert angular_difference_deg(350.0, 10.0) == pytest.approx(20.0)


def test_five_degree_paths_pick_a_worse_bearing_than_fifteen():
    rel = Release(ReleaseCase("c", 150.0, 0.0215, 1.25, 190.0, 0.04, 0.96, 0.6))
    fine = Receptors(
        PlatformGeometry(flight_paths=FlightPathSettings(bearing_step_deg=5.0))
    )
    coarse = Receptors(
        PlatformGeometry(flight_paths=FlightPathSettings(bearing_step_deg=15.0))
    )
    # far from the helideck the paths fan out and bearing resolution matters
    tip = fine.geometry.tip_position

    def far_max(rec):
        pts = rec.all_paths.reshape(len(rec.path_bearings), rec.n_path_points, 3)
        far = pts[:, rec.path_distances >= 1000.0, :].reshape(-1, 3)
        return rel.pct_lfl(far, 112.5, 1.5, "F", tip).max()

    # plume travels toward 292.5 deg, between the 15-degree bearings 285 and 300
    v_fine, v_coarse = far_max(fine), far_max(coarse)
    assert v_fine > 1.2 * v_coarse
    # every coarse bearing is also a fine bearing, so the fine maximum can never be lower
    assert set(np.round(coarse.path_bearings)) <= set(np.round(fine.path_bearings))
