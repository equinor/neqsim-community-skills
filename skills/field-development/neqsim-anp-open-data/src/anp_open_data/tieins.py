"""Screen candidate tie-in hosts and export lines for a new subsea development.

The ranking is a transparent screening score, not a concept selection. It
combines step-out distance, host ullage, water-depth compatibility and simple
flags (operator, ageing host, gas-only line) so that an engineer can see why a
host ranks where it does. Every weight is an input.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

from .tools import haversine_km

DEFAULT_WEIGHTS = {
    "distance": 0.40,
    "ullage": 0.30,
    "water_depth": 0.10,
    "operator": 0.10,
    "remaining_life": 0.10,
}
"""Default weights; they sum to 1.0 and can be overridden per study."""


def _local_xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """Project lon/lat to km on an equirectangular plane centred at (lon0, lat0)."""
    r = 6371.0088
    x = math.radians(lon - lon0) * r * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * r
    return x, y


def point_to_polyline_km(
    point: Sequence[float], line: Sequence[Sequence[float]]
) -> tuple[float, tuple[float, float], float]:
    """Return the shortest distance from a point to a polyline.

    The calculation uses a local equirectangular projection around the point,
    which is accurate to well under 1 % for distances up to a few hundred km.

    Args:
        point: ``(lon, lat)`` in degrees.
        line: Sequence of ``(lon, lat)`` vertices (at least one).

    Returns:
        ``(distance_km, nearest_lonlat, along_km)`` where ``along_km`` is the
        distance from the first vertex to the nearest point along the line.

    Raises:
        ValueError: If the line has no vertices.
    """
    if not line:
        raise ValueError("line has no vertices")
    lon0, lat0 = float(point[0]), float(point[1])
    pts = [_local_xy(float(v[0]), float(v[1]), lon0, lat0) for v in line]
    if len(pts) == 1:
        d = math.hypot(*pts[0])
        return d, (float(line[0][0]), float(line[0][1])), 0.0
    best = (float("inf"), (0.0, 0.0), 0.0)
    along = 0.0
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        px, py = ax + t * dx, ay + t * dy
        d = math.hypot(px, py)
        if d < best[0]:
            best = (d, (px, py), along + t * math.sqrt(seg2))
        along += math.sqrt(seg2)
    d, (px, py), a = best
    r = 6371.0088
    lat = lat0 + math.degrees(py / r)
    lon = lon0 + math.degrees(px / (r * math.cos(math.radians(lat0))))
    return d, (lon, lat), a


def _lines(geometry: Mapping) -> list[list[Sequence[float]]]:
    """Return the vertex lists of a LineString or MultiLineString geometry."""
    t = (geometry or {}).get("type")
    c = (geometry or {}).get("coordinates") or []
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return list(c)
    return []


def nearest_pipeline(
    point: Sequence[float],
    pipelines_geojson: Mapping,
    name_keys: Iterable[str] = ("nome", "name", "NOME", "duto", "DUTO"),
    top: int = 5,
) -> list[dict]:
    """Rank pipeline features by distance from a point.

    Args:
        point: ``(lon, lat)`` of the development (wellhead or centroid).
        pipelines_geojson: GeoJSON with LineString/MultiLineString features, for
            example the ANP ``geoanp:gasodutos_de_escoamento`` layer.
        name_keys: Property names tried in order to label a feature.
        top: Number of results to return.

    Returns:
        Records with ``name``, ``distance_km``, ``nearest_lon``, ``nearest_lat``,
        ``along_km`` and the original ``properties``, nearest first.
    """
    out = []
    for i, f in enumerate(pipelines_geojson.get("features", [])):
        props = f.get("properties") or {}
        name = next((props[k] for k in name_keys if props.get(k)), "feature-%d" % i)
        best = None
        for part in _lines(f.get("geometry")):
            if not part:
                continue
            res = point_to_polyline_km(point, part)
            if best is None or res[0] < best[0]:
                best = res
        if best is None:
            continue
        out.append(
            {
                "name": name,
                "distance_km": round(best[0], 2),
                "nearest_lon": round(best[1][0], 5),
                "nearest_lat": round(best[1][1], 5),
                "along_km": round(best[2], 1),
                "properties": props,
            }
        )
    out.sort(key=lambda r: r["distance_km"])
    return out[:top]


def rank_tie_in_hosts(
    target: Sequence[float],
    hosts: Iterable[Mapping],
    target_water_depth_m: float | None = None,
    required_oil_m3d: float | None = None,
    required_gas_mm3d: float | None = None,
    preferred_operators: Iterable[str] = (),
    max_step_out_km: float = 150.0,
    weights: Mapping[str, float] | None = None,
) -> list[dict]:
    """Score and rank candidate hosts for a subsea tie-in.

    Each host mapping needs ``name``, ``lon`` and ``lat``. Optional keys:
    ``kind`` (``"fpso"``, ``"platform"``, ``"pipeline"``, ``"standalone"``),
    ``operator``, ``water_depth_m``, ``oil_capacity_m3d``, ``oil_m3d_current``,
    ``gas_capacity_mm3d``, ``gas_mm3d_current``, ``remaining_life_years``,
    ``distance_km`` (overrides the great-circle distance, e.g. a pipeline
    nearest-point distance) and ``flags`` (list of strings carried through).

    Sub-scores are in 0..1 (1 is best):

    * distance: ``1 - d / max_step_out_km`` (0 beyond the limit);
    * ullage: free capacity divided by the required rate, capped at 1; 0.5 when
      capacity or current rate is unknown (unknown is not zero);
    * water_depth: 1 when within 500 m of the target depth, falling to 0 at 2000 m;
    * operator: 1 for a preferred operator, 0.5 otherwise;
    * remaining_life: years / 20 capped at 1; 0.5 when unknown.

    A stand-alone option (``kind == "standalone"``) has distance 0 and full
    ullage by construction; give it a ``remaining_life_years`` and rely on cost
    screening elsewhere to judge it.

    Args:
        target: ``(lon, lat)`` of the development.
        hosts: Candidate host mappings.
        target_water_depth_m: Water depth at the development, m.
        required_oil_m3d: Oil (liquid) rate the tie-in needs at plateau, m3/d.
        required_gas_mm3d: Gas rate the tie-in needs at plateau, thousand m3/d.
        preferred_operators: Operators scored 1 on the operator criterion.
        max_step_out_km: Distance at which the distance score reaches 0.
        weights: Criterion weights; defaults to :data:`DEFAULT_WEIGHTS`.

    Returns:
        Records sorted by ``score`` (descending) with ``rank``, ``distance_km``,
        each sub-score, ``feasible_step_out`` and ``notes`` explaining unknowns.

    Raises:
        ValueError: If a host lacks coordinates or weights sum to zero.
    """
    w = dict(DEFAULT_WEIGHTS)
    w.update(weights or {})
    wsum = sum(w.values())
    if wsum <= 0:
        raise ValueError("weights must sum to a positive number")
    pref = {str(o).strip().upper() for o in preferred_operators}
    lon0, lat0 = float(target[0]), float(target[1])
    out = []
    for h in hosts:
        notes = []
        kind = str(h.get("kind", "fpso")).lower()
        if kind == "standalone":
            d = 0.0
        elif h.get("distance_km") is not None:
            d = float(h["distance_km"])
        else:
            if h.get("lon") is None or h.get("lat") is None:
                raise ValueError("host %r has no coordinates" % h.get("name"))
            d = haversine_km(lon0, lat0, float(h["lon"]), float(h["lat"]))
        s_dist = max(0.0, 1.0 - d / max_step_out_km)

        def ullage(cap_key: str, cur_key: str, req: float | None, label: str) -> float | None:
            cap, cur = h.get(cap_key), h.get(cur_key)
            if req is None:
                return None
            if cap is None or cur is None:
                notes.append("%s ullage unknown" % label)
                return 0.5
            free = max(0.0, float(cap) - float(cur))
            return min(1.0, free / req) if req > 0 else 1.0

        if kind == "standalone":
            s_ull = 1.0
        else:
            parts = [
                v
                for v in (
                    ullage("oil_capacity_m3d", "oil_m3d_current", required_oil_m3d, "oil"),
                    ullage("gas_capacity_mm3d", "gas_mm3d_current", required_gas_mm3d, "gas"),
                )
                if v is not None
            ]
            if not parts:
                notes.append("no required rate given; ullage not scored")
            s_ull = min(parts) if parts else 0.5
        wd = h.get("water_depth_m")
        if target_water_depth_m is None or wd is None or kind == "standalone":
            s_wd = 1.0 if kind == "standalone" else 0.5
        else:
            dd = abs(float(wd) - float(target_water_depth_m))
            s_wd = 1.0 if dd <= 500 else max(0.0, 1.0 - (dd - 500) / 1500)
        op = str(h.get("operator") or "").strip().upper()
        s_op = 1.0 if op and op in pref else 0.5
        life = h.get("remaining_life_years")
        if life is None:
            notes.append("remaining host life unknown")
            s_life = 0.5
        else:
            s_life = max(0.0, min(1.0, float(life) / 20.0))
        sub = {
            "distance": s_dist,
            "ullage": s_ull,
            "water_depth": s_wd,
            "operator": s_op,
            "remaining_life": s_life,
        }
        score = sum(w.get(k, 0.0) * v for k, v in sub.items()) / wsum
        out.append(
            {
                "name": h.get("name"),
                "kind": kind,
                "operator": h.get("operator"),
                "distance_km": round(d, 1),
                "feasible_step_out": d <= max_step_out_km,
                "score": round(score, 3),
                "sub_scores": {k: round(v, 3) for k, v in sub.items()},
                "flags": list(h.get("flags") or []),
                "notes": notes,
            }
        )
    out.sort(key=lambda r: (-r["score"], r["distance_km"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
