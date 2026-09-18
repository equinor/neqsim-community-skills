import pytest

from depressurization_screening import DepressurizationModel


def test_depressurization_model_returns_ok_for_mild_case() -> None:
    result = DepressurizationModel().evaluate(
        initial_pressure=20.0,
        target_pressure=15.0,
        inventory=500.0,
        vent_mass_rate=8000.0,
        relieving_temperature=60.0,
        mdmt=-46.0,
    )

    assert result.depressurization_warning == "ok"
    assert result.low_temperature_flag is False
    assert result.blowdown_time_indicator == pytest.approx(0.0625, abs=1e-3)
    assert result.estimated_min_temperature_C > -46.0
    assert result.assumptions


def test_depressurization_model_flags_low_temperature() -> None:
    result = DepressurizationModel().evaluate(
        initial_pressure=100.0,
        target_pressure=7.0,
        inventory=2000.0,
        vent_mass_rate=12000.0,
        relieving_temperature=30.0,
        mdmt=-46.0,
    )

    assert result.low_temperature_flag is True
    assert result.depressurization_warning == "high"
    assert result.estimated_min_temperature_C < -46.0


def test_depressurization_model_flags_slow_blowdown() -> None:
    result = DepressurizationModel().evaluate(
        initial_pressure=120.0,
        target_pressure=8.0,
        inventory=50_000.0,
        vent_mass_rate=120_000.0,
        relieving_temperature=120.0,
        mdmt=-150.0,
    )

    assert result.blowdown_time_indicator > 1.0
    assert result.depressurization_warning == "high"


def test_depressurization_model_rejects_target_above_initial() -> None:
    with pytest.raises(ValueError, match="target_pressure"):
        DepressurizationModel().evaluate(
            initial_pressure=10.0,
            target_pressure=15.0,
            inventory=500.0,
            vent_mass_rate=8000.0,
            relieving_temperature=60.0,
            mdmt=-46.0,
        )
