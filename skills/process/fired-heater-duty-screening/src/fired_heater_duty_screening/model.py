from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class FiredHeaterDutyResult:
    process_duty_kw: float
    fired_duty_kw: float
    fuel_rate_kg_s: float
    average_radiant_flux_kw_m2: float
    flux_ratio: float
    fired_heater_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class FiredHeaterDutyModel:
    """Educational fired-heater duty and radiant-flux screening placeholder."""

    def __init__(self, watch_threshold: float = 0.85) -> None:
        if not 0.0 < watch_threshold <= 1.0:
            raise ValueError("watch_threshold must be in the interval (0, 1]")
        self.watch_threshold = watch_threshold

    def evaluate(
        self,
        *,
        mass_flow: float,
        specific_heat: float,
        inlet_temperature: float,
        outlet_temperature: float,
        radiant_area: float,
        thermal_efficiency: float = 0.85,
        fuel_heating_value: float = 46.0,
        allowable_radiant_flux: float = 37.0,
    ) -> FiredHeaterDutyResult:
        self._require_positive("mass_flow", mass_flow)
        self._require_positive("specific_heat", specific_heat)
        self._require_positive("inlet_temperature", inlet_temperature)
        self._require_positive("outlet_temperature", outlet_temperature)
        if outlet_temperature <= inlet_temperature:
            raise ValueError("outlet_temperature must be greater than inlet_temperature")
        self._require_positive("radiant_area", radiant_area)
        self._require_fraction("thermal_efficiency", thermal_efficiency)
        self._require_positive("fuel_heating_value", fuel_heating_value)
        self._require_positive("allowable_radiant_flux", allowable_radiant_flux)

        delta_t = outlet_temperature - inlet_temperature
        # kg/s * kJ/(kg K) * K = kW.
        process_duty_kw = mass_flow * specific_heat * delta_t
        fired_duty_kw = process_duty_kw / thermal_efficiency
        # Fuel rate: fired duty kW / (MJ/kg * 1000 kW per MW per MJ/s) = kg/s.
        fuel_rate_kg_s = fired_duty_kw / (fuel_heating_value * 1000.0)
        average_radiant_flux = process_duty_kw / radiant_area
        flux_ratio = average_radiant_flux / allowable_radiant_flux
        warning = self._warning(flux_ratio)

        return FiredHeaterDutyResult(
            process_duty_kw=round(process_duty_kw, 3),
            fired_duty_kw=round(fired_duty_kw, 3),
            fuel_rate_kg_s=round(fuel_rate_kg_s, 5),
            average_radiant_flux_kw_m2=round(average_radiant_flux, 4),
            flux_ratio=round(flux_ratio, 4),
            fired_heater_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Process duty uses Q = mass_flow * specific_heat * (T_out - T_in).",
                "All process duty is assigned to the radiant section for the flux estimate.",
                "Constant specific heat; no convection split, tube-wall, or draft modeling.",
                "Move to validated NeqSim FiredHeater and qualified review.",
            ),
        )

    def _warning(self, flux_ratio: float) -> str:
        if flux_ratio >= 1.0:
            return "high-flux"
        if flux_ratio >= self.watch_threshold:
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
    def _require_fraction(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1]")
