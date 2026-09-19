from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class AntiSurgeRecycleResult:
    needs_chart_generation: bool
    in_surge: bool
    surge_margin_fraction: float
    recommended_recycle_flow: float
    total_suction_flow: float
    recycle_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class AntiSurgeRecycleModel:
    """Educational anti-surge recycle planning placeholder.

    Mirrors the proportional recycle step used by NeqSim's anti-surge
    ``Calculator`` (``runAntiSurgeCalc``) so an agent can pre-estimate how much
    recycle flow a centrifugal compressor needs to stay off its surge line, and
    whether a compressor chart (with surge and stonewall curves) must first be
    generated. It is screening-only logic, not an anti-surge control design.
    """

    def __init__(
        self,
        min_surge_margin: float = 0.10,
        step_fraction: float = 0.5,
        max_step_fraction: float = 0.25,
        far_from_surge_factor: float = 1.2,
    ) -> None:
        self._require_positive("min_surge_margin", min_surge_margin)
        self._require_positive("step_fraction", step_fraction)
        self._require_positive("max_step_fraction", max_step_fraction)
        if far_from_surge_factor <= 1.0:
            raise ValueError("far_from_surge_factor must be greater than 1.0")
        self.min_surge_margin = min_surge_margin
        self.step_fraction = step_fraction
        self.max_step_fraction = max_step_fraction
        self.far_from_surge_factor = far_from_surge_factor

    def plan(
        self,
        *,
        inlet_flow: float,
        surge_flow: float,
        chart_provided: bool = True,
        current_recycle: float = 0.0,
    ) -> AntiSurgeRecycleResult:
        """Plan the anti-surge recycle for one operating point.

        Args:
            inlet_flow: actual compressor inlet (suction) volumetric flow in m3/h.
            surge_flow: surge-limit flow at the operating head in m3/h. When no
                vendor chart is available this is the surge flow read from the
                generated surge curve.
            chart_provided: ``False`` if no vendor compressor chart is available,
                in which case a chart (with surge and stonewall curves) must be
                generated before the surge flow is known.
            current_recycle: existing recycle volumetric flow in m3/h.
        """
        self._require_positive("inlet_flow", inlet_flow)
        self._require_positive("surge_flow", surge_flow)
        self._require_non_negative("current_recycle", current_recycle)

        surge_margin = (inlet_flow - surge_flow) / surge_flow
        in_surge = inlet_flow <= surge_flow

        if inlet_flow > self.far_from_surge_factor * surge_flow:
            recommended_recycle = max(inlet_flow / 1.0e6, 1.0e-6)
            warning = "ok"
        else:
            raw_step = self.step_fraction * (surge_flow - inlet_flow)
            max_step = self.max_step_fraction * max(
                current_recycle, max(inlet_flow, surge_flow)
            )
            capped_step = max(-max_step, min(max_step, raw_step))
            recommended_recycle = max(current_recycle + capped_step, inlet_flow / 1.0e6)
            warning = "surge" if in_surge else "recycle"

        total_suction = inlet_flow + recommended_recycle

        return AntiSurgeRecycleResult(
            needs_chart_generation=not chart_provided,
            in_surge=in_surge,
            surge_margin_fraction=round(surge_margin, 4),
            recommended_recycle_flow=round(recommended_recycle, 4),
            total_suction_flow=round(total_suction, 4),
            recycle_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Surge margin is (inlet_flow - surge_flow) / surge_flow.",
                "Recommended recycle mirrors NeqSim's proportional anti-surge step "
                "0.5 * (surge_flow - inlet_flow), capped per iteration.",
                "Surge flow must be taken at the operating head and speed.",
                "If no vendor chart is given, generate a chart (with surge and "
                "stonewall curves) in NeqSim before reading the surge flow.",
                "Move to validated NeqSim compressor curves, the anti-surge "
                "Calculator/Recycle loop, and API 617 review for real design.",
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
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")
