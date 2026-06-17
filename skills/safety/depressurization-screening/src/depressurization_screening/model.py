from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class DepressurizationResult:
    blowdown_time_indicator: float
    estimated_blowdown_time_min: float
    estimated_min_temperature_C: float
    low_temperature_flag: bool
    depressurization_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class DepressurizationModel:
    """Educational blowdown and depressurization screening placeholder."""

    def __init__(
        self,
        target_time_minutes: float = 15.0,
        isentropic_exponent: float = 1.3,
    ) -> None:
        self._require_positive("target_time_minutes", target_time_minutes)
        if isentropic_exponent <= 1.0:
            raise ValueError("isentropic_exponent must be greater than 1.0")
        self.target_time_minutes = target_time_minutes
        self.isentropic_exponent = isentropic_exponent

    def evaluate(
        self,
        *,
        initial_pressure: float,
        target_pressure: float,
        inventory: float,
        vent_mass_rate: float,
        relieving_temperature: float,
        mdmt: float = -20.0,
    ) -> DepressurizationResult:
        self._require_positive("initial_pressure", initial_pressure)
        self._require_positive("target_pressure", target_pressure)
        self._require_positive("inventory", inventory)
        self._require_positive("vent_mass_rate", vent_mass_rate)
        self._require_finite("relieving_temperature", relieving_temperature)
        self._require_finite("mdmt", mdmt)
        if target_pressure >= initial_pressure:
            raise ValueError("target_pressure must be below initial_pressure")

        pressure_ratio = target_pressure / initial_pressure
        vented_mass = inventory * (1.0 - pressure_ratio)
        estimated_blowdown_time_min = vented_mass / vent_mass_rate * 60.0
        blowdown_time_indicator = estimated_blowdown_time_min / self.target_time_minutes

        exponent = (self.isentropic_exponent - 1.0) / self.isentropic_exponent
        initial_temperature_k = relieving_temperature + 273.15
        estimated_min_temperature_k = initial_temperature_k * pressure_ratio ** exponent
        estimated_min_temperature_c = estimated_min_temperature_k - 273.15
        low_temperature_flag = estimated_min_temperature_c < mdmt

        depressurization_warning = self._warning(blowdown_time_indicator, low_temperature_flag)

        return DepressurizationResult(
            blowdown_time_indicator=round(blowdown_time_indicator, 4),
            estimated_blowdown_time_min=round(estimated_blowdown_time_min, 2),
            estimated_min_temperature_C=round(estimated_min_temperature_c, 2),
            low_temperature_flag=low_temperature_flag,
            depressurization_warning=depressurization_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Vented mass to target uses a linear pressure-fraction placeholder.",
                "Blowdown time uses a constant representative vent rate, not a transient profile.",
                "Cold-end temperature uses a simplified isentropic relation ignoring heat input.",
                "Move to a validated NeqSim transient depressurization model for real blowdown design.",
            ),
        )

    @staticmethod
    def _warning(blowdown_time_indicator: float, low_temperature_flag: bool) -> str:
        if blowdown_time_indicator > 1.0 or low_temperature_flag:
            return "high"
        if blowdown_time_indicator > 0.75:
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
