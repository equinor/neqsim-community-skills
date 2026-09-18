from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class WaterDewpointResult:
    saturated_water_content_lb_mmscf: float
    water_spec_lb_mmscf: float
    spec_ratio: float
    dehydration_required: bool
    dehydration_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class WaterDewpointModel:
    """Educational ideal-gas saturated water-content screening placeholder."""

    # Standard-volume basis: 1e6 scf / 379.49 scf-per-lbmol (60 F, 14.696 psia)
    # multiplied by the molar mass of water (18.015 lb/lbmol).
    _LB_WATER_PER_MMSCF_SATURATED = 1.0e6 / 379.49 * 18.015
    # Antoine constants for water vapour pressure (Stull), T in deg C, P in mmHg,
    # nominally valid for roughly 1-100 deg C.
    _ANTOINE_A = 8.07131
    _ANTOINE_B = 1730.63
    _ANTOINE_C = 233.426
    _MMHG_PER_PSIA = 51.7149

    def __init__(self, watch_threshold: float = 0.8) -> None:
        if not 0.0 < watch_threshold <= 1.0:
            raise ValueError("watch_threshold must be in the interval (0, 1]")
        self.watch_threshold = watch_threshold

    def evaluate(
        self,
        *,
        pressure: float,
        temperature: float,
        water_spec: float = 7.0,
    ) -> WaterDewpointResult:
        self._require_positive("pressure", pressure)
        self._require_positive("temperature", temperature)
        self._require_positive("water_spec", water_spec)

        # Convert SI inputs to the field units used by the correlation.
        pressure_psia = pressure * 14.5038
        temperature_c = temperature - 273.15

        # Water vapour pressure from the Antoine equation (mmHg -> psia).
        psat_mmhg = 10.0 ** (
            self._ANTOINE_A - self._ANTOINE_B / (self._ANTOINE_C + temperature_c)
        )
        psat_psia = psat_mmhg / self._MMHG_PER_PSIA

        # Ideal-gas saturation: water mole fraction = Psat / P at equilibrium.
        water_mole_fraction = min(psat_psia / pressure_psia, 1.0)
        saturated = water_mole_fraction * self._LB_WATER_PER_MMSCF_SATURATED

        spec_ratio = saturated / water_spec
        dehydration_required = saturated > water_spec
        warning = self._warning(spec_ratio, dehydration_required)

        return WaterDewpointResult(
            saturated_water_content_lb_mmscf=round(saturated, 4),
            water_spec_lb_mmscf=round(water_spec, 4),
            spec_ratio=round(spec_ratio, 4),
            dehydration_required=dehydration_required,
            dehydration_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Saturated water content uses ideal-gas saturation: y_water = Psat / P.",
                "Water vapour pressure from the Antoine equation (about 1-100 deg C).",
                "Ideal-gas basis under-predicts real water content versus McKetta/CPA; screening only.",
                "No acid-gas, salinity, or hydrate-suppression corrections are included.",
                "Move to validated NeqSim CPA water content and DehydrationTemplate, with qualified review.",
            ),
        )

    def _warning(self, spec_ratio: float, dehydration_required: bool) -> str:
        if dehydration_required:
            return "dehydration-required"
        if spec_ratio >= self.watch_threshold:
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
