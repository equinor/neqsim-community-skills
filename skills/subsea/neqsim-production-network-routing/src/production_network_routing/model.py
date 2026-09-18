from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

_SEVERITY = {"ok": 0, "watch": 1, "high": 2, "not_assessed": -1}


@dataclass(frozen=True)
class WellFlowResult:
    name: str
    manifold: str
    reservoir_pressure_bara: float
    flowing_bottomhole_pressure_bara: float
    drawdown_bar: float
    productivity_index_sm3_per_day_bar: float
    rate_sm3_per_day: float
    tubing_head_pressure_bara: float
    flow_warning: str


@dataclass(frozen=True)
class ManifoldResult:
    name: str
    well_count: int
    total_rate_sm3_per_day: float
    manifold_pressure_bara: float | None
    flowline_length_km: float
    flowline_dp_bar: float
    riser_dp_bar: float
    arrival_pressure_bara: float | None
    arrival_margin_bar: float | None
    arrival_warning: str


@dataclass(frozen=True)
class ProductionNetworkResult:
    host_name: str
    required_arrival_pressure_bara: float
    wells: tuple[WellFlowResult, ...]
    manifolds: tuple[ManifoldResult, ...]
    total_rate_sm3_per_day: float
    min_arrival_pressure_bara: float | None
    overall_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class RegulatedWellResult:
    name: str
    manifold: str
    reservoir_pressure_bara: float
    flowing_bottomhole_pressure_bara: float
    drawdown_bar: float
    productivity_index_sm3_per_day_bar: float
    rate_sm3_per_day: float
    flow_warning: str


@dataclass(frozen=True)
class RegulatedFlowResult:
    target_inlet_pressure_bara: float
    segment_dp_bar: float
    wells: tuple[RegulatedWellResult, ...]
    total_rate_sm3_per_day: float
    flowing_well_count: int
    overall_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]



