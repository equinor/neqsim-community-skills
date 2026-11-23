"""Pipe routing for scene connections.

Three modes, chosen per connection:

- ``supplied``: the connection carries ``route`` (list of [x, y, z] in the scene
  frame), for example from an isometric, a 3D model export, a layout study or a
  surveyed line. The route is used as given; endpoints are joined to the
  equipment nozzles (or faces).
- ``orthogonal``: plant-scale automatic route in pipe-rack style. The pipe leaves
  the source nozzle, rises to a rack elevation that clears every object under
  the run, runs along x then y (falling toward the target when ``min_slope`` is
  set), drops and enters the target nozzle. Parallel pipes get separate rack
  lanes, and a pipe that still clashes with another pipe or an object is moved
  to a free lane. Recorded as assumed.
- ``seabed``: field-scale route along the seabed between the two objects.

End points, in order of preference: a named nozzle on the object
(``from_port``/``to_port`` matching a key in ``obj["nozzles"]`` or a nozzle's
``service``), a port-name convention (gas, vapour, overhead, vent -> top centre;
liquid, oil, water, condensate, drain, bottoms -> bottom centre), then the face
of the envelope that looks toward the other end. Each end records which rule
was used so the report can say how many nozzle positions are real.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

from .schema import AssetScene, geometry_bounds

Point = list[float]

FIELD_SCALE_M = 500.0
CLEARANCE_M = 1.0
STANDOFF_M = 0.6
CLASH_GAP_M = 0.05
MAX_LANE_TRIES = 8

TOP_WORDS = ("gas", "vapour", "vapor", "overhead", "vent", "top", "steam")
BOTTOM_WORDS = (
    "liquid",
    "oil",
    "water",
    "condensate",
    "drain",
    "bottom",
    "bottoms",
    "sump",
)
NOT_OBSTACLES = ("deck", "area", "reservoir", "support")


# ----------------------------------------------------------------- end points
def _unit(v: Sequence[float]) -> Point:
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 0 else [0.0, 0.0, 1.0]


def _face_point(
    bounds: Sequence[float], toward: Sequence[float]
) -> tuple[Point, Point]:
    """Point on the box face that looks toward ``toward`` (mid-height) and its outward direction."""
    cx, cy = (bounds[0] + bounds[3]) / 2.0, (bounds[1] + bounds[4]) / 2.0
    cz = (bounds[2] + bounds[5]) / 2.0
    dx, dy = toward[0] - cx, toward[1] - cy
    if abs(dx) >= abs(dy):
        return [bounds[3] if dx >= 0 else bounds[0], cy, cz], [
            1.0 if dx >= 0 else -1.0,
            0.0,
            0.0,
        ]
    return [cx, bounds[4] if dy >= 0 else bounds[1], cz], [
        0.0,
        1.0 if dy >= 0 else -1.0,
        0.0,
    ]


def _find_nozzle(obj: dict[str, Any], port: str | None) -> dict[str, Any] | None:
    if not port:
        return None
    key = str(port).lower()
    for nid, noz in (obj.get("nozzles") or {}).items():
        if str(nid).lower() == key or str(noz.get("service", "")).lower() == key:
            return noz
    return None


def end_point(
    obj: dict[str, Any],
    port: str | None,
    toward: Sequence[float],
    slot: int = 0,
    spacing: float = 0.5,
) -> dict[str, Any]:
    """Pipe end on an object: ``{"point", "direction", "basis"}`` (basis: nozzle, port_convention, face).

    ``slot`` spreads several pipes that would use the same face or port
    convention side by side (0, +1, -1, +2, ... times ``spacing``) so they get
    their own nozzle positions instead of overlapping. Named nozzles are not moved.
    """
    b = geometry_bounds(obj["geometry"])
    centre = [(b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0, (b[2] + b[5]) / 2.0]
    noz = _find_nozzle(obj, port)
    if noz is not None:
        if "position_m" in noz:
            p = [float(c) for c in noz["position_m"]]
        else:
            p = [centre[i] + float(noz["offset_m"][i]) for i in range(3)]
        d = (
            _unit(noz["direction"])
            if noz.get("direction")
            else _unit([p[i] - centre[i] for i in range(3)])
        )
        return {"point": p, "direction": d, "basis": "nozzle"}
    word = str(port or "").lower()
    if any(w in word for w in TOP_WORDS):
        p, d, basis = [centre[0], centre[1], b[5]], [0.0, 0.0, 1.0], "port_convention"
    elif any(w in word for w in BOTTOM_WORDS):
        p, d, basis = [centre[0], centre[1], b[2]], [0.0, 0.0, -1.0], "port_convention"
    else:
        p, d = _face_point(b, toward)
        basis = "face"
    if slot:
        tangent = [1.0, 0.0, 0.0] if abs(d[2]) > 0.5 else [-d[1], d[0], 0.0]
        k = (slot + 1) // 2 * (1 if slot % 2 else -1)
        half = [(b[3] - b[0]) / 2.0, (b[4] - b[1]) / 2.0, (b[5] - b[2]) / 2.0]
        reach = sum(abs(tangent[i]) * half[i] for i in range(3))
        shift = max(-reach, min(reach, k * spacing))
        p = [p[i] + tangent[i] * shift for i in range(3)]
    return {"point": p, "direction": d, "basis": basis}


def _standoff(end: dict[str, Any], distance: float = STANDOFF_M) -> Point:
    return [end["point"][i] + end["direction"][i] * distance for i in range(3)]


def _dedupe(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or any(abs(p[i] - out[-1][i]) > 1e-6 for i in range(3)):
            out.append([float(c) for c in p])
    return out


# ------------------------------------------------------------------- geometry
def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return max(a0, b0) <= min(a1, b1)


def _footprint_hits(
    bounds: Sequence[float], p: Sequence[float], q: Sequence[float], pad: float
) -> bool:
    xmin, ymin, xmax, ymax = (
        bounds[0] - pad,
        bounds[1] - pad,
        bounds[3] + pad,
        bounds[4] + pad,
    )
    return _overlaps(min(p[0], q[0]), max(p[0], q[0]), xmin, xmax) and _overlaps(
        min(p[1], q[1]), max(p[1], q[1]), ymin, ymax
    )


def segment_distance(
    p1: Sequence[float], q1: Sequence[float], p2: Sequence[float], q2: Sequence[float]
) -> float:
    """Minimum distance between two 3D segments."""
    d1 = [q1[i] - p1[i] for i in range(3)]
    d2 = [q2[i] - p2[i] for i in range(3)]
    r = [p1[i] - p2[i] for i in range(3)]
    a = sum(c * c for c in d1)
    e = sum(c * c for c in d2)
    f = sum(d2[i] * r[i] for i in range(3))
    if a <= 1e-12 and e <= 1e-12:
        return math.sqrt(sum(c * c for c in r))
    if a <= 1e-12:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = sum(d1[i] * r[i] for i in range(3))
        if e <= 1e-12:
            t, s = 0.0, min(max(-c / a, 0.0), 1.0)
        else:
            b = sum(d1[i] * d2[i] for i in range(3))
            denom = a * e - b * b
            s = min(max((b * f - c * e) / denom, 0.0), 1.0) if denom > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t, s = 1.0, min(max((b - c) / a, 0.0), 1.0)
    diff = [p1[i] + d1[i] * s - (p2[i] + d2[i] * t) for i in range(3)]
    return math.sqrt(sum(c * c for c in diff))


def segment_hits_box(
    p: Sequence[float], q: Sequence[float], bounds: Sequence[float], pad: float = 0.0
) -> bool:
    """Slab test: does segment p-q pass through the (padded) box?"""
    t0, t1 = 0.0, 1.0
    for i in range(3):
        lo, hi = bounds[i] - pad, bounds[i + 3] + pad
        d = q[i] - p[i]
        if abs(d) < 1e-12:
            if p[i] < lo or p[i] > hi:
                return False
            continue
        ta, tb = (lo - p[i]) / d, (hi - p[i]) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return False
    return True


# -------------------------------------------------------------------- routers
def orthogonal_route(
    scene: AssetScene,
    source: dict[str, Any],
    target: dict[str, Any],
    diameter: float,
    lane: int = 0,
    conn: dict[str, Any] | None = None,
    slots: tuple[int, int] = (0, 0),
) -> dict[str, Any]:
    """Pipe-rack route between two objects; returns ``{"points", "ends"}``."""
    conn = conn or {}
    sb = geometry_bounds(source["geometry"])
    tb = geometry_bounds(target["geometry"])
    tc = [(tb[0] + tb[3]) / 2.0, (tb[1] + tb[4]) / 2.0, (tb[2] + tb[5]) / 2.0]
    sc = [(sb[0] + sb[3]) / 2.0, (sb[1] + sb[4]) / 2.0, (sb[2] + sb[5]) / 2.0]
    spacing = max(3.0 * diameter, 0.5)
    s_end = end_point(source, conn.get("from_port"), tc, slots[0], spacing)
    t_end = end_point(target, conn.get("to_port"), sc, slots[1], spacing)
    s_out = _standoff(s_end)
    t_out = _standoff(t_end)
    s_path = [s_end["point"], s_out] + _escape(s_end, s_out, sb, tc)
    t_path = list(reversed(_escape(t_end, t_out, tb, sc))) + [t_out, t_end["point"]]
    s_out, t_out = s_path[-1], t_path[0]
    corner = [t_out[0], s_out[1]]
    legs = [(s_out, corner), (corner, t_out)]
    rack = max(s_out[2], t_out[2])
    pad = diameter + 0.2
    for obj in scene.objects:
        if obj["kind"] in NOT_OBSTACLES or obj["geometry"]["shape"] == "polyline":
            continue
        b = geometry_bounds(obj["geometry"])
        if any(_footprint_hits(b, p, q, pad) for p, q in legs):
            rack = max(rack, b[5])
    rack += CLEARANCE_M + lane * max(3.0 * diameter, 0.3)
    slope = float(conn.get("min_slope") or 0.0)
    run1 = abs(corner[0] - s_out[0])
    run2 = abs(t_out[1] - corner[1])
    # A sloped line starts higher and falls toward the target; its low point stays at the rack.
    z0 = rack + slope * (run1 + run2)
    z1 = z0 - slope * run1
    z2 = z1 - slope * run2
    points = _dedupe(
        s_path
        + [
            [s_out[0], s_out[1], z0],
            [corner[0], corner[1], z1],
            [t_out[0], t_out[1], z2],
        ]
        + t_path
    )
    return {"points": points, "ends": [s_end["basis"], t_end["basis"]]}


def _escape(
    end: dict[str, Any], out: Point, bounds: Sequence[float], toward: Sequence[float]
) -> list[Point]:
    """For a downward (bottom) nozzle, step sideways clear of the envelope before the riser."""
    if end["direction"][2] > -0.5:
        return []
    face, d = _face_point(bounds, toward)
    return [
        [
            face[0] + d[0] * STANDOFF_M if d[0] else out[0],
            face[1] + d[1] * STANDOFF_M if d[1] else out[1],
            out[2],
        ]
    ]


def seabed_route(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Field-scale route along the seabed between object bases."""
    sb = geometry_bounds(source["geometry"])
    tb = geometry_bounds(target["geometry"])
    pts = _dedupe(
        [
            [(sb[0] + sb[3]) / 2.0, (sb[1] + sb[4]) / 2.0, sb[2]],
            [(tb[0] + tb[3]) / 2.0, (tb[1] + tb[4]) / 2.0, tb[2]],
        ]
    )
    return {"points": pts, "ends": ["base", "base"]}


