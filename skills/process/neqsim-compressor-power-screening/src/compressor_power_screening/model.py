from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

_UNIVERSAL_GAS_CONSTANT = 8.314  # J/(mol K)


@dataclass(frozen=True)
class CompressorPowerResult:
    pressure_ratio: float
    polytropic_head_kj_kg: float
    discharge_temperature_k: float
    gas_power_kw: float
    power_margin_ratio: float | None
    compressor_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class CompressorPowerModel:
    """Educational polytropic-head compressor power screening placeholder."""

    def __init__(self, watch_threshold: float = 1.1) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self.watch_threshold = watch_threshold

    def evaluate(
        self,
        *,
        suction_pressure: float,
        discharge_pressure: float,
        suction_temperature: float,
        mass_flow: float,
        molecular_weight: float,
        specific_heat_ratio: float = 1.3,
        compressibility: float = 1.0,
        polytropic_efficiency: float = 0.78,
        rated_power: float | None = None,
    ) -> CompressorPowerResult:
        self._require_positive("suction_pressure", suction_pressure)
        self._require_positive("discharge_pressure", discharge_pressure)
        if discharge_pressure <= suction_pressure:
            raise ValueError("discharge_pressure must be greater than suction_pressure")
        self._require_positive("suction_temperature", suction_temperature)
        self._require_positive("mass_flow", mass_flow)
        self._require_positive("molecular_weight", molecular_weight)
        if specific_heat_ratio <= 1.0:
            raise ValueError("specific_heat_ratio must be greater than 1")
        self._require_positive("compressibility", compressibility)
        self._require_fraction("polytropic_efficiency", polytropic_efficiency)
        if rated_power is not None:
            self._require_positive("rated_power", rated_power)

        k = specific_heat_ratio
        pressure_ratio = discharge_pressure / suction_pressure
        exponent = (k - 1.0) / (k * polytropic_efficiency)
        # Specific gas constant in J/(kg K): R_universal / (M in kg/mol).
        specific_r = _UNIVERSAL_GAS_CONSTANT / (molecular_weight / 1000.0)

        head_j_kg = (
            compressibility
            * specific_r
            * suction_temperature
            * (1.0 / exponent)
            * (pressure_ratio ** exponent - 1.0)
        )
        discharge_temperature = suction_temperature * pressure_ratio ** exponent
        gas_power_kw = mass_flow * head_j_kg / polytropic_efficiency / 1000.0

        if rated_power is not None:
            power_margin_ratio: float | None = rated_power / gas_power_kw
        else:
            power_margin_ratio = None
        warning = self._warning(power_margin_ratio)

        return CompressorPowerResult(
            pressure_ratio=round(pressure_ratio, 4),
            polytropic_head_kj_kg=round(head_j_kg / 1000.0, 4),
            discharge_temperature_k=round(discharge_temperature, 3),
            gas_power_kw=round(gas_power_kw, 3),
            power_margin_ratio=(
                None if power_margin_ratio is None else round(power_margin_ratio, 4)
            ),
            compressor_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Single stage with constant k and Z and an ideal-gas head form.",
                "Polytropic head uses Hp = Z R T1 (n / (n - 1)) [(P2 / P1)^((n-1)/n) - 1].",
                "No intercooling, mechanical losses, surge, or vendor curves are included.",
                "Move to validated NeqSim Compressor with real-gas properties and qualified review.",
            ),
        )

    def _warning(self, power_margin_ratio: float | None) -> str:
        if power_margin_ratio is None:
            return "no-rating"
        if power_margin_ratio < 1.0:
            return "over-rated"
        if power_margin_ratio < self.watch_threshold:
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
