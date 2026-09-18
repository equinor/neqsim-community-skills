from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import atan2, degrees, isfinite


@dataclass(frozen=True)
class Sounding:
    distance_m: float
    depth_m: float


@dataclass(frozen=True)
class SlopeInterval:
    from_distance_m: float
    to_distance_m: float
    depth_change_m: float
    slope_deg: float


@dataclass(frozen=True)
class BathymetryResult:
    sounding_count: int
    sorted_soundings: tuple[Sounding, ...]
    interpolated: tuple[dict[str, float], ...]
    slopes: tuple[SlopeInterval, ...]
    steep_sections: tuple[SlopeInterval, ...]
    max_slope_deg: float
    min_depth_m: float
    max_depth_m: float
    slope_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class BathymetryProfileModel:
    """Educational bathymetry profile screening placeholder."""

    def __init__(self, max_slope_deg: float = 10.0) -> None:
        self._require_positive("max_slope_deg", max_slope_deg)
        self.max_slope_deg = max_slope_deg

    def evaluate(
        self,
        *,
        soundings,
        query_distances=None,
    ) -> BathymetryResult:
        points = self._normalize_soundings(soundings)
        if len(points) < 2:
            raise ValueError("at least two soundings are required")

        ordered = tuple(sorted(points, key=lambda item: item.distance_m))
        distances = [item.distance_m for item in ordered]
        if len(set(distances)) != len(distances):
            raise ValueError("sounding distances must be unique")

        slopes: list[SlopeInterval] = []
        steep_sections: list[SlopeInterval] = []
        max_slope_deg = 0.0
        for index in range(len(ordered) - 1):
            start = ordered[index]
            end = ordered[index + 1]
            distance_change = end.distance_m - start.distance_m
            depth_change = end.depth_m - start.depth_m
            slope_deg = degrees(atan2(abs(depth_change), distance_change))
            interval = SlopeInterval(
                from_distance_m=round(start.distance_m, 3),
                to_distance_m=round(end.distance_m, 3),
                depth_change_m=round(depth_change, 3),
                slope_deg=round(slope_deg, 3),
            )
            slopes.append(interval)
            max_slope_deg = max(max_slope_deg, slope_deg)
            if slope_deg >= self.max_slope_deg:
                steep_sections.append(interval)

        interpolated: list[dict[str, float]] = []
        for query in self._normalize_query(query_distances):
            depth, clamped = self._interpolate_depth(ordered, query)
            interpolated.append(
                {
                    "distance_m": round(query, 3),
                    "depth_m": round(depth, 3),
                    "clamped": 1.0 if clamped else 0.0,
                }
            )

        depths = [item.depth_m for item in ordered]

        return BathymetryResult(
            sounding_count=len(ordered),
            sorted_soundings=ordered,
            interpolated=tuple(interpolated),
            slopes=tuple(slopes),
            steep_sections=tuple(steep_sections),
            max_slope_deg=round(max_slope_deg, 3),
            min_depth_m=round(min(depths), 3),
            max_depth_m=round(max(depths), 3),
            slope_warning=self._slope_warning(max_slope_deg),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational bathymetry screening placeholder only.",
                "Depth is interpolated linearly between sorted soundings.",
                "Query distances outside the sounding range are clamped and flagged.",
                "Slope resolution is limited by sounding spacing.",
                "No free-span, on-bottom-stability, scour, or soil analysis is performed.",
                "Move to qualified free-span and stability analyses and validated NeqSim hydraulic review.",
            ),
        )

    def _slope_warning(self, max_slope_deg: float) -> str:
        if max_slope_deg >= self.max_slope_deg:
            return "high"
        if max_slope_deg >= 0.8 * self.max_slope_deg:
            return "watch"
        return "ok"

    @staticmethod
    def _interpolate_depth(ordered, query: float):
        first = ordered[0]
        last = ordered[-1]
        if query <= first.distance_m:
            return first.depth_m, query < first.distance_m
        if query >= last.distance_m:
            return last.depth_m, query > last.distance_m
        for index in range(len(ordered) - 1):
            start = ordered[index]
            end = ordered[index + 1]
            if start.distance_m <= query <= end.distance_m:
                span = end.distance_m - start.distance_m
                fraction = (query - start.distance_m) / span
                depth = start.depth_m + fraction * (end.depth_m - start.depth_m)
                return depth, False
        return last.depth_m, True

    def _normalize_soundings(self, soundings) -> list[Sounding]:
        if soundings is None:
            raise ValueError("soundings must be provided")
        normalized: list[Sounding] = []
        for raw in soundings:
            distance = float(raw["distance_m"])
            depth = float(raw["depth_m"])
            self._require_finite("distance_m", distance)
            self._require_finite("depth_m", depth)
            if distance < 0.0:
                raise ValueError("distance_m must be non-negative")
            if depth < 0.0:
                raise ValueError("depth_m must be non-negative")
            normalized.append(Sounding(distance_m=distance, depth_m=depth))
        return normalized

    def _normalize_query(self, query_distances) -> list[float]:
        if query_distances is None:
            return []
        normalized: list[float] = []
        for raw in query_distances:
            value = float(raw)
            self._require_finite("query distance", value)
            if value < 0.0:
                raise ValueError("query distance must be non-negative")
            normalized.append(value)
        return normalized

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
