"""Near-field inventory: rank the discoveries around a target and export tables, GeoJSON and notes."""

from __future__ import annotations

import csv
import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .geo import bearing_deg, circle_points, cluster_points, compass, haversine_km, point_to_rings_km
from .models import STAGE_LABELS, STAGES, Discovery

OPEN_STAGES = ("in_development", "in_clarification", "not_evaluated", "unknown")
"""Stages that can still influence a new development nearby (not producing, not written off)."""

TABLE_COLUMNS = (
    "country", "kind", "name", "stage_label", "status_raw", "hc_type", "discovery_year", "operator", "distance_km",
    "bearing", "oe_msm3", "resource_class", "water_depth_m", "nearest_host", "plan_flags", "plan_note", "source_url", "n_gaps",
)


@dataclass
class Inventory:
    """Records inside a radius around a target, ranked by distance, with the context to map them.

    Attributes:
        target: ``{"name", "lon", "lat"}`` of the study target.
        radius_km: Study radius.
        records: Records within the radius, nearest first.
        hosts: Host dicts (``name``, ``lon``, ``lat`` ...) read for the same area.
        pipelines: Pipeline dicts with ``parts`` (lists of (lon, lat)).
        layers: Optional polygon layers for the map (``blocks``, ``evaluation_plans``, ``fields``) as GeoJSON features.
        log: Provenance records of the reads.
        as_of: Date of the analysis.
    """

    target: dict[str, Any]
    radius_km: float
    records: list[Discovery]
    hosts: list[dict[str, Any]] = field(default_factory=list)
    pipelines: list[dict[str, Any]] = field(default_factory=list)
    layers: dict[str, Any] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)
    as_of: str = field(default_factory=lambda: _dt.date.today().isoformat())

    def of_kind(self, *kinds: str) -> list[Discovery]:
        """Records of the given kinds (``discovery``, ``field``, ``evaluation_area``)."""
        return [r for r in self.records if r.kind in kinds]

    def by_stage(self, kinds: Sequence[str] = ("discovery", "field")) -> dict[str, list[Discovery]]:
        """Records grouped by stage, in ladder order; empty stages are omitted."""
        out: dict[str, list[Discovery]] = {}
        for stage in STAGES:
            items = [r for r in self.records if r.stage == stage and r.kind in kinds]
            if items:
                out[stage] = items
        return out

    def summary(self) -> dict[str, Any]:
        """Counts, volume roll-up and the nearest object per stage."""
        stages = {}
        for stage, items in self.by_stage().items():
            known = [r.oe_msm3() for r in items if r.oe_msm3() is not None]
            stages[stage] = {
                "label": STAGE_LABELS[stage], "count": len(items),
                "oe_msm3_sum": round(sum(known), 3) if known else None,
                "n_without_volume": len(items) - len(known),
                "nearest": {"name": items[0].name, "kind": items[0].kind, "distance_km": _r(items[0].distance_km)},
            }
        return {
            "target": self.target, "radius_km": self.radius_km, "as_of": self.as_of,
            "n_records": len(self.records),
            "n_discoveries": len(self.of_kind("discovery")), "n_fields": len(self.of_kind("field")),
            "n_evaluation_areas": len(self.of_kind("evaluation_area")), "n_prospects": len(self.of_kind("prospect")), "stages": stages,
            "volume_note": "Volumes are summed only where the source publishes them (Sodir); ANP publishes none.",
        }

    def table(self) -> list[dict[str, Any]]:
        """Flat rows (see :data:`TABLE_COLUMNS`) for CSV or Markdown."""
        rows = []
        for r in self.records:
            host = r.nearest_hosts[0] if r.nearest_hosts else None
            rows.append({
                "country": r.country, "kind": r.kind, "name": r.name, "stage_label": STAGE_LABELS.get(r.stage, r.stage),
                "status_raw": r.status_raw, "hc_type": r.hc_type, "discovery_year": r.discovery_year, "operator": r.operator,
                "distance_km": _r(r.distance_km), "bearing": r.bearing, "oe_msm3": r.oe_msm3(),
                "resource_class": r.volumes.get("resource_class"), "water_depth_m": r.water_depth_m,
                "nearest_host": "%s (%.0f km)" % (host["name"], host["distance_km"]) if host else None,
                "plan_flags": ";".join(r.plan_flags), "plan_note": (r.plan_note or "")[:240], "source_url": r.source_url,
                "n_gaps": len(r.gaps),
            })
        return rows

    def to_geojson(self) -> dict[str, Any]:
        """GeoJSON FeatureCollection (WGS84, lon/lat) for QGIS, ArcGIS or Omnia Maps."""
        feats: list[dict[str, Any]] = [
            {"type": "Feature", "properties": {"role": "target", "name": self.target.get("name")},
             "geometry": {"type": "Point", "coordinates": [self.target["lon"], self.target["lat"]]}},
            {"type": "Feature", "properties": {"role": "study_radius", "radius_km": self.radius_km},
             "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in circle_points(self.target["lon"], self.target["lat"], self.radius_km)]]}},
        ]
        for r in self.records:
            props = r.to_dict()
            props["role"] = r.kind
            geom = ({"type": "Polygon", "coordinates": [[list(p) for p in r.rings[0]]]} if len(r.rings) == 1 else
                    {"type": "MultiPolygon", "coordinates": [[[list(p) for p in ring]] for ring in r.rings]} if r.rings else
                    {"type": "Point", "coordinates": [r.lon, r.lat]})
            feats.append({"type": "Feature", "properties": props, "geometry": geom})
            if r.rings:
                feats.append({"type": "Feature", "properties": dict(props, role=r.kind + "_label_point"),
                              "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]}})
        for h in self.hosts:
            feats.append({"type": "Feature", "properties": dict({k: v for k, v in h.items() if k not in ("lon", "lat")}, role="host"),
                          "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]}})
        for p in self.pipelines:
            feats.append({"type": "Feature", "properties": {k: v for k, v in p.items() if k != "parts"} | {"role": "pipeline"},
                          "geometry": {"type": "MultiLineString", "coordinates": [[list(q) for q in part] for part in p["parts"]]}})
        return {"type": "FeatureCollection", "features": feats}

    def write(self, folder: str | Path, stem: str = "near_field_discoveries") -> dict[str, str]:
        """Write CSV, JSON summary, GeoJSON and a Markdown note into ``folder`` and return the paths."""
        out = Path(folder)
        out.mkdir(parents=True, exist_ok=True)
        paths = {k: out / (stem + ext) for k, ext in (("csv", ".csv"), ("json", ".json"), ("geojson", ".geojson"), ("markdown", ".md"))}
        rows = self.table()
        with paths["csv"].open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(TABLE_COLUMNS))
            w.writeheader()
            w.writerows(rows)
        paths["json"].write_text(json.dumps({"summary": self.summary(), "records": [r.to_dict() for r in self.records],
                                              "clusters": area_clusters(self.records), "log": self.log}, indent=1, ensure_ascii=False, default=str),
                                 encoding="utf-8")
        paths["geojson"].write_text(json.dumps(self.to_geojson(), ensure_ascii=False, default=str), encoding="utf-8")
        paths["markdown"].write_text(to_markdown(self), encoding="utf-8")
        return {k: str(v) for k, v in paths.items()}


def _r(value: float | None, n: int = 1) -> float | None:
    return None if value is None else round(value, n)


def record_distance_km(target: tuple[float, float], rec: Discovery) -> float:
    """Distance from the target to the record outline (0 inside) or to its point."""
    d = point_to_rings_km(target[0], target[1], rec.rings) if rec.rings else None
    return d if d is not None else haversine_km(target[0], target[1], rec.lon, rec.lat)


def nearest_hosts(rec: Discovery, hosts: Iterable[Mapping[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    """The ``n`` hosts nearest to a record, as ``name``, ``distance_km``, ``kind``, ``operator``."""
    scored = sorted(
        ({"name": h.get("name"), "distance_km": round(haversine_km(rec.lon, rec.lat, h["lon"], h["lat"]), 1),
          "kind": h.get("kind"), "operator": h.get("operator"), "phase": h.get("phase")} for h in hosts if h.get("lon") is not None),
        key=lambda x: x["distance_km"])
    return scored[:n]


def near_field(point: tuple[float, float], radius_km: float, records: Iterable[Discovery], *, name: str = "target",
               hosts: Sequence[Mapping[str, Any]] | None = None, pipelines: Sequence[Mapping[str, Any]] | None = None,
               layers: Mapping[str, Any] | None = None, kinds: Sequence[str] | None = None, n_hosts: int = 3,
               log: Sequence[Mapping[str, Any]] | None = None, as_of: str | None = None) -> Inventory:
    """Select the records within ``radius_km`` of ``point`` and add distance, bearing and nearest hosts.

    Args:
        point: ``(lon, lat)`` of the target discovery or prospect.
        radius_km: Study radius in km.
        records: Records from :func:`near_field_discoveries.ncs.fetch_ncs_near_field`,
            :func:`near_field_discoveries.brazil.brazil_records` or both.
        name: Label of the target.
        hosts: Host dicts with ``name``, ``lon``, ``lat``; the nearest ``n_hosts`` are attached to every record.
        pipelines: Pipeline dicts with ``parts`` for the map and GeoJSON.
        layers: Extra map layers (``blocks``, ``evaluation_plans``) as GeoJSON features.
        kinds: Keep only these kinds (default: all).
        n_hosts: Hosts attached per record.
        log: Provenance records of the data reads.
        as_of: Analysis date (ISO); defaults to today.

    Returns:
        An :class:`Inventory` with records sorted nearest first. Records are copied so the inputs stay unchanged.
    """
    selected: list[Discovery] = []
    for rec in records:
        if kinds and rec.kind not in kinds:
            continue
        d = record_distance_km(point, rec)
        if d > radius_km:
            continue
        c = Discovery(**{k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in rec.__dict__.items()})
        c.distance_km = d
        c.bearing = compass(bearing_deg(point[0], point[1], rec.lon, rec.lat)) if d > 0.05 else "at target"
        if hosts:
            c.nearest_hosts = nearest_hosts(c, hosts, n_hosts)
        selected.append(c)
    selected.sort(key=lambda r: (r.distance_km, r.name))
    return Inventory({"name": name, "lon": point[0], "lat": point[1]}, radius_km, selected, list(hosts or []), list(pipelines or []),
                     dict(layers or {}), [dict(x) for x in (log or [])], as_of or _dt.date.today().isoformat())


def area_clusters(records: Iterable[Discovery], link_km: float = 15.0, stages: Sequence[str] = OPEN_STAGES) -> list[dict[str, Any]]:
    """Group open discoveries lying within ``link_km`` of each other: candidates for a joint development.

    Args:
        records: Inventory records (only ``kind == "discovery"`` in the given stages are used).
        link_km: Single-linkage distance between members.
        stages: Stages counted as open.

    Returns:
        One dict per cluster with members, summed Sodir oil equivalent where published, the number of
        members without a volume, the centroid and the nearest host of the first member. A cluster of one
        is a stand-alone candidate. The grouping is geometric; ownership and licence boundaries are not tested.
    """
    cand = [r for r in records if r.kind == "discovery" and r.stage in stages]
    out = []
    for g in cluster_points([(r.lon, r.lat) for r in cand], link_km):
        members = [cand[i] for i in g]
        known = [m.oe_msm3() for m in members if m.oe_msm3() is not None]
        out.append({
            "members": [m.name for m in members], "stages": sorted({m.stage for m in members}),
            "oe_msm3_sum": round(sum(known), 3) if known else None, "n_without_volume": len(members) - len(known),
            "lon": round(sum(m.lon for m in members) / len(members), 4), "lat": round(sum(m.lat for m in members) / len(members), 4),
            "nearest_host": members[0].nearest_hosts[0] if members[0].nearest_hosts else None,
            "min_distance_km": _r(min(m.distance_km for m in members if m.distance_km is not None), 1) if any(m.distance_km is not None for m in members) else None,
        })
    out.sort(key=lambda c: (c["min_distance_km"] is None, c["min_distance_km"]))
    return out


def to_markdown(inv: Inventory, max_rows: int = 40) -> str:
    """Short Markdown note: stage summary, nearest records, clusters and the data gaps to close."""
    s = inv.summary()
    lines = ["# Near-field discoveries around %s" % inv.target.get("name"),
             "", "Target %.4f N, %.4f E; radius %.0f km; analysis date %s." % (inv.target["lat"], inv.target["lon"], inv.radius_km, inv.as_of), "",
             "| Stage | Count | Sum oe (MSm3) | Without volume | Nearest |", "|---|---|---|---|---|"]
    for info in s["stages"].values():
        lines.append("| %s | %d | %s | %d | %s (%s km) |" % (info["label"], info["count"], info["oe_msm3_sum"] if info["oe_msm3_sum"] is not None else "n/a",
                                                          info["n_without_volume"], info["nearest"]["name"], info["nearest"]["distance_km"]))
    lines += ["", "| Name | Kind | Stage | HC | Operator | km | Dir | oe MSm3 | Nearest host |", "|---|---|---|---|---|---|---|---|---|"]
    for row in inv.table()[:max_rows]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % tuple(
            "" if row[k] is None else row[k] for k in ("name", "kind", "stage_label", "hc_type", "operator", "distance_km", "bearing", "oe_msm3", "nearest_host")))
    clusters = [c for c in area_clusters(inv.records) if len(c["members"]) > 1]
    if clusters:
        lines += ["", "## Open discoveries within 15 km of each other (joint-development candidates)"]
        for c in clusters:
            lines.append("- %s (oe %s MSm3; %d without volume)" % (", ".join(c["members"]), c["oe_msm3_sum"] if c["oe_msm3_sum"] is not None else "n/a", c["n_without_volume"]))
    gaps = sorted({g for r in inv.records for g in r.gaps})
    if gaps:
        lines += ["", "## Data gaps"] + ["- " + g for g in gaps]
    lines += ["", "Screening inventory from public data; confirm with the licensee/operator before any decision.", ""]
    return "\n".join(lines)
