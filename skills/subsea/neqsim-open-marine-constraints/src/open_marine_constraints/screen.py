"""Screen a route or point against the registry layers: crossings, km inside, nearest distance, raster exposure."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .client import MarineClient, SourceError
from .geometry import (
    LocalProjection,
    LonLat,
    densify,
    distance_to_geometry,
    feature_geometry_xy,
    haversine_m,
    inside_polygons,
    route_bbox,
    route_length_m,
    segments_intersect,
)
from .sources import SOURCES

NAME_KEYS = ("name", "navn", "NAVN", "offisieltNavn", "Name", "NAME", "title", "id")
VALUE_FIELD = "mw_fshn"  # EMODnet fishing effort: average MW fishing hours (engine power x hours) per C-square

CAVEATS = [
    "Open data is a screening layer: positions and attributes are as published, not survey grade.",
    "A layer that returns zero features means none in the published layer, not that the hazard is absent.",
    "Fishing effort is vessel-tracking based (AIS/VMS) and misses small vessels and recent change; "
    "obtain the owner's current data before sizing protection.",
    "Check the layer metadata at the owner for year, class definitions and units before quoting a value.",
]

IMPLICATIONS = {
    "fishing": "Trawl pull-over and hooking: use as input to burial/rock-dump scope (see neqsim-seabed-protection-screening).",
    "environment": "Protected or sensitive area: routing, drilling discharge and anchoring constraints; confirm with the regulator.",
    "infrastructure": "Existing pipeline/platform: crossing design and clearance (see neqsim-subsea-equipment-placement).",
    "wind": "Wind area: spatial conflict or electrification opportunity; confirm lease status with the owner.",
    "grid": "Onshore grid reach for power from shore; confirm capacity with the grid operator (not in this layer).",
    "hazard": "Obstacle or historic hazard record: survey before installation.",
    "restriction": "Spatial restriction: obtain the permit conditions from the owner.",
}


def _name(properties: Dict[str, Any]) -> str:
    for key in NAME_KEYS:
        value = properties.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def latest_period(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only the newest averaging period of the EMODnet effort layers.

    The layers hold several overlapping 4-year averaging periods per C-square; counting all of them would
    multiply km inside and mix epochs. Cells with no effort in the newest period are absent from it by design.
    """
    periodic = [f for f in features if "avgyears" in (f.get("properties") or {})]
    if not periodic:
        return features
    newest = max(str((f.get("properties") or {}).get("validto", "")) for f in periodic)
    return [f for f in features if "avgyears" not in (f.get("properties") or {}) or str(f["properties"].get("validto", "")) == newest]

