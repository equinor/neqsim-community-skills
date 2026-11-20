"""Facility-wide screening dispersion: any release source to any receptor.

The helideck study is one preset of a general question: *can gas from an unignited
release at one place on a facility reach another place, and in which winds?* This
module answers it for any number of release sources (flare tip, cold vent, PSV tail pipe,
atmospheric vent, drain or purge outlet) and any number of named receptors:

* helideck and flight paths (see :func:`helideck_facility`),
* HVAC and combustion-air intakes, accommodation doors and windows, control room,
* muster areas, lifeboat stations and escape routes,
* crane cabs, laydown areas, walkways and work areas,
* ignition sources such as turbine exhausts, flare boom or hot-work areas,
* the neighbouring installation, a boat approach or any other point, area or line.

A receptor is a set of points (a point, a disc, a rectangle, a polyline, a fan of radial
paths or a path that follows the wind). The plume model, the wind sweep and the
conditional-exceedance semantics are those of :mod:`.study`. Coordinates are
east/north/up metres in one facility frame with true-north axes and height above sea
level; any origin may be used. Wind directions are the direction the wind blows FROM.

The concentration is reported as percent of the ``lfl_vol_frac`` of the release case.
For a toxic or other limit set ``lfl_vol_frac`` to that limit (a volume fraction of the
fuel part of the gas); "% LFL" then reads "% of limit". Results are conditional on an
unignited release and are never annual frequencies.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .model import Release, ReleaseCase, jet_consistency_check
from .receptors import (
    NAUTICAL_MILE_M,
    PlatformGeometry,
    Receptors,
    angular_difference_deg,
)
from .study import (
    STUDY_SEMANTICS,
    StudySettings,
    exceedance_by_speed_bin,
    exceedance_pct,
    threshold_key,
)
from .wind import WindTable, pasquill_by_speed

RECEPTOR_KINDS = (
    "helideck",
    "flight_path",
    "air_intake",
    "accommodation",
    "control_room",
    "muster_area",
    "lifeboat_station",
    "escape_route",
    "crane_cab",
    "work_area",
    "walkway",
    "ignition_source",
    "neighbour",
    "other",
)
"""Receptor kinds used in the documentation; any text is accepted."""

SOURCE_KINDS = (
    "flare_tip",
    "cold_vent",
    "psv_tailpipe",
    "atmospheric_vent",
    "purge_or_drain",
    "other",
)
"""Release-source kinds used in the documentation; any text is accepted."""


@dataclass
class Source:
    """A release point on the facility.

    Attributes:
        name: Source identifier carried into every output.
        east_m: Easting in the facility frame, m.
        north_m: Northing in the facility frame, m.
        height_asl_m: Release height above sea level, m.
        kind: Free-text kind, for example ``flare_tip`` or ``cold_vent``.
        tilt_deg: Release inclination above horizontal, degrees; ``None`` uses the
            study setting. A vertical vent is 90 degrees, a flare tip 20 to 70.
        description: Free text.
    """

    name: str
    east_m: float = 0.0
    north_m: float = 0.0
    height_asl_m: float = 50.0
    kind: str = "flare_tip"
    tilt_deg: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        """Validate the source.

        Raises:
            ValueError: If the name is empty, the height is not positive or the tilt is
                outside (0, 90].
        """
        if not self.name:
            raise ValueError("source name must not be empty")
        if self.height_asl_m <= 0.0:
            raise ValueError("source height above sea level must be positive")
        if self.tilt_deg is not None and not 0.0 < self.tilt_deg <= 90.0:
            raise ValueError("tilt_deg must be in (0, 90]")

    @property
    def position(self) -> np.ndarray:
        """Source position ``(east, north, up)``, m."""
        return np.array([self.east_m, self.north_m, self.height_asl_m])

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Source:
        """Build a source from a mapping (for example parsed JSON).

        Args:
            data: Mapping with the field names of :class:`Source`; ``height_m`` and
                ``id`` are accepted as aliases of ``height_asl_m`` and ``name``.

        Returns:
            The source.
        """
        values = dict(data)
        for old, new in (("height_m", "height_asl_m"), ("id", "name")):
            if old in values and new not in values:
                values[new] = values.pop(old)
        return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})


def _as_points(points: Any) -> np.ndarray:
    """Return an ``(n, 3)`` float array or raise ``ValueError``."""
    arr = np.asarray(points, dtype=float)
    if arr.ndim == 1 and arr.size == 3:
        arr = arr.reshape(1, 3)
    if arr.ndim != 2 or arr.shape[1] != 3 or arr.shape[0] < 1:
        raise ValueError("receptor points must be an array of (east, north, up) rows")
    if not np.all(np.isfinite(arr)):
        raise ValueError("receptor points must be finite")
    return arr


def _densify(vertices: np.ndarray, spacing_m: float) -> np.ndarray:
    """Points along a polyline with at most ``spacing_m`` between neighbours."""
    if spacing_m <= 0.0:
        raise ValueError("spacing must be positive")
    pts = [vertices[0]]
    for a, b in itertools.pairwise(vertices):
        n = max(math.ceil(float(np.linalg.norm(b - a)) / spacing_m), 1)
        for t in np.linspace(0.0, 1.0, n + 1)[1:]:
            pts.append(a + (b - a) * t)
    return np.array(pts)


def into_wind_bearing(wind_from_deg: float, start_deg: float, end_deg: float) -> float:
    """Path bearing into the wind, limited to a clear sector.

    Aircraft and boats approach into the wind. When the wind is from inside the sector
    ``start_deg`` to ``end_deg`` (clockwise) the path points into the wind; otherwise the
    nearest sector edge is used (the path is then NOT truly into wind).

    Args:
        wind_from_deg: Direction the wind blows FROM, degrees true.
        start_deg: Start of the clear sector, degrees true.
        end_deg: End of the clear sector (clockwise from the start), degrees true.

    Returns:
        Path bearing, degrees true.
    """
    w = wind_from_deg % 360.0
    width = (end_deg - start_deg) % 360.0 or 360.0
    if (w - start_deg) % 360.0 <= width:
        return w
    d_start = angular_difference_deg(w, start_deg)
    d_end = angular_difference_deg(w, end_deg)
    return start_deg % 360.0 if d_start < d_end else end_deg % 360.0


@dataclass
class Receptor:
    """A named place where the gas concentration is assessed.

    The concentration of a receptor is the maximum over its points. Use the class
    methods to build points, discs, rectangles, polylines, fans of radial paths and
    paths that follow the wind.

    Attributes:
        name: Receptor identifier carried into every output.
        kind: Free-text kind, for example ``air_intake`` or ``muster_area``.
        points: Array ``(n, 3)`` of east, north, up coordinates, m. For a receptor that
            follows the wind this is a placeholder (the origin).
        thresholds_pct_lfl: Exceedance thresholds of this receptor, percent of the
            limit; ``None`` uses the study settings.
        criterion_source: Source of the governing criterion (standard clause, design
            basis); an empty value is reported as a data gap.
        description: Free text.
        path_coords: Optional ``(n, 2)`` array of ``(path bearing, distance from the
            path origin)`` for each point, for reporting along flight paths and routes.
        wind_selector: Optional function that returns the points to assess for a wind
            direction (FROM, degrees). Used for paths that point into the wind.
        spec: The mapping the receptor was built from, kept for provenance.
    """

    name: str
    kind: str
    points: np.ndarray
    thresholds_pct_lfl: tuple[float, ...] | None = None
    criterion_source: str = ""
    description: str = ""
    path_coords: np.ndarray | None = None
    wind_selector: Callable[[float], np.ndarray] | None = field(
        default=None, repr=False, compare=False
    )
    spec: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate and normalise the receptor.

        Raises:
            ValueError: If the name is empty, the points are invalid or a threshold is
                not positive.
        """
        if not self.name:
            raise ValueError("receptor name must not be empty")
        self.points = _as_points(self.points)
        if self.path_coords is not None:
            self.path_coords = np.asarray(self.path_coords, dtype=float)
            if self.path_coords.shape != (len(self.points), 2):
                raise ValueError(
                    "path_coords must have one (bearing, distance) per point"
                )
        if self.thresholds_pct_lfl is not None:
            self.thresholds_pct_lfl = tuple(float(t) for t in self.thresholds_pct_lfl)
            if not self.thresholds_pct_lfl or min(self.thresholds_pct_lfl) <= 0.0:
                raise ValueError("thresholds must be positive")

    @property
    def follows_wind(self) -> bool:
        """Whether the assessed points depend on the wind direction."""
        return self.wind_selector is not None

    def points_for_wind(self, wind_from_deg: float) -> np.ndarray:
        """Points assessed for a wind direction.

        Args:
            wind_from_deg: Direction the wind blows FROM, degrees true.

        Returns:
            Array ``(n, 3)``; the fixed points unless the receptor follows the wind.
        """
        if self.wind_selector is None:
            return self.points
        return _as_points(self.wind_selector(wind_from_deg))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable description (the input spec when it is known)."""
        if self.spec is not None:
            return dict(self.spec)
        return {
            "name": self.name,
            "kind": self.kind,
            "shape": "points",
            "points": self.points.tolist(),
            "thresholds_pct_lfl": (
                None
                if self.thresholds_pct_lfl is None
                else list(self.thresholds_pct_lfl)
            ),
            "criterion_source": self.criterion_source,
            "description": self.description,
        }

    @classmethod
    def point(
        cls,
        name: str,
        kind: str,
        east_m: float,
        north_m: float,
        height_asl_m: float,
        **kw: Any,
    ) -> Receptor:
        """A single point, for example an air intake or a door.

        Args:
            name: Receptor name.
            kind: Receptor kind.
            east_m: Easting, m.
            north_m: Northing, m.
            height_asl_m: Height above sea level, m.
            **kw: Other :class:`Receptor` fields.

        Returns:
            The receptor.
        """
        return cls(name, kind, [[east_m, north_m, height_asl_m]], **kw)

    @classmethod
    def disc(
        cls,
        name: str,
        kind: str,
        east_m: float,
        north_m: float,
        height_asl_m: float,
        radius_m: float,
        **kw: Any,
    ) -> Receptor:
        """A horizontal disc sampled at the centre and four points on the rim.

        Args:
            name: Receptor name.
            kind: Receptor kind.
            east_m: Centre easting, m.
            north_m: Centre northing, m.
            height_asl_m: Assessment height above sea level, m.
            radius_m: Disc radius, m.
            **kw: Other :class:`Receptor` fields.

        Returns:
            The receptor.

        Raises:
            ValueError: If the radius is not positive.
        """
        if radius_m <= 0.0:
            raise ValueError("radius_m must be positive")
        r = radius_m
        offsets = [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r)]
        return cls(
            name,
            kind,
            [[east_m + dx, north_m + dy, height_asl_m] for dx, dy in offsets],
            **kw,
        )

    @classmethod
    def rectangle(
        cls,
        name: str,
        kind: str,
        east_min_m: float,
        north_min_m: float,
        east_max_m: float,
        north_max_m: float,
        heights_asl_m: float | Sequence[float],
        spacing_m: float = 5.0,
        **kw: Any,
    ) -> Receptor:
        """A grid of points over a rectangle, at one or several heights.

        Args:
            name: Receptor name.
            kind: Receptor kind.
            east_min_m: West edge, m.
            north_min_m: South edge, m.
            east_max_m: East edge, m.
            north_max_m: North edge, m.
            heights_asl_m: One height or several heights above sea level, m.
            spacing_m: Grid spacing, m.
            **kw: Other :class:`Receptor` fields.

        Returns:
            The receptor.

        Raises:
            ValueError: If the rectangle is empty or the spacing is not positive.
        """
        if east_max_m < east_min_m or north_max_m < north_min_m or spacing_m <= 0.0:
            raise ValueError("rectangle needs max >= min and a positive spacing")
        es = np.linspace(
            east_min_m,
            east_max_m,
            max(math.ceil((east_max_m - east_min_m) / spacing_m), 1) + 1,
        )
        ns = np.linspace(
            north_min_m,
            north_max_m,
            max(math.ceil((north_max_m - north_min_m) / spacing_m), 1) + 1,
        )
        heights = np.atleast_1d(np.asarray(heights_asl_m, dtype=float))
        grid = [[e, n, z] for z in heights for n in ns for e in es]
        return cls(name, kind, grid, **kw)

    @classmethod
    def polyline(
        cls,
        name: str,
        kind: str,
        vertices: Sequence[Sequence[float]],
        spacing_m: float = 5.0,
        **kw: Any,
    ) -> Receptor:
        """Points along a polyline, for example an escape route or a walkway.

        Args:
            name: Receptor name.
            kind: Receptor kind.
            vertices: Vertices as ``(east, north, up)`` rows, m.
            spacing_m: Maximum spacing of the points, m.
            **kw: Other :class:`Receptor` fields.

        Returns:
            The receptor; ``path_coords`` holds ``(0, distance along the line)``.
        """
        pts = _densify(_as_points(vertices), spacing_m)
        dist = np.concatenate(
            [[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        )
        return cls(
            name,
            kind,
            pts,
            path_coords=np.column_stack([np.zeros(len(pts)), dist]),
            **kw,
        )

    @classmethod
    def fan(
        cls,
        name: str,
        kind: str,
        east_m: float,
        north_m: float,
        height_asl_m: float,
        start_deg: float,
        end_deg: float,
        length_m: float = NAUTICAL_MILE_M,
        distance_step_m: float = 25.0,
        bearing_step_deg: float = 5.0,
        climb_deg: float = 0.0,
        **kw: Any,
    ) -> Receptor:
        """Radial paths over a sector, for example approach and departure paths.

        Args:
            name: Receptor name.
            kind: Receptor kind.
            east_m: Path origin easting, m.
            north_m: Path origin northing, m.
            height_asl_m: Path origin height above sea level, m.
            start_deg: Sector start (clockwise), degrees true.
            end_deg: Sector end (clockwise), degrees true.
            length_m: Path length, m.
            distance_step_m: Spacing of points along a path, m.
            bearing_step_deg: Spacing of path bearings, degrees (5 or finer).
            climb_deg: Climb or descent gradient, degrees.
            **kw: Other :class:`Receptor` fields.

        Returns:
            The receptor; ``path_coords`` holds ``(bearing, distance)`` per point.

        Raises:
            ValueError: If a step or the length is not positive.
        """
        if min(length_m, distance_step_m, bearing_step_deg) <= 0.0:
            raise ValueError("path length and steps must be positive")
        width = (end_deg - start_deg) % 360.0 or 360.0
        bearings = (start_deg + np.arange(0.0, width + 1e-6, bearing_step_deg)) % 360.0
        dists = np.arange(0.0, length_m + 0.1, distance_step_m)
        rise = math.tan(math.radians(climb_deg))
        pts, coords = [], []
        for b in bearings:
            rb = math.radians(b)
            pts.append(
                np.column_stack(
                    [
                        east_m + dists * math.sin(rb),
                        north_m + dists * math.cos(rb),
                        height_asl_m + dists * rise,
                    ]
                )
            )
            coords.append(np.column_stack([np.full(len(dists), b), dists]))
        return cls(name, kind, np.vstack(pts), path_coords=np.vstack(coords), **kw)

    @classmethod
    def into_wind_path(
        cls,
        name: str,
        kind: str,
        east_m: float,
        north_m: float,
        height_asl_m: float,
        clear_start_deg: float,
        clear_end_deg: float,
        length_m: float = NAUTICAL_MILE_M,
        distance_step_m: float = 25.0,
        climb_deg: float = 0.0,
        **kw: Any,
    ) -> Receptor:
        """One path that points into the wind within a clear sector.

        Args:
            name: Receptor name.
            kind: Receptor kind.
            east_m: Path origin easting, m.
            north_m: Path origin northing, m.
            height_asl_m: Path origin height above sea level, m.
            clear_start_deg: Start of the clear sector (clockwise), degrees true.
            clear_end_deg: End of the clear sector, degrees true.
            length_m: Path length, m.
            distance_step_m: Spacing of points along the path, m.
            climb_deg: Climb or descent gradient, degrees.
            **kw: Other :class:`Receptor` fields.

        Returns:
            The receptor; its points follow the wind direction.

        Raises:
            ValueError: If the length or the step is not positive.
        """
        if min(length_m, distance_step_m) <= 0.0:
            raise ValueError("path length and step must be positive")
        dists = np.arange(0.0, length_m + 0.1, distance_step_m)
        rise = math.tan(math.radians(climb_deg))

        def select(wind_from_deg: float) -> np.ndarray:
            b = math.radians(
                into_wind_bearing(wind_from_deg, clear_start_deg, clear_end_deg)
            )
            return np.column_stack(
                [
                    east_m + dists * math.sin(b),
                    north_m + dists * math.cos(b),
                    height_asl_m + dists * rise,
                ]
            )

        return cls(
            name,
            kind,
            [[east_m, north_m, height_asl_m]],
            wind_selector=select,
            **kw,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Receptor:
        """Build a receptor from a mapping (for example parsed JSON).

        ``shape`` selects the constructor: ``point`` (``east_m``, ``north_m``,
        ``height_asl_m``), ``disc`` (plus ``radius_m``), ``rectangle``
        (``east_min_m``, ``north_min_m``, ``east_max_m``, ``north_max_m``,
        ``heights_asl_m``, ``spacing_m``), ``polyline`` (``vertices``, ``spacing_m``),
        ``fan`` (``east_m``, ``north_m``, ``height_asl_m``, ``start_deg``, ``end_deg``,
        ``length_m``, ``distance_step_m``, ``bearing_step_deg``, ``climb_deg``),
        ``into_wind_path`` (origin, ``clear_start_deg``, ``clear_end_deg``, ``length_m``,
        ``distance_step_m``, ``climb_deg``) or ``points`` (``points``). ``name``,
        ``kind``, ``thresholds_pct_lfl``, ``criterion_source`` and ``description`` are
        common.

        Args:
            data: Mapping describing the receptor.

        Returns:
            The receptor, with the mapping kept as ``spec``.

        Raises:
            ValueError: If the shape is unknown.
            KeyError: If a required key is missing.
        """
        d = dict(data)
        shape = d.pop("shape", "point")
        name = d.pop("name")
        kind = d.pop("kind", "other")
        common = {
            k: d.pop(k)
            for k in ("thresholds_pct_lfl", "criterion_source", "description")
            if k in d
        }
        if shape == "point":
            r = cls.point(
                name, kind, d["east_m"], d["north_m"], d["height_asl_m"], **common
            )
        elif shape == "disc":
            r = cls.disc(
                name,
                kind,
                d["east_m"],
                d["north_m"],
                d["height_asl_m"],
                d["radius_m"],
                **common,
            )
        elif shape == "rectangle":
            r = cls.rectangle(
                name,
                kind,
                d["east_min_m"],
                d["north_min_m"],
                d["east_max_m"],
                d["north_max_m"],
                d["heights_asl_m"],
                d.get("spacing_m", 5.0),
                **common,
            )
        elif shape == "polyline":
            r = cls.polyline(
                name, kind, d["vertices"], d.get("spacing_m", 5.0), **common
            )
        elif shape == "fan":
            r = cls.fan(
                name,
                kind,
                d["east_m"],
                d["north_m"],
                d["height_asl_m"],
                d["start_deg"],
                d["end_deg"],
                d.get("length_m", NAUTICAL_MILE_M),
                d.get("distance_step_m", 25.0),
                d.get("bearing_step_deg", 5.0),
                d.get("climb_deg", 0.0),
                **common,
            )
        elif shape == "into_wind_path":
            r = cls.into_wind_path(
                name,
                kind,
                d["east_m"],
                d["north_m"],
                d["height_asl_m"],
                d["clear_start_deg"],
                d["clear_end_deg"],
                d.get("length_m", NAUTICAL_MILE_M),
                d.get("distance_step_m", 25.0),
                d.get("climb_deg", 0.0),
                **common,
            )
        elif shape == "points":
            r = cls(name, kind, d["points"], **common)
        else:
            raise ValueError(f"unknown receptor shape {shape!r}")
        r.spec = dict(data)
        return r


@dataclass
class FacilityRelease:
    """A release case together with the source it comes from.

    Attributes:
        case: The release case.
        source: The release point.
    """

    case: ReleaseCase
    source: Source


def helideck_facility(
    geometry: PlatformGeometry,
    source_name: str = "flare_tip",
    origin_en: tuple[float, float] = (0.0, 0.0),
) -> tuple[Source, list[Receptor]]:
    """The classic flare-tip, helideck and flight-path set as a facility.

    Args:
        geometry: The platform geometry (tip at the origin of its own frame).
        source_name: Name of the flare-tip source.
        origin_en: ``(east, north)`` of the tip in the facility frame, m; the helideck
            and the paths are translated by it.

    Returns:
        Tuple ``(source, receptors)`` with the receptors ``helideck``,
        ``any_flight_path`` and ``into_wind_path``.
    """
    rec = Receptors(geometry)
    shift = np.array([origin_en[0], origin_en[1], 0.0])
    source = Source(
        source_name, origin_en[0], origin_en[1], geometry.tip_height_asl_m, "flare_tip"
    )
    fp = geometry.flight_paths
    deck_xyz = rec.deck + shift
    coords = np.vstack(
        [
            np.column_stack([np.full(rec.n_path_points, b), rec.path_distances])
            for b in rec.path_bearings
        ]
    )
    receptors = [
        Receptor("helideck", "helideck", rec.deck_points + shift),
        Receptor(
            "any_flight_path", "flight_path", rec.all_paths + shift, path_coords=coords
        ),
        Receptor.into_wind_path(
            "into_wind_path",
            "flight_path",
            float(deck_xyz[0]),
            float(deck_xyz[1]),
            float(deck_xyz[2]),
            geometry.ofs_start_deg,
            geometry.ofs_end_deg,
            fp.length_m,
            fp.distance_step_m,
            fp.climb_deg,
        ),
    ]
    return source, receptors


@dataclass
class FacilityCaseArrays:
    """Maximum percent of the limit per receptor for one case and mode.

    All arrays are indexed ``[sector, sub_offset, speed_bin]``.

    Attributes:
        peak: Maximum over the receptor points, by receptor name.
        location: Coordinates ``(..., 3)`` of the maximum, by receptor name.
        point_index: Index of the maximum in the receptor points (``-1`` for a receptor
            that follows the wind), by receptor name.
    """

    peak: dict[str, np.ndarray]
    location: dict[str, np.ndarray]
    point_index: dict[str, np.ndarray]


def build_release(freelease: FacilityRelease, settings: StudySettings) -> Release:
    """Create the plume release of a facility release (source tilt applied).

    Args:
        freelease: Case and source.
        settings: Study settings.

    Returns:
        The release object.
    """
    params = settings.params
    if freelease.source.tilt_deg is not None:
        params = params.replace(tilt_deg=freelease.source.tilt_deg)
    return Release(freelease.case, params)


def run_facility_case(
    release: Release,
    source: Source,
    wind: WindTable,
    receptors: Sequence[Receptor],
    settings: StudySettings,
    mode: str,
) -> FacilityCaseArrays:
    """Evaluate one release over the whole wind table for one plume mode.

    Args:
        release: The release.
        source: The release point.
        wind: Joint wind table.
        receptors: The receptors.
        settings: Study settings.
        mode: ``briggs`` or ``none``.

    Returns:
        The percent-of-limit arrays of every receptor.
    """
    offsets = settings.offsets_for(wind)
    ns, nb = len(wind.sectors), len(wind.speed_bins)
    shape = (ns, len(offsets), nb)
    peak = {r.name: np.zeros(shape) for r in receptors}
    loc = {r.name: np.zeros(shape + (3,)) for r in receptors}
    idx = {r.name: np.full(shape, -1, dtype=int) for r in receptors}
    fixed = [r for r in receptors if not r.follows_wind]
    moving = [r for r in receptors if r.follows_wind]
    stacked = np.vstack([r.points for r in fixed]) if fixed else None
    bounds = np.cumsum([0] + [len(r.points) for r in fixed])
    stabilities = [
        pasquill_by_speed(float(u), settings.stability_scheme)
        for u in wind.speed_rep_ms
    ]
    tip = source.position
    for i in range(ns):
        for j, off in enumerate(offsets):
            wd = (wind.sector_deg[i] + off) % 360.0
            dynamic_pts = {r.name: r.points_for_wind(wd) for r in moving}
            for k in range(nb):
                u = float(wind.speed_rep_ms[k])
                st = stabilities[k]
                if stacked is not None:
                    c = release.pct_lfl(stacked, wd, u, st, tip, mode)
                    for n, r in enumerate(fixed):
                        seg = c[bounds[n] : bounds[n + 1]]
                        m = int(np.argmax(seg))
                        peak[r.name][i, j, k] = seg[m]
                        idx[r.name][i, j, k] = m
                        loc[r.name][i, j, k] = r.points[m]
                for r in moving:
                    pts = dynamic_pts[r.name]
                    c = release.pct_lfl(pts, wd, u, st, tip, mode)
                    m = int(np.argmax(c))
                    peak[r.name][i, j, k] = c[m]
                    loc[r.name][i, j, k] = pts[m]
    return FacilityCaseArrays(peak, loc, idx)


def _thresholds(receptor: Receptor, settings: StudySettings) -> tuple[float, ...]:
    """Exceedance thresholds of a receptor."""
    return receptor.thresholds_pct_lfl or tuple(settings.thresholds_pct_lfl)


def _describe_peak(
    receptor: Receptor,
    source: Source,
    arrays: FacilityCaseArrays,
    wind: WindTable,
    settings: StudySettings,
) -> dict[str, Any]:
    """Worst condition of one receptor: wind, speed, stability and where it occurs."""
    offsets = settings.offsets_for(wind)
    arr = arrays.peak[receptor.name]
    i, j, k = np.unravel_index(int(np.argmax(arr)), arr.shape)
    xyz = arrays.location[receptor.name][i, j, k]
    dx, dy = float(xyz[0] - source.east_m), float(xyz[1] - source.north_m)
    out: dict[str, Any] = {
        "sector": wind.sectors[i],
        "wind_from_deg": float((wind.sector_deg[i] + offsets[j]) % 360.0),
        "speed_bin": wind.speed_bins[k],
        "speed_m_s": float(wind.speed_rep_ms[k]),
        "pasquill_class": pasquill_by_speed(
            float(wind.speed_rep_ms[k]), settings.stability_scheme
        ),
        "point_east_m": float(xyz[0]),
        "point_north_m": float(xyz[1]),
        "point_up_m": float(xyz[2]),
        "distance_from_source_m": math.hypot(dx, dy),
        "bearing_from_source_deg": math.degrees(math.atan2(dx, dy)) % 360.0,
        "height_above_source_m": float(xyz[2] - source.height_asl_m),
    }
    m = int(arrays.point_index[receptor.name][i, j, k])
    if receptor.path_coords is not None and m >= 0:
        out["path_bearing_deg"] = float(receptor.path_coords[m, 0])
        out["path_distance_m"] = float(receptor.path_coords[m, 1])
    return out


def _receptor_summary(
    receptor: Receptor,
    source: Source,
    arrays: FacilityCaseArrays,
    wind: WindTable,
    settings: StudySettings,
) -> dict[str, Any]:
    """Peak, conditional exceedance by threshold and speed bin, and worst condition."""
    arr = arrays.peak[receptor.name]
    thresholds = _thresholds(receptor, settings)
    return {
        "kind": receptor.kind,
        "n_points": len(receptor.points),
        "peak_pct_lfl": float(arr.max()),
        "thresholds_pct_lfl": list(thresholds),
        "exceed_pct_hours": {
            threshold_key(t): exceedance_pct(arr, wind, t) for t in thresholds
        },
        "exceed_by_speed_bin_pct_hours": {
            threshold_key(t): exceedance_by_speed_bin(arr, wind, t) for t in thresholds
        },
        "peak_condition": _describe_peak(receptor, source, arrays, wind, settings),
    }


@dataclass
class FacilityStudyResult:
    """Result of a facility study over several release cases and receptors.

    Attributes:
        settings: The study settings used.
        wind: The wind table.
        sources: The distinct release sources.
        receptors: The receptors.
        releases: Release objects by case name.
        freleases: Case and source pairs in the order given.
        summaries: Per case: tip data, per mode and receptor summaries.
        arrays: Percent-of-limit arrays by ``"<case>_<mode>"``.
        warnings: Warnings found while building the study.
    """

    settings: StudySettings
    wind: WindTable
    sources: list[Source]
    receptors: list[Receptor]
    releases: dict[str, Release]
    freleases: list[FacilityRelease]
    summaries: dict[str, dict[str, Any]]
    arrays: dict[str, FacilityCaseArrays]
    warnings: list[str]

    def exceedance(
        self, case: str, receptor: str, threshold: float, mode: str = "briggs"
    ) -> float:
        """Percent of wind hours at or above any threshold, given a release.

        Args:
            case: Case name.
            receptor: Receptor name.
            threshold: Threshold, percent of the limit.
            mode: Plume mode.

        Returns:
            Percent of all wind hours, conditional on an ongoing release.
        """
        return exceedance_pct(
            self.arrays[f"{case}_{mode}"].peak[receptor], self.wind, threshold
        )

    def ranking(
        self, threshold: float = 20.0, mode: str = "briggs"
    ) -> list[dict[str, Any]]:
        """Case-receptor pairs ranked by exceedance, then peak concentration.

        Args:
            threshold: Ranking threshold, percent of the limit.
            mode: Plume mode.

        Returns:
            Rows with ``case``, ``source``, ``receptor``, ``kind``, ``peak_pct_lfl`` and
            ``exceed_pct_hours``; the worst first.
        """
        rows = []
        for fr in self.freleases:
            arrays = self.arrays[f"{fr.case.name}_{mode}"]
            for r in self.receptors:
                arr = arrays.peak[r.name]
                rows.append(
                    {
                        "case": fr.case.name,
                        "source": fr.source.name,
                        "receptor": r.name,
                        "kind": r.kind,
                        "peak_pct_lfl": float(arr.max()),
                        "exceed_pct_hours": exceedance_pct(arr, self.wind, threshold),
                    }
                )
        rows.sort(key=lambda row: (-row["exceed_pct_hours"], -row["peak_pct_lfl"]))
        return rows

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping of the whole result."""
        return {
            "semantics": STUDY_SEMANTICS,
            "settings": self.settings.to_dict(),
            "wind": {"source": self.wind.metadata.get("source", "supplied")},
            "sources": [s.to_dict() for s in self.sources],
            "receptors": [r.to_dict() for r in self.receptors],
            "summaries": self.summaries,
            "warnings": self.warnings,
        }

    def save(self, out_dir: str | Path) -> tuple[Path, Path]:
        """Write ``facility_results.json`` and ``facility_arrays.npz``.

        Args:
            out_dir: Output directory (created if needed).

        Returns:
            Tuple of the two written paths.
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        json_path = out / "facility_results.json"
        npz_path = out / "facility_arrays.npz"
        json_path.write_text(
            json.dumps(self.to_dict(), indent=1, default=float), encoding="utf-8"
        )
        flat: dict[str, np.ndarray] = {}
        for key, arr in self.arrays.items():
            for name, values in arr.peak.items():
                flat[f"{key}__{name}__peak"] = values
                flat[f"{key}__{name}__xyz"] = arr.location[name]
        np.savez_compressed(npz_path, **flat)
        return json_path, npz_path


def run_facility_study(
    releases: Sequence[FacilityRelease],
    wind: WindTable,
    receptors: Sequence[Receptor],
    settings: StudySettings | None = None,
) -> FacilityStudyResult:
    """Run the wind sweep of every release case against every receptor.

    Args:
        releases: Release cases with their sources.
        wind: Joint wind table (validated here).
        receptors: Receptors; names must be unique.
        settings: Study settings (defaults are used if ``None``).

    Returns:
        The study result with summaries and arrays.

    Raises:
        ValueError: If there is no release or no receptor, or names are not unique.
    """
    settings = settings or StudySettings()
    if not releases or not receptors:
        raise ValueError("a facility study needs at least one release and one receptor")
    for label, names in (
        ("case", [fr.case.name for fr in releases]),
        ("receptor", [r.name for r in receptors]),
    ):
        if len(set(names)) != len(names):
            raise ValueError(f"{label} names must be unique")
    warnings = list(wind.validate())
    warnings.append(
        "plume model is a screening Gaussian model without platform wake, downwash or "
        "building effects; a Gaussian plume is not valid much below 1 m/s"
    )
    for r in receptors:
        if not r.criterion_source:
            warnings.append(f"receptor {r.name!r} has no stated criterion source")
    sources: list[Source] = []
    for fr in releases:
        if fr.source.name not in [s.name for s in sources]:
            sources.append(fr.source)
    built: dict[str, Release] = {}
    summaries: dict[str, dict[str, Any]] = {}
    arrays: dict[str, FacilityCaseArrays] = {}
    for fr in releases:
        release = build_release(fr, settings)
        built[fr.case.name] = release
        entry: dict[str, Any] = {
            "name": fr.case.name,
            "case": fr.case.to_dict(),
            "source": fr.source.to_dict(),
            "tip": dict(release.tip),
            "jet_axial_distance_20pct_lfl_m": release.jet_distance_to(0.2),
            "jet_axial_distance_10pct_lfl_m": release.jet_distance_to(0.1),
            "jet_consistency_20pct_lfl": [],
            "modes": {},
        }
        for k, label in enumerate(wind.speed_bins):
            if wind.speed_rep_ms[k] >= 9.0:
                break
            stab = pasquill_by_speed(
                float(wind.speed_rep_ms[k]), settings.stability_scheme
            )
            check = jet_consistency_check(
                release, float(wind.speed_rep_ms[k]), stab, fr.source.height_asl_m, 0.2
            )
            check["speed_bin"] = label
            entry["jet_consistency_20pct_lfl"].append(check)
        for mode in settings.modes:
            arr = run_facility_case(release, fr.source, wind, receptors, settings, mode)
            arrays[f"{fr.case.name}_{mode}"] = arr
            entry["modes"][mode] = {
                "receptors": {
                    r.name: _receptor_summary(r, fr.source, arr, wind, settings)
                    for r in receptors
                }
            }
        summaries[fr.case.name] = entry
    return FacilityStudyResult(
        settings,
        wind,
        sources,
        list(receptors),
        built,
        list(releases),
        summaries,
        arrays,
        warnings,
    )


def facility_section(
    study: FacilityStudyResult,
    case: str,
    wind_from_deg: float,
    speed_m_s: float,
    s_range_m: tuple[float, float] = (-50.0, 600.0),
    z_range_m: tuple[float, float] = (2.0, 200.0),
    ds_m: float = 5.0,
    dz_m: float = 2.0,
    azimuth_deg: float | None = None,
    mode: str = "briggs",
    lateral_tolerance_m: float = 15.0,
) -> dict[str, Any]:
    """Vertical section of the plume through a source, with the receptors in the plane.

    The section is the vertical plane through the source of ``case`` along ``azimuth_deg``
    (default: the direction the plume travels, ``wind_from + 180``). It is written in the
    layout expected by overlay tools: ``s`` metres along the plane, ``z`` metres of height
    above sea level and ``values`` of shape ``(len(z), len(s))`` in percent of the limit.
    Receptors with a point within ``lateral_tolerance_m`` of the plane are returned as
    marks (``s``, ``z``, label) so that they can be drawn on a schematic; a receptor is a
    mark of the picture, not a registered position.

    Args:
        study: Facility study result (provides the release, source and receptors).
        case: Case name.
        wind_from_deg: Direction the wind blows FROM, degrees true.
        speed_m_s: Wind speed at the reference height, m/s.
        s_range_m: Distance range along the plane from the source, m.
        z_range_m: Height range above sea level, m.
        ds_m: Distance step, m.
        dz_m: Height step, m.
        azimuth_deg: Azimuth of the plane, degrees true; ``None`` uses the travel direction.
        mode: Plume mode.
        lateral_tolerance_m: Largest distance of a receptor point from the plane for it to
            be marked, m.

    Returns:
        Mapping with ``s``, ``z``, ``values``, ``value_label``, ``levels``, ``title``,
        ``source``, ``azimuth_deg``, ``peak_pct_lfl`` and ``marks``.

    Raises:
        KeyError: If the case is unknown.
        ValueError: If a range or step is not positive.
    """
    if (
        ds_m <= 0.0
        or dz_m <= 0.0
        or s_range_m[1] <= s_range_m[0]
        or z_range_m[1] <= z_range_m[0]
    ):
        raise ValueError("section ranges must be increasing and steps positive")
    fr = next(f for f in study.freleases if f.case.name == case)
    release = study.releases[case]
    azimuth = (
        (wind_from_deg + 180.0) % 360.0 if azimuth_deg is None else azimuth_deg % 360.0
    )
    stab = pasquill_by_speed(float(speed_m_s), study.settings.stability_scheme)
    s = np.arange(s_range_m[0], s_range_m[1] + 0.5 * ds_m, ds_m)
    z = np.arange(z_range_m[0], z_range_m[1] + 0.5 * dz_m, dz_m)
    gs, gz = np.meshgrid(s, z)
    a = math.radians(azimuth)
    src = fr.source
    pts = np.column_stack(
        [
            src.east_m + gs.ravel() * math.sin(a),
            src.north_m + gs.ravel() * math.cos(a),
            gz.ravel(),
        ]
    )
    values = release.pct_lfl(
        pts, wind_from_deg, float(speed_m_s), stab, src.position, mode
    ).reshape(gs.shape)
    marks: list[dict[str, Any]] = []
    for r in study.receptors:
        if r.follows_wind:
            continue
        rel = r.points - src.position
        along = rel[:, 0] * math.sin(a) + rel[:, 1] * math.cos(a)
        lateral = np.abs(rel[:, 0] * math.cos(a) - rel[:, 1] * math.sin(a))
        ok = (lateral <= lateral_tolerance_m) & (along >= s[0]) & (along <= s[-1])
        if not np.any(ok):
            continue
        idx = int(np.argmin(np.where(ok, lateral, np.inf)))
        marks.append(
            {
                "label": r.name,
                "kind": r.kind,
                "s_m": float(along[idx]),
                "z_m": float(r.points[idx, 2]),
                "lateral_offset_m": float(lateral[idx]),
                "peak_pct_lfl_here": float(
                    release.pct_lfl(
                        r.points[idx : idx + 1],
                        wind_from_deg,
                        float(speed_m_s),
                        stab,
                        src.position,
                        mode,
                    )[0]
                ),
            }
        )
    return {
        "s": s.tolist(),
        "z": z.tolist(),
        "values": values.tolist(),
        "value_label": "% LFL",
        "levels": [5, 10, 20, 50, 100],
        "title": f"{case} from {src.name}: wind from {wind_from_deg:03.0f} deg at {speed_m_s:.1f} m/s",
        "source": src.to_dict(),
        "azimuth_deg": azimuth,
        "peak_pct_lfl": float(values.max()),
        "marks": marks,
    }


def write_facility_section(path: str | Path, section: Mapping[str, Any]) -> Path:
    """Write a section from :func:`facility_section` as JSON.

    Args:
        path: Target file (parent folders are created).
        section: The section mapping.

    Returns:
        The written path.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(section, default=float), encoding="utf-8")
    return p


