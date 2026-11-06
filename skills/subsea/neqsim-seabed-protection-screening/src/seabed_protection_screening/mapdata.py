"""Route geometry and map-layer sampling for seabed protection screening.

The module is **offline**: it never opens a network connection. It plans read-only
requests against openly licensed map services and then works on GeoJSON that the
caller has already fetched (or exported from a GIS), so the same code runs in a
sandbox, in CI and on a workstation.

Geometry uses a local equirectangular frame about the route centroid. That is
adequate for intersecting a flowline with polygon and line layers at screening
accuracy and is not a positioning or datum authority.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class MapDataSource:
    """A public map service that supplies one layer family for protection screening."""

    key: str
    name: str
    provider: str
    layer_family: str
    base_url: str
    service: str
    licence: str
    attribution: str
    notes: str


#: Verify licence text and layer names at the provider before publishing results.
MAP_DATA_SOURCES: dict[str, MapDataSource] = {
    "emodnet_seabed_substrate": MapDataSource(
        key="emodnet_seabed_substrate",
        name="EMODnet Geology seabed substrate",
        provider="European Marine Observation and Data Network - Geology",
        layer_family="soil_class",
        base_url="https://drive.emodnet-geology.eu/geoserver/gtk/wms",
        service="WMS",
        licence="open, attribution required",
        attribution="EMODnet Geology",
        notes=(
            "five EUNIS-based substrate classes (mud to sandy mud, sand, coarse sediment, "
            "mixed sediment, rock or hard substrate); surface sediment only - not a "
            "geotechnical strength profile and not a trenchability statement"
        ),
    ),
    "emodnet_human_activities": MapDataSource(
        key="emodnet_human_activities",
        name="EMODnet Human Activities",
        provider="European Marine Observation and Data Network - Human Activities",
        layer_family="fishing_intensity",
        base_url="https://ows.emodnet-humanactivities.eu/wfs",
        service="WFS",
        licence="open, attribution required",
        attribution="EMODnet Human Activities",
        notes=(
            "vessel density by ship type (including fishing) and existing pipelines and "
            "cables; vessel density is a proxy for trawling and anchoring exposure, not "
            "a measured trawl frequency"
        ),
    ),
    "sodir_factmaps": MapDataSource(
        key="sodir_factmaps",
        name="Norwegian Offshore Directorate FactMaps",
        provider="Sokkeldirektoratet (Norwegian Offshore Directorate)",
        layer_family="existing_infrastructure",
        base_url="https://factmaps.sodir.no/arcgis/rest/services/FactMaps/3_0/MapServer",
        service="ArcGIS REST",
        licence="Norwegian Licence for Open Government Data (NLOD)",
        attribution="Norwegian Offshore Directorate FactMaps",
        notes="pipelines and facilities for crossing detection; list layer ids with ?f=json",
    ),
    "emodnet_bathymetry": MapDataSource(
        key="emodnet_bathymetry",
        name="EMODnet Bathymetry digital terrain model",
        provider="European Marine Observation and Data Network - Bathymetry",
        layer_family="bathymetry",
        base_url="https://ows.emodnet-bathymetry.eu/wcs",
        service="WCS",
        licence="CC BY 4.0",
        attribution="EMODnet Bathymetry Consortium",
        notes="seabed slope and water depth along the route",
    ),
    "user_supplied": MapDataSource(
        key="user_supplied",
        name="Project or survey layers supplied by the caller",
        provider="caller",
        layer_family="any",
        base_url="",
        service="GeoJSON file",
        licence="as supplied",
        attribution="as supplied",
        notes=(
            "geotechnical zones, ice-scour maps, fishing-effort data, protected-area and "
            "no-rock-placement polygons, pre-lay survey debris and boulder fields"
        ),
    ),
}


@dataclass(frozen=True)
class MapDataRequest:
    """A planned read-only request. Nothing is sent until the caller executes it."""

    source_key: str
    url: str
    method: str
    purpose: str
    licence: str
    attribution: str

    def to_dict(self) -> dict[str, str]:
        """Return the request as a plain dictionary."""
        return {
            "source": self.source_key,
            "url": self.url,
            "method": self.method,
            "purpose": self.purpose,
            "licence": self.licence,
            "attribution": self.attribution,
        }


def plan_protection_data_package(
    west: float,
    south: float,
    east: float,
    north: float,
    sodir_pipeline_layer_id: int | None = None,
) -> list[MapDataRequest]:
    """Plan the read-only requests that supply the protection-screening layers.

    Layer names inside the EMODnet services change over time, so the plan starts
    with ``GetCapabilities`` for them and the caller picks the layer. The Sodir
    pipeline query is planned only when a layer id is supplied.

    Args:
        west: Western bound in degrees (WGS84).
        south: Southern bound in degrees (WGS84).
        east: Eastern bound in degrees (WGS84).
        north: Northern bound in degrees (WGS84).
        sodir_pipeline_layer_id: Layer id of the pipeline layer in the FactMaps service.

    Returns:
        A list of planned requests.

    Raises:
        ValueError: If the bounding box is empty or outside valid coordinates.
    """
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise ValueError("bounding box must satisfy west < east and south < north in WGS84 degrees")
    requests: list[MapDataRequest] = []
    for key, service, purpose in (
        ("emodnet_seabed_substrate", "WMS", "surface sediment class along the route for trenchability screening"),
        ("emodnet_human_activities", "WFS", "vessel density, pipelines and cables for fishing exposure and crossings"),
    ):
        source = MAP_DATA_SOURCES[key]
        query = urlencode({"service": service, "request": "GetCapabilities"})
        requests.append(
            MapDataRequest(key, "%s?%s" % (source.base_url, query), "GET", purpose, source.licence, source.attribution)
        )
    if sodir_pipeline_layer_id is not None:
        source = MAP_DATA_SOURCES["sodir_factmaps"]
        query = urlencode(
            {
                "where": "1=1",
                "geometry": "%s,%s,%s,%s" % (west, south, east, north),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "outSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "f": "geojson",
            }
        )
        requests.append(
            MapDataRequest(
                "sodir_factmaps",
                "%s/%d/query?%s" % (source.base_url, sodir_pipeline_layer_id, query),
                "GET",
                "existing pipelines for crossing detection",
                source.licence,
                source.attribution,
            )
        )
    return requests


@dataclass(frozen=True)
class RoutePoint:
    """A station on the route with its chainage and position."""

    kp_m: float
    lon: float
    lat: float


@dataclass(frozen=True)
class RouteSegment:
    """A stretch of route over which every sampled attribute is constant."""

    start_kp_m: float
    end_kp_m: float
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def length_m(self) -> float:
        """Segment length in metres."""
        return self.end_kp_m - self.start_kp_m


@dataclass(frozen=True)
class LineCrossing:
    """A crossing between the route and a line feature such as a pipeline or cable."""

    kp_m: float
    feature_id: str
    lon: float
    lat: float
    crossing_angle_deg: float
    crossed_outer_diameter_m: float | None


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return the great-circle distance in metres between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def build_route(lonlat: Sequence[Sequence[float]], spacing_m: float = 100.0) -> list[RoutePoint]:
    """Densify a route polyline into stations with chainage.

    Args:
        lonlat: Ordered ``(longitude, latitude)`` vertices in degrees.
        spacing_m: Maximum station spacing in metres.

    Returns:
        Stations including every input vertex, with cumulative KP in metres.

    Raises:
        ValueError: If fewer than two vertices or a non-positive spacing is given.
    """
    if len(lonlat) < 2:
        raise ValueError("a route needs at least two vertices")
    if spacing_m <= 0.0:
        raise ValueError("spacing_m must be positive")
    points = [RoutePoint(0.0, float(lonlat[0][0]), float(lonlat[0][1]))]
    kp = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(lonlat[:-1], lonlat[1:]):
        length = haversine_m(lon1, lat1, lon2, lat2)
        steps = max(1, int(math.ceil(length / spacing_m)))
        for index in range(1, steps + 1):
            frac = index / steps
            lon = lon1 + (lon2 - lon1) * frac
            lat = lat1 + (lat2 - lat1) * frac
            points.append(RoutePoint(kp + length * frac, lon, lat))
        kp += length
    return points


def read_geojson(path: str | Path) -> dict[str, Any]:
    """Read a GeoJSON file that the caller has already downloaded or exported.

    Args:
        path: Path to a GeoJSON FeatureCollection, Feature or geometry file.

    Returns:
        A FeatureCollection dictionary.

    Raises:
        ValueError: If the file does not contain GeoJSON.
    """
    with open(path, "r", encoding="utf-8") as handle:
        return _as_collection(json.load(handle))


def _as_collection(data: Mapping[str, Any]) -> dict[str, Any]:
    kind = data.get("type")
    if kind == "FeatureCollection":
        return dict(data)
    if kind == "Feature":
        return {"type": "FeatureCollection", "features": [dict(data)]}
    if kind in ("Polygon", "MultiPolygon", "LineString", "MultiLineString", "Point"):
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": dict(data), "properties": {}}]}
    raise ValueError("not a GeoJSON object: type=%r" % (kind,))


def _frame(route: Sequence[RoutePoint]):
    lon0 = sum(p.lon for p in route) / len(route)
    lat0 = sum(p.lat for p in route) / len(route)
    cos0 = math.cos(math.radians(lat0))

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (
            math.radians(lon - lon0) * EARTH_RADIUS_M * cos0,
            math.radians(lat - lat0) * EARTH_RADIUS_M,
        )

    return project


def _ring_contains(x: float, y: float, ring: Sequence[tuple[float, float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _polygons(geometry: Mapping[str, Any]) -> list[list[list[Sequence[float]]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [coords]
    if kind == "MultiPolygon":
        return list(coords)
    return []


def sample_polygon_layer(
    route: Sequence[RoutePoint],
    layer: Mapping[str, Any],
    attribute: str,
    default: Any = None,
    rank_order: Sequence[Any] | None = None,
) -> list[Any]:
    """Return the value of a polygon-layer attribute at every route station.

    Holes are honoured. Where polygons overlap, the value ranked highest in
    ``rank_order`` wins (so a conservative class is never hidden by a lesser one);
    without ``rank_order`` the first matching feature wins.

    Args:
        route: Stations from :func:`build_route`.
        layer: GeoJSON FeatureCollection, Feature or geometry of polygons.
        attribute: Feature property to read.
        default: Value reported where no polygon covers the station.
        rank_order: Optional values ordered from least to most onerous.

    Returns:
        One value per station.
    """
    collection = _as_collection(layer)
    project = _frame(route)
    prepared = []
    for feature in collection["features"]:
        value = (feature.get("properties") or {}).get(attribute)
        polygons = []
        for rings in _polygons(feature.get("geometry") or {}):
            polygons.append([[project(lon, lat) for lon, lat in ring] for ring in rings])
        if polygons and value is not None:
            prepared.append((value, polygons))
    rank = {value: index for index, value in enumerate(rank_order)} if rank_order else None
    values: list[Any] = []
    for point in route:
        x, y = project(point.lon, point.lat)
        hits = []
        for value, polygons in prepared:
            for rings in polygons:
                if rings and _ring_contains(x, y, rings[0]) and not any(_ring_contains(x, y, h) for h in rings[1:]):
                    hits.append(value)
                    break
        if not hits:
            values.append(default)
        elif rank:
            values.append(max(hits, key=lambda v: rank.get(v, -1)))
        else:
            values.append(hits[0])
    return values


def _segment_intersection(p1, p2, q1, q2):
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = q2[0] - q1[0], q2[1] - q1[1]
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return None
    qpx, qpy = q1[0] - p1[0], q1[1] - p1[1]
    t = (qpx * sy - qpy * sx) / denom
    u = (qpx * ry - qpy * rx) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, rx, ry, sx, sy
    return None


def _lines(geometry: Mapping[str, Any]) -> list[Sequence[Sequence[float]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return list(coords)
    return []


def find_line_crossings(
    route: Sequence[RoutePoint],
    layer: Mapping[str, Any],
    id_attribute: str = "name",
    outer_diameter_attribute: str | None = None,
    outer_diameter_unit_m: float = 1.0,
) -> list[LineCrossing]:
    """Find where the route crosses line features such as pipelines and cables.

    Args:
        route: Stations from :func:`build_route`.
        layer: GeoJSON of line features.
        id_attribute: Property holding the feature name; falls back to the feature id.
        outer_diameter_attribute: Optional property with the crossed asset outer diameter.
        outer_diameter_unit_m: Metres per unit of that property (0.0254 for inches).

    Returns:
        Crossings ordered by KP. Collinear overlaps are not reported as crossings.
    """
    collection = _as_collection(layer)
    project = _frame(route)
    xy = [project(p.lon, p.lat) for p in route]
    crossings: list[LineCrossing] = []
    for index, feature in enumerate(collection["features"]):
        props = feature.get("properties") or {}
        feature_id = str(props.get(id_attribute) or feature.get("id") or "feature-%d" % index)
        diameter = None
        if outer_diameter_attribute and props.get(outer_diameter_attribute) is not None:
            diameter = float(props[outer_diameter_attribute]) * outer_diameter_unit_m
        for line in _lines(feature.get("geometry") or {}):
            line_xy = [project(lon, lat) for lon, lat in line]
            for i in range(len(xy) - 1):
                for j in range(len(line_xy) - 1):
                    hit = _segment_intersection(xy[i], xy[i + 1], line_xy[j], line_xy[j + 1])
                    if hit is None:
                        continue
                    t, rx, ry, sx, sy = hit
                    kp = route[i].kp_m + t * (route[i + 1].kp_m - route[i].kp_m)
                    cosang = abs(rx * sx + ry * sy) / (math.hypot(rx, ry) * math.hypot(sx, sy))
                    angle = math.degrees(math.acos(min(1.0, cosang)))
                    crossings.append(
                        LineCrossing(
                            kp_m=kp,
                            feature_id=feature_id,
                            lon=route[i].lon + t * (route[i + 1].lon - route[i].lon),
                            lat=route[i].lat + t * (route[i + 1].lat - route[i].lat),
                            crossing_angle_deg=angle,
                            crossed_outer_diameter_m=diameter,
                        )
                    )
    crossings.sort(key=lambda c: c.kp_m)
    deduped: list[LineCrossing] = []
    for crossing in crossings:
        if deduped and deduped[-1].feature_id == crossing.feature_id and abs(deduped[-1].kp_m - crossing.kp_m) < 1.0:
            continue
        deduped.append(crossing)
    return deduped


def assemble_segments(
    route: Sequence[RoutePoint],
    series: Mapping[str, Sequence[Any]],
) -> list[RouteSegment]:
    """Merge per-station attribute series into constant-attribute route segments.

    Segment boundaries lie midway between stations, so a polygon edge is located to
    within half a station spacing; use a finer spacing where that matters.

    Args:
        route: Stations from :func:`build_route`.
        series: Attribute name to a list with one value per station.

    Returns:
        Contiguous segments covering the whole route.

    Raises:
        ValueError: If a series length differs from the number of stations.
    """
    for name, values in series.items():
        if len(values) != len(route):
            raise ValueError("series %r has %d values for %d stations" % (name, len(values), len(route)))
    bounds = [route[0].kp_m]
    bounds += [(route[i].kp_m + route[i + 1].kp_m) / 2.0 for i in range(len(route) - 1)]
    bounds.append(route[-1].kp_m)
    segments: list[RouteSegment] = []
    start = 0
    for index in range(1, len(route) + 1):
        same = index < len(route) and all(values[index] == values[start] for values in series.values())
        if same:
            continue
        attrs = {name: values[start] for name, values in series.items()}
        if bounds[index] > bounds[start]:
            segments.append(RouteSegment(bounds[start], bounds[index], attrs))
        start = index
    return segments
