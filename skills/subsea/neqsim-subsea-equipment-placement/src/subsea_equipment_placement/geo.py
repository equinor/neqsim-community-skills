"""Planar geometry helpers in a local metre frame (east, north) around an origin."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]
EARTH_RADIUS_M = 6371008.8


def to_local(lon: float, lat: float, origin_lon: float, origin_lat: float) -> Point:
    """Convert WGS84 degrees to local east/north metres (equirectangular about the origin; fine below about 50 km)."""
    east = math.radians(lon - origin_lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat))
    north = math.radians(lat - origin_lat) * EARTH_RADIUS_M
    return (east, north)


def to_lonlat(x: float, y: float, origin_lon: float, origin_lat: float) -> Point:
    """Inverse of :func:`to_local`; returns (lon, lat) degrees."""
    lat = origin_lat + math.degrees(y / EARTH_RADIUS_M)
    lon = origin_lon + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat))))
    return (lon, lat)


def dist(a: Point, b: Point) -> float:
    """Euclidean distance in metres."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_segment_distance(p: Point, a: Point, b: Point) -> Tuple[float, float]:
    """Return (distance, parameter t in [0, 1] of the closest point) from p to segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return dist(p, a), 0.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def point_polyline_distance(p: Point, line: Sequence[Point]) -> float:
    """Minimum distance from a point to a polyline."""
    if len(line) == 1:
        return dist(p, line[0])
    return min(point_segment_distance(p, a, b)[0] for a, b in zip(line, line[1:]))


def polyline_length(line: Sequence[Point]) -> float:
    """Length of a polyline in metres."""
    return sum(dist(a, b) for a, b in zip(line, line[1:]))


def point_in_polygon(p: Point, ring: Sequence[Point]) -> bool:
    """Ray-casting point-in-polygon test (ring need not be closed)."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def point_polygon_distance(p: Point, ring: Sequence[Point]) -> float:
    """Distance from a point to the polygon: 0 inside, otherwise to the nearest edge."""
    if point_in_polygon(p, ring):
        return 0.0
    closed = list(ring) + [ring[0]]
    return point_polyline_distance(p, closed)


def segment_intersection(p: Point, p2: Point, q: Point, q2: Point) -> Optional[Tuple[float, float, float]]:
    """Intersection of segments p-p2 and q-q2: (t along p, u along q, crossing angle in degrees 0..90) or None."""
    r = (p2[0] - p[0], p2[1] - p[1])
    s = (q2[0] - q[0], q2[1] - q[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / den
    u = ((q[0] - p[0]) * r[1] - (q[1] - p[1]) * r[0]) / den
    if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
        return None
    cosang = abs(r[0] * s[0] + r[1] * s[1]) / (math.hypot(*r) * math.hypot(*s))
    return t, u, math.degrees(math.acos(max(0.0, min(1.0, cosang))))


def polyline_crossings(route: Sequence[Point], line: Sequence[Point]) -> List[Tuple[float, float]]:
    """All crossings of a route with a polyline as (chainage along route in m, crossing angle deg)."""
    out = []
    ch = 0.0
    for a, b in zip(route, route[1:]):
        seg = dist(a, b)
        for q, q2 in zip(line, line[1:]):
            hit = segment_intersection(a, b, q, q2)
            if hit:
                out.append((ch + hit[0] * seg, hit[2]))
        ch += seg
    return sorted(out)


def densify(route: Sequence[Point], step_m: float) -> List[Tuple[float, Point]]:
    """Points along a polyline every step_m as (chainage, point)."""
    out, ch = [], 0.0
    for a, b in zip(route, route[1:]):
        seg = dist(a, b)
        n = max(1, int(round(seg / step_m)))
        for i in range(n):
            t = i / n
            out.append((ch + t * seg, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))))
        ch += seg
    out.append((ch, tuple(route[-1])))
    return out


def min_route_line_distance(route: Sequence[Point], line: Sequence[Point], step_m: float = 25.0) -> float:
    """Minimum distance between two polylines (0 when they cross; otherwise the route is sampled every step_m)."""
    if polyline_crossings(route, line):
        return 0.0
    return min(point_polyline_distance(p, line) for _, p in densify(route, step_m))


def slope_deg(depth_fn, p: Point, radius_m: float) -> float:
    """Maximum seabed slope (degrees) around p from a depth function depth_fn(x, y) in metres (positive down)."""
    best = 0.0
    for k in range(8):
        ang = k * math.pi / 4.0
        q = (p[0] + radius_m * math.cos(ang), p[1] + radius_m * math.sin(ang))
        best = max(best, math.degrees(math.atan(abs(depth_fn(*q) - depth_fn(*p)) / radius_m)))
    return best
