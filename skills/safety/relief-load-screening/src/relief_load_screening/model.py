from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class ReliefLoadResult:
    fire_heat_input_kW: float
    relief_mass_rate_kg_per_h: float
    relief_load_indicator: float
    relief_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class ReliefLoadModel:
    """Educational fire-case relief load screening placeholder."""

    def __init__(
        self,
        fire_coefficient_kw: float = 43.2,
        area_exponent: float = 0.82,
        relief_mass_basis_kg_per_h: float = 50_000.0,
    ) -> None:
        self._require_positive("fire_coefficient_kw", fire_coefficient_kw)
        self._require_positive("area_exponent", area_exponent)
        self._require_positive("relief_mass_basis_kg_per_h", relief_mass_basis_kg_per_h)
        self.fire_coefficient_kw = fire_coefficient_kw
        self.area_exponent = area_exponent
        self.relief_mass_basis_kg_per_h = relief_mass_basis_kg_per_h

    def evaluate(
        self,
        *,
        wetted_area: float,
        latent_heat: float,
        relief_pressure: float,
        environment_factor: float = 1.0,
    ) -> ReliefLoadResult:
        self._require_positive("wetted_area", wetted_area)
        self._require_positive("latent_heat", latent_heat)
        self._require_positive("relief_pressure", relief_pressure)
        self._require_positive("environment_factor", environment_factor)

        fire_heat_input_kw = (
            environment_factor * self.fire_coefficient_kw * wetted_area ** self.area_exponent
        )
        relief_mass_rate_kg_per_h = fire_heat_input_kw / latent_heat * 3600.0
        relief_load_indicator = relief_mass_rate_kg_per_h / self.relief_mass_basis_kg_per_h
        relief_warning = self._relief_warning(relief_load_indicator)

        return ReliefLoadResult(
            fire_heat_input_kW=round(fire_heat_input_kw, 2),
            relief_mass_rate_kg_per_h=round(relief_mass_rate_kg_per_h, 2),
            relief_load_indicator=round(relief_load_indicator, 4),
            relief_warning=relief_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Fire heat input uses a public API 521 style adequate-drainage form Q = F * C * A^0.82.",
                "Relief mass rate is fire heat input divided by latent heat of vaporization.",
                "The relief load basis is a configurable public reference value, not a sized relief rate.",
                "Move to validated API 520/521 methods and NeqSim properties for real relief sizing.",
            ),
        )

    @staticmethod
    def _relief_warning(relief_load_indicator: float) -> str:
        if relief_load_indicator > 1.0:
            return "high"
        if relief_load_indicator > 0.5:
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