def evaluate_facility(
    freelease: FacilityRelease,
    wind: WindTable,
    receptors: Sequence[Receptor],
    settings: StudySettings,
    overrides: Mapping[str, float] | None = None,
    thresholds_pct_lfl: Sequence[float] = (10.0, 20.0),
) -> dict[str, dict[str, float]]:
    """Run one sweep with parameter overrides and return the result per receptor.

    Args:
        freelease: Case and source.
        wind: Joint wind table.
        receptors: The receptors.
        settings: Base study settings (the ``briggs`` mode is used).
        overrides: Replacements for ``tilt_deg``, ``sigma0_divisor``, ``wind_exponent``
            and ``mass_flow_scale``.
        thresholds_pct_lfl: Thresholds of the exceedance results.

    Returns:
        Mapping receptor name to ``peak`` and ``hours_ge<threshold>`` values.

    Raises:
        ValueError: If an override key is unknown.
    """
    allowed = {"tilt_deg", "sigma0_divisor", "wind_exponent", "mass_flow_scale"}
    values = dict(overrides or {})
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown sensitivity parameters {sorted(unknown)}")
    scale = values.pop("mass_flow_scale", 1.0)
    params = settings.params.replace(**values) if values else settings.params
    run_settings = dataclasses.replace(settings, params=params, modes=("briggs",))
    case = dataclasses.replace(
        freelease.case, mass_flow_kg_s=freelease.case.mass_flow_kg_s * scale
    )
    source = freelease.source
    if "tilt_deg" in values and source.tilt_deg is not None:
        source = dataclasses.replace(source, tilt_deg=values["tilt_deg"])
    release = build_release(FacilityRelease(case, source), run_settings)
    arr = run_facility_case(release, source, wind, receptors, run_settings, "briggs")
    out: dict[str, dict[str, float]] = {}
    for r in receptors:
        row = {"peak": float(arr.peak[r.name].max())}
        for t in thresholds_pct_lfl:
            row[f"hours_ge{threshold_key(t)}"] = exceedance_pct(
                arr.peak[r.name], wind, t
            )
        out[r.name] = row
    return out