def _screen_features(features: List[Dict[str, Any]], samples_xy: List[Any], step_m: float, route_xy: List[Any], buffer_m: float, proj: LocalProjection, top_n: int) -> Dict[str, Any]:
    stride = max(1, len(samples_xy) // 200)
    dist_samples = samples_xy[::stride] + [samples_xy[-1]]
    min_x = min(p[0] for p in samples_xy) - buffer_m
    max_x = max(p[0] for p in samples_xy) + buffer_m
    min_y = min(p[1] for p in samples_xy) - buffer_m
    max_y = max(p[1] for p in samples_xy) + buffer_m
    entries: List[Dict[str, Any]] = []
    km_inside = 0.0
    inside_samples_total = 0
    effort_values: List[float] = []
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        geo = feature_geometry_xy(geometry, proj)
        box = geo["bbox"]
        if box is None or box[2] < min_x or box[0] > max_x or box[3] < min_y or box[1] > max_y:
            continue
        inside_samples = sum(1 for p in samples_xy if inside_polygons(p, geo["polygons"])) if geo["polygons"] else 0
        crossings = 0
        for line in geo["lines"]:
            for i in range(len(line) - 1):
                for j in range(len(route_xy) - 1):
                    if segments_intersect(line[i], line[i + 1], route_xy[j], route_xy[j + 1]):
                        crossings += 1
        distance = 0.0 if inside_samples else min(distance_to_geometry(p, geo) for p in dist_samples)
        if crossings:
            distance = 0.0
        properties = feature.get("properties") or {}
        if inside_samples:
            km_inside += inside_samples * step_m / 1000.0
            inside_samples_total += inside_samples
            value = properties.get(VALUE_FIELD)
            if isinstance(value, (int, float)):
                effort_values.extend([float(value)] * inside_samples)
        entries.append(
            {
                "name": _name(properties),
                "distance_km": round(distance / 1000.0, 3),
                "inside_samples": inside_samples,
                "crossings": crossings,
                "within_buffer": distance <= buffer_m,
            }
        )
    entries.sort(key=lambda e: e["distance_km"])
    summary: Dict[str, Any] = {
        "features_in_box": len(entries),
        "within_buffer": sum(1 for e in entries if e["within_buffer"]),
        "intersecting": sum(1 for e in entries if e["inside_samples"] or e["crossings"]),
        "line_crossings": sum(e["crossings"] for e in entries),
        "km_inside_polygons": round(km_inside, 2),
        "nearest_km": entries[0]["distance_km"] if entries else None,
        "nearest": entries[:top_n],
    }
    if effort_values:
        summary["effort_mw_fishing_hours"] = {
            "samples_in_cells": inside_samples_total,
            "mean_along_inside_route": round(sum(effort_values) / len(effort_values), 3),
            "max": round(max(effort_values), 3),
        }
    return summary


def _sample_raster(client: MarineClient, key: str, route: Sequence[LonLat], step_km: float, max_samples: int) -> Dict[str, Any]:
    length_km = route_length_m(route) / 1000.0
    step_km = max(step_km, length_km / max_samples) if length_km > 0 else step_km
    points = densify(route, step_km * 1000.0)
    results = [(chain, client.identify(key, lon, lat)) for (lon, lat), chain in points]
    with_data = [r for _, r in results if r["has_data"]]
    classes = [r["class_value"] for r in with_data if r["class_value"] is not None]
    pixels = [r["pixel"] for r in with_data]
    numeric = []
    for p in pixels:
        try:
            numeric.append(float(p))
        except (TypeError, ValueError):
            pass
    return {
        "samples": len(results),
        "sample_spacing_km": round(step_km, 2),
        "samples_with_data": len(with_data),
        "fraction_with_data": round(len(with_data) / len(results), 3) if results else 0.0,
        "max_pixel_value": max(numeric) if numeric else None,
        "class_values_seen": sorted(set(classes)),
        "chainage_km_with_data": [round(c / 1000.0, 1) for c, r in results if r["has_data"]],
        "note": "Raster class values must be read against the owner's legend; NoData means no recorded activity cell.",
    }


def screen_route(
    client: MarineClient,
    route: Sequence[LonLat],
    layers: Sequence[str],
    buffer_km: float = 5.0,
    step_m: float = 250.0,
    max_features: int = 5000,
    raster_step_km: float = 5.0,
    max_raster_samples: int = 60,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Screen a lon/lat route (a single point is allowed) against ``layers`` from ``sources.SOURCES``.

    A layer that fails is reported under ``errors`` and does not stop the others. Distances are planar on a
    local projection, within a few tenths of a percent for routes below a few hundred kilometres.
    """
    pts = [tuple(p) for p in route]
    if not pts:
        raise ValueError("route needs at least one lon/lat point")
    if len(pts) == 1:
        pts = [pts[0], pts[0]]
    bbox = route_bbox(pts, buffer_km)
    proj = LocalProjection((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    samples = [p for p, _ in densify(pts, step_m)]
    samples_xy = [proj.forward(*p) for p in samples]
    route_xy = [proj.forward(*p) for p in pts]
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for key in layers:
        spec = SOURCES[key]
        try:
            if spec["kind"] == "raster":
                entry = _sample_raster(client, key, pts, raster_step_km, max_raster_samples)
            else:
                feature_set = client.features(key, bbox, max_features)
                features = latest_period(feature_set.features)
                entry = _screen_features(features, samples_xy, step_m, route_xy, buffer_km * 1000.0, proj, top_n)
                entry["truncated"] = feature_set.truncated
                periods = sorted({str((f.get("properties") or {}).get("avgyears")) for f in features if (f.get("properties") or {}).get("avgyears")})
                if periods:
                    entry["averaging_periods_used"] = periods
            entry.update({"theme": spec["theme"], "what": spec["what"], "owner": spec["owner"], "implication": IMPLICATIONS.get(spec["theme"], "")})
            results[key] = entry
        except (SourceError, OSError, ValueError) as error:
            errors[key] = str(error)
    return {
        "route_km": round(route_length_m(pts) / 1000.0, 3),
        "bbox": [round(v, 5) for v in bbox],
        "buffer_km": buffer_km,
        "layers": results,
        "errors": errors,
        "caveats": CAVEATS,
        "provenance": client.provenance(),
    }


def screen_earthquakes(client: MarineClient, route: Sequence[LonLat], radius_km: float = 150.0, min_magnitude: float = 4.5, start_year: int = 1900) -> Dict[str, Any]:
    """Count USGS catalogue earthquakes within ``radius_km`` of the route; a historic catalogue, not a hazard model."""
    pts = [tuple(p) for p in route]
    bbox = route_bbox(pts, radius_km)
    feature_set = client.earthquakes(bbox, min_magnitude, start_year)
    samples = [p for p, _ in densify(pts if len(pts) > 1 else [pts[0], pts[0]], 10_000.0)]
    events = []
    for feature in feature_set.features:
        lon, lat = feature["geometry"]["coordinates"][:2]
        distance = min(haversine_m((lon, lat), s) for s in samples) / 1000.0
        if distance <= radius_km:
            props = feature.get("properties", {})
            events.append({"magnitude": props.get("mag"), "place": props.get("place"), "distance_km": round(distance, 1), "year": _year(props.get("time"))})
    events.sort(key=lambda e: -(e["magnitude"] or 0))
    return {
        "radius_km": radius_km,
        "min_magnitude": min_magnitude,
        "start_year": start_year,
        "events_within_radius": len(events),
        "max_magnitude": events[0]["magnitude"] if events else None,
        "strongest": events[:5],
        "truncated": feature_set.truncated,
        "note": "Historic catalogue; completeness varies with magnitude and era. Use a probabilistic hazard study for design.",
    }


def _year(millis: Optional[float]) -> Optional[int]:
    if millis is None:
        return None
    return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc).year


def summary_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten ``screen_route`` output to one row per layer for a report table."""
    rows = []
    for key, entry in result["layers"].items():
        if "fraction_with_data" in entry:
            exposure = f"{entry['samples_with_data']}/{entry['samples']} samples with activity"
        else:
            exposure = f"{entry['intersecting']} intersecting, {entry['km_inside_polygons']} km inside, nearest {entry['nearest_km']} km"
        rows.append({"layer": key, "theme": entry["theme"], "owner": entry["owner"], "exposure": exposure})
    return rows
