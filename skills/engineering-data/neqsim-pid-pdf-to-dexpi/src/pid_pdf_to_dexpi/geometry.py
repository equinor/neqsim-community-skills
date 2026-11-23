"""Vector primitives and a connectivity graph of drawn process lines.

The graph joins straight process-weight strokes where an end touches another end or the
interior of another line (tee), and bridges a short collinear gap between two facing line
ends. Gaps are where CAD systems interrupt a line for an inline symbol (valve, flange,
reducer, spectacle blind); every bridge is recorded so the caller can classify the item.
"""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

Point = tuple[float, float]


@dataclass(frozen=True)
class Segment:
    """A straight stroked line from the drawing."""

    x0: float
    y0: float
    x1: float
    y1: float
    width: float = 1.0
    dashed: bool = False

    @property
    def a(self) -> Point:
        return (self.x0, self.y0)

    @property
    def b(self) -> Point:
        return (self.x1, self.y1)

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in drawing coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float

    def inflate(self, d: float) -> "Rect":
        return Rect(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def contains(self, p: Point) -> bool:
        return self.x0 <= p[0] <= self.x1 and self.y0 <= p[1] <= self.y1

    def intersects(self, other: "Rect") -> bool:
        return not (other.x0 > self.x1 or other.x1 < self.x0 or other.y0 > self.y1 or other.y1 < self.y0)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center(self) -> Point:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def as_list(self) -> list[float]:
        return [round(self.x0, 2), round(self.y0, 2), round(self.x1, 2), round(self.y1, 2)]


def bbox_of(points: Iterable[Point]) -> Rect:
    pts = list(points)
    return Rect(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def dist(p: Point, q: Point) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def project(p: Point, s: Segment) -> tuple[float, Point]:
    """Returns the distance from p to segment s and the closest point on s."""
    vx, vy = s.x1 - s.x0, s.y1 - s.y0
    ll = vx * vx + vy * vy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - s.x0) * vx + (p[1] - s.y0) * vy) / ll))
    c = (s.x0 + t * vx, s.y0 + t * vy)
    return dist(p, c), c


@dataclass
class Bridge:
    """A collinear gap between two facing line ends (an inline symbol position)."""

    seg_i: int
    seg_j: int
    p: Point
    q: Point

    @property
    def midpoint(self) -> Point:
        return ((self.p[0] + self.q[0]) / 2.0, (self.p[1] + self.q[1]) / 2.0)

    @property
    def length(self) -> float:
        return dist(self.p, self.q)

    @property
    def horizontal(self) -> bool:
        return abs(self.q[0] - self.p[0]) >= abs(self.q[1] - self.p[1])


@dataclass
class TraceResult:
    """Shortest drawn route from a start terminal to one reached terminal.

    ``steps`` holds (from segment, point on it, point on next segment, bridge, next segment) for each hop,
    so the caller can rebuild the route on the exact strokes used.
    """

    terminal: str
    length: float
    points: list[Point]
    bridges: list[Bridge] = field(default_factory=list)
    segments: list[int] = field(default_factory=list)
    entry: Point = (0.0, 0.0)
    exit: Point = (0.0, 0.0)
    steps: list[tuple[int, Point, Point, Optional[Bridge], int]] = field(default_factory=list)


