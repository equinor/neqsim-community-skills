import pytest

from bathymetry_profile_screening import BathymetryProfileModel


def _simple_soundings():
    return [
        {"distance_m": 0.0, "depth_m": 300.0},
        {"distance_m": 1000.0, "depth_m": 320.0},
        {"distance_m": 2000.0, "depth_m": 300.0},
    ]


def test_sorts_soundings_by_distance() -> None:
    soundings = [
        {"distance_m": 2000.0, "depth_m": 300.0},
        {"distance_m": 0.0, "depth_m": 300.0},
        {"distance_m": 1000.0, "depth_m": 320.0},
    ]
    result = BathymetryProfileModel().evaluate(soundings=soundings)

    distances = [item.distance_m for item in result.sorted_soundings]
    assert distances == [0.0, 1000.0, 2000.0]


def test_linear_interpolation_midpoint() -> None:
    result = BathymetryProfileModel().evaluate(
        soundings=_simple_soundings(), query_distances=[500.0]
    )

    # Halfway between 300 and 320 m.
    assert result.interpolated[0]["depth_m"] == pytest.approx(310.0, abs=1e-6)
    assert result.interpolated[0]["clamped"] == 0.0


def test_query_outside_range_is_clamped() -> None:
    result = BathymetryProfileModel().evaluate(
        soundings=_simple_soundings(), query_distances=[5000.0]
    )

    assert result.interpolated[0]["depth_m"] == pytest.approx(300.0, abs=1e-6)
    assert result.interpolated[0]["clamped"] == 1.0


def test_steep_section_flagged() -> None:
    soundings = [
        {"distance_m": 0.0, "depth_m": 100.0},
        {"distance_m": 100.0, "depth_m": 400.0},
    ]
    result = BathymetryProfileModel(max_slope_deg=10.0).evaluate(soundings=soundings)

    assert result.max_slope_deg > 10.0
    assert result.slope_warning == "high"
    assert len(result.steep_sections) == 1


def test_min_and_max_depth() -> None:
    result = BathymetryProfileModel().evaluate(soundings=_simple_soundings())

    assert result.min_depth_m == pytest.approx(300.0, abs=1e-6)
    assert result.max_depth_m == pytest.approx(320.0, abs=1e-6)


def test_rejects_single_sounding() -> None:
    with pytest.raises(ValueError, match="at least two soundings"):
        BathymetryProfileModel().evaluate(soundings=[{"distance_m": 0.0, "depth_m": 1.0}])


def test_rejects_duplicate_distance() -> None:
    soundings = [
        {"distance_m": 0.0, "depth_m": 100.0},
        {"distance_m": 0.0, "depth_m": 200.0},
    ]
    with pytest.raises(ValueError, match="unique"):
        BathymetryProfileModel().evaluate(soundings=soundings)
