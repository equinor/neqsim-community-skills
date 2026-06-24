import pytest

from subsea_layout_geometry import SubseaLayoutModel


def _square_layout():
    return [
        {"name": "Host", "x": 0.0, "y": 0.0, "water_depth_m": 100.0, "kind": "host"},
        {"name": "W1", "x": 3000.0, "y": 4000.0, "water_depth_m": 100.0, "kind": "well"},
    ]


def test_cartesian_step_out_uses_euclidean_distance() -> None:
    result = SubseaLayoutModel().evaluate(nodes=_square_layout(), host_name="Host")

    # 3-4-5 triangle: 5000 m = 5.0 km horizontal.
    assert result.step_out_km["W1"] == pytest.approx(5.0, abs=1e-6)
    assert result.straight_line_km["W1"] == pytest.approx(5.0, abs=1e-6)
    assert result.step_out_warning == "ok"
    assert result.node_count == 2
    assert result.assumptions


def test_straight_line_includes_depth_difference() -> None:
    nodes = [
        {"name": "Host", "x": 0.0, "y": 0.0, "water_depth_m": 100.0, "kind": "host"},
        {"name": "W1", "x": 0.0, "y": 0.0, "water_depth_m": 1100.0, "kind": "well"},
    ]
    result = SubseaLayoutModel().evaluate(nodes=nodes, host_name="Host")

    assert result.step_out_km["W1"] == pytest.approx(0.0, abs=1e-6)
    assert result.straight_line_km["W1"] == pytest.approx(1.0, abs=1e-6)


def test_geographic_distance_is_positive_and_reasonable() -> None:
    nodes = [
        {"name": "Host", "x": 2.0, "y": 60.0, "water_depth_m": 120.0, "kind": "host"},
        {"name": "W1", "x": 2.5, "y": 60.0, "water_depth_m": 130.0, "kind": "well"},
    ]
    result = SubseaLayoutModel().evaluate(
        nodes=nodes, host_name="Host", coordinate_system="geographic"
    )

    # 0.5 deg of longitude at 60 deg latitude is roughly 27-28 km.
    assert 25.0 < result.step_out_km["W1"] < 30.0


def test_step_out_warning_flags_high_beyond_guideline() -> None:
    nodes = [
        {"name": "Host", "x": 0.0, "y": 0.0, "water_depth_m": 100.0, "kind": "host"},
        {"name": "W1", "x": 60000.0, "y": 0.0, "water_depth_m": 100.0, "kind": "well"},
    ]
    result = SubseaLayoutModel(max_step_out_km=50.0).evaluate(nodes=nodes, host_name="Host")

    assert result.max_step_out_km == pytest.approx(60.0, abs=1e-6)
    assert result.step_out_warning == "high"


def test_pairwise_distance_matrix_is_complete() -> None:
    nodes = [
        {"name": "Host", "x": 0.0, "y": 0.0, "water_depth_m": 100.0, "kind": "host"},
        {"name": "M1", "x": 1000.0, "y": 0.0, "water_depth_m": 100.0, "kind": "manifold"},
        {"name": "W1", "x": 2000.0, "y": 0.0, "water_depth_m": 100.0, "kind": "well"},
    ]
    result = SubseaLayoutModel().evaluate(nodes=nodes, host_name="Host")

    # 3 nodes -> 3 unique pairs.
    assert len(result.pairwise_distances) == 3


def test_rejects_missing_host() -> None:
    with pytest.raises(ValueError, match="host_name"):
        SubseaLayoutModel().evaluate(nodes=_square_layout(), host_name="Nope")


def test_rejects_single_node() -> None:
    with pytest.raises(ValueError, match="at least two nodes"):
        SubseaLayoutModel().evaluate(
            nodes=[{"name": "Host", "x": 0.0, "y": 0.0}], host_name="Host"
        )


def test_rejects_duplicate_names() -> None:
    nodes = [
        {"name": "W1", "x": 0.0, "y": 0.0},
        {"name": "W1", "x": 1.0, "y": 1.0},
    ]
    with pytest.raises(ValueError, match="unique"):
        SubseaLayoutModel().evaluate(nodes=nodes, host_name="W1")
