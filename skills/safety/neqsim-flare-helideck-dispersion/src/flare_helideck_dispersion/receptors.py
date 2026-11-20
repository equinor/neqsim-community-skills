"""Platform geometry, helideck points and helicopter flight-path receptors.

All coordinates are east/north/up metres relative to the flare tip, with the up
coordinate being height above sea level. Bearings are degrees true, clockwise from north.

The default flight-path assumptions (radial paths across the obstacle-free sector, a
climb or descent gradient of 5 degrees, 1 nautical mile length) are SCREENING
ASSUMPTIONS. Replace them with the approved approach and departure paths of the
installation when those are available.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

NAUTICAL_MILE_M = 1852.0
"""One nautical mile in metres."""


def grid_to_true(
    east_m: float, north_m: float, platform_north_azimuth_deg: float
) -> tuple[float, float]:
    """Convert platform-grid coordinates to true-north east/north coordinates.

    Args:
        east_m: Platform-grid easting, m.
        north_m: Platform-grid northing, m.
        platform_north_azimuth_deg: Azimuth of platform north, degrees clockwise from
            true north.

    Returns:
        Tuple ``(east_true_m, north_true_m)``.
    """
    a = math.radians(platform_north_azimuth_deg)
    return (
        north_m * math.sin(a) + east_m * math.cos(a),
        north_m * math.cos(a) - east_m * math.sin(a),
    )


@dataclass
class FlightPathSettings:
    """Discretisation of the helicopter approach and departure paths.

    Attributes:
        length_m: Path length from the helideck, m (default one nautical mile).
        distance_step_m: Spacing of points along a path, m.
        climb_deg: Climb or descent gradient above the helideck, degrees.
        bearing_step_deg: Spacing of radial path bearings across the obstacle-free
            sector, degrees. Use 5 degrees or finer: 15 degrees is wider than the
            plume at 0.5 to 1.5 km and under-samples exceedance hours.
    """

    length_m: float = NAUTICAL_MILE_M
    distance_step_m: float = 25.0
    climb_deg: float = 5.0
    bearing_step_deg: float = 5.0

    def __post_init__(self) -> None:
        """Validate the settings.

        Raises:
            ValueError: If a value is non-positive or the climb is not below 90 degrees.
        """
        if min(self.length_m, self.distance_step_m, self.bearing_step_deg) <= 0.0:
            raise ValueError("path length and steps must be positive")
        if not 0.0 <= self.climb_deg < 90.0:
            raise ValueError("climb_deg must be in [0, 90)")


@dataclass
class PlatformGeometry:
    """Generic platform layout: flare tip, helideck and obstacle-free sector.

    The tip is the coordinate origin. The helideck is placed by its horizontal distance
    and azimuth as seen from the tip.

    Attributes:
        tip_height_asl_m: Flare-tip height above sea level, m.
        helideck_height_asl_m: Helideck surface height above sea level, m.
        helideck_distance_m: Horizontal distance tip to helideck, m.
        helideck_azimuth_from_tip_deg: Azimuth of the helideck seen from the tip.
        reference_height_above_deck_m: Height above the deck at which exposure is
            assessed (helicopter reference point), m.
        deck_radius_m: Radius of the helideck assessment points around the centre, m
            (half the D-value for a circular deck).
        ofs_start_deg: Start of the obstacle-free sector (clockwise), degrees true.
        ofs_end_deg: End of the obstacle-free sector (clockwise), degrees true.
        flight_paths: Flight-path discretisation.
    """

    tip_height_asl_m: float = 124.0
    helideck_height_asl_m: float = 76.0
    helideck_distance_m: float = 240.0
    helideck_azimuth_from_tip_deg: float = 240.0
    reference_height_above_deck_m: float = 5.0
    deck_radius_m: float = 13.0
    ofs_start_deg: float = 135.0
    ofs_end_deg: float = 345.0
    flight_paths: FlightPathSettings = field(default_factory=FlightPathSettings)

    def __post_init__(self) -> None:
        """Validate the layout.

        Raises:
            ValueError: If heights or distances are non-physical.
        """
        if self.helideck_distance_m <= 0.0 or self.deck_radius_m <= 0.0:
            raise ValueError("helideck distance and deck radius must be positive")
        if self.tip_height_asl_m <= 0.0 or self.helideck_height_asl_m < 0.0:
            raise ValueError("heights above sea level must be non-negative")

    @property
    def ofs_width_deg(self) -> float:
        """Angular width of the obstacle-free sector, degrees."""
        width = (self.ofs_end_deg - self.ofs_start_deg) % 360.0
        return width if width > 0.0 else 360.0

    @property
    def tip_position(self) -> np.ndarray:
        """Tip position ``(0, 0, height)``."""
        return np.array([0.0, 0.0, self.tip_height_asl_m])

    @property
    def helideck_position(self) -> np.ndarray:
        """Helideck assessment point: deck centre at the reference height above deck."""
        az = math.radians(self.helideck_azimuth_from_tip_deg)
        return np.array(
            [
                self.helideck_distance_m * math.sin(az),
                self.helideck_distance_m * math.cos(az),
                self.helideck_height_asl_m + self.reference_height_above_deck_m,
            ]
        )

    @property
    def vertical_separation_m(self) -> float:
        """Tip height minus helideck assessment height, m."""
        return self.tip_height_asl_m - float(self.helideck_position[2])

    @property
    def azimuth_toward_deck_wind_from_deg(self) -> float:
        """Wind direction (FROM) that carries a passive plume from the tip to the deck."""
        return (self.helideck_azimuth_from_tip_deg + 180.0) % 360.0

    @classmethod
    def from_platform_grid(
        cls,
        tip_grid_en: tuple[float, float],
        helideck_grid_en: tuple[float, float],
        platform_north_azimuth_deg: float,
        **kwargs: Any,
    ) -> PlatformGeometry:
        """Build a geometry from platform-grid coordinates.

        Args:
            tip_grid_en: Tip ``(easting, northing)`` on the platform grid, m.
            helideck_grid_en: Helideck ``(easting, northing)`` on the platform grid, m.
            platform_north_azimuth_deg: Azimuth of platform north, degrees true.
            **kwargs: Other :class:`PlatformGeometry` fields (heights, sector).

        Returns:
            The geometry with the helideck placed by distance and azimuth from the tip.
        """
        te, tn = grid_to_true(*tip_grid_en, platform_north_azimuth_deg)
        he, hn = grid_to_true(*helideck_grid_en, platform_north_azimuth_deg)
        de, dn = he - te, hn - tn
        return cls(
            helideck_distance_m=math.hypot(de, dn),
            helideck_azimuth_from_tip_deg=math.degrees(math.atan2(de, dn)) % 360.0,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlatformGeometry:
        """Build a geometry from a mapping (for example parsed JSON).

        Args:
            data: Mapping of field names; ``flight_paths`` may be a nested mapping.

        Returns:
            The geometry.
        """
        values = dict(data)
        paths = values.pop("flight_paths", None)
        known = set(cls.__dataclass_fields__) - {"flight_paths"}
        geometry = cls(**{k: v for k, v in values.items() if k in known})
        if paths:
            geometry.flight_paths = FlightPathSettings(**paths)
        return geometry


def angular_difference_deg(a: float, b: float) -> float:
    """Smallest absolute angular difference between two bearings.

    Args:
        a: First bearing, degrees.
        b: Second bearing, degrees.

    Returns:
        Difference in ``[0, 180]`` degrees.
    """
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


class Receptors:
    """Helideck points and flight-path points derived from a geometry.

    Args:
        geometry: The platform geometry.
    """

    def __init__(self, geometry: PlatformGeometry) -> None:
        self.geometry = geometry
        fp = geometry.flight_paths
        self.deck = geometry.helideck_position
        r = geometry.deck_radius_m
        self.deck_points = np.array(
            [
                [self.deck[0] + dx, self.deck[1] + dy, self.deck[2]]
                for dx, dy in [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r)]
            ]
        )
        width = geometry.ofs_width_deg
        self.path_bearings = (
            geometry.ofs_start_deg + np.arange(0.0, width + 1e-6, fp.bearing_step_deg)
        ) % 360.0
        self.path_distances = np.arange(0.0, fp.length_m + 0.1, fp.distance_step_m)
        self.n_path_points = len(self.path_distances)
        self.all_paths = np.vstack([self.path_points(b) for b in self.path_bearings])

    def path_points(self, bearing_deg: float) -> np.ndarray:
        """3-D points of a climb or descent path from the helideck along a bearing.

        Args:
            bearing_deg: Bearing of the path away from the helideck, degrees true.

        Returns:
            Array ``(n, 3)`` of east, north, up coordinates, m.
        """
        b = math.radians(bearing_deg)
        fp = self.geometry.flight_paths
        e = self.deck[0] + self.path_distances * math.sin(b)
        n = self.deck[1] + self.path_distances * math.cos(b)
        z = self.deck[2] + self.path_distances * math.tan(math.radians(fp.climb_deg))
        return np.column_stack([e, n, z])

    def in_obstacle_free_sector(self, bearing_deg: float) -> bool:
        """Whether a bearing lies inside the obstacle-free sector.

        Args:
            bearing_deg: Bearing, degrees true.

        Returns:
            ``True`` if inside the sector (edges included).
        """
        g = self.geometry
        return (bearing_deg - g.ofs_start_deg) % 360.0 <= g.ofs_width_deg

    def into_wind_bearing(self, wind_from_deg: float) -> float:
        """Take-off or landing bearing for a given wind.

        Helicopters take off and land into the wind. When the wind is from inside the
        obstacle-free sector the path points into the wind; otherwise the nearest sector
        edge is used and the path is then NOT truly into wind (a conservative
        reduction of the into-wind benefit, but not an operational rule).

        Args:
            wind_from_deg: Direction the wind blows FROM, degrees true.

        Returns:
            Path bearing, degrees true.
        """
        w = wind_from_deg % 360.0
        if self.in_obstacle_free_sector(w):
            return w
        g = self.geometry
        d_start = angular_difference_deg(w, g.ofs_start_deg)
        d_end = angular_difference_deg(w, g.ofs_end_deg)
        return g.ofs_start_deg if d_start < d_end else g.ofs_end_deg

    def warnings(self) -> list[str]:
        """Return assumption and resolution warnings for the receptor set.

        Returns:
            List of warning strings.
        """
        out = [
            (
                "flight paths are screening assumptions (radial paths across the "
                f"obstacle-free sector, {self.geometry.flight_paths.climb_deg:.1f} deg gradient) unless the approved paths are "
                "supplied"
            )
        ]
        step = self.geometry.flight_paths.bearing_step_deg
        if step > 5.0:
            out.append(
                f"flight-path bearing step {step:.1f} deg is wider than the plume at 0.5-1.5 "
                "km; exceedance hours are under-sampled (use 5 deg or finer)"
            )
        return out

    def describe(self) -> dict[str, float | None]:
        """Return a compact description for results files.

        Returns:
            Dictionary with counts and the obstacle-free sector.
        """
        g = self.geometry
        return {
            "n_bearings": len(self.path_bearings),
            "bearing_step_deg": g.flight_paths.bearing_step_deg,
            "n_points_per_path": int(self.n_path_points),
            "ofs_start_deg": g.ofs_start_deg,
            "ofs_end_deg": g.ofs_end_deg,
            "path_length_m": g.flight_paths.length_m,
            "climb_deg": g.flight_paths.climb_deg,
        }
