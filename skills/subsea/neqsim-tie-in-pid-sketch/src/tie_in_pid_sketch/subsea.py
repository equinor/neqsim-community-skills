"""Conceptual subsea P&ID sheets: trees, manifolds, flowlines, risers, topside tie-in, injection and umbilical supply.

The one-line sketch in :mod:`tie_in_pid_sketch.templates` covers an oil export line. A subsea tie-back needs branches
(several trees on one manifold, chemical and hydraulic supply, water injection), so this module draws a full sheet:
the author places symbols on a canvas, connects them with services, and gets an SVG, a layout spec for the
``neqsim pfd-check`` layout checker, and completeness findings. Nothing is sized here and every sheet is a concept
drawing: tags are proposals (``*``), and an item that is still a design decision is drawn dashed.

Example::

    sheet = PidSheet("GRIM-PID-001", "Template, production side", revision="04")
    sheet.add("tree", "XT-P1", x=200, y=300, w=70, h=90, label="Production tree")
    sheet.add("gate_valve", "MV-1", x=330, y=300, status="existing")
    sheet.pipe("XT-P1", "e", "MV-1", "w", service="production", arrow=True)
    svg = sheet.to_svg()
"""

from __future__ import annotations

import json
import math
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape

INK = "#1b2a3a"
NEW = "#1e8449"
DECISION = "#c9730a"
FONT = "Arial, Helvetica, sans-serif"

# service -> (colour, stroke width, dash pattern, legend name)
SERVICES: dict[str, tuple[str, float, str, str]] = {
    "production": ("#7d5a1e", 3.4, "", "Production (multiphase well stream)"),
    "gas": ("#c0392b", 3.0, "", "Gas"),
    "injection": ("#2471a3", 3.4, "", "Injection water"),
    "service": ("#7d3c98", 2.2, "", "Service line (MEG / methanol)"),
    "chemical": ("#1e8449", 1.8, "", "Chemical injection"),
    "hydraulic": ("#707b7c", 1.6, "7 4", "Hydraulic supply"),
    "electrical": ("#222222", 1.4, "2 4 9 4", "Power and signal"),
    "vent": ("#c0392b", 1.8, "8 4", "Vent / depressurisation"),
    "signal": ("#222222", 1.0, "3 3", "Instrument connection"),
}

VALVES = (
    "gate_valve",
    "ball_valve",
    "check_valve",
    "esdv",
    "ssiv",
    "choke",
    "control_valve",
    "hydraulic_valve",
)
ISOLATING = ("gate_valve", "ball_valve", "esdv", "ssiv", "hydraulic_valve", "blind")
BOXES = (
    "tree",
    "box",
    "manifold",
    "plet",
    "vessel",
    "boundary",
    "pump",
    "pig_launcher",
    "pig_receiver",
    "connector",
)
KINDS = VALVES + BOXES + ("instrument", "junction", "blind", "note")

KIND_NAMES = {
    "gate_valve": "Gate valve",
    "ball_valve": "Ball valve",
    "check_valve": "Check valve",
    "esdv": "Spring-return actuated valve (ESDV; fail direction in label)",
    "ssiv": "Subsea isolation valve (SSIV)",
    "choke": "Choke",
    "control_valve": "Control valve",
    "hydraulic_valve": "Chemical injection valve",
    "instrument": "Transmitter (P, T, F, Z)",
    "pig_launcher": "Pig launcher",
    "pig_receiver": "Pig receiver",
    "connector": "Hub and clamp connector",
    "blind": "Spectacle blind",
    "pump": "Pump",
    "tree": "Christmas tree",
    "manifold": "Manifold",
    "plet": "Pipeline end termination",
    "box": "Equipment",
    "vessel": "Vessel / tank",
    "boundary": "System boundary",
}

_VALVE_W, _VALVE_H = 28.0, 22.0
_INSTR_R = 17.0


@dataclass
class Symbol:
    """One placed item.

    Attributes:
        kind: one of :data:`KINDS`.
        tag: tag shown with a trailing ``*`` when ``proposed``.
        x: centre x on the canvas.
        y: centre y on the canvas.
        w: width (boxes only).
        h: height (boxes only).
        label: short description below (or inside, for boxes) the symbol; ``\\n`` separates lines.
        status: ``existing`` (thin dark), ``new`` (bold green) or ``decision`` (dashed orange: option or open decision).
        proposed: tag is invented for the sketch.
        rot: 0 or 90 degrees (valves, instruments are not rotated).
        fill: box fill colour.
        label_pos: ``below`` (default), ``above``, ``left`` or ``right`` for the label of small symbols.
    """

    kind: str
    tag: str
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0
    label: str = ""
    status: str = "new"
    proposed: bool = True
    rot: int = 0
    fill: str = "#ffffff"
    label_pos: str = "below"

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(
                "unknown symbol kind {!r}; use one of {}".format(
                    self.kind, ", ".join(KINDS)
                )
            )
        if self.status not in ("existing", "new", "decision"):
            raise ValueError("status must be existing, new or decision")
        if self.rot not in (0, 90):
            raise ValueError("rot must be 0 or 90")
        if self.kind in VALVES:
            self.w, self.h = (
                (_VALVE_W, _VALVE_H) if self.rot == 0 else (_VALVE_H, _VALVE_W)
            )
        elif self.kind == "instrument":
            self.w = self.h = 2 * _INSTR_R
        elif self.kind == "junction":
            self.w = self.h = 8.0
        elif self.kind == "blind":
            self.w, self.h = (30.0, 14.0) if self.rot == 0 else (14.0, 30.0)
        elif self.kind == "connector":
            self.w, self.h = (26.0, 18.0) if self.rot == 0 else (18.0, 26.0)
        elif self.kind in ("pig_launcher", "pig_receiver"):
            self.w = self.w or 96.0
            self.h = self.h or 26.0
        elif self.kind == "pump":
            self.w = self.h = self.w or 46.0
        elif self.w <= 0 or self.h <= 0:
            raise ValueError(f"{self.kind} needs a width and a height")

    @property
    def shown_tag(self) -> str:
        """Tag as drawn: invented tags carry a trailing asterisk."""
        return self.tag + (
            "*" if self.proposed and self.tag and not self.tag.endswith("*") else ""
        )

    def bbox(self) -> tuple[float, float, float, float]:
        """Return (x0, y0, x1, y1) of the symbol body, including a valve actuator."""
        x0, y0, x1, y1 = (
            self.x - self.w / 2,
            self.y - self.h / 2,
            self.x + self.w / 2,
            self.y + self.h / 2,
        )
        if self.kind in ("esdv", "ssiv", "control_valve", "hydraulic_valve"):
            if self.rot == 0:
                y0 -= 28.0
            else:
                x1 += 28.0
        return x0, y0, x1, y1

    def port(self, side: str, off: float = 0.0) -> tuple[float, float]:
        """Connection point on side ``n``, ``s``, ``e`` or ``w``; ``off`` slides along a box edge."""
        if self.kind in VALVES or self.kind in ("blind", "connector"):
            hw, hh = (self.w / 2, self.h / 2)
            if self.rot == 0:
                pts = {
                    "w": (self.x - hw, self.y),
                    "e": (self.x + hw, self.y),
                    "n": (self.x, self.y - hh),
                    "s": (self.x, self.y + hh),
                }
            else:
                pts = {
                    "n": (self.x, self.y - hh),
                    "s": (self.x, self.y + hh),
                    "w": (self.x - hw, self.y),
                    "e": (self.x + hw, self.y),
                }
            return pts[side]
        if self.kind == "junction":
            return (self.x, self.y)
        hw, hh = self.w / 2, self.h / 2
        if side in ("e", "w"):
            off = max(-hh + 4, min(hh - 4, off))
            return (self.x + (hw if side == "e" else -hw), self.y + off)
        off = max(-hw + 4, min(hw - 4, off))
        return (self.x + off, self.y + (hh if side == "s" else -hh))


