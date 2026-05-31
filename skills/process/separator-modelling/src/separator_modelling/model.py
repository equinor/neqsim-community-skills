from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt


@dataclass(frozen=True)
class SeparatorResult:
    gas_load_indicator: float
    residence_time_indicator: float
    capacity_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class SeparatorModel:
    """Educational separator screening placeholder."""

    def __init__(
        self,
        design_gas_load_basis: float = 100_000.0,
        liquid_holdup_volume: float = 25.0,
        target_residence_time_minutes: float = 5.0,
    ) -> None:
        self._require_positive("design_gas_load_basis", design_gas_load_basis)
        self._require_positive("liquid_holdup_volume", liquid_holdup_volume)
        self._require_positive("target_residence_time_minutes", target_residence_time_minutes)
        self.design_gas_load_basis = design_gas_load_basis
        self.liquid_holdup_volume = liquid_holdup_volume
        self.target_residence_time_minutes = target_residence_time_minutes

    def evaluate(
        self,
        *,
        gas_flow: float,
        liquid_flow: float,
        pressure: float,
        temperature: float,
        gas_density: float,
        liquid_density: float,
    ) -> SeparatorResult:
        self._require_non_negative("gas_flow", gas_flow)
        self._require_non_negative("liquid_flow", liquid_flow)
        self._require_positive("pressure", pressure)
        self._require_finite("temperature", temperature)
        self._require_positive("gas_density", gas_density)
        self._require_positive("liquid_density", liquid_density)

        gas_load_indicator = gas_flow * sqrt(gas_density) / self.design_gas_load_basis
        residence_time_minutes = self._residence_time_minutes(liquid_flow)
        residence_time_indicator = residence_time_minutes / self.target_residence_time_minutes
        capacity_warning = self._capacity_warning(gas_load_indicator, residence_time_indicator)

        return SeparatorResult(
            gas_load_indicator=round(gas_load_indicator, 4),
            residence_time_indicator=round(residence_time_indicator, 4),
            capacity_warning=capacity_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Gas load basis is a configurable public reference value, not a design K-factor.",
                "Residence time uses configurable public holdup volume divided by liquid flow.",
                "Move to validated NeqSim models for real separator calculations.",
            ),
        )

    def _residence_time_minutes(self, liquid_flow: float) -> float:
        if liquid_flow == 0.0:
            return float("inf")
        return self.liquid_holdup_volume / liquid_flow * 60.0

    @staticmethod
    def _capacity_warning(gas_load_indicator: float, residence_time_indicator: float) -> str:
        if gas_load_indicator > 1.0 or residence_time_indicator < 0.75:
            return "high"
        if gas_load_indicator > 0.8 or residence_time_indicator < 1.0:
            return "watch"
        return "ok"

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    @classmethod
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")