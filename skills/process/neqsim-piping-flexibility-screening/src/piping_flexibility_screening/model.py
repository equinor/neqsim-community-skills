from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Optional, Tuple


@dataclass(frozen=True)
class PipingFlexibilityResult:
    hoop_stress_mpa: float
    hoop_stress_ratio: float
    delta_temperature_k: float
    free_thermal_expansion_mm: float
    displacement_stress_mpa: float
    allowable_stress_range_mpa: float
    displacement_stress_ratio: float
    flange_pressure_ratio: Optional[float]
    stress_warning: str
    flange_warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class PipingFlexibilityModel:
    """Educational piping-flexibility screening (ASME B31.3 / B16.5 style).

    Estimates hoop (sustained) stress, free thermal expansion, displacement
    (expansion) stress range, an allowable stress range, and a flange-rating
    pressure check using open relations. Screening only.
    """

    def __init__(
        self,
        *,
        stress_range_factor: float = 1.5,
        restrained_relief_factor: float = 0.5,
    ) -> None:
        self._require_positive("stress_range_factor", stress_range_factor)
        self._require_fraction_inclusive("restrained_relief_factor", restrained_relief_factor)
        self.stress_range_factor = stress_range_factor
        self.restrained_relief_factor = restrained_relief_factor

    def evaluate(
        self,
        *,
        outside_diameter_mm: float,
        wall_thickness_mm: float,
        design_pressure_bar: float,
        design_temperature_c: float,
        pipe_length_m: float,
        install_temperature_c: float = 20.0,
        anchor_to_anchor: bool = True,
        youngs_modulus_mpa: float = 200000.0,
        thermal_expansion_coeff_per_k: float = 1.2e-5,
        allowable_stress_mpa: float = 138.0,
        flange_rating_class: Optional[int] = None,
        flange_allowable_pressure_bar: Optional[float] = None,
    ) -> PipingFlexibilityResult:
        self._require_positive("outside_diameter_mm", outside_diameter_mm)
        self._require_positive("wall_thickness_mm", wall_thickness_mm)
        if wall_thickness_mm >= outside_diameter_mm / 2.0:
            raise ValueError("wall_thickness_mm must be less than half the outside diameter")
        self._require_positive("design_pressure_bar", design_pressure_bar)
        self._require_finite("design_temperature_c", design_temperature_c)
        self._require_positive("pipe_length_m", pipe_length_m)
        self._require_finite("install_temperature_c", install_temperature_c)
        self._require_positive("youngs_modulus_mpa", youngs_modulus_mpa)
        self._require_positive("thermal_expansion_coeff_per_k", thermal_expansion_coeff_per_k)
        self._require_positive("allowable_stress_mpa", allowable_stress_mpa)
        if flange_rating_class is not None and flange_rating_class <= 0:
            raise ValueError("flange_rating_class must be positive")
        if flange_allowable_pressure_bar is not None:
            self._require_positive("flange_allowable_pressure_bar", flange_allowable_pressure_bar)

        # Hoop (sustained) stress via Barlow: S = P D / (2 t).
        pressure_mpa = design_pressure_bar * 0.1
        hoop_stress = pressure_mpa * outside_diameter_mm / (2.0 * wall_thickness_mm)
        hoop_stress_ratio = hoop_stress / allowable_stress_mpa

        # Thermal expansion and displacement (expansion) stress range.
        delta_t = design_temperature_c - install_temperature_c
        abs_delta_t = abs(delta_t)
        thermal_strain = thermal_expansion_coeff_per_k * abs_delta_t
        free_expansion_mm = thermal_strain * pipe_length_m * 1000.0

        # Fully restrained worst case: SE = E alpha dT; a routed loop relieves it.
        restrained_stress = youngs_modulus_mpa * thermal_strain
        if anchor_to_anchor:
            displacement_stress = restrained_stress
        else:
            displacement_stress = self.restrained_relief_factor * restrained_stress

        # Simplified allowable stress range SA = factor * allowable.
        allowable_stress_range = self.stress_range_factor * allowable_stress_mpa
        displacement_stress_ratio = displacement_stress / allowable_stress_range

        flange_pressure_ratio: Optional[float] = None
        if flange_allowable_pressure_bar is not None:
            flange_pressure_ratio = design_pressure_bar / flange_allowable_pressure_bar

        stress_warning = self._stress_warning(hoop_stress_ratio, displacement_stress_ratio)
        flange_warning = self._flange_warning(
            design_pressure_bar, flange_allowable_pressure_bar
        )

        return PipingFlexibilityResult(
            hoop_stress_mpa=round(hoop_stress, 3),
            hoop_stress_ratio=round(hoop_stress_ratio, 4),
            delta_temperature_k=round(delta_t, 3),
            free_thermal_expansion_mm=round(free_expansion_mm, 3),
            displacement_stress_mpa=round(displacement_stress, 3),
            allowable_stress_range_mpa=round(allowable_stress_range, 3),
            displacement_stress_ratio=round(displacement_stress_ratio, 4),
            flange_pressure_ratio=(
                None if flange_pressure_ratio is None else round(flange_pressure_ratio, 4)
            ),
            stress_warning=stress_warning,
            flange_warning=flange_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (ASME B31.3 / B16.5 style).",
                "Hoop stress uses the thin-wall Barlow relation S = P D / (2 t).",
                "Displacement stress uses the fully restrained worst case SE = E alpha dT.",
                "A non-anchor-to-anchor routing applies a fixed flexibility relief factor.",
                "Allowable stress range is a simplified multiple of the allowable stress.",
                "Flange check compares design pressure to a supplied allowable pressure only.",
                "Move to a validated pipe-stress/flexibility model and qualified review.",
            ),
        )

    def _stress_warning(
        self, hoop_stress_ratio: float, displacement_stress_ratio: float
    ) -> str:
        if hoop_stress_ratio > 1.0:
            return "hoop-stress-exceeded"
        if displacement_stress_ratio > 1.0:
            return "expansion-stress-exceeded"
        if hoop_stress_ratio > 0.9 or displacement_stress_ratio > 0.9:
            return "watch"
        return "ok"

    @staticmethod
    def _flange_warning(
        design_pressure_bar: float, flange_allowable_pressure_bar: Optional[float]
    ) -> str:
        if flange_allowable_pressure_bar is None:
            return "no-rating"
        if design_pressure_bar > flange_allowable_pressure_bar:
            return "flange-overpressure"
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
    def _require_fraction_inclusive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval [0, 1]")
