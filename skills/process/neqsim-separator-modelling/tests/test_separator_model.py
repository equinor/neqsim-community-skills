import pytest

from separator_modelling import SeparatorModel


def test_separator_model_returns_ok_for_moderate_public_case() -> None:
    result = SeparatorModel().evaluate(
        gas_flow=18_000.0,
        liquid_flow=120.0,
        pressure=55.0,
        temperature=35.0,
        gas_density=18.0,
        liquid_density=720.0,
    )

    assert result.capacity_warning == "ok"
    assert result.gas_load_indicator == pytest.approx(0.7637)
    assert result.residence_time_indicator == pytest.approx(2.5)
    assert result.assumptions


def test_separator_model_flags_high_gas_load() -> None:
    result = SeparatorModel().evaluate(
        gas_flow=30_000.0,
        liquid_flow=200.0,
        pressure=80.0,
        temperature=20.0,
        gas_density=20.0,
        liquid_density=760.0,
    )

    assert result.capacity_warning == "high"
    assert result.gas_load_indicator > 1.0


def test_separator_model_rejects_negative_flow() -> None:
    with pytest.raises(ValueError, match="gas_flow"):
        SeparatorModel().evaluate(
            gas_flow=-1.0,
            liquid_flow=120.0,
            pressure=55.0,
            temperature=35.0,
            gas_density=18.0,
            liquid_density=720.0,
        )