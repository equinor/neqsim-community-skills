from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt

# N6 numeric constant for the IEC 60534 mass-flow gas equation
# with W in kg/h, pressures in bar, and density in kg/m3.
_N6 = 27.3
# Kv (m3/h with dP in bar) to Cv (US gpm with dP in psi) conversion.
_KV_TO_CV = 1.156


@dataclass(frozen=True)
class ControlValveCvResult:
    service: str
    required_kv: float
    required_cv: float
    choked: bool
    choke_limit: float
    cv_margin_ratio: float | None
    valve_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class ControlValveCvModel:
    """Educational control-valve Cv screening placeholder.

    Estimates the required flow coefficient and a choked-flow flag using the
    public IEC 60534-2-1 / ISA-75.01 sizing equations for liquid and gas service.
    """

    def __init__(self, watch_threshold: float = 1.2) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self.watch_threshold = watch_threshold

    def evaluate(
        self,
        *,
        service: str,
        inlet_pressure: float,
        pressure_drop: float,
        # Liquid service
        flow_rate: float | None = None,
        specific_gravity: float | None = None,
        vapor_pressure: float = 0.0,
        critical_pressure: float | None = None,
        fl: float = 0.9,
        # Gas service
        mass_flow: float | None = None,
        inlet_density: float | None = None,
        specific_heat_ratio: float = 1.3,
        xt: float = 0.7,
        # Optional rating
        rated_cv: float | None = None,
    ) -> ControlValveCvResult:
        normalized = service.strip().lower()
        if normalized not in {"liquid", "gas"}:
            raise ValueError("service must be 'liquid' or 'gas'")
        self._require_positive("inlet_pressure", inlet_pressure)
        self._require_positive("pressure_drop", pressure_drop)
        if pressure_drop >= inlet_pressure:
            raise ValueError("pressure_drop must be smaller than inlet_pressure")
        if rated_cv is not None:
            self._require_positive("rated_cv", rated_cv)

        if normalized == "liquid":
            kv, choked, choke_limit = self._liquid(
                inlet_pressure=inlet_pressure,
                pressure_drop=pressure_drop,
                flow_rate=flow_rate,
                specific_gravity=specific_gravity,
                vapor_pressure=vapor_pressure,
                critical_pressure=critical_pressure,
                fl=fl,
            )
        else:
            kv, choked, choke_limit = self._gas(
                inlet_pressure=inlet_pressure,
                pressure_drop=pressure_drop,
                mass_flow=mass_flow,
                inlet_density=inlet_density,
                specific_heat_ratio=specific_heat_ratio,
                xt=xt,
            )

        required_cv = kv * _KV_TO_CV
        cv_margin_ratio: float | None = None
        if rated_cv is not None:
            cv_margin_ratio = rated_cv / required_cv
        warning = self._warning(choked, cv_margin_ratio)

        return ControlValveCvResult(
            service=normalized,
            required_kv=round(kv, 4),
            required_cv=round(required_cv, 4),
            choked=choked,
            choke_limit=round(choke_limit, 4),
            cv_margin_ratio=(None if cv_margin_ratio is None else round(cv_margin_ratio, 4)),
            valve_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Liquid sizing uses Kv = Q * sqrt(SG / dP) with FF and FL choke check.",
                "Gas sizing uses the IEC 60534 mass-flow form with expansion factor Y.",
                "FF = 0.96 - 0.28 * sqrt(Pv / Pc); choked when dP >= FL^2 (P1 - FF Pv).",
                "Cv = 1.156 * Kv; single-phase, fully turbulent, no piping geometry factor.",
                "Move to validated NeqSim ThrottlingValve/ControlValve and qualified review.",
            ),
        )

    def _liquid(
        self,
        *,
        inlet_pressure: float,
        pressure_drop: float,
        flow_rate: float | None,
        specific_gravity: float | None,
        vapor_pressure: float,
        critical_pressure: float | None,
        fl: float,
    ) -> tuple[float, bool, float]:
        if flow_rate is None or specific_gravity is None:
            raise ValueError(
                "liquid service requires flow_rate and specific_gravity"
            )
        self._require_positive("flow_rate", flow_rate)
        self._require_positive("specific_gravity", specific_gravity)
        self._require_finite("vapor_pressure", vapor_pressure)
        if vapor_pressure < 0.0:
            raise ValueError("vapor_pressure must not be negative")
        self._require_fraction("fl", fl)

        if critical_pressure is not None and vapor_pressure > 0.0:
            self._require_positive("critical_pressure", critical_pressure)
            ff = 0.96 - 0.28 * sqrt(vapor_pressure / critical_pressure)
        else:
            ff = 0.96
        choked_dp = fl * fl * (inlet_pressure - ff * vapor_pressure)
        choked = pressure_drop >= choked_dp
        sizing_dp = min(pressure_drop, choked_dp) if choked else pressure_drop
        sizing_dp = max(sizing_dp, 1.0e-9)
        kv = flow_rate * sqrt(specific_gravity / sizing_dp)
        return kv, choked, choked_dp

    def _gas(
        self,
        *,
        inlet_pressure: float,
        pressure_drop: float,
        mass_flow: float | None,
        inlet_density: float | None,
        specific_heat_ratio: float,
        xt: float,
    ) -> tuple[float, bool, float]:
        if mass_flow is None or inlet_density is None:
            raise ValueError("gas service requires mass_flow and inlet_density")
        self._require_positive("mass_flow", mass_flow)
        self._require_positive("inlet_density", inlet_density)
        if specific_heat_ratio <= 1.0:
            raise ValueError("specific_heat_ratio must be greater than 1")
        self._require_fraction("xt", xt)

        x = pressure_drop / inlet_pressure
        fk = specific_heat_ratio / 1.4
        x_choked = fk * xt
        choked = x >= x_choked
        x_eff = min(x, x_choked)
        y = 1.0 - x_eff / (3.0 * fk * xt)
        y = max(0.667, min(1.0, y))
        denom = _N6 * y * sqrt(x_eff * inlet_pressure * inlet_density)
        kv = mass_flow / denom
        return kv, choked, x_choked

    def _warning(self, choked: bool, cv_margin_ratio: float | None) -> str:
        if choked:
            return "choked"
        if cv_margin_ratio is None:
            return "no-rating"
        if cv_margin_ratio < 1.0:
            return "under-sized"
        if cv_margin_ratio < self.watch_threshold:
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
