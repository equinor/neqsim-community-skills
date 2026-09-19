from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, log10


@dataclass(frozen=True)
class HydrateScreeningResult:
    risk_level: str
    margin_indicator: float
    estimated_boundary: float
    water_present: bool
    neqsim_available: bool
    assumptions: tuple[str, ...]


class HydrateScreener:
    """Educational hydrate screening placeholder."""

    def screen(
        self,
        *,
        pressure: float,
        temperature: float,
        water_present: bool,
    ) -> HydrateScreeningResult:
        self._require_positive("pressure", pressure)
        self._require_finite("temperature", temperature)

        estimated_boundary = self._estimated_boundary(pressure)
        margin_indicator = temperature - estimated_boundary
        risk_level = self._risk_level(margin_indicator, water_present)

        return HydrateScreeningResult(
            risk_level=risk_level,
            margin_indicator=round(margin_indicator, 2),
            estimated_boundary=round(estimated_boundary, 2),
            water_present=water_present,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=self._assumptions(water_present),
        )

    @staticmethod
    def _estimated_boundary(pressure: float) -> float:
        return max(-20.0, min(25.0, -6.0 + 8.0 * log10(pressure)))

    @staticmethod
    def _risk_level(margin_indicator: float, water_present: bool) -> str:
        if not water_present:
            return "low"
        if margin_indicator < 2.0:
            return "high"
        if margin_indicator < 8.0:
            return "medium"
        return "low"

    @staticmethod
    def _assumptions(water_present: bool) -> tuple[str, ...]:
        assumptions = [
            "Educational screening placeholder only.",
            "Boundary is a simple public pressure-dependent indicator, not hydrate thermodynamics.",
            "Use validated NeqSim hydrate methods for real calculations.",
        ]
        if not water_present:
            assumptions.append("Water absent was provided by the caller; verify water basis before relying on low risk.")
        return tuple(assumptions)

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")