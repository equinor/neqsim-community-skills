from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, log10


@dataclass(frozen=True)
class PressureDropResult:
    reynolds_number: float
    friction_factor: float
    dp_per_100m_bar: float
    dp_total_bar: float
    guideline_ratio: float
    pressure_drop_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class PressureDropModel:
    """Educational single-phase line pressure-drop screening placeholder."""

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
        viscosity: float,
        pipe_inner_diameter: float,
        length: float = 100.0,
        roughness: float = 4.6e-5,
        guideline_bar_per_100m: float = 0.5,
    ) -> PressureDropResult:
        self._require_positive("fluid_velocity", fluid_velocity)
        self._require_positive("mixture_density", mixture_density)
        self._require_positive("viscosity", viscosity)
        self._require_positive("pipe_inner_diameter", pipe_inner_diameter)
        self._require_positive("length", length)
        self._require_positive("roughness", roughness)
        self._require_positive("guideline_bar_per_100m", guideline_bar_per_100m)

        reynolds = mixture_density * fluid_velocity * pipe_inner_diameter / viscosity
        friction_factor = self._friction_factor(
            reynolds, roughness / pipe_inner_diameter
        )

        dp_per_m_pa = (
            friction_factor
            * (1.0 / pipe_inner_diameter)
            * (mixture_density * fluid_velocity * fluid_velocity / 2.0)
        )
        dp_per_100m_bar = dp_per_m_pa * 100.0 / 1.0e5
        dp_total_bar = dp_per_m_pa * length / 1.0e5
        guideline_ratio = dp_per_100m_bar / guideline_bar_per_100m
        pressure_drop_warning = self._warning(guideline_ratio)

        return PressureDropResult(
            reynolds_number=round(reynolds, 1),
            friction_factor=round(friction_factor, 5),
            dp_per_100m_bar=round(dp_per_100m_bar, 4),
            dp_total_bar=round(dp_total_bar, 4),
            guideline_ratio=round(guideline_ratio, 4),
            pressure_drop_warning=pressure_drop_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Reynolds number uses the standard Re = rho v D / mu form.",
                "Friction factor uses f = 64 / Re in laminar flow and the public Haaland "
                "approximation of the Colebrook equation in turbulent flow.",
                "Pressure gradient uses the Darcy-Weisbach form dP/L = f (1/D) (rho v^2 / 2).",
                "Guideline gradient reflects NORSOK P-002 and GPSA style line pressure-gradient limits.",
                "No two-phase, fittings, elevation, or acceleration losses are included.",
                "Move to validated NeqSim hydraulics (for example PipeBeggsAndBrills) and qualified review.",
            ),
        )

    def _friction_factor(self, reynolds: float, relative_roughness: float) -> float:
        if reynolds < 2000.0:
            return 64.0 / reynolds
        # Public Haaland explicit approximation of the Colebrook equation.
        term = (relative_roughness / 3.7) ** 1.11 + 6.9 / reynolds
        inv_sqrt_f = -1.8 * log10(term)
        return 1.0 / (inv_sqrt_f * inv_sqrt_f)

    def _warning(self, guideline_ratio: float) -> str:
        if guideline_ratio > self.high_threshold:
            return "high"
        if guideline_ratio > self.watch_threshold:
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
