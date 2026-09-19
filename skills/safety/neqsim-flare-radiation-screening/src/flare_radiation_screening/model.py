from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, pi


@dataclass(frozen=True)
class FlareRadiationResult:
    total_heat_release_kw: float
    radiant_heat_flux_kw_m2: float
    allowable_flux_kw_m2: float
    flux_ratio: float
    radiation_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class FlareRadiationModel:
    """Educational API 521 / API 537 point-source flare radiation screening placeholder."""

    def __init__(
        self,
        watch_threshold: float = 0.8,
        high_threshold: float = 1.0,
    ) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self._require_positive("high_threshold", high_threshold)
        if high_threshold <= watch_threshold:
            raise ValueError("high_threshold must be above watch_threshold")
        self.watch_threshold = watch_threshold
        self.high_threshold = high_threshold

    def evaluate(
        self,
        *,
        mass_flow: float,
        heat_of_combustion: float,
        distance: float,
        fraction_radiated: float = 0.2,
        transmissivity: float = 1.0,
        allowable_flux: float = 6.31,
    ) -> FlareRadiationResult:
        self._require_positive("mass_flow", mass_flow)
        self._require_positive("heat_of_combustion", heat_of_combustion)
        self._require_positive("distance", distance)
        self._require_fraction("fraction_radiated", fraction_radiated)
        self._require_fraction("transmissivity", transmissivity)
        self._require_positive("allowable_flux", allowable_flux)

        # Total heat release: kg/s * MJ/kg = MW -> kW.
        total_heat_release_kw = mass_flow * heat_of_combustion * 1000.0
        # Point-source radiant flux: q = tau F Q / (4 pi r^2), in kW/m2.
        flux_kw_m2 = (
            transmissivity
            * fraction_radiated
            * total_heat_release_kw
            / (4.0 * pi * distance * distance)
        )
        flux_ratio = flux_kw_m2 / allowable_flux
        warning = self._warning(flux_ratio)

        return FlareRadiationResult(
            total_heat_release_kw=round(total_heat_release_kw, 3),
            radiant_heat_flux_kw_m2=round(flux_kw_m2, 4),
            allowable_flux_kw_m2=round(allowable_flux, 4),
            flux_ratio=round(flux_ratio, 4),
            radiation_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Total heat release uses Q = mass_flow * heat_of_combustion.",
                "Radiant flux uses the public API 521 / API 537 point-source form "
                "q = tau F Q / (4 pi r^2).",
                "No flame length, tilt, wind, view factor, or solar radiation is included.",
                "Move to validated NeqSim flare classes (Flare.estimateRadiationHeatFlux) and qualified review.",
            ),
        )

    def _warning(self, flux_ratio: float) -> str:
        if flux_ratio >= self.high_threshold:
            return "high"
        if flux_ratio >= self.watch_threshold:
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
