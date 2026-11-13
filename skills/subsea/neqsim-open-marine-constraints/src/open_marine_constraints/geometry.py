"""Dependency-free planar geometry for screening: local projection, route sampling, point-in-polygon, distances."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple

EARTH_RADIUS_M = 6371008.8
LonLat = Tuple[float, float]
XY = Tuple[float, float]


def haversine_m(a: LonLat, b: LonLat) -> float:
    """Great-circle distance in metres between two lon/lat points (degrees)."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


class LocalProjection:
    """Equirectangular projection about a reference point; accurate to well under 1 % within a few hundred km."""

    def __init__(self, lon0: float, lat0: float) -> None:
        self.lon0 = lon0
        self.lat0 = lat0
        self._kx = math.radians(1.0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
        self._ky = math.radians(1.0) * EARTH_RADIUS_M

    def forward(self, lon: float, lat: float) -> XY:
        """Return (x east, y north) in metres."""
        return ((lon - self.lon0) * self._kx, (lat - self.lat0) * self._ky)


def route_length_m(route: Sequence[LonLat]) -> float:
    """Length of a lon/lat polyline in metres."""
    return sum(haversine_m(route[i], route[i + 1]) for i in range(len(route) - 1))


def route_bbox(route: Sequence[LonLat], buffer_km: float = 0.0) -> Tuple[float, float, float, float]:
    """Bounding box (min_lon, min_lat, max_lon, max_lat) of a route, widened by ``buffer_km`` on every side."""
    lons = [p[0] for p in route]
    lats = [p[1] for p in route]
    lat_mid = (min(lats) + max(lats)) / 2
    dlat = buffer_km / 111.195
    dlon = buffer_km / (111.195 * max(0.05, math.cos(math.radians(lat_mid))))
    return (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)


def densify(route: Sequence[LonLat], step_m: float) -> List[Tuple[LonLat, float]]:
    """Points along the route every ``step_m`` (ends included) with their chainage in metres."""
    if len(route) < 2:
        return [(tuple(route[0]), 0.0)] if route else []
    out: List[Tuple[LonLat, float]] = [(tuple(route[0]), 0.0)]
    chain = 0.0
    for a, b in zip(route[:-1], route[1:]):
        seg = haversine_m(a, b)
        n = max(1, int(math.ceil(seg / step_m)))
        for i in range(1, n + 1):
            f = i / n
            out.append(((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f), chain + seg * f))
        chain += seg
    return out


def _rings(geometry: Dict[str, Any]) -> Iterator[List[List[LonLat]]]:
    """Yield polygons as [outer, hole, ...] ring lists."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "Polygon":
        yield [[(p[0], p[1]) for p in ring] for ring in coords]
    elif kind == "MultiPolygon":
        for poly in coords:
            yield [[(p[0], p[1]) for p in ring] for ring in poly]
    elif kind == "GeometryCollection":
        for g in geometry.get("geometries", []):
            yield from _rings(g)


def _lines(geometry: Dict[str, Any]) -> Iterator[List[LonLat]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "LineString":
        yield [(p[0], p[1]) for p in coords]
    elif kind == "MultiLineString":
        for line in coords:
            yield [(p[0], p[1]) for p in line]
    elif kind == "GeometryCollection":
        for g in geometry.get("geometries", []):
            yield from _lines(g)


def _points(geometry: Dict[str, Any]) -> Iterator[LonLat]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "Point":
        yield (coords[0], coords[1])
    elif kind == "MultiPoint":
        for p in coords:
            yield (p[0], p[1])
    elif kind == "GeometryCollection":
        for g in geometry.get("geometries", []):
            yield from _points(g)


def point_in_ring(x: float, y: float, ring: Sequence[XY]) -> bool:
    """Even-odd ray test for a closed or open ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_segment_distance(p: XY, a: XY, b: XY) -> float:
    """Distance from ``p`` to segment ``ab`` in the plane."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def segments_intersect(a: XY, b: XY, c: XY, d: XY) -> bool:
    """True when segments ``ab`` and ``cd`` cross or touch."""

    def orient(p: XY, q: XY, r: XY) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_seg(p: XY, q: XY, r: XY) -> bool:
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and o1 * o2 != 0 and o3 * o4 != 0:
        return True
    return (
        (o1 == 0 and on_seg(a, c, b))
        or (o2 == 0 and on_seg(a, d, b))
        or (o3 == 0 and on_seg(c, a, d))
        or (o4 == 0 and on_seg(c, b, d))
    )


def feature_geometry_xy(geometry: Dict[str, Any], proj: LocalProjection) -> Dict[str, Any]:
    """Project a GeoJSON geometry into local metres: polygons, lines and points plus a bounding box."""
    polys = [[[proj.forward(*p) for p in ring] for ring in poly] for poly in _rings(geometry)]
    lines = [[proj.forward(*p) for p in line] for line in _lines(geometry)]
    pts = [proj.forward(*p) for p in _points(geometry)]
    xs = [p[0] for poly in polys for ring in poly for p in ring] + [p[0] for ln in lines for p in ln] + [p[0] for p in pts]
    ys = [p[1] for poly in polys for ring in poly for p in ring] + [p[1] for ln in lines for p in ln] + [p[1] for p in pts]
    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else None
    return {"polygons": polys, "lines": lines, "points": pts, "bbox": bbox}


def inside_polygons(p: XY, polygons: Iterable[List[List[XY]]]) -> bool:
    """True when ``p`` is inside any polygon (outer ring in, hole rings out)."""
    for rings in polygons:
        if rings and point_in_ring(p[0], p[1], rings[0]) and not any(point_in_ring(p[0], p[1], h) for h in rings[1:]):
            return True
    return False


def distance_to_geometry(p: XY, geo: Dict[str, Any]) -> float:
    """Distance in metres from ``p`` to a projected feature (0 inside a polygon)."""
    if inside_polygons(p, geo["polygons"]):
        return 0.0
    best = math.inf
    for poly in geo["polygons"]:
        for ring in poly:
            for i in range(len(ring) - 1):
                best = min(best, point_segment_distance(p, ring[i], ring[i + 1]))
    for line in geo["lines"]:
        for i in range(len(line) - 1):
            best = min(best, point_segment_distance(p, line[i], line[i + 1]))
    for q in geo["points"]:
        best = min(best, math.hypot(p[0] - q[0], p[1] - q[1]))
    return best
