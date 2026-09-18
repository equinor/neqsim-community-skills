import pytest

from pressure_drop_screening import PressureDropModel


def test_pressure_drop_model_returns_ok_within_guideline() -> None:
    result = PressureDropModel().evaluate(
        fluid_velocity=5.0,
        mixture_density=50.0,
        viscosity=1.2e-5,
        pipe_inner_diameter=0.3,
        length=100.0,
        guideline_bar_per_100m=0.5,
    )

    assert result.pressure_drop_warning == "ok"
    assert result.reynolds_number > 4000.0
    assert result.dp_per_100m_bar > 0.0
    assert result.guideline_ratio < 0.8
    assert result.assumptions


def test_pressure_drop_model_flags_high_above_guideline() -> None:
    result = PressureDropModel().evaluate(
        fluid_velocity=25.0,
        mixture_density=80.0,
        viscosity=1.2e-5,
        pipe_inner_diameter=0.1,
        length=100.0,
        guideline_bar_per_100m=0.5,
    )

    assert result.pressure_drop_warning == "high"
    assert result.guideline_ratio > 1.0


def test_pressure_drop_model_laminar_friction_factor() -> None:
    result = PressureDropModel().evaluate(
        fluid_velocity=0.05,
        mixture_density=800.0,
        viscosity=0.5,
        pipe_inner_diameter=0.1,
        length=100.0,
    )

    assert result.reynolds_number < 2000.0
    # Laminar friction factor f = 64 / Re
    assert result.friction_factor == pytest.approx(64.0 / result.reynolds_number, rel=1e-3)


def test_pressure_drop_model_rejects_negative_viscosity() -> None:
    with pytest.raises(ValueError, match="viscosity"):
        PressureDropModel().evaluate(
            fluid_velocity=5.0,
            mixture_density=50.0,
            viscosity=-1.0e-5,
            pipe_inner_diameter=0.3,
        )
