from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import exp, isfinite, pi, sqrt

_R = 8.314  # J/(mol K)
_STABILITY_CLASSES = ("A", "B", "C", "D", "E", "F")


@dataclass(frozen=True)
class GaussianDispersionResult:
    stability_class: str
    target_concentration_kg_m3: float
    hazard_distance_m: float | None
    peak_concentration_kg_m3: float
    dispersion_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class GaussianDispersionModel:
    """Educational Gaussian point-source dispersion-distance screening placeholder.

    Estimates the downwind centerline distance at which a continuous gas release
    falls to a target concentration using the public Pasquill-Gifford / Briggs
    rural (open-country) dispersion model.
    """

    def __init__(
        self,
        max_distance: float = 10000.0,
        assessment_distance: float | None = None,
    ) -> None:
        self._require_positive("max_distance", max_distance)
        if assessment_distance is not None:
            self._require_positive("assessment_distance", assessment_distance)
        self.max_distance = max_distance
        self.assessment_distance = assessment_distance

    def evaluate(
        self,
        *,
        release_rate: float,
        wind_speed: float,
        stability_class: str,
        target_concentration: float,
        release_height: float = 0.0,
    ) -> GaussianDispersionResult:
        self._require_positive("release_rate", release_rate)
        self._require_positive("wind_speed", wind_speed)
        self._require_positive("target_concentration", target_concentration)
        self._require_finite("release_height", release_height)
        if release_height < 0.0:
            raise ValueError("release_height must not be negative")
        stab = stability_class.strip().upper()
        if stab not in _STABILITY_CLASSES:
            raise ValueError("stability_class must be one of A, B, C, D, E, F")

        peak = 0.0
        hazard_distance: float | None = None
        # Logarithmic scan of downwind distance; record the farthest point that
        # still exceeds the target (the downwind hazard extent).
        steps = 600
        x = 1.0
        ratio = (self.max_distance / x) ** (1.0 / steps)
        for _ in range(steps + 1):
            conc = self._concentration(
                release_rate, wind_speed, stab, x, release_height
            )
            if conc > peak:
                peak = conc
            if conc >= target_concentration:
                hazard_distance = x
            x *= ratio

        warning = self._warning(hazard_distance)

        return GaussianDispersionResult(
            stability_class=stab,
            target_concentration_kg_m3=round(target_concentration, 8),
            hazard_distance_m=(None if hazard_distance is None else round(hazard_distance, 1)),
            peak_concentration_kg_m3=round(peak, 8),
            dispersion_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Continuous Gaussian point source with Briggs rural sigma curves.",
                "Ground-level centerline concentration with a reflection term.",
                "Constant wind speed, flat open terrain, neutral buoyancy, no deposition.",
                "Hazard distance is the farthest downwind point at or above the target.",
                "Move to validated NeqSim dispersion scenarios and qualified review.",
            ),
        )

    def _concentration(
        self,
        q: float,
        u: float,
        stab: str,
        x: float,
        he: float,
    ) -> float:
        sigma_y, sigma_z = self._briggs_sigma(stab, x)
        if sigma_y <= 0.0 or sigma_z <= 0.0:
            return 0.0
        reflection = exp(-(he * he) / (2.0 * sigma_z * sigma_z))
        return q / (pi * u * sigma_y * sigma_z) * reflection

    @staticmethod
    def _briggs_sigma(stab: str, x: float) -> tuple[float, float]:
        # Briggs (1973) open-country dispersion coefficients, x in metres.
        inv = 1.0 / sqrt(1.0 + 0.0001 * x)
        if stab == "A":
            sy = 0.22 * x * inv
            sz = 0.20 * x
        elif stab == "B":
            sy = 0.16 * x * inv
            sz = 0.12 * x
        elif stab == "C":
            sy = 0.11 * x * inv
            sz = 0.08 * x / sqrt(1.0 + 0.0002 * x)
        elif stab == "D":
            sy = 0.08 * x * inv
            sz = 0.06 * x / sqrt(1.0 + 0.0015 * x)
        elif stab == "E":
            sy = 0.06 * x * inv
            sz = 0.03 * x / (1.0 + 0.0003 * x)
        else:  # F
            sy = 0.04 * x * inv
            sz = 0.016 * x / (1.0 + 0.0003 * x)
        return sy, sz

    def _warning(self, hazard_distance: float | None) -> str:
        if hazard_distance is None:
            return "no-hazard-distance"
        if (
            self.assessment_distance is not None
            and hazard_distance > self.assessment_distance
        ):
            return "beyond-assessment-distance"
        return "hazard-zone"

    @classmethod
    def concentration_from_volume_fraction(
        cls,
        *,
        volume_fraction: float,
        molar_mass: float,
        temperature_k: float = 288.15,
        pressure_bara: float = 1.01325,
    ) -> float:
        """Convert a gas volume (mole) fraction to a mass concentration in kg/m3.

        Uses the ideal-gas law for the ambient mixture density.
        """
        cls._require_fraction("volume_fraction", volume_fraction)
        cls._require_positive("molar_mass", molar_mass)
        cls._require_positive("temperature_k", temperature_k)
        cls._require_positive("pressure_bara", pressure_bara)
        molar_density = (pressure_bara * 1.0e5) / (_R * temperature_k)  # mol/m3
        return volume_fraction * molar_density * (molar_mass / 1000.0)

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
        if value <= 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1]")
