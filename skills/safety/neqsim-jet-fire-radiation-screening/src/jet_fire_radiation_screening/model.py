from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, pi, sqrt


@dataclass(frozen=True)
class JetFireRadiationResult:
    total_radiative_power_kw: float
    radiation_flux_kw_m2: float | None
    distance_to_target_m: float | None
    radiation_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class JetFireRadiationModel:
    """Educational jet-fire thermal-radiation screening placeholder.

    Uses the public single-point-source flame radiation model to estimate the
    radiative flux at a distance, or the distance to a target flux.
    """

    # Public radiation-flux acceptance thresholds (kW/m2).
    _SEVERE_LIMIT = 37.5

    def __init__(
        self,
        personnel_limit: float = 4.7,
        equipment_limit: float = 12.5,
    ) -> None:
        self._require_positive("personnel_limit", personnel_limit)
        self._require_positive("equipment_limit", equipment_limit)
        self.personnel_limit = personnel_limit
        self.equipment_limit = equipment_limit

    def evaluate(
        self,
        *,
        release_rate: float,
        heat_of_combustion: float = 50.0e6,
        radiant_fraction: float = 0.2,
        transmissivity: float = 1.0,
        distance: float | None = None,
        target_flux: float | None = None,
    ) -> JetFireRadiationResult:
        self._require_positive("release_rate", release_rate)
        self._require_positive("heat_of_combustion", heat_of_combustion)
        self._require_fraction("radiant_fraction", radiant_fraction)
        self._require_fraction("transmissivity", transmissivity)
        if distance is not None:
            self._require_positive("distance", distance)
        if target_flux is not None:
            self._require_positive("target_flux", target_flux)

        # Radiative power emitted from the flame (W -> kW).
        radiative_power_w = transmissivity * radiant_fraction * release_rate * heat_of_combustion
        total_radiative_power_kw = radiative_power_w / 1000.0

        radiation_flux_kw_m2: float | None = None
        if distance is not None:
            flux_w_m2 = radiative_power_w / (4.0 * pi * distance * distance)
            radiation_flux_kw_m2 = flux_w_m2 / 1000.0

        distance_to_target_m: float | None = None
        if target_flux is not None:
            target_flux_w_m2 = target_flux * 1000.0
            distance_to_target_m = sqrt(radiative_power_w / (4.0 * pi * target_flux_w_m2))

        warning = self._warning(radiation_flux_kw_m2)

        return JetFireRadiationResult(
            total_radiative_power_kw=round(total_radiative_power_kw, 3),
            radiation_flux_kw_m2=(
                None if radiation_flux_kw_m2 is None else round(radiation_flux_kw_m2, 4)
            ),
            distance_to_target_m=(
                None if distance_to_target_m is None else round(distance_to_target_m, 2)
            ),
            radiation_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Single point-source flame radiation: q = tau * Xr * mdot * Hc / (4 pi r^2).",
                "Full combustion of the released mass at the given heat of combustion.",
                "Isotropic emission, no view-factor, flame shape, or wind tilt.",
                "Thresholds: personnel and equipment limits plus a 37.5 kW/m2 severe limit.",
                "Move to validated NeqSim JetFireModel and qualified review.",
            ),
        )

    def _warning(self, radiation_flux_kw_m2: float | None) -> str:
        if radiation_flux_kw_m2 is None:
            return "no-distance"
        if radiation_flux_kw_m2 > self._SEVERE_LIMIT:
            return "severe"
        if radiation_flux_kw_m2 > self.equipment_limit:
            return "high"
        if radiation_flux_kw_m2 > self.personnel_limit:
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
        if value <= 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1]")
