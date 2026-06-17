from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class HydrateMarginResult:
    hydrate_margin_c: float
    subcooling_c: float
    margin_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class HydrateMarginModel:
    """Educational hydrate operating-margin screening placeholder."""

    def __init__(self, min_margin: float = 3.0) -> None:
        self._require_positive("min_margin", min_margin)
        self.min_margin = min_margin

    def evaluate(
        self,
        *,
        operating_temperature: float,
        hydrate_equilibrium_temperature: float,
    ) -> HydrateMarginResult:
        self._require_finite("operating_temperature", operating_temperature)
        self._require_finite(
            "hydrate_equilibrium_temperature", hydrate_equilibrium_temperature
        )

        hydrate_margin = operating_temperature - hydrate_equilibrium_temperature
        subcooling = max(0.0, hydrate_equilibrium_temperature - operating_temperature)
        margin_warning = self._margin_warning(hydrate_margin)

        return HydrateMarginResult(
            hydrate_margin_c=round(hydrate_margin, 2),
            subcooling_c=round(subcooling, 2),
            margin_warning=margin_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Hydrate margin is operating temperature minus the supplied hydrate equilibrium temperature.",
                "Positive subcooling means the operating point is inside the hydrate region.",
                "The hydrate equilibrium temperature should come from a validated NeqSim hydrate calculation.",
                "The minimum margin guideline is a configurable public operating margin, not a design rule.",
                "Move to validated NeqSim hydrate workflows and qualified flow assurance review.",
            ),
        )

    def _margin_warning(self, hydrate_margin: float) -> str:
        if hydrate_margin <= 0.0:
            return "high"
        if hydrate_margin < self.min_margin:
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
