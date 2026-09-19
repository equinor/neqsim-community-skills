from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import exp, isfinite
from typing import Tuple

_HOURS_PER_YEAR = 8760.0


@dataclass(frozen=True)
class ReliabilityDataResult:
    mtbf_years: float
    mtbf_h: float
    unit_availability: float
    system_availability: float
    system_unavailability: float
    reliability_over_mission: float
    expected_failures: float
    availability_warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class ReliabilityDataModel:
    """Educational reliability/availability screening (ISO 14224 / OREDA style).

    Estimates MTBF, steady-state availability with simple parallel redundancy,
    mission reliability, and expected failures from a constant failure rate and
    a mean time to repair. Screening only.
    """

    def __init__(
        self,
        *,
        watch_availability: float = 0.99,
        low_availability: float = 0.95,
    ) -> None:
        self._require_fraction("watch_availability", watch_availability)
        self._require_fraction("low_availability", low_availability)
        if low_availability >= watch_availability:
            raise ValueError("low_availability must be less than watch_availability")
        self.watch_availability = watch_availability
        self.low_availability = low_availability

    def evaluate(
        self,
        *,
        failure_rate_per_year: float,
        mean_time_to_repair_h: float = 24.0,
        redundancy: int = 1,
        mission_time_years: float = 1.0,
        planned_downtime_h_per_year: float = 0.0,
    ) -> ReliabilityDataResult:
        self._require_positive("failure_rate_per_year", failure_rate_per_year)
        self._require_positive("mean_time_to_repair_h", mean_time_to_repair_h)
        self._require_positive_int("redundancy", redundancy)
        self._require_positive("mission_time_years", mission_time_years)
        self._require_planned_downtime("planned_downtime_h_per_year", planned_downtime_h_per_year)

        lam = failure_rate_per_year

        mtbf_years = 1.0 / lam
        mtbf_h = _HOURS_PER_YEAR / lam

        # Single-unit steady-state availability.
        unit_availability = mtbf_h / (mtbf_h + mean_time_to_repair_h)

        # Parallel redundancy from failures, plus additive planned downtime.
        unavailability_from_failures = (1.0 - unit_availability) ** redundancy
        planned_unavailability = planned_downtime_h_per_year / _HOURS_PER_YEAR
        system_unavailability = min(
            unavailability_from_failures + planned_unavailability, 1.0
        )
        system_availability = 1.0 - system_unavailability

        # Mission reliability.
        unit_reliability = exp(-lam * mission_time_years)
        system_reliability = 1.0 - (1.0 - unit_reliability) ** redundancy
        expected_failures = lam * mission_time_years

        availability_warning = self._availability_warning(system_availability)

        return ReliabilityDataResult(
            mtbf_years=round(mtbf_years, 4),
            mtbf_h=round(mtbf_h, 2),
            unit_availability=round(unit_availability, 6),
            system_availability=round(system_availability, 6),
            system_unavailability=round(system_unavailability, 6),
            reliability_over_mission=round(system_reliability, 6),
            expected_failures=round(expected_failures, 4),
            availability_warning=availability_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (ISO 14224 / OREDA style).",
                "Constant failure rate (exponential lifetime) is assumed.",
                "Parallel units are identical and independent (no common cause).",
                "Availability uses A = MTBF_h / (MTBF_h + MTTR).",
                "Planned downtime is added to unavailability and capped at 1.",
                "Move to a validated RAM analysis and qualified reliability dataset.",
            ),
        )

    def _availability_warning(self, system_availability: float) -> str:
        if system_availability < self.low_availability:
            return "low-availability"
        if system_availability < self.watch_availability:
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
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in the open interval (0, 1)")

    @staticmethod
    def _require_positive_int(name: str, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        if value < 1:
            raise ValueError(f"{name} must be at least 1")

    @classmethod
    def _require_planned_downtime(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0 or value >= _HOURS_PER_YEAR:
            raise ValueError(f"{name} must be in [0, 8760)")
