import pytest

from pump_hydraulics_screening import PumpHydraulicsModel


def test_hydraulic_and_shaft_power():
    model = PumpHydraulicsModel()
    result = model.evaluate(
        flow_rate=100.0,
        head=80.0,
        density=850.0,
        efficiency=0.72,
    )
    # P_hyd = 850 * 9.80665 * (100/3600) * 80 / 1000 ~ 18.5 kW
    assert result.hydraulic_power_kw == pytest.approx(18.524, abs=0.05)
    assert result.shaft_power_kw > result.hydraulic_power_kw
    assert result.pump_warning == "no-rating"


def test_npsh_margin_and_warning():
    model = PumpHydraulicsModel()
    result = model.evaluate(
        flow_rate=100.0,
        head=80.0,
        density=850.0,
        suction_pressure=3.0,
        vapor_pressure=1.0,
        static_suction_head=2.0,
        friction_loss=0.5,
        npsh_required=3.0,
    )
    assert result.npsh_available_m is not None
    assert result.npsh_margin_m is not None
    assert result.pump_warning in {"ok", "watch", "npsh-deficit"}


def test_npsh_deficit_flagged():
    model = PumpHydraulicsModel()
    result = model.evaluate(
        flow_rate=100.0,
        head=80.0,
        density=850.0,
        suction_pressure=1.2,
        vapor_pressure=1.0,
        npsh_required=8.0,
    )
    assert result.pump_warning == "npsh-deficit"


def test_off_bep_flagged():
    model = PumpHydraulicsModel()
    result = model.evaluate(
        flow_rate=40.0,
        head=80.0,
        density=850.0,
        bep_flow_rate=100.0,
    )
    assert result.bep_ratio == pytest.approx(0.40, abs=1e-6)
    assert result.pump_warning == "off-bep"


def test_invalid_efficiency_rejected():
    model = PumpHydraulicsModel()
    with pytest.raises(ValueError, match="efficiency"):
        model.evaluate(flow_rate=100.0, head=80.0, density=850.0, efficiency=1.5)


def test_invalid_flow_rejected():
    model = PumpHydraulicsModel()
    with pytest.raises(ValueError, match="flow_rate"):
        model.evaluate(flow_rate=0.0, head=80.0, density=850.0)
