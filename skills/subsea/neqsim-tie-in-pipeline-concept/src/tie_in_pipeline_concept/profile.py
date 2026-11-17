"""Seabed profile along a straight great-circle corridor from the open EMODnet bathymetry DTM."""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

EARTH_RADIUS_KM = 6371.0088
EMODNET_URL = "https://rest.emodnet-bathymetry.eu/depth_sample?geom="


def great_circle_points(
    a: tuple[float, float], b: tuple[float, float], spacing_km: float
) -> tuple[float, list[tuple[float, float, float]]]:
    """Points along the great circle from ``a`` to ``b`` (both ``(lon, lat)`` in degrees).

    Args:
        a: start ``(lon, lat)``.
        b: end ``(lon, lat)``.
        spacing_km: target spacing; the actual spacing is total length divided by the rounded point count.

    Returns:
        ``(total_length_km, [(kp_km, lon, lat), ...])`` including both end points.
    """
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    v1 = (
        math.cos(lat1) * math.cos(lon1),
        math.cos(lat1) * math.sin(lon1),
        math.sin(lat1),
    )
    v2 = (
        math.cos(lat2) * math.cos(lon2),
        math.cos(lat2) * math.sin(lon2),
        math.sin(lat2),
    )
    omega = math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(v1, v2)))))
    total = omega * EARTH_RADIUS_KM
    n = max(1, round(total / spacing_km))
    pts: list[tuple[float, float, float]] = []
    for i in range(n + 1):
        t = i / n
        if omega < 1e-12:
            k1, k2 = 1.0 - t, t
        else:
            k1 = math.sin((1 - t) * omega) / math.sin(omega)
            k2 = math.sin(t * omega) / math.sin(omega)
        v = [k1 * x + k2 * y for x, y in zip(v1, v2)]
        lat = math.degrees(math.atan2(v[2], math.hypot(v[0], v[1])))
        lon = math.degrees(math.atan2(v[1], v[0]))
        pts.append((t * total, lon, lat))
    return total, pts


def fetch_emodnet_depth(
    lon: float,
    lat: float,
    fetch: Callable[[str], dict] | None = None,
    retries: int = 4,
) -> float | None:
    """Water depth in metres (positive down) at a point, or ``None`` on land or outside the DTM.

    Args:
        lon: longitude in degrees.
        lat: latitude in degrees.
        fetch: injectable ``url -> parsed json`` function, used by tests; defaults to the public REST API.
        retries: attempts on transient network errors.

    Returns:
        Depth in metres, positive below mean sea level.
    """
    url = EMODNET_URL + urllib.parse.quote(f"POINT({lon:.6f} {lat:.6f})")

    def _default(u: str) -> dict:
        with urllib.request.urlopen(u, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    getter = fetch or _default
    body: dict = {}
    for attempt in range(retries):
        try:
            body = getter(url)
            break
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    avg = body.get("avg")
    if avg is None:
        return None
    return -float(avg)


@dataclass
class RouteProfile:
    """Seabed profile of a straight corridor."""

    kp_km: list[float]
    lon: list[float]
    lat: list[float]
    depth_m: list[float]
    gaps: list[int]

    @property
    def length_km(self) -> float:
        """Horizontal corridor length in kilometres."""
        return self.kp_km[-1]


def build_profile(
    start: tuple[float, float],
    end: tuple[float, float],
    spacing_km: float = 0.5,
    fetch: Callable[[str], dict] | None = None,
    cache_path: Path | None = None,
) -> RouteProfile:
    """Sample the DTM along the corridor, caching responses on disk.

    Args:
        start: ``(lon, lat)`` of the source facility.
        end: ``(lon, lat)`` of the landing facility.
        spacing_km: sample spacing (500 m is about the DTM resolution on the Norwegian shelf).
        fetch: injectable fetch function (tests).
        cache_path: optional JSON cache keyed by rounded coordinates.

    Returns:
        A :class:`RouteProfile`. Points without depth are listed in ``gaps`` and filled by linear interpolation.
    """
    _total, pts = great_circle_points(start, end, spacing_km)
    cache: dict[str, float | None] = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    depths: list[float | None] = []
    for _kp, lon, lat in pts:
        key = f"{lon:.5f},{lat:.5f}"
        if key not in cache:
            cache[key] = fetch_emodnet_depth(lon, lat, fetch)
        depths.append(cache[key])
    if cache_path:
        Path(cache_path).write_text(json.dumps(cache), encoding="utf-8")
    gaps = [i for i, d in enumerate(depths) if d is None]
    filled = _fill_gaps(depths)
    return RouteProfile(
        [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], filled, gaps
    )


def _fill_gaps(values: Sequence[float | None]) -> list[float]:
    known = [(i, v) for i, v in enumerate(values) if v is not None]
    if not known:
        raise ValueError("no depth values returned for the corridor")
    out: list[float] = []
    for i, v in enumerate(values):
        if v is not None:
            out.append(float(v))
            continue
        left = max((k for k in known if k[0] < i), key=lambda k: k[0], default=None)
        right = min((k for k in known if k[0] > i), key=lambda k: k[0], default=None)
        if left is None:
            out.append(float(right[1]))
        elif right is None:
            out.append(float(left[1]))
        else:
            f = (i - left[0]) / (right[0] - left[0])
            out.append(float(left[1] + f * (right[1] - left[1])))
    return out


def profile_statistics(
    profile: RouteProfile, steep_deg: float = 3.0
) -> dict[str, object]:
    """Depth range, slopes, 3D length and steep intervals of a profile."""
    slopes: list[float] = []
    steep: list[dict[str, float]] = []
    length3d = 0.0
    for i in range(1, len(profile.kp_km)):
        dh = (profile.kp_km[i] - profile.kp_km[i - 1]) * 1000.0
        dz = profile.depth_m[i] - profile.depth_m[i - 1]
        s = math.degrees(math.atan2(dz, dh))
        slopes.append(s)
        length3d += math.hypot(dh, dz)
        if abs(s) >= steep_deg:
            steep.append(
                {
                    "kp_from": profile.kp_km[i - 1],
                    "kp_to": profile.kp_km[i],
                    "slope_deg": s,
                }
            )
    n = max(len(slopes), 1)
    return {
        "length_km": profile.length_km,
        "route_3d_length_km": length3d / 1000.0,
        "min_depth_m": min(profile.depth_m),
        "max_depth_m": max(profile.depth_m),
        "max_slope_deg": max((abs(s) for s in slopes), default=0.0),
        "rms_slope_deg": math.sqrt(sum(s * s for s in slopes) / n),
        "steep_intervals": steep,
        "interpolated_points": len(profile.gaps),
        "note": "DTM cell size is several hundred metres: spans, scours and local steps are not resolved.",
    }