class LineGraph:
    """Connectivity of process line strokes with tee and gap bridging."""

    def __init__(self, segments: list[Segment], endpoint_tol: float = 1.6, gap_max: float = 30.0,
                 lateral_tol: float = 1.0, cell: float = 25.0):
        self.segments = _dedupe(segments)
        self.tol = endpoint_tol
        self.gap_max = gap_max
        self.lateral_tol = lateral_tol
        self.cell = cell
        # adjacency[i][j] = (point on i, point on j, bridge or None)
        self.adjacency: dict[int, dict[int, tuple[Point, Point, Optional[Bridge]]]] = defaultdict(dict)
        self.bridges: list[Bridge] = []
        self._grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, s in enumerate(self.segments):
            for c in self._cells(s):
                self._grid[c].append(i)
        self._connect_touching()
        self._bridge_gaps()

    def _cells(self, s: Segment) -> Iterable[tuple[int, int]]:
        x0, x1 = sorted((s.x0, s.x1))
        y0, y1 = sorted((s.y0, s.y1))
        for gx in range(int(x0 // self.cell), int(x1 // self.cell) + 1):
            for gy in range(int(y0 // self.cell), int(y1 // self.cell) + 1):
                yield gx, gy

    def _near(self, p: Point, radius: float) -> set[int]:
        out: set[int] = set()
        r = int(math.ceil(radius / self.cell))
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                out.update(self._grid.get((cx + dx, cy + dy), ()))
        return out

    def _link(self, i: int, j: int, p_i: Point, p_j: Point, bridge: Optional[Bridge] = None) -> None:
        if j in self.adjacency[i] and bridge is not None:
            return
        self.adjacency[i][j] = (p_i, p_j, bridge)
        self.adjacency[j][i] = (p_j, p_i, bridge)

    def _connect_touching(self) -> None:
        for i, s in enumerate(self.segments):
            for q in (s.a, s.b):
                for j in self._near(q, self.tol):
                    if j == i:
                        continue
                    d, c = project(q, self.segments[j])
                    if d <= self.tol:
                        self._link(i, j, q, c)

    def _bridge_gaps(self) -> None:
        ends: dict[tuple[int, int], list[tuple[int, Point, Point]]] = defaultdict(list)
        for i, s in enumerate(self.segments):
            if s.length < 1e-6:
                continue
            for q, other in ((s.a, s.b), (s.b, s.a)):
                d = ((q[0] - other[0]) / s.length, (q[1] - other[1]) / s.length)
                ends[(int(q[0] // self.cell), int(q[1] // self.cell))].append((i, q, d))
        for cellkey, items in list(ends.items()):
            for i, q, d in items:
                best: Optional[tuple[float, int, Point]] = None
                r = int(math.ceil(self.gap_max / self.cell))
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        for j, p, e in ends.get((cellkey[0] + dx, cellkey[1] + dy), ()):
                            if j == i or j in self.adjacency[i]:
                                continue
                            vx, vy = p[0] - q[0], p[1] - q[1]
                            along = vx * d[0] + vy * d[1]
                            lateral = abs(vx * d[1] - vy * d[0])
                            facing = e[0] * d[0] + e[1] * d[1] < -0.99
                            if self.tol < along <= self.gap_max and lateral <= self.lateral_tol and facing:
                                if best is None or along < best[0]:
                                    best = (along, j, p)
                if best is not None and best[1] not in self.adjacency[i]:
                    bridge = Bridge(i, best[1], q, best[2])
                    self.bridges.append(bridge)
                    self._link(i, best[1], q, best[2], bridge)

    def trace(self, starts: dict[int, Point], terminal_of: Callable[[int, Point], Optional[tuple[str, Point]]],
              exclude_terminal: str = "", max_length: float = 1.0e9) -> dict[str, TraceResult]:
        """Dijkstra from start segments; stops expanding where a terminal is reached.

        Args:
            starts: start segment index -> entry point on it.
            terminal_of: returns (terminal id, exit point) when a segment end lies in a terminal.
            exclude_terminal: the start terminal, never reported as reached.
            max_length: drawn length limit.

        Returns:
            Shortest route to each reached terminal.
        """
        best: dict[int, float] = {}
        prev: dict[int, tuple[int, Point, Point, Optional[Bridge]]] = {}
        entry: dict[int, Point] = {}
        heap: list[tuple[float, int]] = []
        for i, p in starts.items():
            best[i] = 0.0
            entry[i] = p
            heapq.heappush(heap, (0.0, i))
        reached: dict[str, TraceResult] = {}
        while heap:
            cost, i = heapq.heappop(heap)
            if cost > best.get(i, math.inf) or cost > max_length:
                continue
            seg = self.segments[i]
            stop = False
            for end in (seg.a, seg.b):
                if i in starts and dist(end, entry[i]) <= self.tol:
                    continue
                hit = terminal_of(i, end)
                if not hit:
                    continue
                stop = True
                if hit[0] != exclude_terminal:
                    tid, exit_pt = hit
                    total = cost + dist(entry[i], exit_pt)
                    if tid not in reached or total < reached[tid].length:
                        reached[tid] = self._result(tid, total, i, exit_pt, prev, entry)
            if stop:
                continue
            for j, (p_i, p_j, bridge) in self.adjacency[i].items():
                step = dist(entry[i], p_i) + dist(p_i, p_j)
                nc = cost + step
                if nc < best.get(j, math.inf):
                    best[j] = nc
                    prev[j] = (i, p_i, p_j, bridge)
                    entry[j] = p_j
                    heapq.heappush(heap, (nc, j))
        return reached

    def _result(self, tid: str, total: float, last: int, exit_pt: Point, prev, entry) -> TraceResult:
        pts: list[Point] = [exit_pt]
        bridges: list[Bridge] = []
        segs = [last]
        steps = []
        k = last
        while k in prev:
            i, p_i, p_j, bridge = prev[k]
            pts.append(p_j)
            pts.append(p_i)
            if bridge is not None:
                bridges.append(bridge)
            steps.append((i, p_i, p_j, bridge, k))
            segs.append(i)
            k = i
        pts.append(entry[k])
        pts.reverse()
        segs.reverse()
        bridges.reverse()
        steps.reverse()
        return TraceResult(tid, total, simplify(pts), bridges, segs, entry[k], exit_pt, steps)


def simplify(points: list[Point], tol: float = 0.5) -> list[Point]:
    """Drops duplicate and collinear intermediate points."""
    out: list[Point] = []
    for p in points:
        if out and dist(out[-1], p) < tol:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(cross) < tol * max(1.0, dist(a, c)):
            out.pop(i)
        else:
            i += 1
    return [(round(p[0], 2), round(p[1], 2)) for p in out]


def _dedupe(segments: list[Segment]) -> list[Segment]:
    seen: set[tuple[float, float, float, float]] = set()
    out: list[Segment] = []
    for s in segments:
        a, b = sorted((s.a, s.b))
        key = (round(a[0], 1), round(a[1], 1), round(b[0], 1), round(b[1], 1))
        if key in seen or s.length < 0.2:
            continue
        seen.add(key)
        out.append(s)
    return out
