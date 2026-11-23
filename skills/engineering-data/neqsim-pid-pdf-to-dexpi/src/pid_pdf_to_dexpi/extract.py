"""Extract a reviewable P&ID topology from a vector (CAD-exported) PDF sheet.

The result is a ``neqsim_pid_drawing_records.v1`` dictionary: equipment and off-page
connector nodes with nozzles, traced process-line edges with drawn paths, inline valves,
instrument bubbles, warnings and assumptions. It is a draft for engineering review, not
a controlled P&ID: the drawing remains the source of truth.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import ExtractionConfig
from .geometry import LineGraph, Point, Rect, Segment, bbox_of, dist
from .topology import build_network

SCHEMA_VERSION = "neqsim_pid_drawing_records.v1"


@dataclass
class Word:
    """One text word with its box."""

    text: str
    rect: Rect


@dataclass
class Page:
    """Vector primitives of one PDF page, independent of PyMuPDF."""

    width: float
    height: float
    words: list[Word]
    segments: list[Segment]
    curves: list[Segment]
    fills: list[Rect]
    source: dict[str, Any] = field(default_factory=dict)


def load_pdf_page(pdf_path: str | Path, page_index: int = 0) -> Page:
    """Reads text words and stroked/filled primitives from a PDF page with PyMuPDF."""
    import fitz  # PyMuPDF; imported lazily so the geometry core stays dependency-free

    path = Path(pdf_path)
    doc = fitz.open(str(path))
    page = doc[page_index]
    words = [Word(w[4], Rect(w[0], w[1], w[2], w[3])) for w in page.get_text("words")]
    segments: list[Segment] = []
    curves: list[Segment] = []
    fills: list[Rect] = []
    for d in page.get_drawings():
        if d["type"] == "f":
            r = d["rect"]
            fills.append(Rect(r.x0, r.y0, r.x1, r.y1))
            continue
        width = float(d.get("width") or 0.0)
        dashes = d.get("dashes")
        dashed = bool(dashes) and dashes.strip() not in ("[] 0", "[]0", "")
        for item in d["items"]:
            if item[0] == "l":
                segments.append(Segment(item[1].x, item[1].y, item[2].x, item[2].y, width, dashed))
            elif item[0] == "c":
                curves.append(Segment(item[1].x, item[1].y, item[4].x, item[4].y, width, dashed))
            elif item[0] == "re":
                r = item[1]
                for a, b in (((r.x0, r.y0), (r.x1, r.y0)), ((r.x1, r.y0), (r.x1, r.y1)),
                             ((r.x1, r.y1), (r.x0, r.y1)), ((r.x0, r.y1), (r.x0, r.y0))):
                    segments.append(Segment(a[0], a[1], b[0], b[1], width, dashed))
    data = path.read_bytes()
    source = {"file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "page": page_index,
              "pageCount": doc.page_count, "units": "pt"}
    return Page(page.rect.width, page.rect.height, words, segments, curves, fills, source)


def extract_pid_records(pdf_path: str | Path, page_index: int = 0,
                        config: Optional[ExtractionConfig] = None) -> dict[str, Any]:
    """Reads one P&ID sheet and returns ``neqsim_pid_drawing_records.v1``."""
    page = load_pdf_page(pdf_path, page_index)
    return extract_from_page(page, config)


def extract_from_page(page: Page, config: Optional[ExtractionConfig] = None) -> dict[str, Any]:
    """Builds drawing records from page primitives (testable without a PDF)."""
    return _Extractor(page, config or ExtractionConfig()).run()


class _Extractor:
    def __init__(self, page: Page, cfg: ExtractionConfig):
        self.page = page
        self.cfg = cfg
        self.warnings: list[str] = []
        self.assumptions: list[str] = [
            "Process piping is identified by stroke width >= %.2f pt; thinner and dashed strokes are symbols, "
            "signal lines or annotation." % cfg.process_min_width,
            "A collinear gap of up to %.0f pt between facing process-line ends is an inline item (valve, "
            "flange, reducer or blind)." % cfg.gap_max,
            "Off-page connector direction comes from FROM/TO in its label; connectors without FROM/TO are "
            "treated as outlets.",
            "Branches to drains, flare, vents, sampling, chemicals and similar utilities carry no flow in normal "
            "operation (NormalFlow=false).",
        ]
        self.process = [s for s in page.segments if s.width >= cfg.process_min_width and not s.dashed]
        self.thin = [s for s in page.segments if s.width < cfg.process_min_width and not s.dashed]

    # ---------------------------------------------------------------- text
    def _words_in(self, r: Rect) -> list[Word]:
        return [w for w in self.page.words if r.intersects(w.rect)]

    @staticmethod
    def _reading_order(words: list[Word]) -> str:
        rows: list[list[Word]] = []
        for w in sorted(words, key=lambda w: (w.rect.y0, w.rect.x0)):
            if rows and abs(rows[-1][0].rect.y0 - w.rect.y0) < 4.0:
                rows[-1].append(w)
            else:
                rows.append([w])
        return " ".join(" ".join(x.text for x in sorted(r, key=lambda w: w.rect.x0)) for r in rows).strip()

    def _drawing_number(self) -> str:
        pattern = re.compile(self.cfg.drawing_ref_regex)
        refs = [w for w in self.page.words if pattern.match(w.text)]
        if not refs:
            return ""
        corner = max(refs, key=lambda w: w.rect.x0 + w.rect.y0)
        return corner.text

    # ----------------------------------------------------------- equipment
    def _equipment(self) -> list[dict[str, Any]]:
        pattern = re.compile(self.cfg.equipment_tag_regex)
        seen: dict[str, dict[str, Any]] = {}
        for w in self.page.words:
            m = pattern.match(w.text)
            if not m or m.group("code") not in self.cfg.equipment_codes:
                continue
            outline = self._enclosure(w.rect)
            if outline is None:
                continue
            tag = w.text
            rect, has_curves = outline
            score = (2.0 if has_curves else 1.0) * rect.width * rect.height
            if tag not in seen or score > seen[tag]["_score"]:
                kind, cls = self.cfg.equipment_codes[m.group("code")]
                seen[tag] = {"_score": score, "_rect": rect, "tag": tag, "kind": kind, "component_class": cls,
                             "confidence": 0.85 if has_curves else 0.6}
        nodes = []
        for i, item in enumerate(sorted(seen.values(), key=lambda v: v["tag"])):
            rect = item.pop("_rect")
            item.pop("_score")
            item.update({"node_id": "EQ-%d" % (i + 1), "bbox": rect.as_list(), "ports": [],
                         "attributes": self._equipment_data(item["tag"])})
            nodes.append(item)
        return nodes

    def _equipment_data(self, tag: str) -> dict[str, Any]:
        """Reads an equipment data block (TAG NUMBER / SERVICE / DES./OPER. rows) printed on the sheet."""
        anchors = [w for w in self.page.words if w.text == tag]
        for anchor in anchors:
            row_words = [w for w in self.page.words if abs(w.rect.y0 - anchor.rect.y0) < 3 and w.rect.x1 <= anchor.rect.x0]
            if not any(w.text.upper() == "TAG" for w in row_words):
                continue
            x0 = min(w.rect.x0 for w in row_words)
            block = [w for w in self.page.words
                     if anchor.rect.y0 - 2 <= w.rect.y0 <= anchor.rect.y0 + 180 and x0 - 2 <= w.rect.x0 <= x0 + 480]
            rows: dict[int, list[Word]] = defaultdict(list)
            for w in block:
                rows[int(round(w.rect.y0 / 3.0))].append(w)
            data: dict[str, Any] = {"dataBlockSource": "sheet equipment data block"}
            for key in sorted(rows):
                line = " ".join(w.text for w in sorted(rows[key], key=lambda w: w.rect.x0))
                upper = line.upper()
                m = re.search(r"OPER\.?\s*PRESSURE\s+(BARG|BARA|BAR|KPA|MPA|PSIG|PSIA)\s+(.*?)\s*/\s*(-?[\d.]+)", upper)
                if m:
                    data["designPressure"] = "%s %s" % (m.group(2).strip(), m.group(1).lower())
                    data["operatingPressure"] = {"value": float(m.group(3)), "unit": m.group(1).lower()}
                m = re.search(r"OPER\.?\s*TEMPERATURE\s+\S*C\s+(.*?)\s*/\s*(-?[\d.]+)", upper)
                if m:
                    data["designTemperature"] = "%s C" % m.group(1).strip()
                    data["operatingTemperature"] = {"value": float(m.group(2)), "unit": "C"}
                m = re.search(r"ID\s*X\s*TT\s+MM\s+([\d.]+)\s*X\s*([\d.]+)", upper)
                if m:
                    data["insideDiameter_mm"] = float(m.group(1))
                    data["tanTanLength_mm"] = float(m.group(2))
                m = re.match(r"SERVICE\s+(.+)$", line, re.IGNORECASE)
                if m:
                    data["service"] = m.group(1).strip()
                m = re.match(r"MATERIAL\s+(.+)$", line, re.IGNORECASE)
                if m:
                    data["material"] = m.group(1).strip()
            if len(data) > 1:
                return data
        return {}

    def _enclosure(self, tag: Rect) -> Optional[tuple[Rect, bool]]:
        """Grows the thin outline directly above the tag into a closed equipment outline."""
        cx, cy = tag.center
        best = None
        for s in self.thin + [c for c in self.page.curves if not c.dashed]:
            x0, x1 = sorted((s.x0, s.x1))
            if x0 - 0.5 <= cx <= x1 + 0.5 and max(s.y0, s.y1) < tag.y0:
                gap = tag.y0 - max(s.y0, s.y1)
                if gap < 400 and (best is None or gap < best[0]):
                    best = (gap, s)
        if best is None:
            return None
        seed = best[1]
        pool = [s for s in self.thin if abs(s.width - seed.width) < 0.05]
        n_lines = len(pool)
        pool += [s for s in self.page.curves if not s.dashed and abs(s.width - seed.width) < 0.05]
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, s in enumerate(pool):
            for p in (s.a, s.b):
                grid[(int(p[0] // 4), int(p[1] // 4))].append(i)
        start = [i for i, s in enumerate(pool) if s == seed]
        comp, frontier = set(start), list(start)
        while frontier and len(comp) < 5000:
            i = frontier.pop()
            for p in (pool[i].a, pool[i].b):
                gx, gy = int(p[0] // 4), int(p[1] // 4)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for j in grid.get((gx + dx, gy + dy), ()):
                            if j not in comp and min(dist(p, pool[j].a), dist(p, pool[j].b)) < 1.5:
                                comp.add(j)
                                frontier.append(j)
        rect = bbox_of([p for i in comp for p in (pool[i].a, pool[i].b)])
        min_w, min_h = self.cfg.equipment_min_size
        page_area = self.page.width * self.page.height
        if not rect.contains(tag.center) or rect.width < min_w or rect.height < min_h:
            return None
        if rect.width * rect.height > 0.5 * page_area:
            return None
        has_curves = any(i >= n_lines for i in comp)
        return rect, has_curves

    # ---------------------------------------------------------- connectors
    def _connectors(self) -> list[dict[str, Any]]:
        pattern = re.compile(self.cfg.drawing_ref_regex)
        own = self._drawing_number()
        nodes = []
        for w in self.page.words:
            if not pattern.match(w.text):
                continue
            search = Rect(w.rect.x0 - 14, w.rect.y0 - 9, w.rect.x1 + 50, w.rect.y1 + 9)
            pts = [p for s in self.thin if search.contains(s.a) and search.contains(s.b) for p in (s.a, s.b)]
            if len(pts) < 6:
                continue
            box = bbox_of(pts)
            if box.width < w.rect.width or box.height > 40:
                continue
            if w.text == own and box.y0 > 0.85 * self.page.height:
                continue  # title-block drawing number
            label = self._connector_label(box)
            upper = label.upper()
            arrow = self._arrow_direction(pts, box)
            if re.search(r"\bFROM\b", upper):
                direction = "in"
            elif re.search(r"\bTO\b", upper):
                direction = "out"
            elif arrow:
                direction = arrow
            else:
                direction = "out"
                self.warnings.append("Connector %s at (%.0f, %.0f) has no FROM/TO label or readable arrow; "
                                     "treated as outlet." % (w.text, box.x0, box.y0))
            if arrow and arrow != direction:
                self.warnings.append("Connector %s: label says '%s' but the arrow points '%s'; label used."
                                     % (w.text, direction, arrow))
            utility = any(k in upper for k in self.cfg.utility_keywords)
            touch = box.inflate(2.0)
            piped = any(touch.contains(p) for s in self.process for p in (s.a, s.b))
            service = "utility" if utility else "process"
            if not piped:
                service = "signal" if not utility else "utility"
            nodes.append({"node_id": "OPC-%d" % (len(nodes) + 1), "tag": w.text, "kind": "off_page_connector",
                          "component_class": "FlowInPipeOffPageConnector" if direction == "in"
                          else "FlowOutPipeOffPageConnector", "direction": direction, "label": label,
                          "service": service, "bbox": box.as_list(), "ports": [],
                          "confidence": 0.9 if label else 0.6,
                          "attributes": {"continuationSheet": w.text, "processLineAttached": piped}})
        return nodes

    def _arrow_direction(self, pts: list[Point], box: Rect) -> str:
        """Reads flow direction from a pentagon connector: a line attached at the tip flows in."""
        cy = box.center[1]
        tol = 0.15 * box.height + 0.5
        left = [p for p in pts if p[0] - box.x0 < 1.0]
        right = [p for p in pts if box.x1 - p[0] < 1.0]

        def is_tip(side: list[Point]) -> bool:
            return bool(side) and all(abs(p[1] - cy) <= tol for p in side)

        tip = "left" if is_tip(left) and not is_tip(right) else "right" if is_tip(right) and not is_tip(left) else ""
        if not tip:
            return ""
        touch = box.inflate(2.0)
        ends = [p for s in self.process for p in (s.a, s.b) if touch.contains(p)]
        if not ends:
            return ""
        attach = "left" if sum(p[0] for p in ends) / len(ends) < box.center[0] else "right"
        return "in" if attach == tip else "out"

    def _connector_label(self, box: Rect) -> str:
        above = [w for w in self._words_in(Rect(box.x0 - 2, box.y0 - 30, box.x1 + 2, box.y0 - 0.5))
                 if w.rect.y1 <= box.y0 + 0.5]
        text = self._reading_order(above)
        if not text:
            below = [w for w in self._words_in(Rect(box.x0 - 2, box.y1 + 0.5, box.x1 + 2, box.y1 + 16))]
            text = self._reading_order(below)
        return text

    # --------------------------------------------------------- instruments
    def _instruments(self) -> list[dict[str, Any]]:
        letters = re.compile(self.cfg.instrument_letters_regex)
        number = re.compile(self.cfg.instrument_number_regex)
        nums = [w for w in self.page.words if number.match(w.text)]
        out = []
        for w in self.page.words:
            if not letters.match(w.text):
                continue
            cx = w.rect.center[0]
            below = [n for n in nums if 0 <= n.rect.y0 - w.rect.y1 <= 9 and abs(n.rect.center[0] - cx) <= 8]
            if not below:
                continue
            n = min(below, key=lambda n: n.rect.y0 - w.rect.y1)
            center = ((w.rect.x0 + n.rect.x1) / 2.0, (w.rect.y0 + n.rect.y1) / 2.0)
            out.append({"node_id": "INS-%d" % (len(out) + 1), "tag": "%s-%s" % (w.text, n.text), "function": w.text,
                        "number": n.text, "kind": "instrument", "x": round(center[0], 2), "y": round(center[1], 2)})
        return out

    # -------------------------------------------------------------- lines
    def _line_numbers(self) -> list[tuple[Word, re.Match]]:
        pattern = re.compile(self.cfg.line_number_regex)
        out = []
        for w in self.page.words:
            m = pattern.search(w.text)
            if m:
                out.append((w, m))
        return out

    def run(self) -> dict[str, Any]:
        cfg = self.cfg
        equipment = self._equipment()
        connectors = self._connectors()
        instruments = self._instruments()
        lines = self._line_numbers()
        graph = LineGraph(self.process, cfg.endpoint_tol, cfg.gap_max, cfg.gap_lateral_tol)

        terminals: dict[str, Rect] = {}
        equipment_ids: set[str] = set()
        for n in equipment:
            terminals[n["node_id"]] = Rect(*n["bbox"]).inflate(cfg.boundary_margin)
            equipment_ids.add(n["node_id"])
        for n in connectors:
            terminals[n["node_id"]] = Rect(*n["bbox"]).inflate(2.0)
        nodes = {n["node_id"]: n for n in equipment + connectors}
        segments = graph.segments

        def approach(i: int, p: Point, r: Rect) -> Optional[Point]:
            """Projects a free line end that points at an equipment outline onto the outline."""
            s = segments[i]
            other = s.b if dist(p, s.a) < dist(p, s.b) else s.a
            length = dist(p, other)
            if length < 1e-6 or any(dist(p, q) <= cfg.endpoint_tol for j in graph.adjacency[i]
                                    for q in (graph.adjacency[i][j][0],)):
                return None
            d = ((p[0] - other[0]) / length, (p[1] - other[1]) / length)
            for step in range(1, int(cfg.nozzle_reach) + 1):
                q = (p[0] + d[0] * step, p[1] + d[1] * step)
                if r.contains(q):
                    return q
            return None

        def terminal_of(i: int, p: Point) -> Optional[tuple[str, Point]]:
            for tid, r in terminals.items():
                if r.contains(p):
                    return tid, p
            for tid in equipment_ids:
                q = approach(i, p, terminals[tid])
                if q is not None:
                    return tid, q
            return None

        route_list: list[tuple[str, Any]] = []
        attach: dict[int, Point] = {}
        best: dict[tuple, int] = {}
        for tid, r in terminals.items():
            starts: dict[int, Point] = {}
            for i, s in enumerate(segments):
                ins = [p for p in (s.a, s.b) if r.contains(p)]
                if len(ins) == 1:
                    starts[i] = ins[0]
                elif not ins and tid in equipment_ids:
                    for p in (s.a, s.b):
                        if approach(i, p, r) is not None:
                            starts[i] = p
            # Equipment is traced nozzle by nozzle so parallel nozzles on one service are all kept.
            groups = [{i: p} for i, p in starts.items()] if tid in equipment_ids else [starts]
            for group in groups:
                for other, res in graph.trace(group, terminal_of, exclude_terminal=tid).items():
                    entry = next(iter(group.values())) if tid in equipment_ids else (0.0, 0.0)
                    key = (min(tid, other), max(tid, other), round(entry[0]), round(entry[1]))
                    if key in best and route_list[best[key]][1].length <= res.length:
                        continue
                    if key in best:
                        route_list[best[key]] = (tid, res)
                    else:
                        best[key] = len(route_list)
                        route_list.append((tid, res))
                    if tid in equipment_ids:
                        seg = next(iter(group))
                        q = approach(seg, entry, r) if not r.contains(entry) else None
                        attach[best[key]] = q if q is not None else entry

        process_routes = {k for k, (a, res) in enumerate(route_list)
                          if nodes[a].get("service") != "utility" and nodes[res.terminal].get("service") != "utility"}
        network = build_network(graph, route_list, attach=attach)
        edges, tee_nodes = self._edges_from_network(network, nodes, process_routes, lines, instruments)
        self._resolve_roles(nodes, edges)
        for n in equipment:
            if not any(e["from_node"] == n["node_id"] or e["to_node"] == n["node_id"] for e in edges):
                self.warnings.append("Equipment %s has no traced process connection." % n["tag"])
        for n in connectors:
            if n["service"] == "signal":
                continue
            if not any(e["from_node"] == n["node_id"] or e["to_node"] == n["node_id"] for e in edges):
                self.warnings.append("Connector %s (%s) is not traced to equipment or another connector."
                                     % (n["tag"], n["label"] or "no label"))

        source = dict(self.page.source)
        source.update({"pageWidth": round(self.page.width, 2), "pageHeight": round(self.page.height, 2),
                       "drawingNumber": self._drawing_number()})
        counts = {"equipment": len(equipment), "connectors": len(connectors), "tees": len(tee_nodes),
                  "edges": len(edges), "normalFlowEdges": sum(1 for e in edges if e["normal_flow"]),
                  "inlineValves": sum(len(e["inline_items"]) for e in edges), "instruments": len(instruments),
                  "routes": len(route_list), "processStrokes": len(graph.segments),
                  "gapBridges": len(graph.bridges)}
        return {"schemaVersion": SCHEMA_VERSION, "source": source, "nodes": equipment + connectors + tee_nodes,
                "edges": edges, "instruments": instruments, "counts": counts, "warnings": self.warnings,
                "assumptions": self.assumptions, "reviewStatus": "REVIEW_REQUIRED",
                "governance": "Draft topology extracted from a drawing; verify against the controlled revision "
                              "before use in design, safety or operational decisions."}

    def _edges_from_network(self, network, nodes, process_routes, lines, instruments):
        tee_nodes = []
        tee_ids: dict[str, str] = {}
        for k, (name, p) in enumerate(sorted(network.tees.items(), key=lambda kv: (kv[1][1], kv[1][0]))):
            nid = "TEE-%d" % (k + 1)
            tee_ids[name] = nid
            tee_nodes.append({"node_id": nid, "tag": "", "kind": "tee", "component_class": "PipeTee",
                              "bbox": Rect(p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3).as_list(), "ports": [],
                              "confidence": 0.7, "attributes": {}})
        for t in tee_nodes:
            nodes[t["node_id"]] = t

        raw = []
        kept: dict[frozenset, list[float]] = defaultdict(list)
        for e in sorted(network.edges, key=lambda e: -e.length):
            a, b = tee_ids.get(e.a, e.a), tee_ids.get(e.b, e.b)
            pts = list(e.points)
            if len(pts) < 2 and a == b:
                continue
            pair = frozenset((a, b))
            # Parallel duplicates come from doubled strokes and snapping; keep one run per pair and length.
            if any(e.length < 1.0 or abs(e.length - other) <= 0.03 * max(other, 1.0) for other in kept[pair]):
                continue
            kept[pair].append(e.length)
            raw.append([a, b, pts, e])

        # Orientation: +1 a->b, -1 b->a, 0 unknown.
        orient = [0] * len(raw)
        for k, (a, b, _, _) in enumerate(raw):
            na, nb = nodes[a], nodes[b]
            votes = []
            if na["kind"] == "off_page_connector":
                votes.append(1 if na["direction"] == "in" else -1)
            if nb["kind"] == "off_page_connector":
                votes.append(-1 if nb["direction"] == "in" else 1)
            if votes and all(v == votes[0] for v in votes):
                orient[k] = votes[0]
        def propagate() -> None:
            changed = True
            while changed:
                changed = False
                for t in tee_nodes:
                    tid = t["node_id"]
                    inc = [k for k, (a, b, _, _) in enumerate(raw) if tid in (a, b)]
                    ins = sum(1 for k in inc if orient[k] and (raw[k][1] == tid) == (orient[k] == 1))
                    outs = sum(1 for k in inc if orient[k] and (raw[k][0] == tid) == (orient[k] == 1))
                    unknown = [k for k in inc if not orient[k]]
                    if not unknown or ins + outs == 0:
                        continue
                    if ins == 0 or outs == 0:
                        into = outs > 0  # all known branches leave: the unknown ones must feed the tee
                        for k in unknown:
                            orient[k] = 1 if (raw[k][1] == tid) == into else -1
                        changed = True

        propagate()
        while any(not o for o in orient):
            pending = [k for k, o in enumerate(orient) if not o]
            k = next((k for k in pending if nodes[raw[k][0]]["kind"] not in ("tee", "off_page_connector")
                      or nodes[raw[k][1]]["kind"] not in ("tee", "off_page_connector")), pending[0])
            a, b = raw[k][0], raw[k][1]
            orient[k] = -1 if nodes[b]["kind"] not in ("tee", "off_page_connector") else 1
            self.warnings.append("Flow direction between %s and %s could not be derived; assumed outward from "
                                 "equipment." % (nodes[a]["tag"] or a, nodes[b]["tag"] or b))
            propagate()

        edges = []
        for k, (a, b, pts, e) in enumerate(raw):
            bridges = list(e.bridges)
            if orient[k] == -1:
                a, b, pts, bridges = b, a, list(reversed(pts)), list(reversed(bridges))
            src, dst = nodes[a], nodes[b]
            for node, at_end in ((src, False), (dst, True)):
                if node["kind"] not in ("off_page_connector", "tee"):
                    r = Rect(*node["bbox"])
                    p = pts[-1] if at_end else pts[0]
                    q = (min(max(p[0], r.x0), r.x1), min(max(p[1], r.y0), r.y1))
                    if dist(p, q) > 0.5:
                        if at_end:
                            pts.append(q)
                        else:
                            pts.insert(0, q)
            if len(pts) < 2:
                continue
            line_number, fluid = self._nearest_line_number(pts, lines)
            normal = bool(e.routes & process_routes) and fluid not in self.cfg.utility_fluid_codes
            inline = [i for i in (self._classify_inline(br, instruments) for br in bridges) if i]
            conf = min(src.get("confidence", 0.7), dst.get("confidence", 0.7)) * (0.97 ** len(bridges))
            edges.append({"edge_id": "", "from_node": a, "from_port": self._port(src, pts[0], "out"),
                          "to_node": b, "to_port": self._port(dst, pts[-1], "in"), "line_number": line_number,
                          "fluid_code": fluid, "normal_flow": normal, "path": [[round(x, 2), round(y, 2)]
                                                                                for x, y in pts],
                          "length": round(e.length, 1), "inline_items": inline, "gap_count": len(bridges),
                          "confidence": round(conf, 3), "kind": "process"})
        edges.sort(key=lambda d: (not d["normal_flow"], d["length"]))
        for k, d in enumerate(edges):
            d["edge_id"] = "E-%d" % (k + 1)
        return edges, tee_nodes
    def _nearest_line_number(self, pts: list[Point], lines) -> tuple[str, str]:
        best = None
        for w, m in lines:
            c = w.rect.center
            d = min(_dist_to_polyline(c, pts), 1e9)
            if d <= 25.0 and (best is None or d < best[0]):
                best = (d, w.text, m.group("fluid"))
        return (best[1], best[2]) if best else ("", "")

    def _port(self, node: dict[str, Any], p: Point, direction: str) -> str:
        for port in node["ports"]:
            if dist((port["x"], port["y"]), p) < 4.0:
                return port["port_id"]
        port = {"port_id": "%s-P%d" % (node["node_id"], len(node["ports"]) + 1), "x": round(p[0], 2),
                "y": round(p[1], 2), "direction": direction, "role": "", "label": ""}
        if node["kind"] != "off_page_connector":
            nozzle = re.compile(self.cfg.nozzle_regex)
            near = [w for w in self.page.words if nozzle.match(w.text)
                    and dist(w.rect.center, p) <= self.cfg.nozzle_label_radius]
            if near:
                port["label"] = min(near, key=lambda w: dist(w.rect.center, p)).text
        node["ports"].append(port)
        return port["port_id"]

    def _classify_inline(self, br, instruments) -> Optional[dict[str, Any]]:
        mid = br.midpoint
        span = Rect(min(br.p[0], br.q[0]) - 3, min(br.p[1], br.q[1]) - 3,
                    max(br.p[0], br.q[0]) + 3, max(br.p[1], br.q[1]) + 3)
        filled = [f for f in self.page.fills if span.intersects(f) and 2.0 < f.width < 20 and 2.0 < f.height < 20]
        thin = [s for s in self.thin if span.contains(s.a) or span.contains(s.b)]
        if not filled and len(thin) < 2:
            return None
        valve_like = bool(filled) or len(thin) >= 4
        if not valve_like:
            return None
        tag, cls, conf = "", "GenericValve", 0.5
        near = [i for i in instruments if i["function"] in self.cfg.valve_functions
                and dist((i["x"], i["y"]), mid) <= self.cfg.valve_tag_radius]
        if near:
            inst = min(near, key=lambda i: dist((i["x"], i["y"]), mid))
            tag, cls, conf = inst["tag"], self.cfg.valve_functions[inst["function"]], 0.7
        return {"kind": "valve", "component_class": cls, "tag": tag, "x": round(mid[0], 2), "y": round(mid[1], 2),
                "orientation": "horizontal" if br.horizontal else "vertical", "gap": round(br.length, 2),
                "confidence": conf}

    def _resolve_roles(self, nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        out_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in edges:
            if e["normal_flow"]:
                out_edges[e["from_node"]].append(e)

        def downstream_role(edge: dict[str, Any]) -> str:
            frontier, seen = [edge], set()
            while frontier:
                e = frontier.pop(0)
                if e["edge_id"] in seen:
                    continue
                seen.add(e["edge_id"])
                target = nodes[e["to_node"]]
                if target["kind"] == "off_page_connector":
                    role = _role_from_text(target.get("label", ""), "")
                    if role:
                        return role
                elif target["kind"] == "tee":
                    frontier.extend(out_edges[target["node_id"]])
            return _role_from_text("", edge["fluid_code"])

        for node in nodes.values():
            if node["kind"] in ("off_page_connector", "tee"):
                continue
            for e in edges:
                if e["to_node"] == node["node_id"] and e["normal_flow"]:
                    _set_role(node, e["to_port"], "Inlet")
            for e in edges:
                if e["from_node"] == node["node_id"] and e["normal_flow"]:
                    role = downstream_role(e)
                    if role:
                        _set_role(node, e["from_port"], role)
            for port in node["ports"]:
                port["normal_flow"] = any(e["normal_flow"] and port["port_id"] in (e["from_port"], e["to_port"])
                                          for e in edges)
            if node["kind"] in ("separator", "vessel"):
                if not any(p["role"] == "GasOutlet" for p in node["ports"]):
                    unknown = [p for p in node["ports"] if p["direction"] == "out" and not p["role"]
                               and p["normal_flow"]]
                    if unknown:
                        top = min(unknown, key=lambda p: p["y"])
                        top["role"] = "GasOutlet"
                        self.warnings.append("Gas outlet of %s inferred from the highest outlet nozzle %s."
                                             % (node["tag"], top["label"] or top["port_id"]))
                roles = {p["role"] for p in node["ports"]}
                if node["kind"] == "separator" and "WaterOutlet" in roles:
                    node["component_class"] = "ThreePhaseSeparator"

def _role_from_text(label: str, fluid: str) -> str:
    text = label.upper()
    if "GAS" in text:
        return "GasOutlet"
    if "WATER" in text or "HYDROCYCLONE" in text:
        return "WaterOutlet"
    if any(k in text for k in ("OIL", "CONDENSATE", "LIQUID", "STABILI", "CRUDE")):
        return "OilOutlet"
    return {"PG": "GasOutlet", "PW": "WaterOutlet", "PL": "OilOutlet", "PO": "OilOutlet"}.get(fluid, "")


def _set_role(node: dict[str, Any], port_id: str, role: str) -> None:
    for p in node["ports"]:
        if p["port_id"] == port_id and not p["role"]:
            p["role"] = role


def _dist_to_polyline(c: Point, pts: list[Point]) -> float:
    best = math.inf
    for p, q in zip(pts, pts[1:]):
        best = min(best, LineGraphDistance.point_segment(c, p, q))
    return best


class LineGraphDistance:
    """Point-to-segment distance helper."""

    @staticmethod
    def point_segment(c: Point, p: Point, q: Point) -> float:
        vx, vy = q[0] - p[0], q[1] - p[1]
        ll = vx * vx + vy * vy
        t = 0.0 if ll == 0 else max(0.0, min(1.0, ((c[0] - p[0]) * vx + (c[1] - p[1]) * vy) / ll))
        return math.hypot(c[0] - p[0] - t * vx, c[1] - p[1] - t * vy)
