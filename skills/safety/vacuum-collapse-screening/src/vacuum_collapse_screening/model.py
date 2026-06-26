from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

STANDARD_ATMOSPHERE_BARA = 1.01325


@dataclass(frozen=True)
class VacuumCollapseResult:
    estimated_final_pressure_bara: float
    vacuum_depth_bar: float
    margin_to_rating_bar: float
    vacuum_present: bool
    exceeds_rating: bool
    verdict: str
    collapse_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class VacuumCollapseModel:
    """Educational vacuum-collapse (implosion) screening placeholder."""

    def __init__(self, watch_fraction: float = 0.5) -> None:
        if not 0.0 < watch_fraction <= 1.0:
            raise ValueError("watch_fraction must be in the interval (0.0, 1.0]")
        self.watch_fraction = watch_fraction

    def evaluate(
        self,
        *,
        initial_pressure: float,
        initial_temperature: float,
        cold_end_temperature: float,
        condensable_fraction: float = 0.0,
        external_pressure_rating: float = 0.0,
        atmospheric_pressure: float = STANDARD_ATMOSPHERE_BARA,
    ) -> VacuumCollapseResult:
        self._require_positive("initial_pressure", initial_pressure)
        self._require_finite("initial_temperature", initial_temperature)
        self._require_finite("cold_end_temperature", cold_end_temperature)
        self._require_finite("condensable_fraction", condensable_fraction)
        self._require_finite("external_pressure_rating", external_pressure_rating)
        self._require_positive("atmospheric_pressure", atmospheric_pressure)
        if external_pressure_rating < 0.0:
            raise ValueError("external_pressure_rating must not be negative")
        if not 0.0 <= condensable_fraction <= 1.0:
            raise ValueError("condensable_fraction must be between 0.0 and 1.0")
        if cold_end_temperature >= initial_temperature:
            raise ValueError("cold_end_temperature must be below initial_temperature")

        initial_temperature_k = initial_temperature + 273.15
        cold_end_temperature_k = cold_end_temperature + 273.15
        if cold_end_temperature_k <= 0.0:
            raise ValueError("cold_end_temperature must be above absolute zero")

        temperature_ratio = cold_end_temperature_k / initial_temperature_k
        remaining_vapour_fraction = 1.0 - condensable_fraction
        estimated_final_pressure = (
            initial_pressure * temperature_ratio * remaining_vapour_fraction
        )

        vacuum_depth = max(0.0, atmospheric_pressure - estimated_final_pressure)
        margin_to_rating = estimated_final_pressure - external_pressure_rating
        vacuum_present = estimated_final_pressure < atmospheric_pressure
        exceeds_rating = estimated_final_pressure < external_pressure_rating

        verdict = self._verdict(vacuum_present, exceeds_rating)
        collapse_warning = self._warning(
            vacuum_present, exceeds_rating, vacuum_depth, atmospheric_pressure
        )

        return VacuumCollapseResult(
            estimated_final_pressure_bara=round(estimated_final_pressure, 4),
            vacuum_depth_bar=round(vacuum_depth, 4),
            margin_to_rating_bar=round(margin_to_rating, 4),
            vacuum_present=vacuum_present,
            exceeds_rating=exceeds_rating,
            verdict=verdict,
            collapse_warning=collapse_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Rigid, blocked-in vessel held at constant volume during cooldown.",
                "Non-condensing pressure drop uses the ideal-gas relation P2 = P1 * (T2 / T1).",
                "Condensation is a linear vapour-fraction proxy, not a real-fluid flash.",
                "No make-up gas, vacuum relief, or shell buckling check is included.",
                "Move to the validated NeqSim VacuumCollapseAnalyzer for real vacuum design.",
            ),
        )

    @staticmethod
    def _verdict(vacuum_present: bool, exceeds_rating: bool) -> str:
        if not vacuum_present:
            return "no_vacuum"
        if exceeds_rating:
            return "vacuum_exceeds_rating"
        return "vacuum_within_rating"

    def _warning(
        self,
        vacuum_present: bool,
        exceeds_rating: bool,
        vacuum_depth: float,
        atmospheric_pressure: float,
    ) -> str:
        if exceeds_rating:
            return "high"
        if not vacuum_present:
            return "ok"
        if vacuum_depth >= self.watch_fraction * atmospheric_pressure:
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
