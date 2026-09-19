from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class WaxMarginResult:
    wax_margin_c: float
    below_wax_appearance: bool
    margin_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class WaxMarginModel:
    """Educational wax operating-margin screening placeholder."""

    def __init__(self, min_margin: float = 5.0) -> None:
        self._require_positive("min_margin", min_margin)
        self.min_margin = min_margin

    def evaluate(
        self,
        *,
        operating_temperature: float,
        wax_appearance_temperature: float,
    ) -> WaxMarginResult:
        self._require_finite("operating_temperature", operating_temperature)
        self._require_finite(
            "wax_appearance_temperature", wax_appearance_temperature
        )

        wax_margin = operating_temperature - wax_appearance_temperature
        below_wax_appearance = wax_margin <= 0.0
        margin_warning = self._margin_warning(wax_margin)

        return WaxMarginResult(
            wax_margin_c=round(wax_margin, 2),
            below_wax_appearance=below_wax_appearance,
            margin_warning=margin_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Wax margin is operating temperature minus the supplied wax appearance temperature.",
                "A non-positive margin means the operating point is at or below the wax appearance temperature.",
                "The wax appearance temperature should come from a validated NeqSim wax calculation or a public lab measurement.",
                "The minimum margin guideline is a configurable public operating margin, not a design rule.",
                "Move to validated NeqSim wax workflows and qualified flow assurance review.",
            ),
        )

    def _margin_warning(self, wax_margin: float) -> str:
        if wax_margin <= 0.0:
            return "high"
        if wax_margin < self.min_margin:
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
