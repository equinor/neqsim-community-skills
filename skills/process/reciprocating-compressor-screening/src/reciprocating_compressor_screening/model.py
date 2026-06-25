from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Optional, Tuple


@dataclass(frozen=True)
class ReciprocatingCompressorResult:
    pressure_ratio: float
    stages: int
    stage_pressure_ratio: float
    volumetric_efficiency: float
    actual_inlet_capacity_m3_h: float
    discharge_temperature_k: float
    rod_load_ratio: Optional[float]
    capacity_warning: str
    rod_load_warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class ReciprocatingCompressorModel:
    """Educational reciprocating-compressor screening (API 618 / API 619 style).

    Estimates volumetric efficiency, actual inlet capacity, discharge
    temperature, required staging, and a rod-load utilisation ratio using the
    open clearance-volumetric-efficiency relation. Screening only.
    """

    def __init__(
        self,
        *,
        max_stage_ratio: float = 4.0,
        max_discharge_temperature_k: float = 423.15,
    ) -> None:
        self._require_positive("max_stage_ratio", max_stage_ratio)
        self._require_positive("max_discharge_temperature_k", max_discharge_temperature_k)
        self.max_stage_ratio = max_stage_ratio
        self.max_discharge_temperature_k = max_discharge_temperature_k

    def evaluate(
        self,
        *,
        suction_pressure: float,
        discharge_pressure: float,
        suction_temperature: float,
        swept_volume_rate_m3_h: float,
        clearance_fraction: float = 0.12,
        specific_heat_ratio: float = 1.3,
        leakage_allowance: float = 0.03,
        rated_rod_load_kn: Optional[float] = None,
        piston_area_m2: Optional[float] = None,
    ) -> ReciprocatingCompressorResult:
        self._require_positive("suction_pressure", suction_pressure)
        self._require_positive("discharge_pressure", discharge_pressure)
        if discharge_pressure <= suction_pressure:
            raise ValueError("discharge_pressure must be greater than suction_pressure")
        self._require_positive("suction_temperature", suction_temperature)
        self._require_positive("swept_volume_rate_m3_h", swept_volume_rate_m3_h)
        self._require_fraction("clearance_fraction", clearance_fraction)
        if specific_heat_ratio <= 1.0:
            raise ValueError("specific_heat_ratio must be greater than 1")
        self._require_unit_interval("leakage_allowance", leakage_allowance)
        if rated_rod_load_kn is not None:
            self._require_positive("rated_rod_load_kn", rated_rod_load_kn)
        if piston_area_m2 is not None:
            self._require_positive("piston_area_m2", piston_area_m2)

        k = specific_heat_ratio
        overall_ratio = discharge_pressure / suction_pressure

        # Number of stages so each stage stays below max_stage_ratio.
        stages = 1
        while overall_ratio ** (1.0 / stages) > self.max_stage_ratio:
            stages += 1
        stage_ratio = overall_ratio ** (1.0 / stages)

        # Clearance volumetric efficiency: VE = 1 - C (r^(1/k) - 1) - L.
        ve = 1.0 - clearance_fraction * (stage_ratio ** (1.0 / k) - 1.0) - leakage_allowance
        ve = max(ve, 0.0)
        actual_capacity = swept_volume_rate_m3_h * ve

        # Discharge temperature for the first stage (isentropic).
        discharge_temperature = suction_temperature * stage_ratio ** ((k - 1.0) / k)

        # Rod-load utilisation: gas load = dP * piston area.
        rod_load_ratio: Optional[float] = None
        if rated_rod_load_kn is not None and piston_area_m2 is not None:
            delta_p_pa = (discharge_pressure - suction_pressure) * 1.0e5 / stages
            gas_rod_load_kn = delta_p_pa * piston_area_m2 / 1000.0
            rod_load_ratio = gas_rod_load_kn / rated_rod_load_kn

        capacity_warning = self._capacity_warning(ve, discharge_temperature)
        rod_load_warning = self._rod_load_warning(rod_load_ratio)

        return ReciprocatingCompressorResult(
            pressure_ratio=round(overall_ratio, 4),
            stages=stages,
            stage_pressure_ratio=round(stage_ratio, 4),
            volumetric_efficiency=round(ve, 4),
            actual_inlet_capacity_m3_h=round(actual_capacity, 3),
            discharge_temperature_k=round(discharge_temperature, 3),
            rod_load_ratio=(None if rod_load_ratio is None else round(rod_load_ratio, 4)),
            capacity_warning=capacity_warning,
            rod_load_warning=rod_load_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (API 618 / API 619 style).",
                "Volumetric efficiency VE = 1 - C (r^(1/k) - 1) - L with constant k.",
                "Staging splits the overall ratio into equal stage ratios below max_stage_ratio.",
                "Discharge temperature is isentropic; no valve losses or real-gas effects.",
                "Rod load uses gas load only; inertia and reversal are not modelled.",
                "Move to a validated reciprocating-compressor model and qualified review.",
            ),
        )

    def _capacity_warning(self, ve: float, discharge_temperature: float) -> str:
        if discharge_temperature > self.max_discharge_temperature_k:
            return "discharge-temp-high"
        if ve < 0.6:
            return "low-volumetric-efficiency"
        if ve < 0.7:
            return "watch"
        return "ok"

    @staticmethod
    def _rod_load_warning(rod_load_ratio: Optional[float]) -> str:
        if rod_load_ratio is None:
            return "no-rating"
        if rod_load_ratio > 1.0:
            return "rod-load-exceeded"
        if rod_load_ratio > 0.9:
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
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1)")

    @classmethod
    def _require_unit_interval(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in the interval [0, 1)")
