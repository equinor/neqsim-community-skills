from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, pi
from typing import Any, Mapping


@dataclass(frozen=True)
class DynamicEquipment:
    name: str
    equipment_type: str
    dynamic_action: str
    volume_m3: float | None
    liquid_holdup_m3: float | None
    requires_mechanical_design: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DynamicPreparationPlan:
    process_name: str
    process_kind: str
    dynamic_ready: bool
    equipment_actions: tuple[DynamicEquipment, ...]
    estimated_volumes_m3: dict[str, float]
    neqsim_sequence: tuple[str, ...]
    warnings: tuple[str, ...]
    neqsim_available: bool


class DynamicProcessPreparationModel:
    """Readiness checks for NeqSim dynamic process preparation."""

    VALID_PROCESS_KINDS = {"ProcessSystem", "ProcessModel"}
    VESSEL_TYPES = {"separator", "threephaseseparator", "gas scrubber", "vessel", "tank"}

    def evaluate(
        self,
        *,
        process_name: str,
        process_kind: str,
        time_step_seconds: float,
        equipment: list[Mapping[str, Any]],
        total_time_seconds: float | None = None,
        initialization_basis: str = "steady-state NeqSim run",
    ) -> DynamicPreparationPlan:
        self._require_text("process_name", process_name)
        if process_kind not in self.VALID_PROCESS_KINDS:
            raise ValueError("process_kind must be ProcessSystem or ProcessModel")
        self._require_positive("time_step_seconds", time_step_seconds)
        if total_time_seconds is not None:
            self._require_positive("total_time_seconds", total_time_seconds)
        self._require_text("initialization_basis", initialization_basis)
        if not equipment:
            raise ValueError("equipment must contain at least one dynamic candidate")

        equipment_actions = tuple(self._evaluate_equipment(item) for item in equipment)
        estimated_volumes = {
            item.name: item.volume_m3 for item in equipment_actions if item.volume_m3 is not None
        }
        warnings = list(self._global_warnings(equipment_actions, total_time_seconds))
        dynamic_ready = not warnings and all(not item.warnings for item in equipment_actions)

        return DynamicPreparationPlan(
            process_name=process_name,
            process_kind=process_kind,
            dynamic_ready=dynamic_ready,
            equipment_actions=equipment_actions,
            estimated_volumes_m3=estimated_volumes,
            neqsim_sequence=(
                "Confirm the steady-state ProcessSystem or every ProcessModel area converges.",
                "Initialize mechanical design for supported vessels and rotating equipment.",
                "Set geometry and initial holdup or liquid level on dynamic vessels.",
                "Call setCalculateSteadyState(False) on supported dynamic equipment.",
                "Run the initialized model, inspect state, and call storeInitialState().",
                f"Set the transient time step to {time_step_seconds:g} s.",
                "Run runTransient() in a documented time loop and record mass balance and state trends.",
            ),
            warnings=tuple(warnings),
            neqsim_available=find_spec("neqsim") is not None,
        )

    def _evaluate_equipment(self, item: Mapping[str, Any]) -> DynamicEquipment:
        name = str(item.get("name", "")).strip()
        equipment_type = str(item.get("equipment_type", "")).strip()
        self._require_text("equipment.name", name)
        self._require_text(f"{name}.equipment_type", equipment_type)

        normalized_type = equipment_type.lower().replace("-", " ").replace("_", " ")
        length = self._optional_positive(item.get("length_m"), f"{name}.length_m")
        diameter = self._optional_positive(item.get("diameter_m"), f"{name}.diameter_m")
        level = self._optional_fraction(
            item.get("liquid_level_fraction"), f"{name}.liquid_level_fraction"
        )
        requires_mechanical_design = bool(item.get("requires_mechanical_design", False))

        warnings: list[str] = []
        volume = None
        holdup = None
        is_vessel = normalized_type in self.VESSEL_TYPES
        if is_vessel:
            if length is None or diameter is None:
                warnings.append("vessel geometry is missing; set length and internal diameter")
            else:
                volume = round(pi * diameter**2 / 4.0 * length, 6)
                if level is not None:
                    holdup = round(volume * level, 6)
            if level is None:
                warnings.append("initial liquid level fraction is missing")
        elif length is not None or diameter is not None or level is not None:
            warnings.append("geometry or level was supplied for non-vessel equipment; verify basis")

        if requires_mechanical_design and not is_vessel:
            warnings.append("mechanical-design request should be mapped to a supported NeqSim design class")

        return DynamicEquipment(
            name=name,
            equipment_type=equipment_type,
            dynamic_action=self._dynamic_action(normalized_type),
            volume_m3=volume,
            liquid_holdup_m3=holdup,
            requires_mechanical_design=requires_mechanical_design,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _dynamic_action(normalized_type: str) -> str:
        if normalized_type in DynamicProcessPreparationModel.VESSEL_TYPES:
            return "setCalculateSteadyState(False), set geometry, set initial level, then store initial state"
        if "valve" in normalized_type:
            return "setCalculateSteadyState(False), set opening/pressure basis, and attach controller if needed"
        if "stream" in normalized_type:
            return "use as boundary condition and confirm flow, pressure, and temperature basis"
        return "verify dynamic support, then document state variables and initialization basis"

    @staticmethod
    def _global_warnings(
        equipment_actions: tuple[DynamicEquipment, ...], total_time_seconds: float | None
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if total_time_seconds is None:
            warnings.append("total transient duration is not specified")
        if not any(item.volume_m3 is not None for item in equipment_actions):
            warnings.append("no equipment volume estimate is available")
        return tuple(warnings)

    @staticmethod
    def _require_text(name: str, value: str) -> None:
        if not value or not value.strip():
            raise ValueError(f"{name} must be provided")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    @classmethod
    def _optional_positive(cls, value: Any, name: str) -> float | None:
        if value is None:
            return None
        numeric = float(value)
        cls._require_positive(name, numeric)
        return numeric

    @classmethod
    def _optional_fraction(cls, value: Any, name: str) -> float | None:
        if value is None:
            return None
        numeric = float(value)
        cls._require_finite(name, numeric)
        if numeric < 0.0 or numeric > 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
        return numeric

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
