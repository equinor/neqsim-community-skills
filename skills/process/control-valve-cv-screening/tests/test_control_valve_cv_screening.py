import pytest

from control_valve_cv_screening import ControlValveCvModel


def test_liquid_cv_sizing():
    model = ControlValveCvModel()
    result = model.evaluate(
        service="liquid",
        inlet_pressure=10.0,
        pressure_drop=2.0,
        flow_rate=50.0,
        specific_gravity=0.85,
    )
    # Kv = 50 * sqrt(0.85 / 2.0) ~ 32.6 ; Cv = 1.156 * Kv
    assert result.required_kv == pytest.approx(32.596, abs=0.05)
    assert result.required_cv == pytest.approx(result.required_kv * 1.156, abs=1e-3)
    assert result.choked is False
    assert result.valve_warning == "no-rating"


def test_liquid_choked_flag():
    model = ControlValveCvModel()
    result = model.evaluate(
        service="liquid",
        inlet_pressure=10.0,
        pressure_drop=9.0,
        flow_rate=50.0,
        specific_gravity=0.85,
        vapor_pressure=3.0,
        critical_pressure=220.0,
        fl=0.9,
    )
    assert result.choked is True
    assert result.valve_warning == "choked"


def test_gas_cv_sizing():
    model = ControlValveCvModel()
    result = model.evaluate(
        service="gas",
        inlet_pressure=50.0,
        pressure_drop=10.0,
        mass_flow=5000.0,
        inlet_density=40.0,
    )
    assert result.required_cv > 0.0
    assert result.choked is False


def test_gas_choked_flag():
    model = ControlValveCvModel()
    result = model.evaluate(
        service="gas",
        inlet_pressure=50.0,
        pressure_drop=40.0,
        mass_flow=5000.0,
        inlet_density=40.0,
    )
    assert result.choked is True
    assert result.valve_warning == "choked"


def test_rating_margin_warning():
    model = ControlValveCvModel()
    result = model.evaluate(
        service="liquid",
        inlet_pressure=10.0,
        pressure_drop=2.0,
        flow_rate=50.0,
        specific_gravity=0.85,
        rated_cv=20.0,
    )
    assert result.cv_margin_ratio is not None
    assert result.valve_warning == "under-sized"


def test_invalid_service_rejected():
    model = ControlValveCvModel()
    with pytest.raises(ValueError, match="service"):
        model.evaluate(service="steam", inlet_pressure=10.0, pressure_drop=2.0)


def test_invalid_pressure_drop_rejected():
    model = ControlValveCvModel()
    with pytest.raises(ValueError, match="pressure_drop"):
        model.evaluate(
            service="liquid",
            inlet_pressure=5.0,
            pressure_drop=5.0,
            flow_rate=50.0,
            specific_gravity=0.85,
        )
