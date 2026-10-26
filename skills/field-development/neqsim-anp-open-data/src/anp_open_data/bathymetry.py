"""Public bathymetry for SURF and pipeline screening (NOAA ETOPO via ERDDAP).

Downloads a 1 arc-minute ETOPO grid (about 1.8 km) for a bounding box from the
NOAA upwell ERDDAP server, caches it with a manifest, interpolates water depth
at any point and builds seabed profiles (KP, depth, slope) along a route.

ETOPO is a global relief model, not survey data: depths are good to tens of
metres in deep water and short-wavelength features (scarps, pockmarks, salt
diapir crests) narrower than a few km are smoothed out. Use it for concept
routing, riser and flowline length and slope screening only; detailed design
needs a route survey (MBES).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
from pathlib import Path
from typing import Callable, Sequence

from .tools import haversine_km

ETOPO_ERDDAP = "https://upwell.pfeg.noaa.gov/erddap/griddap/etopo180.json"
NOAA_DEM_IDENTIFY = (
    "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_global_mosaic/ImageServer/identify"
)


def build_etopo_url(bbox: Sequence[float], stride: int = 1, base: str = ETOPO_ERDDAP) -> str:
    """Build the ERDDAP griddap query for ``bbox = (min_lon, max_lon, min_lat, max_lat)``."""
    lon0, lon1, lat0, lat1 = bbox
    return "%s?altitude[(%s):%d:(%s)][(%s):%d:(%s)]" % (base, lat0, stride, lat1, lon0, stride, lon1)


def _default_get(url: str, timeout: float) -> bytes:
    """HTTP GET returning the body bytes."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "neqsim-anp-open-data"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed public host
        return r.read()


