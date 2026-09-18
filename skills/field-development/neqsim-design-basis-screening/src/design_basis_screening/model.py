from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

# Indicative public screening defaults only.
_DEFAULT_MIN_FLOW_MARGIN = 1.10  # design flow / operating flow
_DEFAULT_MIN_PRESSURE_MARGIN = 1.10  # design pressure / operating pressure
_DEFAULT_MIN_TEMPERATURE_MARGIN_C = 10.0  # design T - operating T [C]


@dataclass(frozen=True)
class DesignBasisResult:
    flow_margin: float
    pressure_margin: float
    temperature_margin_c: float
    flow_flag: str
    pressure_flag: str
    temperature_flag: str
    standards: tuple[str, ...]
    design_warning: str
    flags: tuple[str, ...]
    neqsim_available: bool
    assumptions: tuple[str, ...]


class DesignBasisModel:
    """Educational design-basis margin screening placeholder.

    Compares operating capacities and conditions against the proposed design
    capacities and conditions, computes indicative flow / pressure / temperature
    margins, and flags margins below transparent public thresholds. It is a
    placeholder only: real design capacities, ratings, and code compliance must
    come from validated mechanical design, the applicable standards (ASME, API,
    DNV, NORSOK), and qualified engineering review.
    """

    def __init__(
        self,
        *,
        min_flow_margin: float = _DEFAULT_MIN_FLOW_MARGIN,
        min_pressure_margin: float = _DEFAULT_MIN_PRESSURE_MARGIN,
        min_temperature_margin_c: float = _DEFAULT_MIN_TEMPERATURE_MARGIN_C,
    ) -> None:
        self._require_positive("min_flow_margin", min_flow_margin)
        self._require_positive("min_pressure_margin", min_pressure_margin)
        self._require_finite("min_temperature_margin_c", min_temperature_margin_c)
        if min_temperature_margin_c < 0.0:
            raise ValueError("min_temperature_margin_c must be non-negative")
        self.min_flow_margin = min_flow_margin
        self.min_pressure_margin = min_pressure_margin
        self.min_temperature_margin_c = min_temperature_margin_c

    def evaluate(
        self,
        *,
        operating_flow: float,
        design_flow: float,
        operating_pressure_bara: float,
        design_pressure_bara: float,
        operating_temperature_c: float,
        design_temperature_c: float,
        standards: tuple[str, ...] | list[str] | None = None,
    ) -> DesignBasisResult:
        self._require_positive("operating_flow", operating_flow)
        self._require_positive("design_flow", design_flow)
        self._require_positive("operating_pressure_bara", operating_pressure_bara)
        self._require_positive("design_pressure_bara", design_pressure_bara)
        self._require_finite("operating_temperature_c", operating_temperature_c)
        self._require_finite("design_temperature_c", design_temperature_c)

        flow_margin = design_flow / operating_flow
        pressure_margin = design_pressure_bara / operating_pressure_bara
        temperature_margin_c = design_temperature_c - operating_temperature_c

        flow_flag = "ok" if flow_margin >= self.min_flow_margin else "low"
        pressure_flag = (
            "ok" if pressure_margin >= self.min_pressure_margin else "low"
        )
        temperature_flag = (
            "ok"
            if temperature_margin_c >= self.min_temperature_margin_c
            else "low"
        )

        flags: list[str] = []
        if flow_flag == "low":
            flags.append(
                f"flow margin {flow_margin:.2f} below recommended "
                f"{self.min_flow_margin:.2f}"
            )
        if pressure_flag == "low":
            flags.append(
                f"pressure margin {pressure_margin:.2f} below recommended "
                f"{self.min_pressure_margin:.2f}"
            )
        if temperature_flag == "low":
            flags.append(
                f"temperature margin {temperature_margin_c:.1f} C below "
                f"recommended {self.min_temperature_margin_c:.1f} C"
            )

        standards_norm = self._normalize_standards(standards)
        if not standards_norm:
            flags.append("no design standards basis supplied")

        design_warning = "watch" if flags else "ok"

        return DesignBasisResult(
            flow_margin=round(flow_margin, 4),
            pressure_margin=round(pressure_margin, 4),
            temperature_margin_c=round(temperature_margin_c, 4),
            flow_flag=flow_flag,
            pressure_flag=pressure_flag,
            temperature_flag=temperature_flag,
            standards=standards_norm,
            design_warning=design_warning,
            flags=tuple(flags),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational design-basis margin screening placeholder only.",
                "Margins are simple ratios/differences vs indicative public thresholds.",
                "No code-rating, wall-thickness, or mechanical-design check is performed.",
                "Standards list is echoed only, not checked for applicability.",
                "Use validated mechanical design and applicable standards for real basis.",
            ),
        )

    @staticmethod
    def _normalize_standards(
        standards: tuple[str, ...] | list[str] | None,
    ) -> tuple[str, ...]:
        if not standards:
            return ()
        cleaned = []
        for item in standards:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return tuple(cleaned)

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
