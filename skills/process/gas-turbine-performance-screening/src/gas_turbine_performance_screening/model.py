from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Optional, Tuple

ISO_REFERENCE_TEMPERATURE_K = 288.15


@dataclass(frozen=True)
class GasTurbinePerformanceResult:
    site_power_kw: float
    ambient_derate_factor: float
    altitude_derate_factor: float
    pressure_loss_derate_factor: float
    total_derate_factor: float
    site_heat_rate_kj_kwh: float
    thermal_efficiency: float
    fuel_heat_input_kw: float
    exhaust_mass_flow_kg_s: float
    exhaust_temperature_k: float
    power_margin_ratio: Optional[float]
    power_warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class GasTurbinePerformanceModel:
    """Educational gas-turbine performance screening (ISO 3977 / GL1029 style).

    Estimates site-rated shaft power, site heat rate, thermal efficiency, fuel
    heat input, exhaust mass flow, and exhaust temperature from an ISO base
    rating using open derate factors. Screening only.
    """

    def __init__(
        self,
        *,
        ambient_derate_per_k: float = 0.007,
        altitude_derate_per_m: float = 1.1e-4,
        inlet_loss_derate_per_mbar: float = 0.002,
        exhaust_loss_derate_per_mbar: float = 0.001,
        specific_exhaust_flow_kg_s_per_kw: float = 0.003,
        base_exhaust_temperature_k: float = 773.15,
    ) -> None:
        self._require_positive("ambient_derate_per_k", ambient_derate_per_k)
        self._require_positive("altitude_derate_per_m", altitude_derate_per_m)
        self._require_positive("inlet_loss_derate_per_mbar", inlet_loss_derate_per_mbar)
        self._require_positive("exhaust_loss_derate_per_mbar", exhaust_loss_derate_per_mbar)
        self._require_positive(
            "specific_exhaust_flow_kg_s_per_kw", specific_exhaust_flow_kg_s_per_kw
        )
        self._require_positive("base_exhaust_temperature_k", base_exhaust_temperature_k)
        self.ambient_derate_per_k = ambient_derate_per_k
        self.altitude_derate_per_m = altitude_derate_per_m
        self.inlet_loss_derate_per_mbar = inlet_loss_derate_per_mbar
        self.exhaust_loss_derate_per_mbar = exhaust_loss_derate_per_mbar
        self.specific_exhaust_flow_kg_s_per_kw = specific_exhaust_flow_kg_s_per_kw
        self.base_exhaust_temperature_k = base_exhaust_temperature_k

    def evaluate(
        self,
        *,
        iso_base_power_kw: float,
        iso_heat_rate_kj_kwh: float,
        ambient_temperature_k: float = ISO_REFERENCE_TEMPERATURE_K,
        site_elevation_m: float = 0.0,
        relative_humidity: float = 0.6,
        inlet_pressure_loss_mbar: float = 10.0,
        exhaust_pressure_loss_mbar: float = 10.0,
        required_shaft_power_kw: Optional[float] = None,
    ) -> GasTurbinePerformanceResult:
        self._require_positive("iso_base_power_kw", iso_base_power_kw)
        self._require_positive("iso_heat_rate_kj_kwh", iso_heat_rate_kj_kwh)
        self._require_positive("ambient_temperature_k", ambient_temperature_k)
        self._require_non_negative("site_elevation_m", site_elevation_m)
        self._require_unit_interval("relative_humidity", relative_humidity)
        self._require_non_negative("inlet_pressure_loss_mbar", inlet_pressure_loss_mbar)
        self._require_non_negative("exhaust_pressure_loss_mbar", exhaust_pressure_loss_mbar)
        if required_shaft_power_kw is not None:
            self._require_positive("required_shaft_power_kw", required_shaft_power_kw)

        # Ambient derate above the ISO reference temperature (cap any uprate).
        ambient_factor = 1.0 - self.ambient_derate_per_k * (
            ambient_temperature_k - ISO_REFERENCE_TEMPERATURE_K
        )
        ambient_factor = self._clamp_factor(ambient_factor)

        # Altitude derate from reduced barometric pressure.
        altitude_factor = self._clamp_factor(
            1.0 - self.altitude_derate_per_m * site_elevation_m
        )

        # Inlet and exhaust pressure-loss derate.
        inlet_factor = self._clamp_factor(
            1.0 - self.inlet_loss_derate_per_mbar * inlet_pressure_loss_mbar
        )
        exhaust_factor = self._clamp_factor(
            1.0 - self.exhaust_loss_derate_per_mbar * exhaust_pressure_loss_mbar
        )
        pressure_loss_factor = inlet_factor * exhaust_factor

        # Small humidity effect relative to the 0.6 reference.
        humidity_factor = self._clamp_factor(1.0 - 0.01 * (relative_humidity - 0.6))

        total_factor = ambient_factor * altitude_factor * pressure_loss_factor * humidity_factor
        site_power = iso_base_power_kw * total_factor

        # Heat rate degrades as power derates (efficiency loss screening).
        site_heat_rate = iso_heat_rate_kj_kwh * (1.0 + 0.5 * (1.0 - total_factor))
        thermal_efficiency = 3600.0 / site_heat_rate
        fuel_heat_input = site_power * site_heat_rate / 3600.0

        exhaust_mass_flow = site_power * self.specific_exhaust_flow_kg_s_per_kw
        exhaust_temperature = self.base_exhaust_temperature_k + 0.5 * (
            ambient_temperature_k - ISO_REFERENCE_TEMPERATURE_K
        )

        power_margin_ratio: Optional[float] = None
        if required_shaft_power_kw is not None:
            power_margin_ratio = site_power / required_shaft_power_kw

        power_warning = self._power_warning(power_margin_ratio)

        return GasTurbinePerformanceResult(
            site_power_kw=round(site_power, 2),
            ambient_derate_factor=round(ambient_factor, 4),
            altitude_derate_factor=round(altitude_factor, 4),
            pressure_loss_derate_factor=round(pressure_loss_factor, 4),
            total_derate_factor=round(total_factor, 4),
            site_heat_rate_kj_kwh=round(site_heat_rate, 2),
            thermal_efficiency=round(thermal_efficiency, 4),
            fuel_heat_input_kw=round(fuel_heat_input, 2),
            exhaust_mass_flow_kg_s=round(exhaust_mass_flow, 3),
            exhaust_temperature_k=round(exhaust_temperature, 2),
            power_margin_ratio=(
                None if power_margin_ratio is None else round(power_margin_ratio, 4)
            ),
            power_warning=power_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (ISO 3977 / GL1029 style).",
                "Ambient derate is a linear ~0.7%/K above the 288.15 K ISO reference.",
                "Altitude derate is linear in elevation from reduced barometric pressure.",
                "Inlet/exhaust losses derate power ~0.2%/mbar and ~0.1%/mbar.",
                "Exhaust mass flow uses a fixed specific-flow screening factor.",
                "Exhaust temperature is a typical fixed value adjusted by ambient only.",
                "Move to a validated gas-turbine model and qualified package review.",
            ),
        )

    @staticmethod
    def _power_warning(power_margin_ratio: Optional[float]) -> str:
        if power_margin_ratio is None:
            return "no-rating"
        if power_margin_ratio < 1.0:
            return "insufficient-power"
        if power_margin_ratio < 1.1:
            return "watch"
        return "ok"

    @staticmethod
    def _clamp_factor(value: float) -> float:
        if value < 0.0:
            return 0.0
        return value

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

    @classmethod
    def _require_unit_interval(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval [0, 1]")
