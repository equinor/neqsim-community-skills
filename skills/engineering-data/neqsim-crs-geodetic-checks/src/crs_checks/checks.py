"""Checks that catch the CRS mistakes that silently move map-derived positions and lengths."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

from .transform import AmbiguousOperationError, Point, transform

UTM_EASTING_RANGE = (160_000.0, 840_000.0)


def _crs(code: str):
    from pyproj import CRS

    return CRS.from_user_input(code)


def to_geographic(points: Sequence[Point], crs: str) -> list[Point]:
    """Lon/lat on the CRS's own datum (a conversion, no datum change, so no operation choice)."""
    from pyproj import Transformer

    c = _crs(crs)
    if c.is_geographic:
        return [(float(x), float(y)) for x, y in points]
    t = Transformer.from_crs(c, c.geodetic_crs, always_xy=True)
    return [t.transform(x, y) for x, y in points]


def area_of_use_check(
    points: Sequence[Point], crs: str, margin_deg: float = 0.5
) -> dict[str, object]:
    """Are the points inside the CRS area of use? Points far outside usually mean a wrong CRS or swapped axes."""
    c = _crs(crs)
    area = c.area_of_use
    if area is None:
        return {
            "crs": crs,
            "area": None,
            "outside": [],
            "note": "the CRS has no area of use",
        }
    lonlat = to_geographic(points, crs)
    outside = [
        i
        for i, (lon, lat) in enumerate(lonlat)
        if not (
            area.west - margin_deg <= lon <= area.east + margin_deg
            and area.south - margin_deg <= lat <= area.north + margin_deg
        )
    ]
    return {
        "crs": crs,
        "crs_name": c.name,
        "area": area.name,
        "bounds": [area.west, area.south, area.east, area.north],
        "outside": outside,
        "lonlat": [(round(lon, 6), round(lat, 6)) for lon, lat in lonlat],
    }


def axis_check(points: Sequence[Point], crs: str) -> list[str]:
    """Plausibility of the coordinate values for the CRS type (swapped lat/lon, degrees in a projected CRS...)."""
    c = _crs(crs)
    findings = []
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    if c.is_geographic:
        if any(abs(v) > 180 for v in xs) or any(abs(v) > 90 for v in ys):
            findings.append(
                "values exceed degree ranges: these look like projected metres, not lon/lat"
            )
        else:
            area = c.area_of_use
            if area is not None:
                inside = all(
                    area.west <= x <= area.east and area.south <= y <= area.north
                    for x, y in points
                )
                swapped = all(
                    area.west <= y <= area.east and area.south <= x <= area.north
                    for x, y in points
                )
                if swapped and not inside:
                    findings.append(
                        "the points fit the area of use only with x and y swapped: lat/lon order "
                        "is probably reversed"
                    )
    else:
        if all(abs(v) <= 180 for v in xs) and all(abs(v) <= 90 for v in ys):
            findings.append("values look like degrees in a projected CRS")
        if "UTM" in c.name.upper():
            if any(not UTM_EASTING_RANGE[0] <= x <= UTM_EASTING_RANGE[1] for x in xs):
                findings.append(
                    "eastings outside 160-840 km: wrong UTM zone, swapped axes or a false-easting "
                    "difference"
                )
            if any(y < 0 for y in ys):
                findings.append("negative northings in a UTM CRS")
    return findings


def geojson_check(document: dict[str, object]) -> list[str]:
    """RFC 7946 GeoJSON is WGS 84 lon/lat; flag documents that are not."""
    findings = []
    if "crs" in document:
        findings.append(
            f"the document carries a 'crs' member ({document['crs']}): not RFC 7946; read the "
            "coordinates in that CRS, not as WGS 84"
        )
    coords: list[float] = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            if node and all(isinstance(v, (int, float)) for v in node):
                coords.extend(float(v) for v in node[:2])
            else:
                for item in node:
                    walk(item)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in ("coordinates", "geometry", "features", "geometries"):
                    walk(value)

    walk(document)
    if any(abs(v) > 180 for v in coords[0::2]) or any(
        abs(v) > 90 for v in coords[1::2]
    ):
        findings.append(
            "coordinate values exceed lon/lat ranges: projected coordinates in a GeoJSON file"
        )
    return findings


def datum_sensitivity(
    points: Sequence[Point],
    candidates: Sequence[str],
    operations: dict[str, str] | None = None,
) -> dict[str, object]:
    """How far apart the same numbers land when read in each candidate CRS (for example ED50 vs WGS 84 UTM 31N).

    Each candidate is taken to WGS 84 (EPSG:4326). Named ``operations`` per candidate are used when given;
    otherwise the most accurate available operation is used and recorded, since only the size of the shift
    matters here.
    """
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    operations = operations or {}
    placed: dict[str, list[Point]] = {}
    used: dict[str, dict[str, object]] = {}
    for crs in candidates:
        try:
            result = transform(points, crs, "EPSG:4326", operations.get(crs))
            note = "named" if operations.get(crs) else "single result"
        except AmbiguousOperationError:
            result = transform(points, crs, "EPSG:4326", "best")
            note = "most accurate available, chosen for the sensitivity only"
        placed[crs] = list(result.coordinates)
        used[crs] = {
            "operation": result.operation,
            "accuracy_m": result.accuracy_m,
            "choice": note,
        }
    pairs = []
    names = list(placed)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            shifts = [
                geod.inv(p[0], p[1], q[0], q[1])[2]
                for p, q in zip(placed[a], placed[b])
            ]
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "max_shift_m": round(max(shifts), 2),
                    "mean_shift_m": round(sum(shifts) / len(shifts), 2),
                }
            )
    return {
        "candidates": used,
        "pairs": pairs,
        "max_shift_m": max((p["max_shift_m"] for p in pairs), default=0.0),
    }


def projection_factors(crs: str, lon: float, lat: float) -> dict[str, float]:
    """Grid convergence (degrees) and point scale factor of a projected CRS at a geographic point."""
    from pyproj import Proj

    c = _crs(crs)
    if not c.is_projected:
        raise ValueError(f"{crs} is not a projected CRS")
    factors = Proj(c).get_factors(lon, lat)
    return {
        "meridian_convergence_deg": float(factors.meridian_convergence),
        "meridional_scale": float(factors.meridional_scale),
        "parallel_scale": float(factors.parallel_scale),
        "areal_scale": float(factors.areal_scale),
    }


def route_lengths(points: Sequence[Point], crs: str) -> dict[str, float]:
    """Grid length against geodesic length on the CRS ellipsoid for a polyline in a projected CRS."""
    from pyproj import Geod

    c = _crs(crs)
    if not c.is_projected:
        raise ValueError(
            f"{crs} is not a projected CRS; give the route in projected coordinates"
        )
    grid = sum(math.dist(a, b) for a, b in itertools.pairwise(points))
    lonlat = to_geographic(points, crs)
    geod = Geod(a=c.ellipsoid.semi_major_metre, b=c.ellipsoid.semi_minor_metre)
    geodesic = geod.line_length([p[0] for p in lonlat], [p[1] for p in lonlat])
    return {
        "grid_length_m": grid,
        "geodesic_length_m": float(geodesic),
        "difference_m": grid - float(geodesic),
        "difference_ppm": (
            (grid - float(geodesic)) / float(geodesic) * 1e6 if geodesic else 0.0
        ),
    }