def fetch_etopo_grid(
    bbox: Sequence[float],
    cache_dir: str | Path,
    stride: int = 1,
    getter: Callable[[str, float], bytes] | None = None,
    offline: bool = False,
    timeout: float = 180.0,
) -> dict:
    """Fetch (or load from cache) an ETOPO grid and return it as a regular grid.

    Args:
        bbox: ``(min_lon, max_lon, min_lat, max_lat)`` in degrees.
        cache_dir: Folder for the cached JSON and manifest (task references folder).
        stride: Grid stride (1 = 1 arc-minute).
        getter: Optional ``getter(url, timeout) -> bytes`` (tests).
        offline: Never use the network; a missing cache raises.
        timeout: Network timeout in seconds.

    Returns:
        ``{"lats": [...], "lons": [...], "z": [[altitude per lon] per lat],
        "source", "url", "file", "retrieved_utc", "status"}``. Altitude is in
        metres, negative below sea level; lats and lons are ascending.

    Raises:
        FileNotFoundError: Offline mode without a cache.
        ValueError: The response holds no grid rows.
    """
    url = build_etopo_url(bbox, stride)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    fname = cache / ("etopo_%s.json" % key)
    manifest = fname.with_suffix(".manifest.json")
    status = "cache"
    if fname.exists():
        raw = json.loads(fname.read_text(encoding="utf-8"))
        retrieved = json.loads(manifest.read_text(encoding="utf-8")).get("retrieved_utc") if manifest.exists() else None
    else:
        if offline:
            raise FileNotFoundError("offline mode and no cached ETOPO grid %s" % fname.name)
        raw = json.loads((getter or _default_get)(url, timeout).decode("utf-8"))
        fname.write_text(json.dumps(raw), encoding="utf-8")
        retrieved = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        status = "downloaded"
    grid = grid_from_erddap(raw)
    grid.update(
        {
            "source": "NOAA ETOPO 1 arc-minute (etopo180) via upwell ERDDAP",
            "url": url,
            "file": fname.name,
            "retrieved_utc": retrieved,
            "status": status,
        }
    )
    if status == "downloaded":
        manifest.write_text(
            json.dumps(
                {
                    "source": grid["source"],
                    "url": url,
                    "file": fname.name,
                    "bbox": list(bbox),
                    "stride": stride,
                    "n_lat": len(grid["lats"]),
                    "n_lon": len(grid["lons"]),
                    "retrieved_utc": retrieved,
                    "use_limit": "screening only; not survey data",
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    return grid


def grid_from_erddap(raw: dict) -> dict:
    """Convert an ERDDAP griddap JSON table (rows of lat, lon, altitude) to a grid."""
    table = raw.get("table", {})
    cols = table.get("columnNames", ["latitude", "longitude", "altitude"])
    rows = table.get("rows") or []
    if not rows:
        raise ValueError("ERDDAP response holds no rows")
    ilat, ilon, iz = cols.index("latitude"), cols.index("longitude"), cols.index("altitude")
    lats = sorted({float(r[ilat]) for r in rows})
    lons = sorted({float(r[ilon]) for r in rows})
    li = {v: i for i, v in enumerate(lats)}
    lj = {v: j for j, v in enumerate(lons)}
    z = [[float("nan")] * len(lons) for _ in lats]
    for r in rows:
        if r[iz] is not None:
            z[li[float(r[ilat])]][lj[float(r[ilon])]] = float(r[iz])
    return {"lats": lats, "lons": lons, "z": z}


def _index(axis: Sequence[float], v: float) -> tuple[int, float]:
    """Return lower index and fraction of ``v`` on an ascending regular axis."""
    if not axis[0] <= v <= axis[-1]:
        raise ValueError("point %.4f outside grid range %.4f..%.4f" % (v, axis[0], axis[-1]))
    step = (axis[-1] - axis[0]) / (len(axis) - 1)
    i = min(int((v - axis[0]) / step), len(axis) - 2)
    return i, (v - axis[i]) / step


def altitude_at(grid: dict, lat: float, lon: float) -> float:
    """Bilinear altitude (m, negative below sea level) at a point."""
    i, fy = _index(grid["lats"], lat)
    j, fx = _index(grid["lons"], lon)
    z = grid["z"]
    return (
        z[i][j] * (1 - fx) * (1 - fy)
        + z[i][j + 1] * fx * (1 - fy)
        + z[i + 1][j] * (1 - fx) * fy
        + z[i + 1][j + 1] * fx * fy
    )


def depth_at(grid: dict, lat: float, lon: float) -> float:
    """Water depth (m, positive down) at a point; 0 on land."""
    return max(0.0, -altitude_at(grid, lat, lon))


def _interp_gc(lon0: float, lat0: float, lon1: float, lat1: float, f: float) -> tuple[float, float]:
    """Point at fraction ``f`` along the great circle between two points."""
    p0, l0, p1, l1 = map(math.radians, (lat0, lon0, lat1, lon1))
    d = 2 * math.asin(math.sqrt(math.sin((p1 - p0) / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin((l1 - l0) / 2) ** 2))
    if d < 1e-12:
        return lon0, lat0
    a = math.sin((1 - f) * d) / math.sin(d)
    b = math.sin(f * d) / math.sin(d)
    x = a * math.cos(p0) * math.cos(l0) + b * math.cos(p1) * math.cos(l1)
    y = a * math.cos(p0) * math.sin(l0) + b * math.cos(p1) * math.sin(l1)
    zz = a * math.sin(p0) + b * math.sin(p1)
    return math.degrees(math.atan2(y, x)), math.degrees(math.atan2(zz, math.hypot(x, y)))


def profile_along_route(grid: dict, waypoints: Sequence[Sequence[float]], step_km: float = 1.0) -> list[dict]:
    """Seabed profile along a route of ``(lon, lat)`` waypoints.

    Args:
        grid: Output of :func:`fetch_etopo_grid`.
        waypoints: Route vertices as ``(lon, lat)``; segments follow great circles.
        step_km: Sampling interval.

    Returns:
        Rows ``{"kp_km", "lon", "lat", "depth_m", "slope_deg"}``; slope is the
        absolute seabed gradient over the preceding step (0 at KP 0).
    """
    rows: list[dict] = []
    kp = 0.0
    for (lo0, la0), (lo1, la1) in zip(waypoints[:-1], waypoints[1:]):
        seg = haversine_km(lo0, la0, lo1, la1)
        n = max(1, int(math.ceil(seg / step_km)))
        start = 0 if not rows else 1
        for k in range(start, n + 1):
            lon, lat = _interp_gc(lo0, la0, lo1, la1, k / n)
            rows.append({"kp_km": round(kp + seg * k / n, 3), "lon": round(lon, 5), "lat": round(lat, 5),
                         "depth_m": round(depth_at(grid, lat, lon), 1)})
        kp += seg
    for a, b in zip(rows[:-1], rows[1:]):
        dx = (b["kp_km"] - a["kp_km"]) * 1000.0
        b["slope_deg"] = round(math.degrees(math.atan2(abs(b["depth_m"] - a["depth_m"]), dx)), 2) if dx > 0 else 0.0
    if rows:
        rows[0]["slope_deg"] = 0.0
    return rows


def flag_slopes(profile: Sequence[dict], limits_deg: Sequence[float] = (5.0, 10.0)) -> dict:
    """Summarise a profile: length, depth range, max slope and length above each slope limit."""
    if not profile:
        return {}
    out = {
        "length_km": profile[-1]["kp_km"],
        "depth_start_m": profile[0]["depth_m"],
        "depth_end_m": profile[-1]["depth_m"],
        "depth_min_m": min(r["depth_m"] for r in profile),
        "depth_max_m": max(r["depth_m"] for r in profile),
        "max_slope_deg": max(r["slope_deg"] for r in profile),
    }
    for lim in limits_deg:
        km = 0.0
        for a, b in zip(profile[:-1], profile[1:]):
            if b["slope_deg"] > lim:
                km += b["kp_km"] - a["kp_km"]
        out["length_above_%gdeg_km" % lim] = round(km, 2)
    return out
