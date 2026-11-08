"""Constraint screening of subsea equipment sites and routes.

No limit value is built in. Every numeric limit is a :class:`Limit` that carries its value, unit, source and basis. A check with a
missing or non-approved limit never reports PASS or FAIL: it reports NEEDS_REVIEW together with the indicative outcome, so a screening
number cannot be read as compliance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import geo

APPROVED_BASES = ("APPROVED", "SUPPLIED")


@dataclass
class Limit:
    """A limit with provenance. ``basis``: APPROVED or SUPPLIED (with a source), ASSUMED or NONE (screening only)."""

    value: Optional[float] = None
    unit: str = ""
    source: str = ""
    basis: str = "NONE"

    @property
    def approved(self) -> bool:
        """True when the limit has a value, an approved/supplied basis and a source."""
        return self.value is not None and self.basis in APPROVED_BASES and bool(self.source)


@dataclass
class Structure:
    """An existing or planned subsea structure or host with an exclusion radius limit."""

    id: str
    point: geo.Point
    kind: str = "structure"
    clearance: Limit = field(default_factory=Limit)


@dataclass
class Line:
    """An existing line, cable or umbilical as a polyline in local metres."""

    id: str
    points: List[geo.Point]
    kind: str = "pipeline"
    status: str = "existing"
    service: str = ""
    clearance: Limit = field(default_factory=Limit)


@dataclass
class Zone:
    """A polygon zone (safety zone, caution area, restricted area).

    ``hard`` zones may not be entered by new equipment. Zones that only need approval or procedure (for example vessel exclusion or
    caution zones) are ``hard=False``: a route that enters one is listed in ``zones_entered`` with its type so the approval is planned.
    """

    id: str
    ring: List[geo.Point]
    type: str = "zone"
    active: bool = True
    hard: bool = True


@dataclass
class Target:
    """A reservoir target for a well: horizontal position and true vertical depth below the seabed."""

    id: str
    point: geo.Point
    tvd_below_seabed_m: float


@dataclass
class PlacementBasis:
    """Everything a screening needs. Coordinates are local metres (see :func:`geo.to_local`)."""

    host: Optional[Structure] = None
    structures: List[Structure] = field(default_factory=list)
    lines: List[Line] = field(default_factory=list)
    zones: List[Zone] = field(default_factory=list)
    targets: List[Target] = field(default_factory=list)
    depth_fn: Optional[Callable[[float, float], float]] = None          # positive-down water depth, m
    fishing_fn: Optional[Callable[[float, float], float]] = None        # user-defined fishing intensity
    limits: Dict[str, Limit] = field(default_factory=dict)
    slope_radius_m: float = 100.0


def _check(cid: str, desc: str, value: Optional[float], unit: str, limit: Optional[Limit], op: str, note: str = "") -> dict:
    """Build one check row. ``op`` is '>=' (value must be at least the limit) or '<=' (value must not exceed it)."""
    row = {"id": cid, "description": desc, "value": None if value is None else float(value), "unit": unit, "operator": op,
           "limit": None if limit is None else limit.value, "limit_basis": "NONE" if limit is None else limit.basis,
           "limit_source": "" if limit is None else limit.source, "note": note, "indicative": None}
    if value is None:
        row["status"] = "NOT_ASSESSED"
        return row
    if limit is None or limit.value is None:
        row["status"] = "NEEDS_REVIEW"
        return row
    ok = value >= limit.value if op == ">=" else value <= limit.value
    row["indicative"] = "PASS" if ok else "FAIL"
    row["status"] = row["indicative"] if limit.approved else "NEEDS_REVIEW"
    return row


def screen_site(site: geo.Point, basis: PlacementBasis, kind: str = "template") -> dict:
    """Screen one site against exclusion zones, structures, lines, seabed and well reach. Returns checks and a verdict."""
    L = basis.limits
    checks: List[dict] = []
    if basis.zones:
        near = min(((geo.point_polygon_distance(site, z.ring), z) for z in basis.zones if z.hard and z.active), key=lambda t: t[0], default=None)
        if near:
            checks.append(_check("ZONE", "Distance to the nearest active hard zone (0 = inside %s)" % near[1].id, near[0], "m", L.get("zone_clearance_m"), ">="))
    if basis.structures or basis.host:
        items = list(basis.structures) + ([basis.host] if basis.host else [])
        d, s = min(((geo.dist(site, s.point), s) for s in items), key=lambda t: t[0])
        checks.append(_check("STRUCT", "Distance to the nearest structure (%s)" % s.id, d, "m", s.clearance if s.clearance.value is not None else L.get("structure_clearance_m"), ">="))
    if basis.lines:
        d, ln = min(((geo.point_polyline_distance(site, l.points), l) for l in basis.lines), key=lambda t: t[0])
        checks.append(_check("LINE", "Distance to the nearest existing line (%s)" % ln.id, d, "m", ln.clearance if ln.clearance.value is not None else L.get("line_clearance_m"), ">="))
    if basis.depth_fn:
        checks.append(_check("SLOPE", "Maximum seabed slope within %.0f m" % basis.slope_radius_m, geo.slope_deg(basis.depth_fn, site, basis.slope_radius_m), "deg", L.get("max_slope_deg"), "<="))
        checks.append(_check("DEPTH", "Water depth", basis.depth_fn(*site), "m", L.get("max_water_depth_m"), "<="))
        if L.get("min_water_depth_m") is not None:
            checks.append(_check("DEPTH_MIN", "Water depth against the supported minimum", basis.depth_fn(*site), "m", L.get("min_water_depth_m"), ">="))
    if basis.fishing_fn:
        checks.append(_check("FISHING", "Fishing intensity at the site (user-defined measure)", basis.fishing_fn(*site), "-", L.get("max_fishing_intensity"), "<="))
    if basis.targets:
        reach = [(geo.dist(site, t.point), t) for t in basis.targets]
        far, tf = max(reach, key=lambda r: r[0])
        checks.append(_check("REACH", "Largest horizontal reach to a target (%s)" % tf.id, far, "m", L.get("max_horizontal_reach_m"), "<="))
        erd = max(d / t.tvd_below_seabed_m for d, t in reach if t.tvd_below_seabed_m > 0)
        checks.append(_check("ERD", "Largest horizontal-reach to TVD ratio", erd, "-", L.get("max_erd_ratio"), "<="))
    if basis.host:
        checks.append(_check("STEPOUT", "Distance to the host", geo.dist(site, basis.host.point), "m", L.get("max_stepout_m"), "<="))
    hard_fail = [c["id"] for c in checks if c["status"] == "FAIL"]
    indicative_fail = [c["id"] for c in checks if c["status"] == "NEEDS_REVIEW" and c["indicative"] == "FAIL"]
    verdict = "FAIL" if hard_fail else ("NEEDS_REVIEW" if any(c["status"] in ("NEEDS_REVIEW", "NOT_ASSESSED") for c in checks) else "PASS")
    return {"site": site, "kind": kind, "checks": checks, "verdict": verdict, "hard_fail": hard_fail, "indicative_fail": indicative_fail}


def screen_route(route: Sequence[geo.Point], basis: PlacementBasis, terminal_zone_ids: Sequence[str] = (), step_m: float = 25.0,
                 search_radius_m: float = 2000.0) -> dict:
    """Screen a route: length, crossings (count and angle), parallel clearance, hard-zone entry, slope and straight end lengths.

    Parallel clearance considers lines inside a ``search_radius_m`` box around the route (a larger radius costs time only)."""
    L = basis.limits
    pts = [tuple(p) for p in route]
    length = geo.polyline_length(pts)
    checks = [_check("LENGTH", "Route length", length, "m", L.get("max_route_length_m"), "<=")]
    crossings = []
    for ln in basis.lines:
        for ch, ang in geo.polyline_crossings(pts, ln.points):
            crossings.append({"line": ln.id, "kind": ln.kind, "status": ln.status, "chainage_m": ch, "angle_deg": ang})
    checks.append(_check("XCOUNT", "Number of crossings with existing lines", len(crossings), "-", L.get("max_crossings"), "<="))
    if crossings:
        checks.append(_check("XANGLE", "Smallest crossing angle", min(c["angle_deg"] for c in crossings), "deg", L.get("min_crossing_angle_deg"), ">="))
    samples = geo.densify(pts, step_m)
    clear, near = float("inf"), None
    rx0, rx1 = min(p[0] for p in pts) - search_radius_m, max(p[0] for p in pts) + search_radius_m
    ry0, ry1 = min(p[1] for p in pts) - search_radius_m, max(p[1] for p in pts) + search_radius_m
    for ln in basis.lines:
        if any(c["line"] == ln.id for c in crossings):
            continue  # a crossing is treated by its own checks; clearance applies to the approach and departure
        if max(p[0] for p in ln.points) < rx0 or min(p[0] for p in ln.points) > rx1 or max(p[1] for p in ln.points) < ry0 or min(p[1] for p in ln.points) > ry1:
            continue  # outside the search box around the route
        for ch, p in samples:
            d = geo.point_polyline_distance(p, ln.points)
            if d < clear:
                clear, near = d, ln
    if near is not None:
        checks.append(_check("PARALLEL", "Smallest clearance to a non-crossed line (%s)" % near.id, clear, "m", near.clearance if near.clearance.value is not None else L.get("line_clearance_m"), ">="))
    entries = []
    zones_entered = []
    for z in basis.zones:
        if not z.active or z.id in terminal_zone_ids:
            continue
        if any(geo.point_in_polygon(p, z.ring) for _, p in samples):
            zones_entered.append({"id": z.id, "type": z.type, "hard": z.hard})
            if z.hard:
                entries.append(z.id)
    checks.append({"id": "ZONEENTRY", "description": "Active hard zones entered other than at a terminal zone", "value": float(len(entries)), "unit": "-",
                   "operator": "<=", "limit": 0.0, "limit_basis": "SUPPLIED", "limit_source": "route definition", "note": ", ".join(entries),
                   "indicative": "PASS" if not entries else "FAIL", "status": "PASS" if not entries else "FAIL"})
    if basis.depth_fn:
        checks.append(_check("SLOPE", "Maximum seabed slope along the route", max(geo.slope_deg(basis.depth_fn, p, basis.slope_radius_m) for _, p in samples), "deg", L.get("max_slope_deg"), "<="))
    for label, seg_a, seg_b in (("START", pts[0], pts[1]), ("END", pts[-1], pts[-2])):
        checks.append(_check("STRAIGHT_" + label, "Straight length at the %s of the route" % label.lower(), geo.dist(seg_a, seg_b), "m", L.get("min_straight_end_m"), ">="))
    hard_fail = [c["id"] for c in checks if c["status"] == "FAIL"]
    verdict = "FAIL" if hard_fail else ("NEEDS_REVIEW" if any(c["status"] in ("NEEDS_REVIEW", "NOT_ASSESSED") for c in checks) else "PASS")
    return {"length_m": length, "crossings": crossings, "zones_entered": zones_entered, "checks": checks, "verdict": verdict, "hard_fail": hard_fail}


def candidate_grid(center: geo.Point, half_width_m: float, step_m: float, region: Optional[Sequence[geo.Point]] = None) -> List[geo.Point]:
    """Square grid of candidate sites around ``center``; optionally keep only those inside ``region``."""
    n = int(half_width_m // step_m)
    pts = [(center[0] + i * step_m, center[1] + j * step_m) for i in range(-n, n + 1) for j in range(-n, n + 1)]
    return [p for p in pts if region is None or geo.point_in_polygon(p, region)]


def rank_sites(candidates: Sequence[geo.Point], basis: PlacementBasis, weights: Optional[Dict[str, float]] = None,
               route_fn: Optional[Callable[[geo.Point], Sequence[geo.Point]]] = None) -> List[dict]:
    """Screen and rank sites. Sites with a hard FAIL are listed last. Score (lower is better) is a weighted sum of
    mean target reach, host step-out and crossings; weights default to 1 (reach), 1 (step-out) and 1000 m per crossing and are
    declared assumptions, not design values."""
    w = {"reach": 1.0, "stepout": 1.0, "crossing": 1000.0}
    w.update(weights or {})
    out = []
    for c in candidates:
        r = screen_site(c, basis)
        reach = sum(geo.dist(c, t.point) for t in basis.targets) / len(basis.targets) if basis.targets else 0.0
        step = geo.dist(c, basis.host.point) if basis.host else 0.0
        nx = 0
        if route_fn is not None and basis.host:
            rr = screen_route(route_fn(c), basis, terminal_zone_ids=[z.id for z in basis.zones if basis.host and geo.point_in_polygon(basis.host.point, z.ring)])
            nx = len(rr["crossings"])
            r["route"] = {"length_m": rr["length_m"], "crossings": nx, "verdict": rr["verdict"], "hard_fail": rr["hard_fail"]}
            if rr["hard_fail"]:
                r["hard_fail"] = r["hard_fail"] + ["ROUTE:" + h for h in rr["hard_fail"]]
                r["verdict"] = "FAIL"
        r["score"] = w["reach"] * reach + w["stepout"] * step + w["crossing"] * nx + 500.0 * len(r["indicative_fail"])
        r["mean_reach_m"], r["stepout_m"] = reach, step
        out.append(r)
    out.sort(key=lambda r: (r["verdict"] == "FAIL", r["score"]))
    return out


def to_geojson(items: Sequence[dict], origin: Tuple[float, float]) -> dict:
    """GeoJSON FeatureCollection (WGS84) of screened sites (points) with verdicts."""
    feats = []
    for r in items:
        lon, lat = geo.to_lonlat(r["site"][0], r["site"][1], origin[0], origin[1])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"verdict": r["verdict"], "score": r.get("score"), "hard_fail": r["hard_fail"], "indicative_fail": r["indicative_fail"]}})
    return {"type": "FeatureCollection", "features": feats}
