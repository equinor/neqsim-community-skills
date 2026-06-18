import pytest

from compressor_power_screening import CompressorPowerModel


def test_compressor_power_model_ok_with_rated_power() -> None:
    result = CompressorPowerModel().evaluate(
        suction_pressure=30.0,
        discharge_pressure=90.0,
        suction_temperature=313.15,
        mass_flow=25.0,
        molecular_weight=19.0,
        rated_power=20000.0,
    )

    assert result.compressor_warning == "ok"
    assert result.gas_power_kw > 0.0
    assert result.discharge_temperature_k > 313.15
    assert result.power_margin_ratio is not None
    assert result.assumptions


def test_compressor_power_model_over_rated_when_power_too_small() -> None:
    result = CompressorPowerModel().evaluate(
        suction_pressure=30.0,
        discharge_pressure=120.0,
        suction_temperature=313.15,
        mass_flow=40.0,
        molecular_weight=19.0,
        rated_power=1000.0,
    )

    assert result.compressor_warning == "over-rated"
    assert result.power_margin_ratio < 1.0


def test_compressor_power_model_no_rating_returns_none_margin() -> None:
    result = CompressorPowerModel().evaluate(
        suction_pressure=30.0,
        discharge_pressure=90.0,
        suction_temperature=313.15,
        mass_flow=25.0,
        molecular_weight=19.0,
    )

    assert result.compressor_warning == "no-rating"
    assert result.power_margin_ratio is None


def test_compressor_power_model_rejects_low_discharge_pressure() -> None:
    with pytest.raises(ValueError, match="discharge_pressure"):
        CompressorPowerModel().evaluate(
            suction_pressure=90.0,
            discharge_pressure=30.0,
            suction_temperature=313.15,
            mass_flow=25.0,
            molecular_weight=19.0,
        )
