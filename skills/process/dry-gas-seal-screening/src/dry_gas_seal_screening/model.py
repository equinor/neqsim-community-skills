from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class DryGasSealResult:
    total_seal_gas_supply_nl_per_min: float
    separation_gas_supply_nl_per_min: float
    seal_gas_supply_margin_ratio: float
    condensation_margin_c: float
    condensation_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class DryGasSealModel:
    """Educational dry gas seal supply and condensation screening placeholder."""

    def __init__(
        self,
        watch_margin_c: float = 8.0,
        high_margin_c: float = 3.0,
    ) -> None:
        self._require_positive("watch_margin_c", watch_margin_c)
        self._require_positive("high_margin_c", high_margin_c)
        if high_margin_c >= watch_margin_c:
            raise ValueError("high_margin_c must be below watch_margin_c")
        self.watch_margin_c = watch_margin_c
        self.high_margin_c = high_margin_c

    def evaluate(
        self,
        *,
        seal_leakage_rate_nl_per_min: float,
        seal_cavity_temperature_c: float,
        hydrocarbon_dew_point_c: float,
        seal_count: int = 2,
        supply_margin: float = 1.25,
        separation_gas_rate_nl_per_min: float = 0.0,
    ) -> DryGasSealResult:
        self._require_positive(
            "seal_leakage_rate_nl_per_min", seal_leakage_rate_nl_per_min
        )
        self._require_finite("seal_cavity_temperature_c", seal_cavity_temperature_c)
        self._require_finite("hydrocarbon_dew_point_c", hydrocarbon_dew_point_c)
        self._require_positive_int("seal_count", seal_count)
        self._require_at_least("supply_margin", supply_margin, 1.0)
        self._require_non_negative(
            "separation_gas_rate_nl_per_min", separation_gas_rate_nl_per_min
        )

        total_seal_gas_supply = (
            seal_leakage_rate_nl_per_min * seal_count * supply_margin
        )
        separation_gas_supply = separation_gas_rate_nl_per_min * seal_count
        condensation_margin = seal_cavity_temperature_c - hydrocarbon_dew_point_c
        condensation_warning = self._condensation_warning(condensation_margin)

        return DryGasSealResult(
            total_seal_gas_supply_nl_per_min=round(total_seal_gas_supply, 2),
            separation_gas_supply_nl_per_min=round(separation_gas_supply, 2),
            seal_gas_supply_margin_ratio=round(supply_margin, 4),
            condensation_margin_c=round(condensation_margin, 3),
            condensation_warning=condensation_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Seal gas supply demand is leakage x seal count x a supply margin.",
                "Separation (secondary) gas supply scales with the seal count.",
                "Condensation margin is seal cavity temperature minus the "
                "hydrocarbon dew point at the seal/vent reference condition.",
                "A small or negative condensation margin flags retrograde "
                "condensation risk per API 692 seal-gas conditioning intent.",
                "Move to validated NeqSim dry gas seal analysis and qualified "
                "rotating-equipment review for real seal system design.",
            ),
        )

    def _condensation_warning(self, condensation_margin_c: float) -> str:
        if condensation_margin_c <= self.high_margin_c:
            return "high"
        if condensation_margin_c <= self.watch_margin_c:
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
            raise ValueError(f"{name} must not be negative")

    @classmethod
    def _require_at_least(cls, name: str, value: float, minimum: float) -> None:
        cls._require_finite(name, value)
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")

    @staticmethod
    def _require_positive_int(name: str, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        if value <= 0:
            raise ValueError(f"{name} must be a positive integer")
