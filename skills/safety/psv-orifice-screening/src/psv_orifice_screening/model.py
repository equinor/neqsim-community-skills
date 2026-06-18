from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt


# Standard API 526 effective orifice areas in mm2 (from published in2 values).
_API_ORIFICES: tuple[tuple[str, float], ...] = (
    ("D", 71.0),
    ("E", 126.0),
    ("F", 198.0),
    ("G", 325.0),
    ("H", 506.0),
    ("J", 830.0),
    ("K", 1186.0),
    ("L", 1841.0),
    ("M", 2323.0),
    ("N", 2800.0),
    ("P", 4116.0),
    ("Q", 7129.0),
    ("R", 10323.0),
    ("T", 16774.0),
)


@dataclass(frozen=True)
class PsvOrificeResult:
    coefficient_c: float
    required_area_mm2: float
    selected_orifice: str
    selected_orifice_area_mm2: float
    area_margin_ratio: float
    psv_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class PsvOrificeModel:
    """Educational API 520 Part I critical gas-flow PSV orifice screening placeholder."""

    def __init__(self, watch_threshold: float = 1.1) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self.watch_threshold = watch_threshold

    def evaluate(
        self,
        *,
        relief_rate: float,
        relieving_pressure: float,
        temperature: float,
        molecular_weight: float,
        compressibility: float = 1.0,
        specific_heat_ratio: float = 1.3,
        discharge_coefficient: float = 0.975,
        back_pressure_correction: float = 1.0,
        combination_correction: float = 1.0,
    ) -> PsvOrificeResult:
        self._require_positive("relief_rate", relief_rate)
        self._require_positive("relieving_pressure", relieving_pressure)
        self._require_positive("temperature", temperature)
        self._require_positive("molecular_weight", molecular_weight)
        self._require_positive("compressibility", compressibility)
        if specific_heat_ratio <= 1.0:
            raise ValueError("specific_heat_ratio must be greater than 1")
        self._require_fraction("discharge_coefficient", discharge_coefficient)
        self._require_fraction("back_pressure_correction", back_pressure_correction)
        self._require_fraction("combination_correction", combination_correction)

        k = specific_heat_ratio
        coefficient_c = 0.03948 * sqrt(
            k * (2.0 / (k + 1.0)) ** ((k + 1.0) / (k - 1.0))
        )
        # API 520 metric form expects the relieving pressure in kPa absolute.
        relieving_pressure_kpa = relieving_pressure * 100.0
        required_area = (
            relief_rate
            / (
                coefficient_c
                * discharge_coefficient
                * relieving_pressure_kpa
                * back_pressure_correction
                * combination_correction
            )
            * sqrt(temperature * compressibility / molecular_weight)
        )

        selected_orifice, selected_area = self._select_orifice(required_area)
        if selected_area > 0.0:
            margin_ratio = selected_area / required_area
        else:
            margin_ratio = 0.0
        warning = self._warning(selected_orifice, margin_ratio)

        return PsvOrificeResult(
            coefficient_c=round(coefficient_c, 5),
            required_area_mm2=round(required_area, 3),
            selected_orifice=selected_orifice,
            selected_orifice_area_mm2=round(selected_area, 3),
            area_margin_ratio=round(margin_ratio, 4),
            psv_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Assumes critical (choked) gas flow; the choked criterion is not verified.",
                "Required area uses the public API 520 Part I form "
                "A = (W / (C Kd P1 Kb Kc)) * sqrt(T Z / M).",
                "Orifice letters use published API 526 effective areas.",
                "Move to validated NeqSim relief sizing (ReliefValveSizing) and qualified review.",
            ),
        )

    @staticmethod
    def _select_orifice(required_area: float) -> tuple[str, float]:
        for letter, area in _API_ORIFICES:
            if area >= required_area:
                return letter, area
        return "none", 0.0

    def _warning(self, selected_orifice: str, margin_ratio: float) -> str:
        if selected_orifice == "none":
            return "oversize-needed"
        if margin_ratio < self.watch_threshold:
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

    @classmethod
    def _require_fraction(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1]")
