from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, pi, sqrt
from typing import Optional, Tuple


@dataclass(frozen=True)
class GasScrubberSizingResult:
    souders_brown_velocity_m_s: float
    gas_volumetric_flow_m3_s: float
    required_area_m2: float
    required_diameter_m: float
    actual_velocity_m_s: Optional[float]
    velocity_utilisation: Optional[float]
    gas_load_factor: Optional[float]
    demister_velocity_limit_m_s: float
    demister_utilisation: Optional[float]
    sizing_warning: str
    demister_warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class GasScrubberSizingModel:
    """Educational gas-scrubber sizing screening (GPSA / API RP 12J style).

    Uses the open Souders-Brown / K-factor relation to size a vertical gas
    scrubber, checks the velocity utilisation against an existing vessel
    diameter, and screens the mist-eliminator gas load. Screening only.
    """

    def __init__(
        self,
        *,
        watch_utilisation: float = 0.8,
        oversized_utilisation: float = 0.3,
    ) -> None:
        self._require_unit_fraction("watch_utilisation", watch_utilisation)
        self._require_unit_fraction("oversized_utilisation", oversized_utilisation)
        if oversized_utilisation >= watch_utilisation:
            raise ValueError(
                "oversized_utilisation must be less than watch_utilisation"
            )
        self.watch_utilisation = watch_utilisation
        self.oversized_utilisation = oversized_utilisation

    def evaluate(
        self,
        *,
        gas_mass_flow_kg_s: float,
        gas_density_kg_m3: float,
        liquid_density_kg_m3: float,
        k_factor_m_s: float = 0.107,
        vessel_inside_diameter_m: Optional[float] = None,
        mist_eliminator_k_factor: float = 0.12,
        demister_present: bool = True,
    ) -> GasScrubberSizingResult:
        self._require_positive("gas_mass_flow_kg_s", gas_mass_flow_kg_s)
        self._require_positive("gas_density_kg_m3", gas_density_kg_m3)
        self._require_positive("liquid_density_kg_m3", liquid_density_kg_m3)
        if liquid_density_kg_m3 <= gas_density_kg_m3:
            raise ValueError(
                "liquid_density_kg_m3 must be greater than gas_density_kg_m3"
            )
        self._require_positive("k_factor_m_s", k_factor_m_s)
        self._require_positive("mist_eliminator_k_factor", mist_eliminator_k_factor)
        if vessel_inside_diameter_m is not None:
            self._require_positive("vessel_inside_diameter_m", vessel_inside_diameter_m)

        density_ratio = (liquid_density_kg_m3 - gas_density_kg_m3) / gas_density_kg_m3
        density_factor = sqrt(density_ratio)

        # Souders-Brown maximum gas velocity: v_max = K sqrt((rho_l - rho_g) / rho_g).
        v_max = k_factor_m_s * density_factor

        # Actual gas volumetric flow and required vessel area / diameter.
        q_gas = gas_mass_flow_kg_s / gas_density_kg_m3
        required_area = q_gas / v_max
        required_diameter = sqrt(4.0 * required_area / pi)

        # Demister Souders-Brown limit.
        demister_limit = mist_eliminator_k_factor * density_factor

        actual_velocity: Optional[float] = None
        velocity_utilisation: Optional[float] = None
        gas_load_factor: Optional[float] = None
        demister_utilisation: Optional[float] = None

        if vessel_inside_diameter_m is not None:
            actual_area = pi / 4.0 * vessel_inside_diameter_m ** 2.0
            actual_velocity = q_gas / actual_area
            velocity_utilisation = actual_velocity / v_max
            # Effective K-factor from the actual velocity.
            gas_load_factor = actual_velocity / density_factor
            demister_utilisation = actual_velocity / demister_limit
        else:
            # Sized to requirement: the actual velocity equals v_max.
            demister_utilisation = v_max / demister_limit

        sizing_warning = self._sizing_warning(velocity_utilisation)
        demister_warning = self._demister_warning(
            demister_present, demister_utilisation
        )

        return GasScrubberSizingResult(
            souders_brown_velocity_m_s=round(v_max, 4),
            gas_volumetric_flow_m3_s=round(q_gas, 5),
            required_area_m2=round(required_area, 5),
            required_diameter_m=round(required_diameter, 4),
            actual_velocity_m_s=(
                None if actual_velocity is None else round(actual_velocity, 4)
            ),
            velocity_utilisation=(
                None if velocity_utilisation is None else round(velocity_utilisation, 4)
            ),
            gas_load_factor=(
                None if gas_load_factor is None else round(gas_load_factor, 4)
            ),
            demister_velocity_limit_m_s=round(demister_limit, 4),
            demister_utilisation=(
                None if demister_utilisation is None else round(demister_utilisation, 4)
            ),
            sizing_warning=sizing_warning,
            demister_warning=demister_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (GPSA / API RP 12J style).",
                "Souders-Brown velocity v_max = K sqrt((rho_l - rho_g) / rho_g).",
                "Vertical vessel with uniform gas velocity across the cross-section.",
                "Demister limit uses a single mist-eliminator K-factor.",
                "No inlet device, liquid handling, or settling-section detail is modelled.",
                "Move to a validated separator sizing method and qualified review.",
            ),
        )

    def _sizing_warning(self, velocity_utilisation: Optional[float]) -> str:
        if velocity_utilisation is None:
            return "ok"
        if velocity_utilisation > 1.0:
            return "undersized"
        if velocity_utilisation > self.watch_utilisation:
            return "watch"
        if velocity_utilisation < self.oversized_utilisation:
            return "oversized"
        return "ok"

    @staticmethod
    def _demister_warning(
        demister_present: bool, demister_utilisation: Optional[float]
    ) -> str:
        if not demister_present:
            return "no-demister"
        if demister_utilisation is None:
            return "ok"
        if demister_utilisation > 1.0:
            return "mist-eliminator-overloaded"
        if demister_utilisation > 0.9:
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
    def _require_unit_fraction(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1)")
