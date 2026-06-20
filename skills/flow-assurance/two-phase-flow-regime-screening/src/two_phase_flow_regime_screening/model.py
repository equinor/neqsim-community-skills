from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, pi


@dataclass(frozen=True)
class TwoPhaseRegimeResult:
    superficial_gas_velocity_m_s: float
    superficial_liquid_velocity_m_s: float
    mixture_velocity_m_s: float
    flow_regime: str
    slug_risk: bool
    regime_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class TwoPhaseRegimeModel:
    """Educational two-phase flow-regime screening placeholder.

    Classifies a horizontal gas-liquid flow regime from superficial velocities
    with a simplified Mandhane-style decision tree and flags slug risk.
    """

    def __init__(self, high_velocity_limit: float = 20.0) -> None:
        self._require_positive("high_velocity_limit", high_velocity_limit)
        self.high_velocity_limit = high_velocity_limit

    def evaluate(
        self,
        *,
        pipe_inner_diameter: float | None = None,
        superficial_gas_velocity: float | None = None,
        superficial_liquid_velocity: float | None = None,
        gas_mass_flow: float | None = None,
        liquid_mass_flow: float | None = None,
        gas_density: float | None = None,
        liquid_density: float | None = None,
    ) -> TwoPhaseRegimeResult:
        if superficial_gas_velocity is not None and superficial_liquid_velocity is not None:
            self._require_non_negative("superficial_gas_velocity", superficial_gas_velocity)
            self._require_non_negative(
                "superficial_liquid_velocity", superficial_liquid_velocity
            )
            vsg = superficial_gas_velocity
            vsl = superficial_liquid_velocity
        elif (
            pipe_inner_diameter is not None
            and gas_mass_flow is not None
            and liquid_mass_flow is not None
            and gas_density is not None
            and liquid_density is not None
        ):
            self._require_positive("pipe_inner_diameter", pipe_inner_diameter)
            self._require_non_negative("gas_mass_flow", gas_mass_flow)
            self._require_non_negative("liquid_mass_flow", liquid_mass_flow)
            self._require_positive("gas_density", gas_density)
            self._require_positive("liquid_density", liquid_density)
            area = pi / 4.0 * pipe_inner_diameter * pipe_inner_diameter
            vsg = (gas_mass_flow / gas_density) / area
            vsl = (liquid_mass_flow / liquid_density) / area
        else:
            raise ValueError(
                "provide either superficial velocities or "
                "(pipe_inner_diameter, gas/liquid mass flow, gas/liquid density)"
            )

        regime = self._classify(vsg, vsl)
        slug_risk = regime in {"slug", "elongated-bubble"}
        mixture_velocity = vsg + vsl
        warning = self._warning(slug_risk, mixture_velocity)

        return TwoPhaseRegimeResult(
            superficial_gas_velocity_m_s=round(vsg, 4),
            superficial_liquid_velocity_m_s=round(vsl, 4),
            mixture_velocity_m_s=round(mixture_velocity, 4),
            flow_regime=regime,
            slug_risk=slug_risk,
            regime_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Horizontal flow with a simplified Mandhane-style velocity map.",
                "Superficial velocities from volumetric flow over the full pipe area.",
                "Boundaries are public approximations, not the digitized Mandhane chart.",
                "No inclination, fluid-property, surface-tension, or entrainment effects.",
                "Move to validated NeqSim multiphase pipe flow and qualified review.",
            ),
        )

    def _classify(self, vsg: float, vsl: float) -> str:
        # Simplified public Mandhane-style boundaries for horizontal flow (m/s).
        if vsg >= 10.0:
            return "annular-mist"
        if vsl >= 2.0:
            return "dispersed-bubble"
        if vsl < 0.1:
            return "stratified-smooth" if vsg < 0.5 else "stratified-wavy"
        if vsg < 1.0:
            return "elongated-bubble"
        return "slug"

    def _warning(self, slug_risk: bool, mixture_velocity: float) -> str:
        if mixture_velocity > self.high_velocity_limit:
            return "high-velocity"
        if slug_risk:
            return "slug-risk"
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
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must not be negative")