def supplied_route(
    source: dict[str, Any],
    target: dict[str, Any],
    route: Sequence[Sequence[float]],
    conn: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Supplied route joined to the nozzle (or nearest face) of each end object."""
    conn = conn or {}
    pts = [[float(c) for c in p] for p in route]
    start = end_point(source, conn.get("from_port"), pts[0])
    end = end_point(target, conn.get("to_port"), pts[-1])
    return {
        "points": _dedupe([start["point"]] + pts + [end["point"]]),
        "ends": [start["basis"], end["basis"]],
    }


def route_mode(scene: AssetScene, conn: dict[str, Any], routing: str = "auto") -> str:
    """Routing mode for one connection."""
    if conn.get("route"):
        return "supplied"
    if routing in ("orthogonal", "seabed", "straight"):
        return routing
    b = scene.bounds()
    return "seabed" if max(b[3] - b[0], b[4] - b[1]) > FIELD_SCALE_M else "orthogonal"


# --------------------------------------------------------------------- clashes
def _segments(
    points: Sequence[Sequence[float]], skip_ends: bool
) -> list[tuple[Sequence[float], Sequence[float]]]:
    segs = list(itertools.pairwise(points))
    if skip_ends:
        return segs[1:-1] if len(segs) > 2 else []
    return segs


def pipe_clashes(
    routes: dict[str, dict[str, Any]],
    radii: dict[str, float],
    ends: dict[str, tuple[str, str]],
) -> list[dict[str, Any]]:
    """Pipe-to-pipe clashes closer than the sum of radii plus a gap.

    Pipes that share an equipment item may meet at its nozzle stubs, so their
    first and last segments are not compared.
    """
    ids = list(routes)
    out: list[dict[str, Any]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            limit = radii[a] + radii[b] + CLASH_GAP_M
            shared = bool(set(ends[a]) & set(ends[b]))
            best = min(
                (
                    segment_distance(p1, q1, p2, q2)
                    for p1, q1 in _segments(routes[a]["points"], shared)
                    for p2, q2 in _segments(routes[b]["points"], shared)
                ),
                default=float("inf"),
            )
            if best < limit:
                out.append(
                    {
                        "type": "pipe",
                        "a": a,
                        "b": b,
                        "distance_m": round(best, 3),
                        "required_m": round(limit, 3),
                    }
                )
    return out


def object_clashes(
    scene: AssetScene,
    routes: dict[str, dict[str, Any]],
    radii: dict[str, float],
    ends: dict[str, tuple[str, str]],
) -> list[dict[str, Any]]:
    """Pipes passing through equipment: any other item, or their own end items beyond the nozzle stubs."""
    out: list[dict[str, Any]] = []
    for cid, route in routes.items():
        all_segs = list(zip(route["points"][:-1], route["points"][1:]))
        inner = _segments(route["points"], True)
        for obj in scene.objects:
            if obj["kind"] in NOT_OBSTACLES or obj["geometry"]["shape"] == "polyline":
                continue
            b = geometry_bounds(obj["geometry"])
            if obj["id"] in ends[cid]:
                hit = any(segment_hits_box(p, q, b, -0.05) for p, q in inner)
            else:
                hit = any(segment_hits_box(p, q, b, radii[cid]) for p, q in all_segs)
            if hit:
                out.append({"type": "object", "a": cid, "b": obj["id"]})
    return out


# ------------------------------------------------------------------ top level
def route_connections(
    scene: AssetScene,
    diameter: float,
    routing: str = "auto",
    resolve_clashes: bool = True,
) -> dict[str, dict[str, Any]]:
    """Route every connection; returns ``{connection id: {"points", "mode", "ends", "lane"}}``.

    Automatic rack routes get their own lane in order; with ``resolve_clashes``
    an automatic route that still clashes with an earlier pipe or an object is
    moved up lane by lane (up to ``MAX_LANE_TRIES``). Remaining clashes are
    reported by ``check_clashes``.
    """
    out: dict[str, dict[str, Any]] = {}
    radii: dict[str, float] = {}
    ends: dict[str, tuple[str, str]] = {}
    used: dict[tuple[str, tuple[float, ...]], int] = {}

    def slot_for(obj: dict[str, Any], port: str | None, toward: Sequence[float]) -> int:
        base = end_point(obj, port, toward)
        if base["basis"] == "nozzle":
            return 0
        key = (obj["id"], tuple(round(c, 3) for c in base["point"]))
        used[key] = used.get(key, -1) + 1
        return used[key]

    lane = 0
    for conn in scene.connections:
        a = scene.get(conn["from"])
        b = scene.get(conn["to"])
        if a is None or b is None:
            continue
        d = float(conn.get("diameter") or diameter)
        cid = conn["id"]
        radii[cid] = d / 2.0
        ends[cid] = (a["id"], b["id"])
        mode = route_mode(scene, conn, routing)
        if mode == "supplied":
            r = supplied_route(a, b, conn["route"], conn)
        elif mode == "orthogonal":
            sbb, tbb = geometry_bounds(a["geometry"]), geometry_bounds(b["geometry"])
            slots = (
                slot_for(
                    a,
                    conn.get("from_port"),
                    [(tbb[i] + tbb[i + 3]) / 2.0 for i in range(3)],
                ),
                slot_for(
                    b,
                    conn.get("to_port"),
                    [(sbb[i] + sbb[i + 3]) / 2.0 for i in range(3)],
                ),
            )
            tries = MAX_LANE_TRIES if resolve_clashes else 1
            first = None
            chosen = None
            for attempt in range(tries):
                cand = orthogonal_route(scene, a, b, d, lane + attempt, conn, slots)
                cand["lane"] = lane + attempt
                if first is None:
                    first = cand
                if not resolve_clashes:
                    chosen = cand
                    break
                trial = dict(out)
                trial[cid] = cand
                own = [
                    c
                    for c in pipe_clashes(trial, radii, ends)
                    if cid in (c["a"], c["b"])
                ]
                own += object_clashes(scene, {cid: cand}, radii, ends)
                if not own:
                    chosen = cand
                    break
            r = chosen or first  # type: ignore[assignment]
            lane = r["lane"] + 1
        elif mode == "seabed":
            r = seabed_route(a, b)
        else:
            sb, tb = geometry_bounds(a["geometry"]), geometry_bounds(b["geometry"])
            r = {
                "points": [
                    [(sb[i] + sb[i + 3]) / 2.0 for i in range(3)],
                    [(tb[i] + tb[i + 3]) / 2.0 for i in range(3)],
                ],
                "ends": ["centre", "centre"],
            }
        r["mode"] = mode
        out[cid] = r
    return out


def check_clashes(
    scene: AssetScene, routes: dict[str, dict[str, Any]], diameter: float
) -> list[dict[str, Any]]:
    """All remaining pipe-to-pipe and pipe-to-equipment clashes for routed connections."""
    radii: dict[str, float] = {}
    ends: dict[str, tuple[str, str]] = {}
    for conn in scene.connections:
        if conn["id"] in routes:
            radii[conn["id"]] = float(conn.get("diameter") or diameter) / 2.0
            ends[conn["id"]] = (conn["from"], conn["to"])
    return pipe_clashes(routes, radii, ends) + object_clashes(
        scene, routes, radii, ends
    )


def route_length(points: Sequence[Sequence[float]]) -> float:
    """Length of a route in metres."""
    return sum(
        sum((q[i] - p[i]) ** 2 for i in range(3)) ** 0.5
        for p, q in itertools.pairwise(points)
    )


def routing_summary(routes: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Count of connections per routing mode."""
    counts: dict[str, int] = {}
    for r in routes.values():
        counts[r["mode"]] = counts.get(r["mode"], 0) + 1
    return counts


ROUTE_WORDS = {
    "supplied": "routed from supplied geometry",
    "orthogonal": "auto-routed over a pipe rack (assumed)",
    "seabed": "auto-routed along the seabed (assumed)",
    "straight": "straight schematic links",
}


def describe_routing(counts: dict[str, int]) -> str | None:
    """Caption sentence for the routing used."""
    if not counts:
        return None
    parts = [f"{n} {ROUTE_WORDS[m]}" for m, n in sorted(counts.items())]
    return (
        "Connections: "
        + ", ".join(parts)
        + "; auto routes are illustrative, not the as-built path."
    )
