from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

_GRAVITY = 9.80665  # m/s^2
_BAR_TO_PA = 1.0e5


@dataclass(frozen=True)
class PumpHydraulicsResult:
    hydraulic_power_kw: float
    shaft_power_kw: float
    npsh_available_m: float | None
    npsh_margin_m: float | None
    bep_ratio: float | None
    pump_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class PumpHydraulicsModel:
    """Educational centrifugal-pump hydraulics screening placeholder.

    Estimates hydraulic and shaft power, the available NPSH, and the
    best-efficiency-point (BEP) flow ratio using public pump relations.
    """

    def __init__(
        self,
        npsh_watch_margin: float = 1.0,
        bep_low: float = 0.70,
        bep_high: float = 1.20,
    ) -> None:
        self._require_positive("npsh_watch_margin", npsh_watch_margin)
        self._require_positive("bep_low", bep_low)
        self._require_positive("bep_high", bep_high)
        if bep_high <= bep_low:
            raise ValueError("bep_high must be greater than bep_low")
        self.npsh_watch_margin = npsh_watch_margin
        self.bep_low = bep_low
        self.bep_high = bep_high

    def evaluate(
        self,
        *,
        flow_rate: float,
        head: float,
        density: float,
        efficiency: float = 0.70,
        suction_pressure: float | None = None,
        vapor_pressure: float | None = None,
        static_suction_head: float = 0.0,
        friction_loss: float = 0.0,
        npsh_required: float | None = None,
        bep_flow_rate: float | None = None,
    ) -> PumpHydraulicsResult:
        self._require_positive("flow_rate", flow_rate)
        self._require_positive("head", head)
        self._require_positive("density", density)
        self._require_fraction("efficiency", efficiency)
        self._require_finite("static_suction_head", static_suction_head)
        self._require_finite("friction_loss", friction_loss)
        if friction_loss < 0.0:
            raise ValueError("friction_loss must not be negative")
        if npsh_required is not None:
            self._require_positive("npsh_required", npsh_required)
        if bep_flow_rate is not None:
            self._require_positive("bep_flow_rate", bep_flow_rate)

        # Convert volumetric flow from m3/h to m3/s.
        flow_m3s = flow_rate / 3600.0
        hydraulic_power_w = density * _GRAVITY * flow_m3s * head
        hydraulic_power_kw = hydraulic_power_w / 1000.0
        shaft_power_kw = hydraulic_power_kw / efficiency

        npsh_available: float | None = None
        npsh_margin: float | None = None
        if suction_pressure is not None and vapor_pressure is not None:
            self._require_positive("suction_pressure", suction_pressure)
            self._require_positive("vapor_pressure", vapor_pressure)
            pressure_head = (
                (suction_pressure - vapor_pressure) * _BAR_TO_PA / (density * _GRAVITY)
            )
            npsh_available = pressure_head + static_suction_head - friction_loss
            if npsh_required is not None:
                npsh_margin = npsh_available - npsh_required

        bep_ratio: float | None = None
        if bep_flow_rate is not None:
            bep_ratio = flow_rate / bep_flow_rate

        warning = self._warning(npsh_margin, bep_ratio)

        return PumpHydraulicsResult(
            hydraulic_power_kw=round(hydraulic_power_kw, 4),
            shaft_power_kw=round(shaft_power_kw, 4),
            npsh_available_m=(None if npsh_available is None else round(npsh_available, 3)),
            npsh_margin_m=(None if npsh_margin is None else round(npsh_margin, 3)),
            bep_ratio=(None if bep_ratio is None else round(bep_ratio, 4)),
            pump_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Hydraulic power uses P = rho g Q H with constant density.",
                "Shaft power uses P_shaft = P_hydraulic / efficiency.",
                "NPSHa uses (P_suction - P_vapor) / (rho g) + static head - friction loss.",
                "BEP ratio uses Q / Q_bep against a public preferred operating window.",
                "Affinity laws, suction recirculation, and vendor curves are not modeled.",
                "Move to validated NeqSim Pump with real-fluid properties and qualified review.",
            ),
        )

    def _warning(
        self, npsh_margin: float | None, bep_ratio: float | None
    ) -> str:
        if npsh_margin is not None and npsh_margin <= 0.0:
            return "npsh-deficit"
        if bep_ratio is not None and (bep_ratio < 0.50 or bep_ratio > self.bep_high):
            return "off-bep"
        if npsh_margin is not None and npsh_margin < self.npsh_watch_margin:
            return "watch"
        if bep_ratio is not None and (
            bep_ratio < self.bep_low or bep_ratio > 1.10
        ):
            return "watch"
        if npsh_margin is None and bep_ratio is None:
            return "no-rating"
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
