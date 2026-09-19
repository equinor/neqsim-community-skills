import pytest

from pipe_route_profile import PipeRouteModel


def _straight_flat_route():
    return [
        {"name": "A", "x": 0.0, "y": 0.0, "depth_m": 300.0},
        {"name": "B", "x": 4000.0, "y": 0.0, "depth_m": 300.0},
        {"name": "C", "x": 8000.0, "y": 0.0, "depth_m": 300.0},
    ]


def test_flat_route_length_is_horizontal_sum() -> None:
    result = PipeRouteModel().evaluate(waypoints=_straight_flat_route())

    assert result.total_horizontal_length_km == pytest.approx(8.0, abs=1e-6)
    assert result.total_route_length_km == pytest.approx(8.0, abs=1e-6)
    assert result.max_slope_deg == pytest.approx(0.0, abs=1e-9)
    assert result.slope_warning == "ok"
    assert result.net_elevation_change_m == pytest.approx(0.0, abs=1e-9)
    assert len(result.segments) == 2
    assert len(result.kp_profile) == 3


def test_rising_route_reports_net_rise() -> None:
    waypoints = [
        {"name": "Tree", "x": 0.0, "y": 0.0, "depth_m": 340.0},
        {"name": "Riser", "x": 8000.0, "y": 0.0, "depth_m": 120.0},
    ]
    result = PipeRouteModel().evaluate(waypoints=waypoints)

    assert result.net_elevation_change_m == pytest.approx(220.0, abs=1e-6)
    assert result.total_rise_m == pytest.approx(220.0, abs=1e-6)
    assert result.total_descent_m == pytest.approx(0.0, abs=1e-9)


def test_3d_length_exceeds_horizontal_when_descending() -> None:
    waypoints = [
        {"name": "A", "x": 0.0, "y": 0.0, "depth_m": 100.0},
        {"name": "B", "x": 400.0, "y": 0.0, "depth_m": 400.0},
    ]
    result = PipeRouteModel().evaluate(waypoints=waypoints)

    # 300 m horizontal? no: 400 horizontal, 300 depth -> 500 m 3D (3-4-5).
    assert result.total_horizontal_length_km == pytest.approx(0.4, abs=1e-6)
    assert result.total_route_length_km == pytest.approx(0.5, abs=1e-6)
    assert result.total_descent_m == pytest.approx(300.0, abs=1e-6)


def test_steep_slope_flagged_high() -> None:
    waypoints = [
        {"name": "A", "x": 0.0, "y": 0.0, "depth_m": 100.0},
        {"name": "B", "x": 100.0, "y": 0.0, "depth_m": 400.0},
    ]
    result = PipeRouteModel(max_slope_deg=15.0).evaluate(waypoints=waypoints)

    assert result.max_slope_deg > 15.0
    assert result.slope_warning == "high"


def test_geographic_route_length_reasonable() -> None:
    waypoints = [
        {"name": "A", "x": 2.0, "y": 60.0, "depth_m": 120.0},
        {"name": "B", "x": 2.2, "y": 60.0, "depth_m": 120.0},
    ]
    result = PipeRouteModel().evaluate(
        waypoints=waypoints, coordinate_system="geographic"
    )

    # ~0.2 deg longitude at 60 deg latitude ~ 11 km.
    assert 9.0 < result.total_horizontal_length_km < 13.0


def test_rejects_single_waypoint() -> None:
    with pytest.raises(ValueError, match="at least two waypoints"):
        PipeRouteModel().evaluate(waypoints=[{"name": "A", "x": 0.0, "y": 0.0, "depth_m": 1.0}])


def test_rejects_negative_depth() -> None:
    waypoints = [
        {"name": "A", "x": 0.0, "y": 0.0, "depth_m": -1.0},
        {"name": "B", "x": 1.0, "y": 0.0, "depth_m": 1.0},
    ]
    with pytest.raises(ValueError, match="non-negative"):
        PipeRouteModel().evaluate(waypoints=waypoints)