class ProductionNetworkModel:
    """Educational production-network routing screening placeholder.

    Routes wells through manifolds and flowlines/risers to a host and rolls up
    a screening arrival pressure. Well rates use a simple linear inflow
    (productivity index); network pressure drop uses a supplied screening
    gradient. It is a transparent placeholder only: real inflow, multiphase
    hydraulics, and arrival conditions must come from validated NeqSim tools
    (``PipeBeggsAndBrills``, ``SimpleReservoir``, MCP ``runPipeline`` /
    ``runProcess`` / ``runFlowAssurance``).
    """

    def __init__(self) -> None:
        pass

    def evaluate(
        self,
        *,
        wells,
        manifolds,
        host_name: str = "HOST",
        required_arrival_pressure_bara: float,
    ) -> ProductionNetworkResult:
        self._require_positive(
            "required_arrival_pressure_bara", required_arrival_pressure_bara
        )
        manifold_rows = self._normalize_manifolds(manifolds)
        well_rows = self._normalize_wells(wells, set(manifold_rows))

        well_results: list[WellFlowResult] = []
        for well in well_rows:
            drawdown = well["reservoir_pressure_bara"] - well["fbhp_bara"]
            rate = well["pi"] * max(0.0, drawdown)
            flow_warning = "high" if rate <= 0.0 else "ok"
            well_results.append(
                WellFlowResult(
                    name=well["name"],
                    manifold=well["manifold"],
                    reservoir_pressure_bara=round(well["reservoir_pressure_bara"], 3),
                    flowing_bottomhole_pressure_bara=round(well["fbhp_bara"], 3),
                    drawdown_bar=round(drawdown, 3),
                    productivity_index_sm3_per_day_bar=round(well["pi"], 5),
                    rate_sm3_per_day=round(rate, 3),
                    tubing_head_pressure_bara=round(well["thp_bara"], 3),
                    flow_warning=flow_warning,
                )
            )

        manifold_results: list[ManifoldResult] = []
        for manifold in manifold_rows.values():
            routed = [w for w in well_results if w.manifold == manifold["name"]]
            total_rate = sum(w.rate_sm3_per_day for w in routed)
            flowline_dp = (
                manifold["gradient_bar_per_km"] * manifold["flowline_length_km"]
            )

            if not routed:
                manifold_results.append(
                    ManifoldResult(
                        name=manifold["name"],
                        well_count=0,
                        total_rate_sm3_per_day=0.0,
                        manifold_pressure_bara=None,
                        flowline_length_km=round(manifold["flowline_length_km"], 3),
                        flowline_dp_bar=round(flowline_dp, 3),
                        riser_dp_bar=round(manifold["riser_dp_bar"], 3),
                        arrival_pressure_bara=None,
                        arrival_margin_bar=None,
                        arrival_warning="high",
                    )
                )
                continue

            # Most-constrained well sets the manifold collection pressure.
            manifold_pressure = min(w.tubing_head_pressure_bara for w in routed)
            arrival = manifold_pressure - flowline_dp - manifold["riser_dp_bar"]
            margin = arrival - required_arrival_pressure_bara
            arrival_warning = self._arrival_warning(
                margin, required_arrival_pressure_bara
            )

            manifold_results.append(
                ManifoldResult(
                    name=manifold["name"],
                    well_count=len(routed),
                    total_rate_sm3_per_day=round(total_rate, 3),
                    manifold_pressure_bara=round(manifold_pressure, 3),
                    flowline_length_km=round(manifold["flowline_length_km"], 3),
                    flowline_dp_bar=round(flowline_dp, 3),
                    riser_dp_bar=round(manifold["riser_dp_bar"], 3),
                    arrival_pressure_bara=round(arrival, 3),
                    arrival_margin_bar=round(margin, 3),
                    arrival_warning=arrival_warning,
                )
            )

        total_rate = sum(m.total_rate_sm3_per_day for m in manifold_results)
        arrivals = [
            m.arrival_pressure_bara
            for m in manifold_results
            if m.arrival_pressure_bara is not None
        ]
        min_arrival = min(arrivals) if arrivals else None

        overall_warning = self._worst(
            *[w.flow_warning for w in well_results],
            *[m.arrival_warning for m in manifold_results],
        )

        return ProductionNetworkResult(
            host_name=str(host_name).strip(),
            required_arrival_pressure_bara=round(required_arrival_pressure_bara, 3),
            wells=tuple(well_results),
            manifolds=tuple(manifold_results),
            total_rate_sm3_per_day=round(total_rate, 3),
            min_arrival_pressure_bara=(
                None if min_arrival is None else round(min_arrival, 3)
            ),
            overall_warning=overall_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational production-network routing screening placeholder only.",
                "Well rate uses a linear productivity-index inflow, not a real IPR.",
                "Manifold collection pressure is the lowest routed well THP (screening).",
                "Flowline/riser pressure drop uses a supplied screening gradient, not multiphase hydraulics.",
                "No gas/oil/water phase split, temperature, or hydrate check is performed.",
                "Use NeqSim PipeBeggsAndBrills, SimpleReservoir, and MCP runPipeline/runProcess for real arrival conditions.",
            ),
        )

    def regulate_flow_from_inlet_pressure(
        self,
        *,
        wells,
        target_inlet_pressure_bara: float,
        segment_dp_bar=None,
    ) -> RegulatedFlowResult:
        """Screen well flow regulated by a facility inlet/separator pressure.

        Solves each well's rate from a fixed facility inlet pressure and the
        reservoir pressure, mirroring how a NeqSim ``WellFlowlineNetwork`` (or a
        single-train ``Adjuster``) iterates the manifold pressure to hold a
        target endpoint pressure. The flowing bottomhole pressure is the target
        inlet pressure plus a screening sum of segment pressure drops; the rate
        uses a linear productivity-index inflow. Screening only.
        """
        self._require_positive(
            "target_inlet_pressure_bara", target_inlet_pressure_bara
        )

        default_dp = {"well": 60.0, "choke": 10.0, "flowline": 5.0, "riser": 8.0}
        if segment_dp_bar is None:
            segment_dp_bar = default_dp
        segment_total = 0.0
        for key, value in dict(segment_dp_bar).items():
            dp = float(value)
            self._require_non_negative(f"segment_dp_bar.{key}", dp)
            segment_total += dp

        if not wells:
            raise ValueError("at least one well is required")

        results: list[RegulatedWellResult] = []
        seen = set()
        for raw in wells:
            name = str(raw["name"]).strip()
            if not name:
                raise ValueError("each well must have a non-empty name")
            if name in seen:
                raise ValueError(f"duplicate well name {name!r}")
            seen.add(name)
            manifold = str(raw.get("manifold", "")).strip()
            reservoir_pressure = float(raw["reservoir_pressure_bara"])
            pi = float(raw["productivity_index_sm3_per_day_bar"])
            self._require_positive(
                f"{name}.reservoir_pressure_bara", reservoir_pressure
            )
            self._require_positive(
                f"{name}.productivity_index_sm3_per_day_bar", pi
            )

            well_dp = float(raw.get("segment_dp_bar", segment_total))
            self._require_non_negative(f"{name}.segment_dp_bar", well_dp)
            fbhp = target_inlet_pressure_bara + well_dp
            drawdown = reservoir_pressure - fbhp

            if drawdown <= 0.0:
                rate = 0.0
                flow_warning = "high"
            else:
                rate = pi * drawdown
                max_rate = raw.get("max_rate_sm3_per_day")
                if max_rate is not None:
                    max_rate = float(max_rate)
                    self._require_positive(f"{name}.max_rate_sm3_per_day", max_rate)
                    if rate > max_rate:
                        rate = max_rate
                        flow_warning = "watch"
                    else:
                        flow_warning = "ok"
                else:
                    flow_warning = "ok"

            results.append(
                RegulatedWellResult(
                    name=name,
                    manifold=manifold,
                    reservoir_pressure_bara=round(reservoir_pressure, 3),
                    flowing_bottomhole_pressure_bara=round(fbhp, 3),
                    drawdown_bar=round(drawdown, 3),
                    productivity_index_sm3_per_day_bar=round(pi, 5),
                    rate_sm3_per_day=round(rate, 3),
                    flow_warning=flow_warning,
                )
            )

        total_rate = sum(w.rate_sm3_per_day for w in results)
        flowing = sum(1 for w in results if w.rate_sm3_per_day > 0.0)
        overall_warning = self._worst(*[w.flow_warning for w in results])

        return RegulatedFlowResult(
            target_inlet_pressure_bara=round(target_inlet_pressure_bara, 3),
            segment_dp_bar=round(segment_total, 3),
            wells=tuple(results),
            total_rate_sm3_per_day=round(total_rate, 3),
            flowing_well_count=flowing,
            overall_warning=overall_warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational pressure-regulated flow screening placeholder only.",
                "Flow is solved from a fixed facility inlet/separator pressure and each well's reservoir pressure.",
                "Flowing bottomhole pressure is the inlet pressure plus a screening sum of segment pressure drops.",
                "Well rate uses a linear productivity-index inflow, not a real IPR.",
                "No multiphase hydraulics, temperature, or hydrate check is performed.",
                "Use NeqSim WellFlowlineNetwork.setTargetEndpointPressure (or a single-train Adjuster) for a real pressure-regulated solve.",
            ),
        )

    @staticmethod
    def _arrival_warning(margin: float, required: float) -> str:
        if margin < 0.0:
            return "high"
        if margin < 0.1 * required:
            return "watch"
        return "ok"

    @staticmethod
    def _worst(*warnings: str) -> str:
        assessed = [w for w in warnings if w != "not_assessed"]
        if not assessed:
            return "not_assessed"
        return max(assessed, key=lambda w: _SEVERITY[w])

    def _normalize_manifolds(self, manifolds):
        if not manifolds:
            raise ValueError("at least one manifold is required")
        rows = {}
        for raw in manifolds:
            name = str(raw["name"]).strip()
            if not name:
                raise ValueError("each manifold must have a non-empty name")
            if name in rows:
                raise ValueError(f"duplicate manifold name {name!r}")
            length = float(raw["flowline_length_km"])
            gradient = float(raw["pressure_gradient_bar_per_km"])
            riser_dp = float(raw.get("riser_dp_bar", 0.0))
            self._require_non_negative(f"{name}.flowline_length_km", length)
            self._require_non_negative(f"{name}.pressure_gradient_bar_per_km", gradient)
            self._require_non_negative(f"{name}.riser_dp_bar", riser_dp)
            rows[name] = {
                "name": name,
                "flowline_length_km": length,
                "gradient_bar_per_km": gradient,
                "riser_dp_bar": riser_dp,
            }
        return rows

    def _normalize_wells(self, wells, manifold_names):
        if not wells:
            raise ValueError("at least one well is required")
        rows = []
        seen = set()
        for raw in wells:
            name = str(raw["name"]).strip()
            if not name:
                raise ValueError("each well must have a non-empty name")
            if name in seen:
                raise ValueError(f"duplicate well name {name!r}")
            seen.add(name)
            manifold = str(raw["manifold"]).strip()
            if manifold not in manifold_names:
                raise ValueError(
                    f"well {name!r} routes to unknown manifold {manifold!r}"
                )
            reservoir_pressure = float(raw["reservoir_pressure_bara"])
            fbhp = float(raw["flowing_bottomhole_pressure_bara"])
            pi = float(raw["productivity_index_sm3_per_day_bar"])
            thp = float(raw["tubing_head_pressure_bara"])
            self._require_positive(f"{name}.reservoir_pressure_bara", reservoir_pressure)
            self._require_non_negative(
                f"{name}.flowing_bottomhole_pressure_bara", fbhp
            )
            self._require_positive(f"{name}.productivity_index_sm3_per_day_bar", pi)
            self._require_positive(f"{name}.tubing_head_pressure_bara", thp)
            rows.append(
                {
                    "name": name,
                    "manifold": manifold,
                    "reservoir_pressure_bara": reservoir_pressure,
                    "fbhp_bara": fbhp,
                    "pi": pi,
                    "thp_bara": thp,
                }
            )
        return rows

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
