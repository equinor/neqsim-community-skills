from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class ControlLoopSetup:
    loop_name: str
    controlled_variable: str
    transmitter_class: str
    loop_ready: bool
    controller_steps: tuple[str, ...]
    autotune_steps: tuple[str, ...]
    validation_warnings: tuple[str, ...]
    neqsim_available: bool


class DynamicInstrumentControllerModel:
    """Readiness checks for NeqSim dynamic instruments and controllers."""

    TRANSMITTERS = {
        "level": "LevelTransmitter",
        "pressure": "PressureTransmitter",
        "temperature": "TemperatureTransmitter",
        "flow": "VolumeFlowTransmitter",
    }

    def evaluate(
        self,
        *,
        loop_name: str,
        controlled_variable: str,
        transmitter_target: str,
        manipulated_equipment: str,
        setpoint: float,
        minimum_value: float,
        maximum_value: float,
        reverse_acting: bool,
        kp: float,
        ti: float,
        td: float = 0.0,
    ) -> ControlLoopSetup:
        self._require_text("loop_name", loop_name)
        self._require_text("transmitter_target", transmitter_target)
        self._require_text("manipulated_equipment", manipulated_equipment)
        variable = controlled_variable.strip().lower()
        if variable not in self.TRANSMITTERS:
            raise ValueError("controlled_variable must be one of level, pressure, temperature, flow")
        self._require_finite("setpoint", setpoint)
        self._require_finite("minimum_value", minimum_value)
        self._require_finite("maximum_value", maximum_value)
        self._require_finite("kp", kp)
        self._require_finite("ti", ti)
        self._require_finite("td", td)

        warnings: list[str] = []
        if minimum_value >= maximum_value:
            warnings.append("minimum_value must be lower than maximum_value")
        elif not (minimum_value <= setpoint <= maximum_value):
            warnings.append("setpoint is outside transmitter range")
        if kp == 0.0:
            warnings.append("kp is zero; controller will not provide proportional action")
        if ti < 0.0 or td < 0.0:
            warnings.append("ti and td should be non-negative for a first dynamic trial")
        if variable == "level" and not reverse_acting:
            warnings.append("level control commonly uses reverse action on liquid outlet valves; verify action")
        if variable == "pressure" and reverse_acting:
            warnings.append("pressure control action is case-dependent; verify direct/reverse cause and effect")

        transmitter_class = self.TRANSMITTERS[variable]
        return ControlLoopSetup(
            loop_name=loop_name,
            controlled_variable=variable,
            transmitter_class=transmitter_class,
            loop_ready=not warnings,
            controller_steps=(
                f"Create ns.process.measurementdevice.{transmitter_class} for {transmitter_target}.",
                f"Set transmitter minimum={minimum_value:g} and maximum={maximum_value:g}.",
                "Create ns.process.controllerdevice.ControllerDeviceBaseClass().",
                "Call controller.setTransmitter(transmitter).",
                f"Call controller.setReverseActing({reverse_acting}).",
                f"Call controller.setControllerSetPoint({setpoint:g}).",
                f"Call controller.setControllerParameters({kp:g}, {ti:g}, {td:g}).",
                f"Attach the controller to {manipulated_equipment} with setController(controller).",
                "Add the transmitter to the ProcessSystem and run transient validation.",
            ),
            autotune_steps=(
                "Call controller.resetEventLog() before deliberate excitation.",
                "Apply one or more setpoint steps and run enough transient time to capture response.",
                "Call controller.autoTuneFromEventLog(False) and record Kp, Ti, and Td.",
                "Re-run the transient case and verify stability, saturation, and physical state variables.",
            ),
            validation_warnings=tuple(warnings),
            neqsim_available=find_spec("neqsim") is not None,
        )

    @staticmethod
    def _require_text(name: str, value: str) -> None:
        if not value or not value.strip():
            raise ValueError(f"{name} must be provided")

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
