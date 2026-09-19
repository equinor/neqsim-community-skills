import pytest

from line_velocity_check import LineVelocityModel


def test_line_velocity_model_returns_ok_within_limits() -> None:
    result = LineVelocityModel().evaluate(
        fluid_velocity=12.0,
        mixture_density=50.0,
        c_factor=122.0,
        max_velocity_guideline=20.0,
    )

    assert result.velocity_warning == "ok"
    assert result.erosional_velocity_m_per_s == pytest.approx(17.25, abs=0.05)
    assert result.velocity_ratio == pytest.approx(0.6956, abs=1e-3)
    assert result.operating_indicator == pytest.approx(0.6956, abs=1e-3)
    assert result.assumptions


def test_line_velocity_model_flags_high_above_erosional_velocity() -> None:
    result = LineVelocityModel().evaluate(
        fluid_velocity=20.0,
        mixture_density=50.0,
        c_factor=122.0,
        max_velocity_guideline=20.0,
    )

    assert result.velocity_warning == "high"
    assert result.velocity_ratio > 1.0


def test_line_velocity_model_flags_watch_near_limit() -> None:
    result = LineVelocityModel().evaluate(
        fluid_velocity=17.0,
        mixture_density=50.0,
        c_factor=122.0,
        max_velocity_guideline=20.0,
    )

    assert result.velocity_warning == "watch"
    assert 0.8 < result.operating_indicator <= 1.0


def test_line_velocity_model_rejects_negative_density() -> None:
    with pytest.raises(ValueError, match="mixture_density"):
        LineVelocityModel().evaluate(
            fluid_velocity=12.0,
            mixture_density=-50.0,
        )
