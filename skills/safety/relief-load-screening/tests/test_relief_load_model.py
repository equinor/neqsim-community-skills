import pytest

from relief_load_screening import ReliefLoadModel


def test_relief_load_model_returns_ok_for_small_fire_zone() -> None:
    result = ReliefLoadModel().evaluate(
        wetted_area=50.0,
        latent_heat=300.0,
        relief_pressure=20.0,
        environment_factor=1.0,
    )

    assert result.relief_warning == "ok"
    assert result.relief_load_indicator == pytest.approx(0.2564, abs=1e-3)
    assert result.fire_heat_input_kW == pytest.approx(1068.2, abs=1.0)
    assert result.assumptions


def test_relief_load_model_flags_high_load_for_large_fire_zone() -> None:
    result = ReliefLoadModel().evaluate(
        wetted_area=400.0,
        latent_heat=150.0,
        relief_pressure=10.0,
        environment_factor=1.0,
    )

    assert result.relief_warning == "high"
    assert result.relief_load_indicator > 1.0


def test_relief_load_model_environment_factor_reduces_load() -> None:
    base = ReliefLoadModel().evaluate(
        wetted_area=120.0,
        latent_heat=250.0,
        relief_pressure=15.0,
        environment_factor=1.0,
    )
    credited = ReliefLoadModel().evaluate(
        wetted_area=120.0,
        latent_heat=250.0,
        relief_pressure=15.0,
        environment_factor=0.3,
    )

    assert credited.relief_mass_rate_kg_per_h < base.relief_mass_rate_kg_per_h


def test_relief_load_model_rejects_negative_area() -> None:
    with pytest.raises(ValueError, match="wetted_area"):
        ReliefLoadModel().evaluate(
            wetted_area=-1.0,
            latent_heat=300.0,
            relief_pressure=20.0,
            environment_factor=1.0,
        )
