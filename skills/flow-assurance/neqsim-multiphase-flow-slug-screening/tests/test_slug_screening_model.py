import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multiphase_flow_slug_screening import SlugScreeningModel


def test_slug_regime_flagged_as_watch_without_capacity():
    model = SlugScreeningModel()
    result = model.evaluate(
        superficial_gas_velocity=6.0,
        superficial_liquid_velocity=1.0,
        pipe_internal_diameter=0.3,
    )
    assert "slug" in result.flow_regime_indicator
    assert result.slug_warning == "watch"
    assert result.capacity_ratio is None


def test_capacity_ratio_high_warning():
    model = SlugScreeningModel()
    result = model.evaluate(
        superficial_gas_velocity=4.0,
        superficial_liquid_velocity=1.0,
        pipe_internal_diameter=0.3,
        available_slug_catcher_volume=0.1,
    )
    assert result.capacity_ratio > 1.0
    assert result.slug_warning == "high"


def test_capacity_ratio_ok_warning():
    model = SlugScreeningModel()
    result = model.evaluate(
        superficial_gas_velocity=4.0,
        superficial_liquid_velocity=1.0,
        pipe_internal_diameter=0.3,
        available_slug_catcher_volume=100.0,
    )
    assert result.capacity_ratio < 0.8
    assert result.slug_warning == "ok"


def test_slug_volume_matches_geometry():
    model = SlugScreeningModel()
    result = model.evaluate(
        superficial_gas_velocity=4.0,
        superficial_liquid_velocity=1.0,
        pipe_internal_diameter=0.3,
        slug_length_to_diameter=30.0,
        liquid_holdup_in_slug=0.8,
        surge_factor=1.2,
    )
    # slug_length = 9 m, area = pi*0.3^2/4 = 0.0706858 m2, holdup 0.8
    expected_slug_volume = 9.0 * (3.141592653589793 * 0.3**2 / 4.0) * 0.8
    assert result.estimated_slug_volume_m3 == pytest.approx(
        round(expected_slug_volume, 4)
    )
    assert result.recommended_slug_catcher_volume_m3 == pytest.approx(
        round(expected_slug_volume * 1.2, 4)
    )


def test_invalid_holdup():
    model = SlugScreeningModel()
    with pytest.raises(ValueError, match="liquid_holdup_in_slug"):
        model.evaluate(
            superficial_gas_velocity=4.0,
            superficial_liquid_velocity=1.0,
            pipe_internal_diameter=0.3,
            liquid_holdup_in_slug=1.5,
        )


def test_invalid_threshold_ordering():
    with pytest.raises(ValueError, match="watch_threshold"):
        SlugScreeningModel(watch_threshold=1.0, high_threshold=0.8)