def facility_tilt_scan(
    freelease: FacilityRelease,
    wind: WindTable,
    receptors: Sequence[Receptor],
    settings: StudySettings,
    tilts_deg: Sequence[float] = (20.0, 30.0, 40.0, 55.0, 70.0, 90.0),
    thresholds_pct_lfl: Sequence[float] = (10.0, 20.0),
) -> list[dict[str, Any]]:
    """Scan the release inclination and report peaks and exceedance per receptor.

    The scan matters for any inclined release of dense gas: a flat tip leaves cold gas
    low, a vertical vent lifts it. The base inclination is always included.

    Args:
        freelease: Case and source.
        wind: Joint wind table.
        receptors: The receptors.
        settings: Base study settings.
        tilts_deg: Inclinations to evaluate, degrees.
        thresholds_pct_lfl: Thresholds of the exceedance results.

    Returns:
        One row per inclination, ascending, with a ``receptors`` mapping.
    """
    base = (
        freelease.source.tilt_deg
        if freelease.source.tilt_deg is not None
        else settings.params.tilt_deg
    )
    rows = []
    for tilt in sorted({float(t) for t in tilts_deg} | {float(base)}):
        fr = FacilityRelease(
            freelease.case,
            dataclasses.replace(freelease.source, tilt_deg=tilt),
        )
        rows.append(
            {
                "tilt_deg": tilt,
                "receptors": evaluate_facility(
                    fr, wind, receptors, settings, None, thresholds_pct_lfl
                ),
            }
        )
    return rows


