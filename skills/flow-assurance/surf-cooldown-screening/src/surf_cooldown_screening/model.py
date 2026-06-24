from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, log


@dataclass(frozen=True)
class SurfCooldownResult:
    no_touch_time_hours: float
    target_temperature_c: float
    verdict: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class SurfCooldownModel:
    """Educational SURF flowline/riser cooldown and no-touch-time screening placeholder."""

    VERDICT_OK = "ok"
    VERDICT_MARGINAL = "marginal"
    VERDICT_CRITICAL = "critical"
    VERDICT_NO_HYDRATE_RISK = "no_hydrate_risk"

    def __init__(
        self,
        hydrate_margin: float = 3.0,
        required_no_touch_time: float | None = None,
    ) -> None:
        self._require_finite("hydrate_margin", hydrate_margin)
        if required_no_touch_time is not None:
            self._require_positive("required_no_touch_time", required_no_touch_time)
        self.hydrate_margin = hydrate_margin
        self.required_no_touch_time = required_no_touch_time

    @staticmethod
    def time_constant_from_lumped_mass(
        *,
        fluid_density: float,
        specific_heat: float,
        internal_diameter: float,
        overall_u_value: float,
    ) -> float:
        """Estimate a lumped exponential time constant in hours.

        Uses the public single-node relation ``tau = rho * cp * D / (4 * U)`` for a
        circular cross section, where the volume-to-surface ratio is ``D / 4``.
        """
        for name, value in (
            ("fluid_density", fluid_density),
            ("specific_heat", specific_heat),
            ("internal_diameter", internal_diameter),
            ("overall_u_value", overall_u_value),
        ):
            SurfCooldownModel._require_positive(name, value)
        tau_seconds = fluid_density * specific_heat * internal_diameter / (4.0 * overall_u_value)
        return tau_seconds / 3600.0

    def evaluate(
        self,
        *,
        initial_temperature: float,
        seabed_temperature: float,
        hydrate_equilibrium_temperature: float | None,
        time_constant_hours: float,
    ) -> SurfCooldownResult:
        self._require_finite("initial_temperature", initial_temperature)
        self._require_finite("seabed_temperature", seabed_temperature)
        self._require_positive("time_constant_hours", time_constant_hours)

        no_hydrate_risk = (
            hydrate_equilibrium_temperature is None
            or not isfinite(hydrate_equilibrium_temperature)
            or hydrate_equilibrium_temperature <= seabed_temperature
        )

        if no_hydrate_risk:
            return self._build_result(
                no_touch_time=float("inf"),
                target_temperature=seabed_temperature,
                verdict=self.VERDICT_NO_HYDRATE_RISK,
            )

        target_temperature = hydrate_equilibrium_temperature + self.hydrate_margin

        if initial_temperature <= target_temperature:
            no_touch_time = 0.0
        elif target_temperature <= seabed_temperature:
            no_touch_time = float("inf")
        else:
            ratio = (target_temperature - seabed_temperature) / (
                initial_temperature - seabed_temperature
            )
            no_touch_time = -time_constant_hours * log(ratio)

        return self._build_result(
            no_touch_time=no_touch_time,
            target_temperature=target_temperature,
            verdict=self._classify_verdict(no_touch_time),
        )

    def _classify_verdict(self, no_touch_time: float) -> str:
        if no_touch_time == float("inf"):
            return self.VERDICT_OK
        if self.required_no_touch_time is not None:
            if no_touch_time >= self.required_no_touch_time:
                return self.VERDICT_OK
            if no_touch_time >= 0.75 * self.required_no_touch_time:
                return self.VERDICT_MARGINAL
            return self.VERDICT_CRITICAL
        if no_touch_time >= 12.0:
            return self.VERDICT_OK
        if no_touch_time >= 6.0:
            return self.VERDICT_MARGINAL
        return self.VERDICT_CRITICAL

    def _build_result(
        self,
        *,
        no_touch_time: float,
        target_temperature: float,
        verdict: str,
    ) -> SurfCooldownResult:
        no_touch_rounded = (
            no_touch_time if no_touch_time == float("inf") else round(no_touch_time, 2)
        )
        return SurfCooldownResult(
            no_touch_time_hours=no_touch_rounded,
            target_temperature_c=round(target_temperature, 2),
            verdict=verdict,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Single-node lumped exponential cooldown T(t)=T_seabed+(T0-T_seabed)*exp(-t/tau).",
                "No-touch time is the time to reach the hydrate temperature plus the margin.",
                "The hydrate equilibrium temperature should come from a validated NeqSim hydrate calculation.",
                "The time constant should come from a validated lumped or distributed cooldown model.",
                "The hydrate margin and verdict bands are configurable public guidelines, not design rules.",
                "Move to validated NeqSim cooldown workflows and qualified flow assurance review.",
            ),
        )

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