@dataclass
class Pipe:
    """A line between two ports, drawn orthogonally."""

    a: str
    pa: str
    b: str
    pb: str
    service: str
    points: list[tuple[float, float]]
    label: str = ""
    arrow: bool = False
    flex: bool = False
    status: str = "new"
    dashed: bool = False
    label_dy: float = -9.0
    label_dx: float = 0.0
    line_id: str = ""

    def length(self) -> float:
        """Polyline length in canvas units."""
        return sum(
            math.hypot(q[0] - p[0], q[1] - p[1])
            for p, q in zip(self.points, self.points[1:])
        )


class PidSheet:
    """A conceptual P&ID sheet. Build with :meth:`add` and :meth:`pipe`, then :meth:`to_svg` and :meth:`layout_spec`."""

    def __init__(
        self,
        drawing_no: str,
        title: str,
        revision: str = "A",
        subtitle: str = "",
        width: float = 1600.0,
        height: float = 1130.0,
        status_note: str = "CONCEPTUAL - NOT FOR CONSTRUCTION - screening grade, not reviewed",
        date: str = "",
        prepared_by: str = "NeqSim agent-assisted study",
        role: str = "",
    ) -> None:
        self.drawing_no, self.title, self.revision, self.subtitle = (
            drawing_no,
            title,
            revision,
            subtitle,
        )
        self.width, self.height = float(width), float(height)
        self.status_note, self.date, self.prepared_by, self.role = (
            status_note,
            date,
            prepared_by,
            role,
        )
        self.symbols: dict[str, Symbol] = {}
        self.pipes: list[Pipe] = []
        self.zones: list[tuple[float, float, float, float, str, str]] = []
        self.texts: list[tuple[float, float, str, float, str, str]] = []
        self.notes: list[str] = []
        self.waivers: list[dict[str, str]] = []
        self.decor: list[str] = []
        self.basis: list[str] = []
        self._line_no = 0

    # ------------------------------------------------------------------ building
    def add(self, kind: str, tag: str, x: float, y: float, **kw) -> Symbol:
        """Place a symbol and return it. Raises ``ValueError`` on a duplicate tag."""
        if tag in self.symbols:
            raise ValueError(f"duplicate tag {tag!r} on sheet {self.drawing_no}")
        kw.setdefault("proposed", True)
        sym = Symbol(kind, tag, float(x), float(y), **kw)
        self.symbols[tag] = sym
        return sym

    def zone(
        self, x: float, y: float, w: float, h: float, label: str, where: str = "top"
    ) -> None:
        """A dashed grouping frame (for example the template or the platform) drawn behind everything; ``where`` is ``top`` or ``bottom``."""
        self.zones.append((x, y, w, h, label, where))

    def text(
        self,
        x: float,
        y: float,
        text: str,
        size: float = 12.0,
        anchor: str = "start",
        weight: str = "normal",
        fill: str = INK,
    ) -> None:
        """Free text on the sheet (not a node)."""
        self.texts.append((x, y, text, size, anchor, weight + "|" + fill))

    def note(self, text: str) -> None:
        """Add a numbered note to the notes block."""
        self.notes.append(text)

    def waive(self, code: str, reason: str) -> None:
        """Waive a layout-checker finding code with a reason (shown as INFO, recorded in the layout spec)."""
        self.waivers.append({"code": code, "reason": reason})

    def add_table(
        self,
        x: float,
        y: float,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        col_w: Sequence[float],
        row_h: float = 19.0,
        title: str = "",
    ) -> tuple[float, float]:
        """Draw a small data table (decoration, not a node) and return its (width, height)."""
        w = float(sum(col_w))
        top = y + (22.0 if title else 0.0)
        out: list[str] = []
        if title:
            out.append(self._t(x, y + 14, title, 12, bold=True, fill="#44546a"))
        out.append(
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{w:.1f}" height="{row_h:.1f}" fill="#e8eef6" stroke="#8a97a6" stroke-width="1"/>'
        )
        cx = x
        for h, cw in zip(headers, col_w):
            out.append(self._t(cx + 5, top + row_h - 6, h, 10, bold=True))
            cx += cw
        for i, row in enumerate(rows):
            ry = top + row_h * (i + 1)
            out.append(
                '<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" fill="{}" stroke="#c5ccd6" stroke-width="0.8"/>'.format(
                    x, ry, w, row_h, "#ffffff" if i % 2 == 0 else "#f6f8fb"
                )
            )
            cx = x
            for cell, cw in zip(row, col_w):
                out.append(self._t(cx + 5, ry + row_h - 6, str(cell), 10))
                cx += cw
        self.decor.extend(out)
        return w, (top - y) + row_h * (len(rows) + 1)

    def add_profile(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        xs: Sequence[float],
        ys: Sequence[float],
        title: str,
        xlabel: str,
        ylabel: str,
        markers: Sequence[tuple[float, str, str]] = (),
        invert_y: bool = True,
        y_pad: float = 3.0,
    ) -> None:
        """Draw a line profile (for example seabed depth against KP) with axes and labelled vertical markers (decoration)."""
        x0, x1 = min(xs), max(xs)
        lo, hi = min(ys) - y_pad, max(ys) + y_pad
        px, py = 52.0, 26.0
        pw, ph = w - px - 12.0, h - py - 34.0

        def sx(v: float) -> float:
            return x + px + (v - x0) / ((x1 - x0) or 1.0) * pw

        def sy(v: float) -> float:
            f = (v - lo) / ((hi - lo) or 1.0)
            return y + py + (f if invert_y else 1.0 - f) * ph

        out = [self._t(x, y + 14, title, 12, bold=True, fill="#44546a")]
        out.append(
            f'<rect x="{x + px:.1f}" y="{y + py:.1f}" width="{pw:.1f}" height="{ph:.1f}" fill="#ffffff" stroke="#8a97a6" stroke-width="1"/>'
        )
        for k in range(5):
            gv = lo + (hi - lo) * k / 4.0
            gy = sy(gv)
            out.append(
                f'<line x1="{x + px:.1f}" y1="{gy:.1f}" x2="{x + px + pw:.1f}" y2="{gy:.1f}" stroke="#dde3ea" stroke-width="0.8"/>'
            )
            out.append(self._t(x + px - 5, gy + 3.5, f"{gv:.0f}", 9.5, "end"))
        for k in range(0, int(x1) + 1, 3):
            out.append(
                self._t(sx(k), y + py + ph + 14, "%d" % k, 9.5, "middle")  # noqa: UP031
            )
        out.append(self._t(x + px + pw / 2, y + h - 4, xlabel, 10, "middle"))
        out.append(
            f'<text x="{x + 12:.1f}" y="{y + py + ph / 2:.1f}" font-family="{FONT}" font-size="10" text-anchor="middle" fill="{INK}" transform="rotate(-90 {x + 12:.1f} {y + py + ph / 2:.1f})">{escape(ylabel)}</text>'
        )
        pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(xs, ys))
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="#7d5a1e" stroke-width="2"/>'
        )
        for mx, text, col in markers:
            out.append(
                f'<line x1="{sx(mx):.1f}" y1="{y + py:.1f}" x2="{sx(mx):.1f}" y2="{y + py + ph:.1f}" stroke="{col}" stroke-width="1.4" stroke-dasharray="5 3"/>'
            )
            out.append(self._t(sx(mx) - 4, y + py + 12, text, 9.5, "end", fill=col))
        self.decor.extend(out)

    def _pt(
        self, ref: str | tuple[float, float], side: str, off: float
    ) -> tuple[float, float]:
        if isinstance(ref, tuple):
            return (float(ref[0]), float(ref[1]))
        if ref not in self.symbols:
            raise KeyError(f"unknown tag {ref!r} on sheet {self.drawing_no}")
        return self.symbols[ref].port(side, off)

    def pipe(
        self,
        a: str | tuple[float, float],
        pa: str,
        b: str | tuple[float, float],
        pb: str,
        service: str = "production",
        via: Sequence[tuple[float, float]] | None = None,
        mid: float | None = None,
        offa: float = 0.0,
        offb: float = 0.0,
        label: str = "",
        arrow: bool | None = None,
        flex: bool = False,
        dashed: bool = False,
        status: str = "new",
        label_dy: float = -9.0,
        label_dx: float = 0.0,
    ) -> Pipe:
        """Connect two ports with an orthogonal line drawn in the flow direction (``a`` to ``b``).

        ``via`` gives intermediate points; ``mid`` the x (or y) of the jog. Process lines get a flow arrowhead at ``b`` unless
        ``arrow=False``; instrument connections never do.
        """
        if service not in SERVICES:
            raise ValueError(
                "unknown service {!r}; use one of {}".format(
                    service, ", ".join(SERVICES)
                )
            )
        if arrow is None:
            arrow = service != "signal"
        p0 = self._pt(a, pa, offa)
        p1 = self._pt(b, pb, offb)
        pts: list[tuple[float, float]] = [p0]
        if via:
            pts += [(float(v[0]), float(v[1])) for v in via]
        else:
            vertical_first = pa in ("n", "s")
            if abs(p0[0] - p1[0]) > 0.5 and abs(p0[1] - p1[1]) > 0.5:
                if vertical_first:
                    my = p0[1] + (p1[1] - p0[1]) / 2.0 if mid is None else mid
                    pts += [(p0[0], my), (p1[0], my)]
                else:
                    mx = p0[0] + (p1[0] - p0[0]) / 2.0 if mid is None else mid
                    pts += [(mx, p0[1]), (mx, p1[1])]
        pts.append(p1)
        self._line_no += 1
        pipe = Pipe(
            a if isinstance(a, str) else "pt%d_a" % self._line_no,  # noqa: UP031
            pa,
            b if isinstance(b, str) else "pt%d_b" % self._line_no,  # noqa: UP031
            pb,
            service,
            pts,
            label,
            arrow,
            flex,
            status,
            dashed,
            label_dy,
            label_dx,
            "L%02d" % self._line_no,  # noqa: UP031
        )
        self.pipes.append(pipe)
        return pipe

    def chain(
        self, tags: Sequence[str], service: str = "production", label: str = "", **kw
    ) -> list[Pipe]:
        """Connect consecutive tags with the facing ports (east-west or north-south, from their positions), in flow order."""
        out: list[Pipe] = []
        for i in range(len(tags) - 1):
            s0, s1 = self.symbols[tags[i]], self.symbols[tags[i + 1]]
            dx, dy = s1.x - s0.x, s1.y - s0.y
            if abs(dx) >= abs(dy):
                pa, pb = ("e", "w") if dx >= 0 else ("w", "e")
            else:
                pa, pb = ("s", "n") if dy >= 0 else ("n", "s")
            out.append(
                self.pipe(
                    tags[i],
                    pa,
                    tags[i + 1],
                    pb,
                    service,
                    label=label if i == 0 else "",
                    **kw,
                )
            )
        return out

    def tap(
        self,
        instrument: str,
        target: str,
        side: str = "n",
        target_side: str = "s",
        via: Sequence[tuple[float, float]] | None = None,
    ) -> Pipe:
        """Instrument connection (thin dashed) from a transmitter to a symbol or a junction."""
        return self.pipe(
            instrument, side, target, target_side, service="signal", via=via
        )

    # ------------------------------------------------------------------ analysis
    def graph(self) -> dict[str, list[str]]:
        """Adjacency of tags through pipes (signal lines excluded)."""
        g: dict[str, list[str]] = {t: [] for t in self.symbols}
        for p in self.pipes:
            if p.service == "signal" or p.a not in g or p.b not in g:
                continue
            g[p.a].append(p.b)
            g[p.b].append(p.a)
        return g

    def isolation_count(self, a: str, b: str, kinds: Iterable[str] = ISOLATING) -> int:
        """Number of isolating valves on the shortest path between two tags (``-1`` when they are not connected)."""
        g = self.graph()
        if a not in g or b not in g:
            raise KeyError("unknown tag")
        prev: dict[str, str | None] = {a: None}
        queue = deque([a])
        while queue:
            cur = queue.popleft()
            if cur == b:
                break
            for nxt in g[cur]:
                if nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        if b not in prev:
            return -1
        kinds = tuple(kinds)
        count, node = 0, prev[b]
        while node is not None and node != a:
            if self.symbols[node].kind in kinds:
                count += 1
            node = prev[node]
        return count

    def validate(
        self,
        required_kinds: Iterable[str] = (),
        min_isolation: dict[tuple[str, str], int] | None = None,
    ) -> list[str]:
        """Completeness findings; an empty list means the sheet is internally consistent.

        Checks: every symbol with a flow axis is on a line, tags are unique (enforced by :meth:`add`), every required kind is
        present, and every ``(a, b)`` in ``min_isolation`` has at least that many isolating valves in series.
        """
        findings: list[str] = []
        g = self.graph()
        signalled = {p.a for p in self.pipes if p.service == "signal"} | {
            p.b for p in self.pipes if p.service == "signal"
        }
        for tag, sym in self.symbols.items():
            if sym.kind in ("note", "boundary"):
                continue
            if (
                not g[tag]
                and tag not in signalled
                and not any(p.a == tag or p.b == tag for p in self.pipes)
            ):
                findings.append(f"{tag} ({sym.kind}) is not connected to any line")
        present = {s.kind for s in self.symbols.values()}
        for kind in required_kinds:
            if kind not in present:
                findings.append(f"no {KIND_NAMES.get(kind, kind)} on the sheet")
        for (a, b), need in (min_isolation or {}).items():
            have = self.isolation_count(a, b)
            if have < need:
                findings.append(
                    "%s to %s has %d isolating valve(s) in series, %d required"  # noqa: UP031
                    % (a, b, max(have, 0), need)
                )
        return findings

    # ------------------------------------------------------------------ drawing
    @staticmethod
    def _style(status: str) -> tuple[str, float, str]:
        if status == "existing":
            return INK, 1.7, ""
        if status == "decision":
            return DECISION, 2.4, "7 4"
        return NEW, 2.8, ""

    def _draw_symbol(self, s: Symbol) -> list[str]:
        col, sw, dash = self._style(s.status)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        base = f'stroke="{col}" stroke-width="{sw:.1f}" fill="#ffffff"{da}'
        out: list[str] = []
        x, y = s.x, s.y
        k = s.kind
        if k in VALVES:
            tf = f' transform="rotate(90 {x:.1f} {y:.1f})"' if s.rot == 90 else ""
            out.append(f"<g{tf}>")
            out.append(
                f'<polygon points="{x - 14:.1f},{y - 11:.1f} {x + 14:.1f},{y + 11:.1f} {x + 14:.1f},{y - 11:.1f} {x - 14:.1f},{y + 11:.1f}" {base}/>'
            )
            if k == "ball_valve":
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{col}"/>')
            elif k == "check_valve":
                out.append(
                    f'<polygon points="{x - 6:.1f},{y - 6:.1f} {x + 7:.1f},{y:.1f} {x - 6:.1f},{y + 6:.1f}" fill="{col}"/>'
                )
            elif k == "choke":
                out.append(
                    f'<line x1="{x - 12:.1f}" y1="{y + 16:.1f}" x2="{x + 12:.1f}" y2="{y - 16:.1f}" stroke="{col}" stroke-width="{sw:.1f}"/>'
                )
                out.append(
                    f'<polygon points="{x + 12:.1f},{y - 16:.1f} {x + 5:.1f},{y - 14:.1f} {x + 10:.1f},{y - 9:.1f}" fill="{col}"/>'
                )
            elif k in ("esdv", "ssiv", "control_valve", "hydraulic_valve"):
                out.append(
                    f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y - 14:.1f}" stroke="{col}" stroke-width="{sw:.1f}"/>'
                )
                if k == "control_valve":
                    out.append(
                        f'<path d="M{x - 12:.1f},{y - 14:.1f} A12,12 0 0 1 {x + 12:.1f},{y - 14:.1f} Z" {base}/>'
                    )
                else:
                    out.append(
                        f'<rect x="{x - 11:.1f}" y="{y - 28:.1f}" width="22" height="14" {base}/>'
                    )
                    letter = {"esdv": "S", "ssiv": "S", "hydraulic_valve": "H"}[k]
                    out.append(
                        f'<text x="{x:.1f}" y="{y - 17.5:.1f}" font-family="{FONT}" font-size="11" font-weight="bold" text-anchor="middle" fill="{col}">{letter}</text>'
                    )
            out.append("</g>")
        elif k == "instrument":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{_INSTR_R:.1f}" {base}/>')
            out.append(
                f'<line x1="{x - _INSTR_R:.1f}" y1="{y:.1f}" x2="{x + _INSTR_R:.1f}" y2="{y:.1f}" stroke="{col}" stroke-width="1"/>'
            )
            letters, _, number = s.shown_tag.partition("-")
            out.append(
                f'<text x="{x:.1f}" y="{y - 3.5:.1f}" font-family="{FONT}" font-size="10.5" font-weight="bold" text-anchor="middle" fill="{INK}">{escape(letters)}</text>'
            )
            out.append(
                f'<text x="{x:.1f}" y="{y + 11:.1f}" font-family="{FONT}" font-size="9" text-anchor="middle" fill="{INK}">{escape(number)}</text>'
            )
        elif k == "junction":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{INK}"/>')
        elif k == "blind":
            if s.rot == 0:
                out.append(
                    f'<circle cx="{x - 8:.1f}" cy="{y:.1f}" r="7" {base}/><circle cx="{x + 8:.1f}" cy="{y:.1f}" r="7" fill="{col}" stroke="{col}" stroke-width="{sw:.1f}"/>'
                )
            else:
                out.append(
                    f'<circle cx="{x:.1f}" cy="{y - 8:.1f}" r="7" {base}/><circle cx="{x:.1f}" cy="{y + 8:.1f}" r="7" fill="{col}" stroke="{col}" stroke-width="{sw:.1f}"/>'
                )
        elif k == "connector":
            if s.rot == 0:
                out.append(
                    f'<polygon points="{x - 13:.1f},{y - 8:.1f} {x - 2:.1f},{y - 5:.1f} {x - 2:.1f},{y + 5:.1f} {x - 13:.1f},{y + 8:.1f}" {base}/><polygon points="{x + 13:.1f},{y - 8:.1f} {x + 2:.1f},{y - 5:.1f} {x + 2:.1f},{y + 5:.1f} {x + 13:.1f},{y + 8:.1f}" {base}/>'
                )
            else:
                out.append(
                    f'<polygon points="{x - 8:.1f},{y - 13:.1f} {x - 5:.1f},{y - 2:.1f} {x + 5:.1f},{y - 2:.1f} {x + 8:.1f},{y - 13:.1f}" {base}/><polygon points="{x - 8:.1f},{y + 13:.1f} {x - 5:.1f},{y + 2:.1f} {x + 5:.1f},{y + 2:.1f} {x + 8:.1f},{y + 13:.1f}" {base}/>'
                )
        elif k == "pump":
            r = s.w / 2
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" {base}/>')
            out.append(
                f'<path d="M{x - r * 0.62:.1f},{y + r * 0.62:.1f} L{x + r:.1f},{y:.1f} L{x - r * 0.62:.1f},{y - r * 0.62:.1f}" fill="none" stroke="{col}" stroke-width="{sw:.1f}"/>'
            )
        elif k in ("pig_launcher", "pig_receiver"):
            x0, y0 = x - s.w / 2, y - s.h / 2
            out.append(
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{s.w:.1f}" height="{s.h:.1f}" rx="6" {base}/>'
            )
            door = x0 if k == "pig_launcher" else x0 + s.w
            out.append(
                f'<line x1="{door:.1f}" y1="{y0 - 4:.1f}" x2="{door:.1f}" y2="{y0 + s.h + 4:.1f}" stroke="{col}" stroke-width="{sw + 1:.1f}"/>'
            )
            out.append(
                f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0 - 12:.1f}" stroke="{col}" stroke-width="{sw:.1f}"/>'
            )
        elif k == "boundary":
            x0, y0 = x - s.w / 2, y - s.h / 2
            out.append(
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{s.w:.1f}" height="{s.h:.1f}" rx="4" fill="#f7f7f7" stroke="#555555" stroke-width="1.4" stroke-dasharray="8 4"/>'
            )
        else:  # tree, box, manifold, plet, vessel
            x0, y0 = x - s.w / 2, y - s.h / 2
            rx = 14 if k == "vessel" else 3
            out.append(
                '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" %s/>'  # noqa: UP031
                % (
                    x0,
                    y0,
                    s.w,
                    s.h,
                    rx,
                    base.replace('fill="#ffffff"', f'fill="{s.fill}"'),
                )
            )
            if k == "tree":
                out.append(
                    f'<line x1="{x0:.1f}" y1="{y0 + 20:.1f}" x2="{x0 + s.w:.1f}" y2="{y0 + 20:.1f}" stroke="{col}" stroke-width="1"/>'
                )
            if k == "manifold":
                for off in (-0.3, 0.3):
                    out.append(
                        f'<line x1="{x0 - 0.0:.1f}" y1="{y + off * s.h:.1f}" x2="{x0 + 8:.1f}" y2="{y + off * s.h:.1f}" stroke="{col}" stroke-width="1"/>'
                    )
                    out.append(
                        f'<line x1="{x0 + s.w - 8:.1f}" y1="{y + off * s.h:.1f}" x2="{x0 + s.w:.1f}" y2="{y + off * s.h:.1f}" stroke="{col}" stroke-width="1"/>'
                    )
            if k == "plet":
                out.append(
                    f'<rect x="{x0 - 8:.1f}" y="{y - 7:.1f}" width="8" height="14" fill="{col}"/>'
                )
        return out

    def _label_lines(self, s: Symbol) -> list[str]:
        out: list[str] = []
        tag = "" if s.kind == "boundary" else s.shown_tag
        lines = [ln for ln in s.label.split("\n") if ln]
        k = s.kind
        if k == "instrument":
            for i, ln in enumerate(lines):
                out.append(
                    self._t(
                        s.x + _INSTR_R + 6,
                        s.y + 4 + 11 * i - 5.5 * (len(lines) - 1),
                        ln,
                        9.5,
                        "start",
                    )
                )
            return out
        if k == "junction":
            return out
        if k in BOXES and k not in (
            "pump",
            "pig_launcher",
            "pig_receiver",
            "connector",
        ):
            x0, y0 = s.x - s.w / 2, s.y - s.h / 2
            y0 + 15 if k == "tree" else s.y - 7 * (len(lines)) - (7 if tag else 0)
            if k == "tree":
                if tag:
                    out.append(self._t(s.x, y0 + 14, tag, 11.5, "middle", bold=True))
                for i, ln in enumerate(lines):
                    out.append(self._t(s.x, y0 + 36 + 12.5 * i, ln, 10.5, "middle"))
            else:
                yy = s.y - (len(lines) * 6.5 + (7 if tag else 0)) + 4
                if tag:
                    out.append(self._t(s.x, yy, tag, 11.5, "middle", bold=True))
                    yy += 15
                for i, ln in enumerate(lines):
                    out.append(self._t(s.x, yy + 12.5 * i, ln, 10.5, "middle"))
            return out
        x0, y0, x1, y1 = s.bbox()
        if s.label_pos == "above":
            _ty, _ly = y0 - 6, y0 - 6 - 12.5 * len(lines) if tag else y0 - 6
            if tag:
                out.append(
                    self._t(
                        s.x, y0 - 6 - 12.5 * len(lines), tag, 11, "middle", bold=True
                    )
                )
            for i, ln in enumerate(lines):
                out.append(
                    self._t(s.x, y0 - 6 - 12.5 * (len(lines) - 1 - i), ln, 10, "middle")
                )
            return out
        anchor = "middle"
        tx = s.x
        if s.label_pos in ("left", "right"):
            anchor = "end" if s.label_pos == "left" else "start"
            tx = x0 - 7 if s.label_pos == "left" else x1 + 7
            yy = s.y - 6 * len(lines)
            if tag:
                out.append(self._t(tx, yy, tag, 11, anchor, bold=True))
                yy += 13
            for i, ln in enumerate(lines):
                out.append(self._t(tx, yy + 12 * i + 4, ln, 10, anchor))
            return out
        yy = y1 + 15
        if tag:
            out.append(self._t(tx, yy, tag, 11, anchor, bold=True))
            yy += 13
        for i, ln in enumerate(lines):
            out.append(self._t(tx, yy + 12 * i, ln, 10, anchor))
        return out

    @staticmethod
    def _t(
        x: float,
        y: float,
        text: str,
        size: float = 11.0,
        anchor: str = "start",
        bold: bool = False,
        fill: str = INK,
    ) -> str:
        return '<text x="{:.1f}" y="{:.1f}" font-family="{}" font-size="{:.1f}" text-anchor="{}" font-weight="{}" fill="{}">{}</text>'.format(
            x, y, FONT, size, anchor, "bold" if bold else "normal", fill, escape(text)
        )

    def _draw_pipe(self, p: Pipe) -> list[str]:
        col, sw, dash, _ = SERVICES[p.service]
        da = (
            f' stroke-dasharray="{dash}"'
            if dash
            else (' stroke-dasharray="9 5"' if p.dashed else "")
        )
        if p.status == "decision" and not dash:
            da = ' stroke-dasharray="9 5"'
            col = DECISION
        out: list[str] = []
        if p.flex and len(p.points) == 2:
            (x0, y0), (x1, y1) = p.points
            n = 14
            seg = []
            for i in range(n + 1):
                t = i / n
                px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                amp = 7.0 * math.sin(t * math.pi * 3)
                if abs(x1 - x0) >= abs(y1 - y0):
                    py += amp
                else:
                    px += amp
                seg.append(f"{px:.1f},{py:.1f}")
            out.append(
                '<polyline points="{}" fill="none" stroke="{}" stroke-width="{:.1f}"{} stroke-linejoin="round"/>'.format(
                    " ".join(seg), col, sw, da
                )
            )
        else:
            pts = " ".join("{:.1f},{:.1f}".format(*q) for q in p.points)
            out.append(
                f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="{sw:.1f}"{da} stroke-linejoin="round" stroke-linecap="butt"/>'
            )
        if p.arrow and p.service != "signal":
            out.append(self._arrowhead(p, col))
        if p.label:
            (lx, ly), horiz = self._label_anchor(p)
            if horiz:
                out.append(
                    self._t(
                        lx + p.label_dx,
                        ly + p.label_dy,
                        p.label,
                        10.5,
                        "middle",
                        fill=col if col != "#222222" else INK,
                    )
                )
            else:
                out.append(
                    self._t(
                        lx + 8 + p.label_dx, ly + 4, p.label, 10.5, "start", fill=col
                    )
                )
        return out

    @staticmethod
    def _longest(p: Pipe) -> tuple[tuple[float, float], tuple[float, float]]:
        best, bl = (p.points[0], p.points[-1]), -1.0
        for q0, q1 in zip(p.points, p.points[1:]):
            ln = math.hypot(q1[0] - q0[0], q1[1] - q0[1])
            if ln > bl:
                best, bl = (q0, q1), ln
        return best

    def _label_anchor(self, p: Pipe) -> tuple[tuple[float, float], bool]:
        q0, q1 = self._longest(p)
        horiz = abs(q1[0] - q0[0]) >= abs(q1[1] - q0[1])
        return (((q0[0] + q1[0]) / 2, (q0[1] + q1[1]) / 2), horiz)

    def _arrowhead(self, p: Pipe, col: str) -> str:
        q0, q1 = p.points[-2], p.points[-1]
        dx, dy = q1[0] - q0[0], q1[1] - q0[1]
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        back = 0.0
        tipx, tipy = q1[0] - ux * back, q1[1] - uy * back
        bx, by = tipx - ux * 10, tipy - uy * 10
        nx, ny = -uy * 5.5, ux * 5.5
        return f'<polygon points="{tipx:.1f},{tipy:.1f} {bx + nx:.1f},{by + ny:.1f} {bx - nx:.1f},{by - ny:.1f}" fill="{col}"/>'

    def _legend_size(self) -> tuple[float, float]:
        used_services = {p.service for p in self.pipes}
        used_kinds = [
            k for k in KIND_NAMES if any(s.kind == k for s in self.symbols.values())
        ]
        rows1 = len(used_services) + 3
        rows2 = (len(used_kinds) + 2) // 3
        return 980.0, 30 + max(rows1 * 21, rows2 * 46 + 14) + 10

    def _legend(
        self, x0: float | None = None, y0: float | None = None
    ) -> tuple[list[str], tuple[float, float, float, float]]:
        w, h = self._legend_size()
        x0 = 24.0 if x0 is None else x0
        y0 = self.height - 24.0 - h if y0 is None else y0
        used_services = sorted(
            {p.service for p in self.pipes}, key=lambda s: list(SERVICES).index(s)
        )
        used_kinds = [
            k for k in KIND_NAMES if any(s.kind == k for s in self.symbols.values())
        ]
        out = [
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#ffffff" stroke="#555555" stroke-width="1"/>'
        ]
        out.append(self._t(x0 + 10, y0 + 20, "Legend", 12, bold=True))
        yy = y0 + 42
        for sv in used_services:
            col, sw, dash, name = SERVICES[sv]
            da = f' stroke-dasharray="{dash}"' if dash else ""
            out.append(
                f'<line x1="{x0 + 12:.1f}" y1="{yy - 4:.1f}" x2="{x0 + 62:.1f}" y2="{yy - 4:.1f}" stroke="{col}" stroke-width="{sw:.1f}"{da}/>'
            )
            out.append(self._t(x0 + 72, yy, name, 10.5))
            yy += 21
        for status, name in (
            ("existing", "Existing (thin, dark)"),
            ("new", "New scope (bold, green)"),
            ("decision", "Option or open decision (dashed)"),
        ):
            col, sw, dash = self._style(status)
            da = f' stroke-dasharray="{dash}"' if dash else ""
            out.append(
                f'<rect x="{x0 + 12:.1f}" y="{yy - 12:.1f}" width="50" height="11" fill="#ffffff" stroke="{col}" stroke-width="{sw:.1f}"{da}/>'
            )
            out.append(self._t(x0 + 72, yy - 2, name, 10.5))
            yy += 21
        half = (len(used_kinds) + 2) // 3
        for idx, k in enumerate(used_kinds):
            col, row = divmod(idx, half)
            cx = x0 + 300 + col * 225
            yy = y0 + 70 + row * 46
            demo = Symbol(
                k,
                "PT-" if k == "instrument" else "",
                cx + 30,
                yy - 5,
                w=44,
                h=16,
                status="new",
                proposed=False,
            )
            if k in BOXES and k not in (
                "pump",
                "pig_launcher",
                "pig_receiver",
                "connector",
            ):
                demo.w, demo.h = 40.0, 14.0
            out += self._draw_symbol(demo)
            out.append(self._t(cx + 62, yy - 1, KIND_NAMES[k], 10))
        return out, (x0, y0, w, h)

    def _title_block(self) -> tuple[list[str], tuple[float, float, float, float]]:
        w, h = 470.0, 112.0
        x0, y0 = self.width - w - 20, self.height - h - 20
        out = [
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#ffffff" stroke="#1b2a3a" stroke-width="2"/>'
        ]
        out.append(self._t(x0 + 10, y0 + 22, self.title, 14, bold=True))
        if self.subtitle:
            out.append(self._t(x0 + 10, y0 + 40, self.subtitle, 10.5))
        out.append(
            f'<line x1="{x0:.1f}" y1="{y0 + 50:.1f}" x2="{x0 + w:.1f}" y2="{y0 + 50:.1f}" stroke="#1b2a3a" stroke-width="1"/>'
        )
        out.append(
            self._t(
                x0 + 10,
                y0 + 68,
                f"Drawing {self.drawing_no}    Revision {self.revision}    {self.date}",
                11,
                bold=True,
            )
        )
        out.append(
            self._t(x0 + 10, y0 + 85, self.status_note, 9.5, fill="#c0392b", bold=True)
        )
        out.append(
            self._t(
                x0 + 10,
                y0 + 102,
                f"Prepared by: {self.prepared_by}. A qualified engineer must review.",
                9.5,
            )
        )
        return out, (x0, y0, w, h)

    def _notes_lines(self, w: float) -> list[str]:
        lines: list[str] = []
        for i, n in enumerate(self.notes, 1):
            cur, first = "", True
            for wd in n.split():
                if len(cur) + len(wd) + 1 > int(w / 5.3):
                    lines.append(
                        (("%d. " % i) if first else "    ") + cur  # noqa: UP031
                    )
                    cur, first = wd, False
                else:
                    cur = (cur + " " + wd).strip()
            lines.append((("%d. " % i) if first else "    ") + cur)  # noqa: UP031
        return lines

    def _notes_block(
        self, x0: float, y0: float, w: float
    ) -> tuple[list[str], tuple[float, float, float, float]]:
        lines = self._notes_lines(w)
        h = 30 + 13 * len(lines) + 8
        out = [
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#ffffff" stroke="#555555" stroke-width="1"/>'
        ]
        out.append(self._t(x0 + 10, y0 + 20, "Notes", 12, bold=True))
        for i, ln in enumerate(lines):
            out.append(self._t(x0 + 10, y0 + 38 + 13 * i, ln, 9.5))
        return out, (x0, y0, w, h)

    def _notes_box(self) -> tuple[float, float, float, float] | None:
        if not self.notes:
            return None
        _, tb = self._title_block()
        w = tb[2]
        h = 30 + 13 * len(self._notes_lines(w)) + 8
        return (tb[0], tb[1] - 12.0 - h, w, h)

    def layout(self) -> dict[str, tuple[float, float, float, float]]:
        """Bounding boxes of the legend, notes, title block and the free drawing area above them."""
        _, lb = self._legend()
        _, tb = self._title_block()
        nb = self._notes_box()
        top = min(lb[1], nb[1] if nb else lb[1])
        return {
            "legend": lb,
            "title_block": tb,
            "notes": nb or (0.0, 0.0, 0.0, 0.0),
            "band_top": (0.0, top, 0.0, 0.0),
        }

    def to_svg(self) -> str:
        """Render the sheet as a standalone SVG string."""
        body: list[str] = []
        body.append(
            f'<rect width="{self.width:.0f}" height="{self.height:.0f}" fill="#ffffff"/>'
        )
        body.append(
            f'<rect x="8" y="8" width="{self.width - 16:.0f}" height="{self.height - 16:.0f}" fill="none" stroke="#1b2a3a" stroke-width="2.5"/>'
        )
        for x, y, w, h, label, where in self.zones:
            body.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="#fafbfd" stroke="#8a97a6" stroke-width="1.4" stroke-dasharray="14 6"/>'
            )
            body.append(
                self._t(
                    x + 14,
                    y + 22 if where == "top" else y + h - 12,
                    label,
                    13,
                    bold=True,
                    fill="#44546a",
                )
            )
        for p in self.pipes:
            body += self._draw_pipe(p)
        body += self.decor
        for s in self.symbols.values():
            body.append(f'<g data-tag="{escape(s.tag)}">')
            body += self._draw_symbol(s)
            body += self._label_lines(s)
            body.append("</g>")
        for x, y, text, size, anchor, wf in self.texts:
            weight, _, fill = wf.partition("|")
            body.append(self._t(x, y, text, size, anchor, weight == "bold", fill))
        tb, _ = self._title_block()
        body += tb
        lg, _ = self._legend()
        body += lg
        nbox = self._notes_box()
        if nbox:
            nb, _ = self._notes_block(nbox[0], nbox[1], nbox[2])
            body += nb
        return '<svg xmlns="http://www.w3.org/2000/svg" width="{:.0f}" height="{:.0f}" viewBox="0 0 {:.0f} {:.0f}">\n{}\n</svg>\n'.format(
            self.width, self.height, self.width, self.height, "\n".join(body)
        )

    # ------------------------------------------------------------------ layout checker export
    def layout_spec(self, intended_width_mm: float = 420.0) -> dict:
        """A ``neqsim.pfd_layout.v1`` spec of this sheet for ``neqsim pfd-check``.

        Stream numbers are not required for a P&ID sketch (lines carry line numbers instead), and valve, instrument and junction
        symbols are small by design.
        """
        nodes = []
        for s in self.symbols.values():
            x0, y0, x1, y1 = s.bbox()
            texts = []
            tag = s.shown_tag
            lines = [ln for ln in s.label.split("\n") if ln]
            if s.kind == "instrument":
                texts.append(
                    {
                        "text": tag,
                        "x": s.x,
                        "y": s.y,
                        "font_size": 10.0,
                        "anchor": "middle",
                        "kind": "inside",
                    }
                )
                for i, ln in enumerate(lines):
                    texts.append(
                        {
                            "text": ln,
                            "x": s.x + _INSTR_R + 6,
                            "y": s.y + 4 + 11 * i - 5.5 * (len(lines) - 1),
                            "font_size": 9.5,
                            "anchor": "start",
                            "kind": "outside",
                        }
                    )
            elif s.kind in BOXES and s.kind not in (
                "pump",
                "pig_launcher",
                "pig_receiver",
                "connector",
                "boundary",
            ):
                yy = (
                    s.y - (len(lines) * 6.5 + (7 if tag else 0)) + 4
                    if s.kind != "tree"
                    else y0 + 14
                )
                if tag:
                    texts.append(
                        {
                            "text": tag,
                            "x": s.x,
                            "y": yy,
                            "font_size": 11.5,
                            "anchor": "middle",
                            "kind": "inside",
                            "bold": True,
                        }
                    )
                    yy += 15 if s.kind != "tree" else 22
                for i, ln in enumerate(lines):
                    texts.append(
                        {
                            "text": ln,
                            "x": s.x,
                            "y": yy + 12.5 * i,
                            "font_size": 10.5,
                            "anchor": "middle",
                            "kind": "inside",
                        }
                    )
            elif s.kind == "boundary":
                for i, ln in enumerate(lines):
                    texts.append(
                        {
                            "text": ln,
                            "x": s.x,
                            "y": s.y + 12.5 * i - 6 * len(lines) + 6,
                            "font_size": 10.5,
                            "anchor": "middle",
                            "kind": "inside",
                        }
                    )
            elif s.kind != "junction":
                if s.label_pos in ("left", "right"):
                    anchor = "end" if s.label_pos == "left" else "start"
                    tx = x0 - 7 if s.label_pos == "left" else x1 + 7
                    yy = s.y - 6 * len(lines)
                    if tag:
                        texts.append(
                            {
                                "text": tag,
                                "x": tx,
                                "y": yy,
                                "font_size": 11.0,
                                "anchor": anchor,
                                "kind": "outside",
                            }
                        )
                        yy += 13
                    for i, ln in enumerate(lines):
                        texts.append(
                            {
                                "text": ln,
                                "x": tx,
                                "y": yy + 12 * i + 4,
                                "font_size": 10.0,
                                "anchor": anchor,
                                "kind": "outside",
                            }
                        )
                else:
                    yy = y1 + 15
                    if s.label_pos == "above":
                        yy = y0 - 6 - 12.5 * len(lines)
                    if tag:
                        texts.append(
                            {
                                "text": tag,
                                "x": s.x,
                                "y": yy,
                                "font_size": 11.0,
                                "anchor": "middle",
                                "kind": "outside",
                            }
                        )
                        yy += 13
                    for i, ln in enumerate(lines):
                        texts.append(
                            {
                                "text": ln,
                                "x": s.x,
                                "y": yy + 12 * i,
                                "font_size": 10.0,
                                "anchor": "middle",
                                "kind": "outside",
                            }
                        )
            nodes.append(
                {
                    "id": s.tag,
                    "kind": {
                        "junction": "junction",
                        "boundary": "boundary",
                        "tree": "vessel",
                        "manifold": "equipment",
                        "plet": "equipment",
                        "box": "equipment",
                        "vessel": "vessel",
                        "pump": "pump",
                        "instrument": "instrument",
                    }.get(s.kind, s.kind if s.kind in VALVES else "equipment"),
                    "tag": tag if s.kind != "boundary" else None,
                    "bbox": [x0, y0, x1 - x0, y1 - y0],
                    "texts": texts,
                    "style": {
                        "shape": s.kind,
                        "fill": s.fill,
                        "dash": "dashed" if s.status == "decision" else "",
                    },
                }
            )
        edges = []
        for p in self.pipes:
            col, sw, dash, _ = SERVICES[p.service]
            pts = [list(q) for q in p.points]
            frm = p.a if p.a in self.symbols else None
            to = p.b if p.b in self.symbols else None
            role = ""
            fluid = {
                "production": "mixed",
                "injection": "water",
                "service": "glycol",
                "gas": "gas",
                "chemical": "chemical",
                "hydraulic": "hydraulic",
                "electrical": "electrical",
                "vent": "vent",
                "signal": "sensing",
            }[p.service]
            if p.service == "signal":
                # a sensing line runs from the process to the instrument in the checker's model
                pts, frm, to, role = pts[::-1], to, frm, "sensing"
            elif p.points[-1][0] < p.points[0][0] - 1.0:
                role = "return"
            edges.append(
                {
                    "id": p.line_id,
                    "from": frm,
                    "to": to,
                    "points": pts,
                    "arrow_end": bool(p.arrow),
                    "arrow_start": False,
                    "fluid": fluid,
                    "stream": "",
                    "role": role,
                    "style": {"color": col, "dash": dash, "width": str(sw)},
                    **(
                        {
                            "label": {
                                "text": p.label,
                                "x": self._label_anchor(p)[0][0] + p.label_dx,
                                "y": self._label_anchor(p)[0][1] + p.label_dy,
                                "font_size": 10.5,
                                "anchor": "middle",
                                "kind": "annotation",
                            }
                        }
                        if p.label
                        else {}
                    ),
                }
            )
        lay = self.layout()
        waivers = list(self.waivers)
        if any(s.status == "decision" for s in self.symbols.values()):
            waivers.append(
                {
                    "code": "SYMBOL_INCONSISTENT",
                    "reason": "a dashed outline marks an option or open decision (explained in the legend)",
                }
            )
        if any(s.kind == "instrument" for s in self.symbols.values()):
            waivers.append(
                {
                    "code": "PRODUCT_POSITION",
                    "reason": "transmitters are sinks of sensing lines, not products",
                }
            )
        tbx = lay["title_block"]
        nbx = lay["notes"]
        if nbx[2] > 0:
            x0u, y0u = min(tbx[0], nbx[0]), min(tbx[1], nbx[1])
            tbx = (
                x0u,
                y0u,
                max(tbx[0] + tbx[2], nbx[0] + nbx[2]) - x0u,
                max(tbx[1] + tbx[3], nbx[1] + nbx[3]) - y0u,
            )
        band_top = lay["band_top"][1]
        return {
            "schema": "neqsim.pfd_layout.v1",
            "kind": "pid",
            "name": self.drawing_no,
            "canvas": {
                "width": self.width,
                "height": self.height,
                "unit": "px",
                "intended_width_mm": intended_width_mm,
            },
            "drawing_area": [16.0, 16.0, self.width - 32.0, band_top - 32.0],
            "nodes": nodes,
            "edges": edges,
            "labels": [
                {
                    "text": t[2],
                    "x": t[0],
                    "y": t[1],
                    "font_size": t[3],
                    "anchor": t[4],
                    "kind": "annotation",
                }
                for t in self.texts
            ]
            + [
                {
                    "text": z[4],
                    "x": z[0] + 14,
                    "y": z[1] + 22 if z[5] == "top" else z[1] + z[3] - 12,
                    "font_size": 13.0,
                    "anchor": "start",
                    "kind": "annotation",
                }
                for z in self.zones
            ],
            "junctions": [],
            "title": True,
            "footer": True,
            "legend": {"bbox": list(lay["legend"])},
            "title_block": {"bbox": list(tbx)},
            "flow_direction": "lr",
            "waivers": waivers,
            "options": {"require_stream_ids": False, "max_crossings": 0},
            "y_axis": "down",
            "arrow_length": 9.0,
        }

    def write(self, base_path: str) -> dict[str, str]:
        """Write ``<base>.svg`` and ``<base>.layout.json`` and return their paths."""
        svg_path, spec_path = base_path + ".svg", base_path + ".layout.json"
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(self.to_svg())
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(self.layout_spec(), fh, indent=1)
        return {"svg": svg_path, "layout": spec_path}
