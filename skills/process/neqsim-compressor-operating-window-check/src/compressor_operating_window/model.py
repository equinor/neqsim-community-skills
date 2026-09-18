from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class CompressorOperatingWindowResult:
    surge_margin_fraction: float
    stonewall_margin_fraction: float
    limiting_margin_fraction: float
    operating_window_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class CompressorOperatingWindowModel:
    """Educational compressor operating window screening placeholder."""

    def __init__(
        self,
        min_surge_margin: float = 0.10,
        min_stonewall_margin: float = 0.05,
    ) -> None:
        self._require_positive("min_surge_margin", min_surge_margin)
        self._require_positive("min_stonewall_margin", min_stonewall_margin)
        self.min_surge_margin = min_surge_margin
        self.min_stonewall_margin = min_stonewall_margin

    def evaluate(
        self,
        *,
        operating_flow: float,
        surge_flow: float,
        stonewall_flow: float,
    ) -> CompressorOperatingWindowResult:
        self._require_positive("operating_flow", operating_flow)
        self._require_positive("surge_flow", surge_flow)
        self._require_positive("stonewall_flow", stonewall_flow)
        if surge_flow >= stonewall_flow:
            raise ValueError("stonewall_flow must be greater than surge_flow")

        surge_margin = (operating_flow - surge_flow) / surge_flow
        stonewall_margin = (stonewall_flow - operating_flow) / stonewall_flow
        limiting_margin = min(surge_margin, stonewall_margin)
        warning = self._operating_warning(surge_margin, stonewall_margin)

        return CompressorOperatingWindowResult(
            surge_margin_fraction=round(surge_margin, 4),
            stonewall_margin_fraction=round(stonewall_margin, 4),
            limiting_margin_fraction=round(limiting_margin, 4),
            operating_window_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Surge margin is (operating_flow - surge_flow) / surge_flow.",
                "Stonewall margin is (stonewall_flow - operating_flow) / stonewall_flow.",
                "Margins assume the same speed line and reference conditions for all flows.",
                "Move to validated NeqSim performance curves and API 617 review for real design.",
            ),
        )

    def _operating_warning(self, surge_margin: float, stonewall_margin: float) -> str:
        if surge_margin <= 0.0 or stonewall_margin <= 0.0:
            return "high"
        if surge_margin < self.min_surge_margin or stonewall_margin < self.min_stonewall_margin:
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
