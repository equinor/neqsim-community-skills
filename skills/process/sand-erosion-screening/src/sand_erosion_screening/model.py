from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt


@dataclass(frozen=True)
class SandErosionResult:
    erosional_velocity_m_per_s: float
    velocity_ratio: float
    erosion_rate_mm_per_yr: float
    cumulative_erosion_mm: float
    usable_wall_mm: float
    remaining_wall_mm: float
    remaining_life_years: float | None
    erosion_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class SandErosionModel:
    """Educational sand-erosion and remaining-wall-life screening placeholder.

    Provides a transparent, screening-level estimate of solids (sand) erosion
    rate, cumulative wall loss over a design life, the remaining wall thickness,
    and a remaining-life indicator. It is intended for learning and workflow
    scaffolding only and uses a public, simplified screening form rather than the
    validated DNV RP O501 model.
    """

    # Transparent public screening coefficient (mm/yr per kg/day per (m/s)^2 per
    # m^-2). It is NOT a DNV RP O501 constant and exists only to make the
    # educational screening dimensionally consistent and order-of-magnitude
    # reasonable. Use the validated NeqSim ErosionPredictionCalculator for design.
    EROSION_SCREENING_COEFF: float = 1.0e-5

    def __init__(
        self,
        watch_remaining_life_fraction: float = 1.0,
        high_remaining_life_fraction: float = 0.5,
    ) -> None:
        self._require_positive(
            "watch_remaining_life_fraction", watch_remaining_life_fraction
        )
        self._require_positive(
            "high_remaining_life_fraction", high_remaining_life_fraction
        )
        if high_remaining_life_fraction >= watch_remaining_life_fraction:
            raise ValueError(
                "high_remaining_life_fraction must be below "
                "watch_remaining_life_fraction"
            )
        self.watch_remaining_life_fraction = watch_remaining_life_fraction
        self.high_remaining_life_fraction = high_remaining_life_fraction

    def evaluate(
        self,
        *,
        fluid_velocity: float,
        mixture_density: float,
        pipe_diameter: float,
        wall_thickness: float,
        sand_rate: float = 0.0,
        corrosion_allowance: float = 3.0,
        material_factor: float = 1.0,
        design_life_years: float = 25.0,
        c_factor: float = 122.0,
    ) -> SandErosionResult:
        self._require_positive("fluid_velocity", fluid_velocity)
        self._require_positive("mixture_density", mixture_density)
        self._require_positive("pipe_diameter", pipe_diameter)
        self._require_positive("wall_thickness", wall_thickness)
        self._require_non_negative("sand_rate", sand_rate)
        self._require_non_negative("corrosion_allowance", corrosion_allowance)
        self._require_positive("material_factor", material_factor)
        self._require_positive("design_life_years", design_life_years)
        self._require_positive("c_factor", c_factor)
        if corrosion_allowance >= wall_thickness:
            raise ValueError("corrosion_allowance must be below wall_thickness")

        erosional_velocity = c_factor / sqrt(mixture_density)
        velocity_ratio = fluid_velocity / erosional_velocity

        erosion_rate = (
            self.EROSION_SCREENING_COEFF
            * material_factor
            * sand_rate
            * fluid_velocity**2
            / pipe_diameter**2
        )

        usable_wall = wall_thickness - corrosion_allowance
        cumulative_erosion = erosion_rate * design_life_years
        remaining_wall = usable_wall - cumulative_erosion

        if erosion_rate > 0.0:
            remaining_life_years: float | None = usable_wall / erosion_rate
        else:
            remaining_life_years = None

        erosion_warning = self._erosion_warning(
            velocity_ratio=velocity_ratio,
            remaining_life_years=remaining_life_years,
            design_life_years=design_life_years,
        )

        return SandErosionResult(
            erosional_velocity_m_per_s=round(erosional_velocity, 2),
            velocity_ratio=round(velocity_ratio, 4),
            erosion_rate_mm_per_yr=round(erosion_rate, 4),
            cumulative_erosion_mm=round(cumulative_erosion, 3),
            usable_wall_mm=round(usable_wall, 3),
            remaining_wall_mm=round(remaining_wall, 3),
            remaining_life_years=(
                None
                if remaining_life_years is None
                else round(remaining_life_years, 2)
            ),
            erosion_warning=erosion_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Erosional velocity uses a public API RP 14E form Ve = C / sqrt(rho).",
                "The SI C constant default of 122 corresponds to a continuous-service C of 100.",
                "Sand erosion uses a transparent screening proportionality, not the DNV RP O501 model.",
                "Erosion rate scales with sand rate, velocity squared, and inverse diameter squared.",
                "Remaining life assumes a constant erosion rate and a fixed corrosion allowance.",
                "Move to the validated NeqSim ErosionPredictionCalculator (DNV RP O501) for design and sand-management decisions.",
            ),
        )

    def _erosion_warning(
        self,
        *,
        velocity_ratio: float,
        remaining_life_years: float | None,
        design_life_years: float,
    ) -> str:
        if remaining_life_years is None:
            life_band = "ok"
        elif remaining_life_years < self.high_remaining_life_fraction * design_life_years:
            life_band = "high"
        elif remaining_life_years < self.watch_remaining_life_fraction * design_life_years:
            life_band = "watch"
        else:
            life_band = "ok"

        if velocity_ratio > 1.0:
            velocity_band = "high"
        elif velocity_ratio > 0.8:
            velocity_band = "watch"
        else:
            velocity_band = "ok"

        order = {"ok": 0, "watch": 1, "high": 2}
        return life_band if order[life_band] >= order[velocity_band] else velocity_band

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
