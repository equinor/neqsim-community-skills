from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

_SEVERITY = {"ok": 0, "watch": 1, "high": 2, "not_assessed": -1}


@dataclass(frozen=True)
class StepOutScreeningResult:
    step_out_km: float
    max_step_out_km: float
    step_out_warning: str
    arrival_pressure_bara: float
    min_arrival_pressure_bara: float
    arrival_pressure_margin_bar: float
    pressure_warning: str
    hydrate_margin_c: float | None
    hydrate_warning: str
    overall_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class StepOutScreeningModel:
    """Educational subsea step-out and arrival-pressure screening placeholder."""

    def __init__(self, max_step_out_km: float = 50.0) -> None:
        self._require_positive("max_step_out_km", max_step_out_km)
        self.max_step_out_km = max_step_out_km

    def evaluate(
        self,
        *,
        step_out_km: float,
        arrival_pressure_bara: float,
        min_arrival_pressure_bara: float,
        hydrate_margin_c: float | None = None,
    ) -> StepOutScreeningResult:
        self._require_positive("step_out_km", step_out_km)
        self._require_positive("arrival_pressure_bara", arrival_pressure_bara)
        self._require_positive("min_arrival_pressure_bara", min_arrival_pressure_bara)

        step_out_warning = self._step_out_warning(step_out_km)

        margin = arrival_pressure_bara - min_arrival_pressure_bara
        pressure_warning = self._pressure_warning(margin, min_arrival_pressure_bara)

        hydrate_warning = self._hydrate_warning(hydrate_margin_c)

        overall_warning = self._worst(
            step_out_warning, pressure_warning, hydrate_warning
        )

        return StepOutScreeningResult(
            step_out_km=round(step_out_km, 3),
            max_step_out_km=self.max_step_out_km,
            step_out_warning=step_out_warning,
            arrival_pressure_bara=round(arrival_pressure_bara, 3),
            min_arrival_pressure_bara=round(min_arrival_pressure_bara, 3),
            arrival_pressure_margin_bar=round(margin, 3),
            pressure_warning=pressure_warning,
            hydrate_margin_c=(
                None if hydrate_margin_c is None else round(float(hydrate_margin_c), 3)
            ),
            hydrate_warning=hydrate_warning,
            overall_warning=overall_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational step-out screening placeholder only.",
                "No hydraulic, thermal, or thermodynamic calculation is performed.",
                "Arrival pressure and hydrate margin must come from validated tools.",
                "Guideline thresholds are illustrative public values only.",
                "Escalate any 'watch' or 'high' verdict to detailed flow-assurance review.",
            ),
        )

    def _step_out_warning(self, step_out_km: float) -> str:
        if step_out_km >= self.max_step_out_km:
            return "high"
        if step_out_km >= 0.8 * self.max_step_out_km:
            return "watch"
        return "ok"

    @staticmethod
    def _pressure_warning(margin: float, minimum: float) -> str:
        if margin < 0.0:
            return "high"
        if margin < 0.1 * minimum:
            return "watch"
        return "ok"

    def _hydrate_warning(self, hydrate_margin_c: float | None) -> str:
        if hydrate_margin_c is None:
            return "not_assessed"
        value = float(hydrate_margin_c)
        self._require_finite("hydrate_margin_c", value)
        if value < 0.0:
            return "high"
        if value < 2.0:
            return "watch"
        return "ok"

    @staticmethod
    def _worst(*warnings: str) -> str:
        assessed = [w for w in warnings if w != "not_assessed"]
        if not assessed:
            return "not_assessed"
        return max(assessed, key=lambda w: _SEVERITY[w])

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
