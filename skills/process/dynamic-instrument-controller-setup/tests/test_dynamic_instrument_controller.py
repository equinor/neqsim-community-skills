import pytest

from dynamic_instrument_controller_setup import DynamicInstrumentControllerModel


def test_level_loop_returns_ready_setup() -> None:
    setup = DynamicInstrumentControllerModel().evaluate(
        loop_name="LC-001",
        controlled_variable="level",
        transmitter_target="V-001",
        manipulated_equipment="LCV-001",
        setpoint=0.3,
        minimum_value=0.01,
        maximum_value=0.99,
        reverse_acting=True,
        kp=25.8,
        ti=400.1,
        td=0.0,
    )

    assert setup.loop_ready is True
    assert setup.transmitter_class == "LevelTransmitter"
    assert any("setControllerParameters" in step for step in setup.controller_steps)
    assert any("autoTuneFromEventLog" in step for step in setup.autotune_steps)


def test_pressure_loop_flags_setpoint_outside_range() -> None:
    setup = DynamicInstrumentControllerModel().evaluate(
        loop_name="PC-001",
        controlled_variable="pressure",
        transmitter_target="V-001 gas outlet",
        manipulated_equipment="PCV-001",
        setpoint=12.0,
        minimum_value=0.0,
        maximum_value=10.0,
        reverse_acting=False,
        kp=1.0,
        ti=2000.0,
    )

    assert setup.loop_ready is False
    assert "setpoint is outside transmitter range" in setup.validation_warnings


def test_flow_loop_uses_verified_volume_flow_transmitter_class() -> None:
    setup = DynamicInstrumentControllerModel().evaluate(
        loop_name="FC-001",
        controlled_variable="flow",
        transmitter_target="feed stream",
        manipulated_equipment="FCV-001",
        setpoint=100.0,
        minimum_value=0.0,
        maximum_value=200.0,
        reverse_acting=False,
        kp=1.0,
        ti=30.0,
    )

    assert setup.transmitter_class == "VolumeFlowTransmitter"
    assert setup.loop_ready is True


def test_controller_setup_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="controlled_variable"):
        DynamicInstrumentControllerModel().evaluate(
            loop_name="QC-001",
            controlled_variable="composition",
            transmitter_target="stream",
            manipulated_equipment="valve",
            setpoint=1.0,
            minimum_value=0.0,
            maximum_value=2.0,
            reverse_acting=False,
            kp=1.0,
            ti=10.0,
        )
