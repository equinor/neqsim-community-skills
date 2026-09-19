from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import asin, atan2, cos, degrees, isfinite, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000.0
_VALID_SYSTEMS = ("cartesian", "geographic")


@dataclass(frozen=True)
class RouteWaypoint:
    name: str
    x: float
    y: float
    depth_m: float


@dataclass(frozen=True)
class RouteSegment:
    from_name: str
    to_name: str
    horizontal_km: float
    length_3d_km: float
    depth_change_m: float
    slope_deg: float


@dataclass(frozen=True)
class PipeRouteResult:
    waypoint_count: int
    coordinate_system: str
    segments: tuple[RouteSegment, ...]
    kp_profile: tuple[dict[str, float], ...]
    total_horizontal_length_km: float
    total_route_length_km: float
    net_elevation_change_m: float
    total_rise_m: float
    total_descent_m: float
    max_slope_deg: float
    slope_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class PipeRouteModel:
    """Educational pipe-route length and elevation-profile screening placeholder."""

    def __init__(self, max_slope_deg: float = 15.0) -> None:
        self._require_positive("max_slope_deg", max_slope_deg)
        self.max_slope_deg = max_slope_deg

    def evaluate(
        self,
        *,
        waypoints,
        coordinate_system: str = "cartesian",
    ) -> PipeRouteResult:
        system = self._normalize_system(coordinate_system)
        route = self._normalize_waypoints(waypoints)

        if len(route) < 2:
            raise ValueError("at least two waypoints are required")

        segments: list[RouteSegment] = []
        cumulative_horizontal_m = 0.0
        cumulative_route_m = 0.0
        total_rise_m = 0.0
        total_descent_m = 0.0
        max_slope_deg = 0.0

        kp_profile: list[dict[str, float]] = [
            {
                "name_index": 0.0,
                "kp_km": 0.0,
                "depth_m": round(route[0].depth_m, 2),
            }
        ]

        for index in range(len(route) - 1):
            start = route[index]
            end = route[index + 1]
            horizontal_m = self._horizontal_distance_m(start, end, system)
            depth_change = end.depth_m - start.depth_m
            length_3d_m = sqrt(horizontal_m**2 + depth_change**2)
            slope_deg = self._segment_slope_deg(horizontal_m, depth_change)

            cumulative_horizontal_m += horizontal_m
            cumulative_route_m += length_3d_m
            if depth_change < 0.0:
                total_rise_m += -depth_change
            else:
                total_descent_m += depth_change
            max_slope_deg = max(max_slope_deg, slope_deg)

            segments.append(
                RouteSegment(
                    from_name=start.name,
                    to_name=end.name,
                    horizontal_km=round(horizontal_m / 1000.0, 4),
                    length_3d_km=round(length_3d_m / 1000.0, 4),
                    depth_change_m=round(depth_change, 2),
                    slope_deg=round(slope_deg, 3),
                )
            )
            kp_profile.append(
                {
                    "name_index": float(index + 1),
                    "kp_km": round(cumulative_horizontal_m / 1000.0, 4),
                    "depth_m": round(end.depth_m, 2),
                }
            )

        net_change = route[0].depth_m - route[-1].depth_m

        return PipeRouteResult(
            waypoint_count=len(route),
            coordinate_system=system,
            segments=tuple(segments),
            kp_profile=tuple(kp_profile),
            total_horizontal_length_km=round(cumulative_horizontal_m / 1000.0, 4),
            total_route_length_km=round(cumulative_route_m / 1000.0, 4),
            net_elevation_change_m=round(net_change, 2),
            total_rise_m=round(total_rise_m, 2),
            total_descent_m=round(total_descent_m, 2),
            max_slope_deg=round(max_slope_deg, 3),
            slope_warning=self._slope_warning(max_slope_deg),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational route geometry screening placeholder only.",
                "Route length follows the supplied waypoints, not an optimised corridor.",
                "Depth is seabed water depth, positive downwards.",
                "Net positive elevation change means the route ends shallower than it starts.",
                "Slope flags candidate steep sections only; no span or stability analysis is done.",
                "Move to validated NeqSim hydraulic and flow assurance workflows and qualified review.",
            ),
        )

    def _slope_warning(self, max_slope_deg: float) -> str:
        if max_slope_deg >= self.max_slope_deg:
            return "high"
        if max_slope_deg >= 0.8 * self.max_slope_deg:
            return "watch"
        return "ok"

    def _horizontal_distance_m(
        self, start: RouteWaypoint, end: RouteWaypoint, system: str
    ) -> float:
        if system == "geographic":
            return self._haversine_m(start.x, start.y, end.x, end.y)
        delta_x = end.x - start.x
        delta_y = end.y - start.y
        return sqrt(delta_x**2 + delta_y**2)

    @staticmethod
    def _segment_slope_deg(horizontal_m: float, depth_change_m: float) -> float:
        return degrees(atan2(abs(depth_change_m), horizontal_m))

    def _normalize_waypoints(self, waypoints) -> list[RouteWaypoint]:
        if waypoints is None:
            raise ValueError("waypoints must be provided")
        normalized: list[RouteWaypoint] = []
        for raw in waypoints:
            name = str(raw["name"]).strip()
            if not name:
                raise ValueError("each waypoint must have a non-empty name")
            x = float(raw["x"])
            y = float(raw["y"])
            depth = float(raw.get("depth_m", 0.0))
            self._require_finite(f"{name}.x", x)
            self._require_finite(f"{name}.y", y)
            self._require_finite(f"{name}.depth_m", depth)
            if depth < 0.0:
                raise ValueError(f"{name}.depth_m must be non-negative")
            normalized.append(RouteWaypoint(name=name, x=x, y=y, depth_m=depth))
        return normalized

    @staticmethod
    def _normalize_system(coordinate_system: str) -> str:
        system = str(coordinate_system).strip().lower()
        if system not in _VALID_SYSTEMS:
            raise ValueError(
                f"coordinate_system must be one of {_VALID_SYSTEMS}, got {coordinate_system!r}"
            )
        return system

    @staticmethod
    def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        phi1 = radians(lat1)
        phi2 = radians(lat2)
        delta_phi = radians(lat2 - lat1)
        delta_lambda = radians(lon2 - lon1)
        haversine = (
            sin(delta_phi / 2.0) ** 2
            + cos(phi1) * cos(phi2) * sin(delta_lambda / 2.0) ** 2
        )
        return 2.0 * EARTH_RADIUS_M * asin(sqrt(haversine))

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
