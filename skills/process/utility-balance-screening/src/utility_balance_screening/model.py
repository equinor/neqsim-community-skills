from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt
from typing import Optional, Tuple

# Constant cooling-water properties used by the screening relation.
_WATER_DENSITY_KG_M3 = 1000.0
_WATER_CP_KJ_KG_K = 4.18
_AIR_DESIGN_MARGIN = 1.3


@dataclass(frozen=True)
class UtilityBalanceResult:
    instrument_air_demand_nm3_h: float
    cooling_water_flow_m3_h: float
    wobbe_index_mj_sm3: Optional[float]
    wobbe_in_band: Optional[bool]
    air_utilisation: Optional[float]
    cooling_utilisation: Optional[float]
    utility_warning: str
    wobbe_warning: str
    neqsim_available: bool
    assumptions: Tuple[str, ...]


class UtilityBalanceModel:
    """Educational utility-balance screening (NORSOK U-001 / ISA-7.0.01 style).

    Estimates instrument air demand, cooling water flow from a duty and a
    temperature rise, a fuel gas Wobbe index with a band check, and capacity
    utilisation ratios using open utility relations. Screening only.
    """

    def __init__(
        self,
        *,
        watch_utilisation: float = 0.9,
    ) -> None:
        self._require_positive("watch_utilisation", watch_utilisation)
        if watch_utilisation >= 1.0:
            raise ValueError("watch_utilisation must be less than 1")
        self.watch_utilisation = watch_utilisation

    def evaluate(
        self,
        *,
        instrument_air_consumers: int,
        air_per_consumer_nm3_h: float = 0.3,
        cooling_duty_kw: float = 0.0,
        cooling_water_delta_t_c: float = 10.0,
        fuel_gas_lhv_mj_sm3: Optional[float] = None,
        fuel_gas_relative_density: Optional[float] = None,
        wobbe_min: float = 47.2,
        wobbe_max: float = 51.41,
        instrument_air_capacity_nm3_h: Optional[float] = None,
        cooling_water_capacity_m3_h: Optional[float] = None,
    ) -> UtilityBalanceResult:
        self._require_non_negative_int("instrument_air_consumers", instrument_air_consumers)
        self._require_positive("air_per_consumer_nm3_h", air_per_consumer_nm3_h)
        self._require_non_negative("cooling_duty_kw", cooling_duty_kw)
        self._require_positive("cooling_water_delta_t_c", cooling_water_delta_t_c)
        self._require_wobbe_band(wobbe_min, wobbe_max)
        if instrument_air_capacity_nm3_h is not None:
            self._require_positive("instrument_air_capacity_nm3_h", instrument_air_capacity_nm3_h)
        if cooling_water_capacity_m3_h is not None:
            self._require_positive("cooling_water_capacity_m3_h", cooling_water_capacity_m3_h)

        # Fuel gas inputs must be supplied as a pair.
        if (fuel_gas_lhv_mj_sm3 is None) != (fuel_gas_relative_density is None):
            raise ValueError(
                "fuel_gas_lhv_mj_sm3 and fuel_gas_relative_density must be supplied together"
            )

        # Instrument air demand with a fixed design margin.
        air_demand = instrument_air_consumers * air_per_consumer_nm3_h * _AIR_DESIGN_MARGIN

        # Cooling water flow in m3/h from the duty and the temperature rise.
        cooling_flow = (
            cooling_duty_kw
            * 3600.0
            / (_WATER_DENSITY_KG_M3 * _WATER_CP_KJ_KG_K * cooling_water_delta_t_c)
        )

        # Fuel gas Wobbe index and band check.
        wobbe_index: Optional[float] = None
        wobbe_in_band: Optional[bool] = None
        if fuel_gas_lhv_mj_sm3 is not None and fuel_gas_relative_density is not None:
            self._require_positive("fuel_gas_lhv_mj_sm3", fuel_gas_lhv_mj_sm3)
            self._require_positive("fuel_gas_relative_density", fuel_gas_relative_density)
            wobbe_index = fuel_gas_lhv_mj_sm3 / sqrt(fuel_gas_relative_density)
            wobbe_in_band = wobbe_min <= wobbe_index <= wobbe_max

        # Capacity utilisation ratios.
        air_utilisation: Optional[float] = None
        if instrument_air_capacity_nm3_h is not None:
            air_utilisation = air_demand / instrument_air_capacity_nm3_h
        cooling_utilisation: Optional[float] = None
        if cooling_water_capacity_m3_h is not None:
            cooling_utilisation = cooling_flow / cooling_water_capacity_m3_h

        utility_warning = self._utility_warning(air_utilisation, cooling_utilisation)
        wobbe_warning = self._wobbe_warning(wobbe_in_band)

        return UtilityBalanceResult(
            instrument_air_demand_nm3_h=round(air_demand, 3),
            cooling_water_flow_m3_h=round(cooling_flow, 3),
            wobbe_index_mj_sm3=(None if wobbe_index is None else round(wobbe_index, 3)),
            wobbe_in_band=wobbe_in_band,
            air_utilisation=(None if air_utilisation is None else round(air_utilisation, 4)),
            cooling_utilisation=(
                None if cooling_utilisation is None else round(cooling_utilisation, 4)
            ),
            utility_warning=utility_warning,
            wobbe_warning=wobbe_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only (NORSOK U-001 / ISA-7.0.01 style).",
                "Instrument air demand uses a fixed 1.3 design margin.",
                "Cooling water uses constant rho=1000 kg/m3 and cp=4.18 kJ/kg.K.",
                "Wobbe index uses W = LHV / sqrt(relative_density) against one band.",
                "Capacity utilisation is demand divided by installed capacity.",
                "Move to a validated utility balance and qualified utility design.",
            ),
        )

    def _utility_warning(
        self,
        air_utilisation: Optional[float],
        cooling_utilisation: Optional[float],
    ) -> str:
        if air_utilisation is not None and air_utilisation > 1.0:
            return "air-undersized"
        if cooling_utilisation is not None and cooling_utilisation > 1.0:
            return "cooling-undersized"
        utilisations = [u for u in (air_utilisation, cooling_utilisation) if u is not None]
        if any(u > self.watch_utilisation for u in utilisations):
            return "watch"
        return "ok"

    @staticmethod
    def _wobbe_warning(wobbe_in_band: Optional[bool]) -> str:
        if wobbe_in_band is None:
            return "no-fuel-data"
        if not wobbe_in_band:
            return "wobbe-out-of-range"
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
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")

    @staticmethod
    def _require_non_negative_int(name: str, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    @classmethod
    def _require_wobbe_band(cls, wobbe_min: float, wobbe_max: float) -> None:
        cls._require_positive("wobbe_min", wobbe_min)
        cls._require_positive("wobbe_max", wobbe_max)
        if wobbe_max <= wobbe_min:
            raise ValueError("wobbe_max must be greater than wobbe_min")
