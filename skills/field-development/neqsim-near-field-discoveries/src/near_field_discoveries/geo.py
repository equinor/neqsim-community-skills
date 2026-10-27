"""Small geometry helpers on a spherical earth (no third-party packages).

Distances are great-circle; polygon and polyline distances use a local
equirectangular projection around the query point, which is accurate to well
under one percent inside a few hundred kilometres. Geometries may be GeoJSON
(``Polygon``, ``MultiPolygon``, ``LineString``, ``MultiLineString``, ``Point``)
or Esri JSON (``rings``, ``paths``, ``x``/``y``) as served by Sodir.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

EARTH_RADIUS_KM = 6371.0088
Ring = Sequence[Sequence[float]]

_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km between two (lon, lat) points in degrees."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Initial bearing in degrees clockwise from north, from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    y = math.sin(dlmb) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlmb)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass(bearing: float) -> str:
    """16-point compass label for a bearing in degrees."""
    return _COMPASS[int((bearing % 360.0) / 22.5 + 0.5) % 16]


def bbox_around(lon: float, lat: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return ``(min_lon, min_lat, max_lon, max_lat)`` enclosing a circle of ``radius_km``."""
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def circle_points(lon: float, lat: float, radius_km: float, n: int = 120) -> list[tuple[float, float]]:
    """Closed ring of (lon, lat) points on the circle of ``radius_km`` around a point."""
    pts = []
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        dlat = math.degrees(radius_km * math.cos(th) / EARTH_RADIUS_KM)
        dlon = math.degrees(radius_km * math.sin(th) / EARTH_RADIUS_KM) / max(math.cos(math.radians(lat)), 1e-6)
        pts.append((lon + dlon, lat + dlat))
    return pts


def _xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    k = math.cos(math.radians(lat0))
    return (
        math.radians(lon - lon0) * EARTH_RADIUS_KM * k,
        math.radians(lat - lat0) * EARTH_RADIUS_KM,
    )


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / d2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rings_from_geometry(geometry: Mapping[str, Any] | None) -> list[list[tuple[float, float]]]:
    """Exterior rings of a GeoJSON polygon/multipolygon or Esri ``rings`` as (lon, lat) lists."""
    if not geometry:
        return []
    if "rings" in geometry:
        return [[(float(p[0]), float(p[1])) for p in ring] for ring in geometry["rings"] if len(ring) >= 3]
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        polys = [coords]
    elif kind == "MultiPolygon":
        polys = coords
    else:
        return []
    return [[(float(p[0]), float(p[1])) for p in poly[0]] for poly in polys if poly and len(poly[0]) >= 3]


def lines_from_geometry(geometry: Mapping[str, Any] | None) -> list[list[tuple[float, float]]]:
    """Parts of a GeoJSON line/multiline or Esri ``paths`` as (lon, lat) lists."""
    if not geometry:
        return []
    if "paths" in geometry:
        return [[(float(p[0]), float(p[1])) for p in part] for part in geometry["paths"] if len(part) >= 2]
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "LineString":
        parts = [coords]
    elif kind == "MultiLineString":
        parts = coords
    else:
        return []
    return [[(float(p[0]), float(p[1])) for p in part] for part in parts if len(part) >= 2]


def point_from_geometry(geometry: Mapping[str, Any] | None) -> tuple[float, float] | None:
    """(lon, lat) of a point geometry, or the vertex-mean of a polygon; ``None`` if empty."""
    if not geometry:
        return None
    if "x" in geometry and "y" in geometry:
        return float(geometry["x"]), float(geometry["y"])
    if geometry.get("type") == "Point":
        c = geometry["coordinates"]
        return float(c[0]), float(c[1])
    pts = [p for ring in rings_from_geometry(geometry) for p in ring]
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def point_in_rings(lon: float, lat: float, rings: Iterable[Ring]) -> bool:
    """Ray-casting point-in-polygon test over several exterior rings."""
    for ring in rings:
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-300) + xi:
                inside = not inside
            j = i
        if inside:
            return True
    return False


def point_to_rings_km(lon: float, lat: float, rings: Iterable[Ring]) -> float | None:
    """Distance in km from a point to the nearest polygon edge; 0.0 when inside; ``None`` if no rings."""
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        return None
    if point_in_rings(lon, lat, rings):
        return 0.0
    best = float("inf")
    for ring in rings:
        pts = [_xy(p[0], p[1], lon, lat) for p in ring]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            best = min(best, _seg_dist(0.0, 0.0, a[0], a[1], b[0], b[1]))
    return best


def point_to_lines_km(lon: float, lat: float, parts: Iterable[Ring]) -> float | None:
    """Distance in km from a point to the nearest segment of a polyline; ``None`` if no parts."""
    best = float("inf")
    for part in parts:
        pts = [_xy(p[0], p[1], lon, lat) for p in part]
        for a, b in zip(pts, pts[1:]):
            best = min(best, _seg_dist(0.0, 0.0, a[0], a[1], b[0], b[1]))
    return None if best == float("inf") else best


def cluster_points(points: Sequence[tuple[float, float]], link_km: float) -> list[list[int]]:
    """Single-linkage clusters of (lon, lat) points; points closer than ``link_km`` join one cluster.

    Returns:
        Index groups, each sorted, ordered by their first index.
    """
    n = len(points)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if haversine_km(points[i][0], points[i][1], points[j][0], points[j][1]) <= link_km:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def median(values: Sequence[float]) -> float:
    """Median of a non-empty list."""
    s = sorted(values)
    m = len(s) // 2
    return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])
