from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Optional, Tuple

# Water hydrostatic gradient (bar/m) used to blend the effective gradient.
_WATER_GRADIENT_BAR_PER_M = 0.0981
# Fraction of the hydrostatic head gas lift can typically remove (screening).
_GAS_LIFT_LIGHTENING_FRACTION = 0.5


@dataclass(frozen=True)
class ArtificialLiftResult:
    natural_rate_sm3_d: float
    required_pwf_bar: float
    required_pressure_reduction_bar: float
    esp_required_head_m: Optional[float]
    gas_lift_feasible: bool
    esp_feasible: bool
    recommended_method: str
    warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class ArtificialLiftModel:
    """Educational artificial-lift screening (straight-line IPR based).

    Compares natural deliverability from a straight-line IPR against a target
    rate and screens gas lift and ESP feasibility from the required
    bottomhole-pressure reduction. Screening only.
    """

    def __init__(
        self,
        *,
        gas_lift_lightening_fraction: float = _GAS_LIFT_LIGHTENING_FRACTION,
    ) -> None:
        self._require_fraction("gas_lift_lightening_fraction", gas_lift_lightening_fraction)
        self.gas_lift_lightening_fraction = gas_lift_lightening_fraction

    def evaluate(
        self,
        *,
        reservoir_pressure_bar: float,
        bottomhole_flowing_pressure_bar: float,
        productivity_index_sm3_d_bar: float,
        target_rate_sm3_d: float,
        water_cut: float = 0.0,
        gas_lift_available: bool = True,
        max_injection_gas_sm3_d: Optional[float] = None,
        esp_max_head_m: Optional[float] = None,
        fluid_gradient_bar_per_m: float = 0.09,
        well_depth_m: float = 2000.0,
    ) -> ArtificialLiftResult:
        self._require_positive("reservoir_pressure_bar", reservoir_pressure_bar)
        self._require_positive("bottomhole_flowing_pressure_bar", bottomhole_flowing_pressure_bar)
        self._require_positive("productivity_index_sm3_d_bar", productivity_index_sm3_d_bar)
        self._require_positive("target_rate_sm3_d", target_rate_sm3_d)
        self._require_unit_interval("water_cut", water_cut)
        self._require_positive("fluid_gradient_bar_per_m", fluid_gradient_bar_per_m)
        self._require_positive("well_depth_m", well_depth_m)
        if max_injection_gas_sm3_d is not None:
            self._require_positive("max_injection_gas_sm3_d", max_injection_gas_sm3_d)
        if esp_max_head_m is not None:
            self._require_positive("esp_max_head_m", esp_max_head_m)
        if bottomhole_flowing_pressure_bar > reservoir_pressure_bar:
            raise ValueError(
                "bottomhole_flowing_pressure_bar must not exceed reservoir_pressure_bar"
            )

        pi = productivity_index_sm3_d_bar

        # Natural deliverability from a straight-line IPR.
        natural_rate = pi * (reservoir_pressure_bar - bottomhole_flowing_pressure_bar)

        # Bottomhole pressure required to deliver the target rate.
        required_pwf = reservoir_pressure_bar - target_rate_sm3_d / pi

        # Effective gradient blends fluid and water gradients.
        effective_gradient = (
            fluid_gradient_bar_per_m * (1.0 - water_cut)
            + _WATER_GRADIENT_BAR_PER_M * water_cut
        )

        esp_required_head: Optional[float] = None
        gas_lift_feasible = False
        esp_feasible = False

        if natural_rate >= target_rate_sm3_d:
            required_reduction = 0.0
            recommended = "natural-flow"
        elif required_pwf <= 0.0:
            required_reduction = bottomhole_flowing_pressure_bar - required_pwf
            recommended = "infeasible"
        else:
            required_reduction = bottomhole_flowing_pressure_bar - required_pwf

            # ESP screening: head needed for the pressure reduction.
            esp_required_head = required_reduction / effective_gradient
            if esp_max_head_m is not None and esp_required_head <= esp_max_head_m:
                esp_feasible = True

            # Gas-lift screening: column lightening limit.
            max_gas_lift_reduction = (
                self.gas_lift_lightening_fraction * effective_gradient * well_depth_m
            )
            if gas_lift_available and required_reduction <= max_gas_lift_reduction:
                gas_lift_feasible = True

            if gas_lift_feasible:
                recommended = "gas-lift"
            elif esp_feasible:
                recommended = "esp"
            else:
                recommended = "infeasible"

        return ArtificialLiftResult(
            natural_rate_sm3_d=round(natural_rate, 3),
            required_pwf_bar=round(required_pwf, 3),
            required_pressure_reduction_bar=round(max(required_reduction, 0.0), 3),
            esp_required_head_m=(
                None if esp_required_head is None else round(esp_required_head, 3)
            ),
            gas_lift_feasible=gas_lift_feasible,
            esp_feasible=esp_feasible,
            recommended_method=recommended,
            warning=recommended,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (straight-line IPR).",
                "Inflow uses q = PI * (Pr - Pwf) with no turbulence or saturation.",
                "Effective gradient blends fluid and water (0.0981 bar/m) gradients.",
                "Gas lift can remove up to half the hydrostatic head (screening).",
                "ESP head uses H = dP / effective_gradient.",
                "Move to validated nodal analysis and qualified lift design.",
            ),
        )

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
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in the open interval (0, 1)")

    @classmethod
    def _require_unit_interval(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in [0, 1)")
