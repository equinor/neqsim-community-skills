import pytest

from noise_screening import ValveNoiseModel


def test_basic_noise_indicator():
    model = ValveNoiseModel()
    result = model.evaluate(
        mass_flow=5.0,
        pressure_drop=10.0,
        inlet_density=40.0,
        sound_speed=400.0,
    )
    assert result.vena_contracta_velocity_m_s > 0.0
    assert result.mach_number > 0.0
    assert result.estimated_spl_1m_dba > 0.0
    assert result.noise_warning in {"ok", "action", "high"}


def test_high_noise_warning():
    model = ValveNoiseModel()
    result = model.evaluate(
        mass_flow=50.0,
        pressure_drop=80.0,
        inlet_density=30.0,
        sound_speed=420.0,
    )
    assert result.noise_warning in {"action", "high"}


def test_sound_speed_from_gas_properties():
    model = ValveNoiseModel()
    result = model.evaluate(
        mass_flow=5.0,
        pressure_drop=10.0,
        inlet_density=40.0,
        specific_heat_ratio=1.3,
        temperature=300.0,
        molar_mass=18.0,
    )
    assert result.mach_number > 0.0


def test_missing_sound_speed_inputs_rejected():
    model = ValveNoiseModel()
    with pytest.raises(ValueError, match="provide sound_speed"):
        model.evaluate(
            mass_flow=5.0,
            pressure_drop=10.0,
            inlet_density=40.0,
        )


def test_invalid_levels_rejected():
    with pytest.raises(ValueError, match="high_level"):
        ValveNoiseModel(action_level=110.0, high_level=85.0)


def test_invalid_mass_flow_rejected():
    model = ValveNoiseModel()
    with pytest.raises(ValueError, match="mass_flow"):
        model.evaluate(
            mass_flow=0.0,
            pressure_drop=10.0,
            inlet_density=40.0,
            sound_speed=400.0,
        )
