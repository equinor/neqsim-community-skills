"""Junction graph: merges traced routes into a pipe network with explicit tees.

Every traced route runs between two terminals (equipment or off-page connectors). Routes
share strokes where lines join, so pairwise routes alone cannot say where a branch tees in.
Here all routes are rebuilt on the exact strokes they used, merged into one point graph,
and chains of degree-2 points are contracted. Points where three or more pipe pieces meet
become tee nodes, so every edge of the result is one physical run of pipe.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .geometry import Bridge, LineGraph, Point, TraceResult, dist, project, simplify


@dataclass
class NetEdge:
    """One contracted pipe run between two network nodes."""

    a: str
    b: str
    points: list[Point]
    bridges: list[Bridge] = field(default_factory=list)
    routes: set[int] = field(default_factory=set)
    length: float = 0.0


@dataclass
class Network:
    """Contracted pipe network."""

    edges: list[NetEdge]
    tees: dict[str, Point]


def build_network(graph: LineGraph, routes: list[tuple[str, TraceResult]], snap: float = 0.6,
                  attach: Optional[dict[int, Point]] = None) -> Network:
    """Merges routes (start terminal id, trace) into a contracted network with tee nodes.

    ``attach`` optionally gives, per route index, the point where the route leaves its start terminal
    when that differs from the first stroke end (a nozzle reached across a thin flange or stub).
    """
    attach = attach or {}
    keys: dict[tuple[int, int], str] = {}
    coords: dict[str, Point] = {}

    def node(p: Point) -> str:
        k = (int(round(p[0] / snap)), int(round(p[1] / snap)))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                hit = keys.get((k[0] + dx, k[1] + dy))
                if hit is not None:
                    return hit
        name = "p%d" % len(coords)
        keys[k] = name
        coords[name] = p
        return name

    adj: dict[str, dict[str, tuple[Optional[Bridge], set[int]]]] = defaultdict(dict)
    seg_points: dict[int, list[tuple[float, str]]] = defaultdict(list)
    seg_cover: dict[int, list[tuple[float, float, int]]] = defaultdict(list)

    def link(u: str, v: str, rid: int, bridge: Optional[Bridge] = None) -> None:
        if u == v:
            return
        if v in adj[u]:
            adj[u][v][1].add(rid)
            adj[v][u][1].add(rid)
            return
        adj[u][v] = (bridge, {rid})
        adj[v][u] = (bridge, {rid})

    def param(seg: int, p: Point) -> tuple[float, Point]:
        s = graph.segments[seg]
        _, c = project(p, s)
        length = max(s.length, 1e-9)
        return dist(s.a, c) / length, c

    def along(seg: int, p: Point, q: Point, rid: int) -> tuple[str, str]:
        tp, cp = param(seg, p)
        tq, cq = param(seg, q)
        u, v = node(cp), node(cq)
        seg_points[seg].append((tp, u))
        seg_points[seg].append((tq, v))
        seg_cover[seg].append((min(tp, tq), max(tp, tq), rid))
        return u, v

    for rid, (start, res) in enumerate(routes):
        term_a, term_b = "T:" + start, "T:" + res.terminal
        segs = res.segments
        if not segs:
            continue
        entry = res.entry
        start_at = attach.get(rid, entry)
        for k, seg in enumerate(segs):
            if k < len(res.steps):
                _, p_i, p_j, bridge, _ = res.steps[k]
                u, v = along(seg, entry, p_i, rid)
                if k == 0:
                    link(term_a, node(start_at), rid)
                    link(node(start_at), node(entry), rid)
                    link(node(entry), u, rid)
                link(v, node(p_i), rid)
                link(node(p_i), node(p_j), rid, bridge)
                entry = p_j
            else:
                u, v = along(seg, entry, res.exit, rid)
                if k == 0:
                    link(term_a, node(start_at), rid)
                    link(node(start_at), node(entry), rid)
                    link(node(entry), u, rid)
                link(v, node(res.exit), rid)
                link(node(res.exit), term_b, rid)
        if len(segs) == 0:
            continue

    for seg, items in seg_points.items():
        items.sort()
        for (t0, u), (t1, v) in zip(items, items[1:]):
            covering = {rid for lo, hi, rid in seg_cover[seg] if lo - 1e-6 <= t0 and t1 <= hi + 1e-6}
            for rid in covering or {-1}:
                link(u, v, rid)

    for t in [n for n in adj if n.startswith("T:")]:
        coords.setdefault(t, (0.0, 0.0))

    special = {n for n in adj if n.startswith("T:") or len(adj[n]) >= 3}
    tees = {n: coords[n] for n in special if not n.startswith("T:")}
    seen: set[frozenset[str]] = set()
    edges: list[NetEdge] = []
    for s in sorted(special):
        for first in list(adj[s]):
            if frozenset((s, first)) in seen:
                continue
            chain = [s, first]
            bridges: list[Bridge] = []
            cover: set[int] = set(adj[s][first][1])
            if adj[s][first][0] is not None:
                bridges.append(adj[s][first][0])
            seen.add(frozenset((s, first)))
            cur, prev = first, s
            while cur not in special:
                nxt = [n for n in adj[cur] if n != prev]
                if not nxt:
                    break
                n = nxt[0]
                seen.add(frozenset((cur, n)))
                if adj[cur][n][0] is not None:
                    bridges.append(adj[cur][n][0])
                cover |= adj[cur][n][1]
                prev, cur = cur, n
                chain.append(cur)
            if cur not in special:
                continue
            pts = [coords[n] for n in chain if not n.startswith("T:")]
            pts = simplify(pts) if pts else []
            length = sum(dist(p, q) for p, q in zip(pts, pts[1:]))
            edges.append(NetEdge(_name(s), _name(cur), pts, bridges, {r for r in cover if r >= 0}, length))
    return Network([e for e in edges if e.a != e.b or len(e.points) > 1], {_name(k): v for k, v in tees.items()})


def _name(n: str) -> str:
    return n[2:] if n.startswith("T:") else "TEE:" + n