def facility_tornado(
    freelease: FacilityRelease,
    wind: WindTable,
    receptors: Sequence[Receptor],
    settings: StudySettings,
    receptor: str,
    threshold_pct_lfl: float = 20.0,
    ranges: Mapping[str, tuple[float, float]] | None = None,
) -> list[dict[str, Any]]:
    """One-at-a-time sensitivity of the exceedance at one receptor.

    Args:
        freelease: Case and source.
        wind: Joint wind table.
        receptors: The receptors.
        settings: Base study settings.
        receptor: Receptor whose exceedance is ranked.
        threshold_pct_lfl: Threshold of the ranked exceedance.
        ranges: Low and high values by parameter; defaults to the helideck ranges.

    Returns:
        Rows sorted by swing, largest first.
    """
    from .sensitivity import DEFAULT_RANGES

    ranges = dict(ranges or DEFAULT_RANGES)
    key = f"hours_ge{threshold_key(threshold_pct_lfl)}"
    rows = []
    for name, (lo, hi) in ranges.items():
        low = evaluate_facility(
            freelease, wind, receptors, settings, {name: lo}, (threshold_pct_lfl,)
        )
        high = evaluate_facility(
            freelease, wind, receptors, settings, {name: hi}, (threshold_pct_lfl,)
        )
        rows.append(
            {
                "parameter": name,
                "low_input": lo,
                "high_input": hi,
                "hours_low": low[receptor][key],
                "hours_high": high[receptor][key],
                "swing_hours": abs(high[receptor][key] - low[receptor][key]),
            }
        )
    rows.sort(key=lambda row: -row["swing_hours"])
    return rows
