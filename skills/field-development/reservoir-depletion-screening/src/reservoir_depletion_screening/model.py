from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

_VALID_FLUIDS = ("gas", "oil")


@dataclass(frozen=True)
class DepletionStep:
    year: float
    pressure_bara: float
    cumulative_production_sm3: float
    recovery_factor: float
    water_cut_fraction: float
    hydrocarbon_rate_sm3_per_day: float
    water_rate_sm3_per_day: float
    depleted: bool


@dataclass(frozen=True)
class ReservoirDepletionResult:
    fluid_type: str
    initial_pressure_bara: float
    abandonment_pressure_bara: float
    recoverable_volume_sm3: float
    years_simulated: float
    final_pressure_bara: float
    final_recovery_factor: float
    plateau_years: float | None
    years_to_abandonment: float | None
    depletion_warning: str
    steps: tuple[DepletionStep, ...]
    neqsim_available: bool
    assumptions: tuple[str, ...]


class ReservoirDepletionModel:
    """Educational reservoir tank-depletion screening placeholder.

    Models reservoir pressure and gas/oil/water production as a simple
    function of time using a linear material-balance screening. It is a
    transparent placeholder only: real depletion behaviour must come from a
    validated NeqSim ``SimpleReservoir`` (``runTransient``) tank model or the
    NeqSim MCP ``runReservoir`` workflow.
    """

    def __init__(self, *, watch_recovery_factor: float = 0.8) -> None:
        if not (0.0 < watch_recovery_factor < 1.0):
            raise ValueError("watch_recovery_factor must be between 0 and 1")
        self.watch_recovery_factor = watch_recovery_factor

    def evaluate(
        self,
        *,
        fluid_type: str,
        initial_pressure_bara: float,
        abandonment_pressure_bara: float,
        recoverable_volume_sm3: float,
        offtake_rate_sm3_per_day: float,
        years: float,
        time_step_years: float = 1.0,
        initial_water_cut_fraction: float = 0.0,
        water_cut_rise_per_year: float = 0.0,
    ) -> ReservoirDepletionResult:
        fluid = self._normalize_fluid(fluid_type)
        self._require_positive("initial_pressure_bara", initial_pressure_bara)
        self._require_non_negative(
            "abandonment_pressure_bara", abandonment_pressure_bara
        )
        if abandonment_pressure_bara >= initial_pressure_bara:
            raise ValueError(
                "abandonment_pressure_bara must be below initial_pressure_bara"
            )
        self._require_positive("recoverable_volume_sm3", recoverable_volume_sm3)
        self._require_positive("offtake_rate_sm3_per_day", offtake_rate_sm3_per_day)
        self._require_positive("years", years)
        self._require_positive("time_step_years", time_step_years)
        self._require_fraction("initial_water_cut_fraction", initial_water_cut_fraction)
        self._require_finite("water_cut_rise_per_year", water_cut_rise_per_year)
        if water_cut_rise_per_year < 0.0:
            raise ValueError("water_cut_rise_per_year must be non-negative")

        pressure_span = initial_pressure_bara - abandonment_pressure_bara
        days_per_step = 365.0 * time_step_years

        steps: list[DepletionStep] = []
        cumulative = 0.0
        plateau_years: float | None = None
        years_to_abandonment: float | None = None
        depleted = False

        n_steps = int(round(years / time_step_years))
        for index in range(1, n_steps + 1):
            year = round(index * time_step_years, 6)

            if not depleted:
                cumulative += offtake_rate_sm3_per_day * days_per_step
            cumulative = min(cumulative, recoverable_volume_sm3)

            recovery_factor = cumulative / recoverable_volume_sm3
            pressure = initial_pressure_bara - pressure_span * recovery_factor
            pressure = max(pressure, abandonment_pressure_bara)

            water_cut = self._clamp_fraction(
                initial_water_cut_fraction + water_cut_rise_per_year * year
            )

            if pressure <= abandonment_pressure_bara or recovery_factor >= 1.0:
                step_depleted = True
                if years_to_abandonment is None:
                    years_to_abandonment = year
            else:
                step_depleted = False

            hydrocarbon_rate = 0.0 if step_depleted else offtake_rate_sm3_per_day
            water_rate = (
                0.0
                if step_depleted
                else offtake_rate_sm3_per_day
                * self._water_to_hydrocarbon_ratio(water_cut)
            )

            if step_depleted and not depleted:
                depleted = True

            if plateau_years is None and step_depleted:
                plateau_years = round(year - time_step_years, 6)

            steps.append(
                DepletionStep(
                    year=year,
                    pressure_bara=round(pressure, 3),
                    cumulative_production_sm3=round(cumulative, 3),
                    recovery_factor=round(recovery_factor, 5),
                    water_cut_fraction=round(water_cut, 5),
                    hydrocarbon_rate_sm3_per_day=round(hydrocarbon_rate, 3),
                    water_rate_sm3_per_day=round(water_rate, 3),
                    depleted=step_depleted,
                )
            )

        final = steps[-1]
        warning = self._depletion_warning(final.recovery_factor, depleted)

        return ReservoirDepletionResult(
            fluid_type=fluid,
            initial_pressure_bara=round(initial_pressure_bara, 3),
            abandonment_pressure_bara=round(abandonment_pressure_bara, 3),
            recoverable_volume_sm3=round(recoverable_volume_sm3, 3),
            years_simulated=round(n_steps * time_step_years, 6),
            final_pressure_bara=final.pressure_bara,
            final_recovery_factor=final.recovery_factor,
            plateau_years=plateau_years,
            years_to_abandonment=years_to_abandonment,
            depletion_warning=warning,
            steps=tuple(steps),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational reservoir tank-depletion screening placeholder only.",
                "Pressure declines linearly with recovery factor (constant-property screening).",
                "No PVT, aquifer, injection, or coning physics is modelled.",
                "Water cut follows a supplied linear screening trend, not a saturation model.",
                "Recoverable volume and offtake rate are user inputs, not a reservoir estimate.",
                "Use NeqSim SimpleReservoir (runTransient) or MCP runReservoir for real depletion.",
            ),
        )

    @staticmethod
    def _water_to_hydrocarbon_ratio(water_cut: float) -> float:
        if water_cut >= 1.0:
            return float("inf")
        return water_cut / (1.0 - water_cut)

    def _depletion_warning(self, recovery_factor: float, depleted: bool) -> str:
        if depleted:
            return "high"
        if recovery_factor >= self.watch_recovery_factor:
            return "watch"
        return "ok"

    @staticmethod
    def _clamp_fraction(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _normalize_fluid(fluid_type: str) -> str:
        fluid = str(fluid_type).strip().lower()
        if fluid not in _VALID_FLUIDS:
            raise ValueError(
                f"fluid_type must be one of {_VALID_FLUIDS}, got {fluid_type!r}"
            )
        return fluid

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
    def _require_fraction(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be between 0 and 1")
