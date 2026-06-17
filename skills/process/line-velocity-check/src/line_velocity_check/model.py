from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt


@dataclass(frozen=True)
class LineVelocityResult:
    erosional_velocity_m_per_s: float
    velocity_ratio: float
    guideline_ratio: float
    operating_indicator: float
    velocity_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class LineVelocityModel:
    """Educational process line velocity screening placeholder."""

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
        fluid_velocity: float,
        mixture_density: float,
        c_factor: float = 122.0,
        max_velocity_guideline: float = 20.0,
    ) -> LineVelocityResult:
        self._require_positive("fluid_velocity", fluid_velocity)
        self._require_positive("mixture_density", mixture_density)
        self._require_positive("c_factor", c_factor)
        self._require_positive("max_velocity_guideline", max_velocity_guideline)

        erosional_velocity = c_factor / sqrt(mixture_density)
        velocity_ratio = fluid_velocity / erosional_velocity
        guideline_ratio = fluid_velocity / max_velocity_guideline
        operating_indicator = max(velocity_ratio, guideline_ratio)
        velocity_warning = self._velocity_warning(operating_indicator)

        return LineVelocityResult(
            erosional_velocity_m_per_s=round(erosional_velocity, 2),
            velocity_ratio=round(velocity_ratio, 4),
            guideline_ratio=round(guideline_ratio, 4),
            operating_indicator=round(operating_indicator, 4),
            velocity_warning=velocity_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Erosional velocity uses a public API RP 14E metric form Ve = C / sqrt(rho).",
                "The SI C constant default of 122 corresponds to a continuous-service C of 100.",
                "The recommended velocity guideline reflects NORSOK P-001 style upper velocity limits.",
                "Move to validated line sizing and qualified review for real piping design.",
            ),
        )

    def _velocity_warning(self, operating_indicator: float) -> str:
        if operating_indicator > self.high_threshold:
            return "high"
        if operating_indicator > self.watch_threshold:
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
