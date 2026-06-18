import pytest

from fired_heater_duty_screening import FiredHeaterDutyModel


def test_fired_heater_model_ok_with_large_area() -> None:
    result = FiredHeaterDutyModel().evaluate(
        mass_flow=15.0,
        specific_heat=2.4,
        inlet_temperature=473.15,
        outlet_temperature=623.15,
        radiant_area=400.0,
    )

    assert result.fired_heater_warning == "ok"
    assert result.fired_duty_kw > result.process_duty_kw
    assert result.fuel_rate_kg_s > 0.0
    assert result.assumptions


def test_fired_heater_model_high_flux_with_small_area() -> None:
    result = FiredHeaterDutyModel().evaluate(
        mass_flow=30.0,
        specific_heat=2.6,
        inlet_temperature=473.15,
        outlet_temperature=653.15,
        radiant_area=120.0,
    )

    assert result.fired_heater_warning == "high-flux"
    assert result.flux_ratio >= 1.0


def test_fired_heater_model_duty_matches_energy_balance() -> None:
    result = FiredHeaterDutyModel().evaluate(
        mass_flow=10.0,
        specific_heat=2.5,
        inlet_temperature=400.0,
        outlet_temperature=500.0,
        radiant_area=200.0,
        thermal_efficiency=0.8,
    )

    expected_process = 10.0 * 2.5 * 100.0
    assert result.process_duty_kw == pytest.approx(expected_process)
    assert result.fired_duty_kw == pytest.approx(expected_process / 0.8)


def test_fired_heater_model_rejects_low_outlet_temperature() -> None:
    with pytest.raises(ValueError, match="outlet_temperature"):
        FiredHeaterDutyModel().evaluate(
            mass_flow=15.0,
            specific_heat=2.4,
            inlet_temperature=623.15,
            outlet_temperature=473.15,
            radiant_area=200.0,
        )
