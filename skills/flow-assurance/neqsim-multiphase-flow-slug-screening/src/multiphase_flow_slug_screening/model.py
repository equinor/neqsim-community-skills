from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, pi, sqrt

GRAVITY_M_PER_S2 = 9.80665


@dataclass(frozen=True)
class SlugScreeningResult:
    mixture_velocity_m_per_s: float
    froude_number: float
    liquid_fraction: float
    flow_regime_indicator: str
    estimated_slug_volume_m3: float
    recommended_slug_catcher_volume_m3: float
    capacity_ratio: float | None
    slug_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class SlugScreeningModel:
    """Educational multiphase slug-flow and slug-catcher screening placeholder."""

    def __init__(
        self,
        watch_threshold: float = 0.8,
        high_threshold: float = 1.0,
    ) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self._require_positive("high_threshold", high_threshold)
        if watch_threshold >= high_threshold:
            raise ValueError("watch_threshold must be below high_threshold")
        self.watch_threshold = watch_threshold
        self.high_threshold = high_threshold

    def evaluate(
        self,
        *,
        superficial_gas_velocity: float,
        superficial_liquid_velocity: float,
        pipe_internal_diameter: float,
        slug_length_to_diameter: float = 30.0,
        liquid_holdup_in_slug: float = 0.8,
        surge_factor: float = 1.2,
        available_slug_catcher_volume: float | None = None,
    ) -> SlugScreeningResult:
        self._require_positive(
            "superficial_gas_velocity", superficial_gas_velocity
        )
        self._require_positive(
            "superficial_liquid_velocity", superficial_liquid_velocity
        )
        self._require_positive("pipe_internal_diameter", pipe_internal_diameter)
        self._require_positive(
            "slug_length_to_diameter", slug_length_to_diameter
        )
        self._require_fraction("liquid_holdup_in_slug", liquid_holdup_in_slug)
        self._require_at_least("surge_factor", surge_factor, 1.0)
        if available_slug_catcher_volume is not None:
            self._require_positive(
                "available_slug_catcher_volume", available_slug_catcher_volume
            )

        mixture_velocity = (
            superficial_gas_velocity + superficial_liquid_velocity
        )
        froude_number = mixture_velocity / sqrt(
            GRAVITY_M_PER_S2 * pipe_internal_diameter
        )
        liquid_fraction = superficial_liquid_velocity / mixture_velocity
        flow_regime_indicator = self._flow_regime_indicator(
            froude_number, liquid_fraction
        )

        pipe_area = pi * pipe_internal_diameter**2 / 4.0
        slug_length = slug_length_to_diameter * pipe_internal_diameter
        estimated_slug_volume = (
            slug_length * pipe_area * liquid_holdup_in_slug
        )
        recommended_slug_catcher_volume = estimated_slug_volume * surge_factor

        capacity_ratio: float | None = None
        if available_slug_catcher_volume is not None:
            capacity_ratio = (
                recommended_slug_catcher_volume / available_slug_catcher_volume
            )

        slug_warning = self._slug_warning(
            flow_regime_indicator, capacity_ratio
        )

        return SlugScreeningResult(
            mixture_velocity_m_per_s=round(mixture_velocity, 3),
            froude_number=round(froude_number, 3),
            liquid_fraction=round(liquid_fraction, 4),
            flow_regime_indicator=flow_regime_indicator,
            estimated_slug_volume_m3=round(estimated_slug_volume, 4),
            recommended_slug_catcher_volume_m3=round(
                recommended_slug_catcher_volume, 4
            ),
            capacity_ratio=(
                None if capacity_ratio is None else round(capacity_ratio, 4)
            ),
            slug_warning=slug_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Mixture velocity is the sum of the superficial gas and liquid "
                "velocities.",
                "The Froude number uses the pipe inside diameter as the length "
                "scale.",
                "The flow regime indicator is a coarse public heuristic, not a "
                "validated flow-pattern map.",
                "Slug volume is slug length x pipe area x liquid holdup, with a "
                "surge factor for the recommended slug-catcher volume.",
                "Move to validated NeqSim multiphase pipe flow and qualified "
                "flow-assurance review for real slug-catcher sizing.",
            ),
        )

    def _flow_regime_indicator(
        self, froude_number: float, liquid_fraction: float
    ) -> str:
        if liquid_fraction < 0.01:
            return "stratified/annular (gas-dominated)"
        if liquid_fraction > 0.9:
            return "bubble/dispersed (liquid-dominated)"
        if froude_number > 3.5:
            return "intermittent/slug (screening)"
        return "transition"

    def _slug_warning(
        self, flow_regime_indicator: str, capacity_ratio: float | None
    ) -> str:
        if capacity_ratio is not None:
            if capacity_ratio > self.high_threshold:
                return "high"
            if capacity_ratio > self.watch_threshold:
                return "watch"
            return "ok"
        if "slug" in flow_regime_indicator:
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
        if not 0.0 < value <= 1.0:
            raise ValueError(f"{name} must be within (0, 1]")

    @classmethod
    def _require_at_least(cls, name: str, value: float, minimum: float) -> None:
        cls._require_finite(name, value)
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
