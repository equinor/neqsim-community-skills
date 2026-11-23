"""HAZOP node-pack generator from a P&ID layout and a valve/instrument list.

A node pack is the document set a facilitator hands out *before* a HAZOP session: for each
node the drawing(s) it appears on with the node boundary marked, the design intent, the
design and operating pressure and temperature per operating mode, the equipment, valve
and instrument list taken from the drawing lists, the parameters to challenge and a seeded
worksheet.  The generator is offline and deterministic: it reads

* ``neqsim.pfd_layout.v1`` layout JSON (``nodes`` with ``bbox`` in canvas pixels, ``edges``
  with ``points``) or a connectivity JSON with ``anchor`` positions in millimetres,
* an optional valve/instrument list and line list (CSV),
* node definitions (plain dictionaries, see :func:`build_node_pack`),

and writes the node CSV/markdown tables and one marked-up PNG per node and drawing.

It never judges a hazard.  Items missing from the drawing, a node without design
conditions or a node without a drawing selection become entries in ``missing_evidence`` so
that a gap is never presented as complete.

Evidence status: every number in a node definition is whatever the caller supplied; the
generator copies the caller's ``source`` and ``status`` fields and marks an empty status
``UNVERIFIED``.
"""

from __future__ import annotations

import csv
import fnmatch
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .seeds import (
    DEFAULT_DEVIATION_SEEDS,
    EQUIPMENT_DEVIATION_SEEDS,
    normalise_equipment_type,
)

SCHEMA = "hazop_node_pack.v1"

# Project proposal prefixes ignored when tags are matched (``GR-EV-9101`` == ``EV-9101``).
# The default is an example; set to an empty tuple to match tags exactly.
TAG_PREFIXES: tuple[str, ...] = ("GR-",)

# Item categories used in the node tables.
VALVE_WORDS = (
    "valve",
    "esdv",
    "choke",
    "bdv",
    "check",
    "psv",
    "pzv",
    "relief",
    "blind",
    "spectacle",
)
INSTRUMENT_WORDS = (
    "instrument",
    "transmitter",
    "detector",
    "logic",
    "controller",
    "sensor",
    "sample",
    "flow meter",
    "analyser",
    "analyzer",
)

# Item kind (layout ``kind`` or list ``type``) -> equipment type that seeds deviations.
KIND_TO_EQUIPMENT_TYPE: dict[str, str] = {
    "pump": "pump",
    "vessel": "separator",
    "separator": "separator",
    "compressor": "compressor",
    "heat exchanger": "heatexchanger",
    "choke": "valve",
    "control valve": "valve",
    "control_valve": "valve",
    "esdv": "valve",
    "ssiv": "valve",
    "gate_valve": "valve",
    "ball_valve": "valve",
    "hydraulic_valve": "valve",
    "check_valve": "valve",
    "tree": "tree",
    "pig_receiver": "pigreceiver",
    "pig receiver": "pigreceiver",
    "pig_launcher": "pigreceiver",
    "manifold": "manifold",
    "plet": "manifold",
    "uta": "umbilical",
    "heat_exchanger": "heatexchanger",
    "xmt": "tree",
    "annulus": "annulus",
    "umbilical": "umbilical",
    "hipps": "hipps",
    "riser": "riser",
    "chemical_storage": "chemicalstorage",
    "chemical storage": "chemicalstorage",
    "chemical_tank": "chemicalstorage",
}

# Wording that folds onto the seed keys defined in EXTRA_DEVIATION_SEEDS.
EXTRA_TYPE_ALIASES: dict[str, str] = {
    "xmt": "tree",
    "christmastree": "tree",
    "wellhead": "tree",
    "annulusa": "annulus",
    "pigger": "pigreceiver",
    "pigtrap": "pigreceiver",
    "piglauncher": "pigreceiver",
    "hipp": "hipps",
    "hips": "hipps",
    "plet": "manifold",
    "uta": "umbilical",
    "chemicaltank": "chemicalstorage",
    "chemicalinjection": "chemicalstorage",
}

# Deviation seeds for node types that the base HAZOP preparation does not know.
EXTRA_DEVIATION_SEEDS: dict[str, list[tuple[str, str]]] = {
    "tree": [
        ("NO", "FLOW"),
        ("MORE", "PRESSURE"),
        ("LESS", "TEMPERATURE"),
        ("OTHER THAN", "CONTAINMENT"),
    ],
    "annulus": [
        ("MORE", "PRESSURE"),
        ("LESS", "PRESSURE"),
        ("AS WELL AS", "CONTAMINATION"),
    ],
    "umbilical": [
        ("NO", "FLOW"),
        ("MORE", "PRESSURE"),
        ("REVERSE", "FLOW"),
        ("OTHER THAN", "CONTROL SIGNAL"),
    ],
    "pigreceiver": [
        ("MORE", "PRESSURE"),
        ("OTHER THAN", "OPERATION"),
        ("AS WELL AS", "LIQUID"),
        ("NO", "FLOW"),
    ],
    "hipps": [("MORE", "PRESSURE"), ("NO", "CLOSURE"), ("OTHER THAN", "SPURIOUS TRIP")],
    "riser": [
        ("MORE", "PRESSURE"),
        ("LESS", "FLOW"),
        ("OTHER THAN", "LEAK"),
        ("LESS", "TEMPERATURE"),
    ],
    "manifold": [("NO", "FLOW"), ("MORE", "PRESSURE"), ("REVERSE", "FLOW")],
    "chemicalstorage": [
        ("MORE", "LEVEL"),
        ("LESS", "LEVEL"),
        ("OTHER THAN", "FIRE"),
        ("AS WELL AS", "CONTAMINATION"),
    ],
}

PARAMETER_HINTS = {
    "PRESSURE": "operating, design and test pressure; shut-in, settle-out and surge",
    "FLOW": "rate, turndown, reverse flow, slug",
    "TEMPERATURE": "operating, cooldown, Joule-Thomson and blowdown minimum",
    "LEVEL": "inventory and level",
    "CONTAMINATION": "composition, water, sand, H2S/CO2, chemicals",
    "CLOSURE": "valve closing time and leak tightness",
    "OPERATION": "non-routine operation, intervention, isolation",
}

_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass
class Item:
    """One drawing item (equipment, valve, instrument, boundary)."""

    sheet: str
    key: str
    tag: str
    kind: str
    category: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels
    label: str = ""
    new: bool | None = None


@dataclass
class Pipe:
    """One line (polyline) on a sheet."""

    sheet: str
    key: str
    line_no: str
    service: str
    points: list[tuple[float, float]]
    members: tuple[str, ...] = ()


@dataclass
class Sheet:
    """A drawing with items and pipes in image pixel coordinates."""

    sheet_id: str
    image_size: tuple[int, int]
    items: dict[str, Item] = field(default_factory=dict)
    pipes: list[Pipe] = field(default_factory=list)
    image_path: str = ""


def _category(kind: str) -> str:
    text = str(kind or "").lower()
    if any(word in text for word in INSTRUMENT_WORDS):
        return "instrument"
    if any(word in text for word in VALVE_WORDS):
        return "valve"
    if "boundary" in text or "junction" in text or text == "spec_break":
        return "boundary"
    return "equipment"


def clean_tag(tag: str) -> str:
    """Strip the proposal asterisk and whitespace from a drawing tag."""
    return str(tag or "").strip().rstrip("*").strip()


def strip_tag_prefix(text: str, prefixes: Sequence[str] | None = None) -> str:
    """Remove one leading project prefix (case-insensitive) from a tag or glob pattern."""
    for prefix in TAG_PREFIXES if prefixes is None else prefixes:
        if prefix and text.upper().startswith(prefix.upper()):
            return text[len(prefix) :]
    return text


def norm_tag(tag: str, prefixes: Sequence[str] | None = None) -> str:
    """Tag used for matching: no asterisk and no leading project prefix such as ``GR-``.

    Sheet generators often label ``EV-9101`` where the register says ``GR-EV-9101``; both
    must select the same item. ``prefixes`` defaults to :data:`TAG_PREFIXES`.
    """
    return strip_tag_prefix(clean_tag(tag), prefixes)


def sheet_from_layout(
    layout_path: str | Path,
    image_size: tuple[int, int],
    *,
    sheet_id: str | None = None,
    image_path: str | Path = "",
) -> Sheet:
    """Read a ``neqsim.pfd_layout.v1`` layout JSON into pixel coordinates of an image.

    ``image_size`` is the size in pixels of the PNG that was rendered from the same layout;
    the layout canvas is scaled to it.
    """
    layout = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    canvas = layout.get("canvas", {})
    cw = float(canvas.get("width") or image_size[0])
    ch = float(canvas.get("height") or image_size[1])
    sx, sy = image_size[0] / cw, image_size[1] / ch
    sheet = Sheet(
        sheet_id=sheet_id or str(layout.get("name") or Path(layout_path).stem),
        image_size=image_size,
        image_path=str(image_path),
    )
    for node in layout.get("nodes", []):
        if "bbox" not in node or "id" not in node:
            continue
        x, y, w, h = node["bbox"]
        key = str(node["id"])
        tag = clean_tag(node.get("tag") or "")
        kind = str(node.get("kind") or "")
        text = " ".join(
            str(t.get("text", "")) if isinstance(t, Mapping) else str(t)
            for t in node.get("texts", [])
        )
        sheet.items[key] = Item(
            sheet=sheet.sheet_id,
            key=key,
            tag=tag or key,
            kind=kind,
            category=_category(kind),
            bbox=(x * sx, y * sy, (x + w) * sx, (y + h) * sy),
            label=text.strip(),
            new=None,
        )
    for edge in layout.get("edges", []):
        pts = [(float(px) * sx, float(py) * sy) for px, py in edge.get("points", [])]
        sheet.pipes.append(
            Pipe(
                sheet=sheet.sheet_id,
                key=str(edge.get("id")),
                line_no="",
                service=str(edge.get("fluid") or ""),
                points=pts,
                members=(str(edge.get("from") or ""), str(edge.get("to") or "")),
            )
        )
    return sheet


def sheet_from_connectivity(
    connectivity_path: str | Path,
    image_size: tuple[int, int],
    *,
    sheet_id: str | None = None,
    canvas_mm: tuple[float, float] = (420.0, 297.0),
    y_up: bool = True,
    symbol_half_mm: float = 5.0,
    image_path: str | Path = "",
) -> Sheet:
    """Read a connectivity JSON (nodes with ``anchor`` in mm, ``pipes`` with ``points``).

    ``y_up`` is True when the generator used a mathematical y axis (origin at the bottom
    left), which is what matplotlib-based sheet builders use.
    """
    data = json.loads(Path(connectivity_path).read_text(encoding="utf-8"))
    sx, sy = image_size[0] / canvas_mm[0], image_size[1] / canvas_mm[1]

    def px(x: float, y: float) -> tuple[float, float]:
        yy = (canvas_mm[1] - y) if y_up else y
        return x * sx, yy * sy

    sheet = Sheet(
        sheet_id=sheet_id or str(data.get("sheet") or Path(connectivity_path).stem),
        image_size=image_size,
        image_path=str(image_path),
    )
    for node in data.get("nodes", []):
        if "anchor" not in node or "id" not in node:
            continue
        ax, ay = node["anchor"]
        cx, cy = px(float(ax), float(ay))
        half = symbol_half_mm * sx
        key = str(node["id"])
        kind = str(node.get("kind") or "")
        sheet.items[key] = Item(
            sheet=sheet.sheet_id,
            key=key,
            tag=clean_tag(node.get("tag") or key),
            kind=kind,
            category=_category(kind),
            bbox=(cx - half, cy - half, cx + half, cy + half),
            label=str(node.get("desc") or ""),
            new=bool(node.get("new")) if "new" in node else None,
        )
    members: dict[str, list[str]] = {}
    for edge in data.get("edges", []):
        bucket = members.setdefault(str(edge.get("pipe")), [])
        for end in (edge.get("from_", edge.get("from")), edge.get("to")):
            if end is not None and str(end) not in bucket:
                bucket.append(str(end))
    for pipe in data.get("pipes", []):
        pts = [px(float(a), float(b)) for a, b in pipe.get("points", [])]
        name = str(pipe.get("name"))
        sheet.pipes.append(
            Pipe(
                sheet=sheet.sheet_id,
                key=name,
                line_no=str(pipe.get("line_no") or ""),
                service=str(pipe.get("service") or ""),
                points=pts,
                members=tuple(members.get(name, [])),
            )
        )
    return sheet


def read_csv_rows(path: str | Path | None) -> list[dict[str, str]]:
    """Read a CSV file (utf-8 with or without BOM) into dictionaries; empty if absent."""
    if not path or not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _matches(tag: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(tag, pat) or tag == pat for pat in patterns)


def select_items(
    sheet: Sheet,
    *,
    tags: Sequence[str] = (),
    keys: Sequence[str] = (),
    tag_globs: Sequence[str] = (),
) -> list[Item]:
    """Items of a sheet chosen by tag, layout key or glob pattern (asterisks ignored)."""
    chosen: list[Item] = []
    wanted_tags = {norm_tag(t) for t in tags}
    wanted_keys = {str(k) for k in keys}
    globs = [strip_tag_prefix(g) for g in tag_globs]
    for item in sheet.items.values():
        if (
            item.key in wanted_keys
            or norm_tag(item.tag) in wanted_tags
            or _matches(norm_tag(item.tag), globs)
        ):
            chosen.append(item)
    # An in-line junction joins the selection when two or more of its neighbours are in it;
    # repeat so that a chain of junctions between two selected items is followed.
    chosen_keys = {i.key for i in chosen}
    neighbours: dict[str, set[str]] = {}
    for pipe in sheet.pipes:
        for member in pipe.members:
            neighbours.setdefault(member, set()).update(
                m for m in pipe.members if m != member
            )
    changed = True
    while changed:
        changed = False
        for item in sheet.items.values():
            if item.key in chosen_keys or not _is_junction(item):
                continue
            if len(neighbours.get(item.key, set()) & chosen_keys) >= 2:
                chosen.append(item)
                chosen_keys.add(item.key)
                changed = True
    return chosen


def unmatched_requests(
    sheet: Sheet,
    *,
    tags: Sequence[str] = (),
    keys: Sequence[str] = (),
    tag_globs: Sequence[str] = (),
) -> list[str]:
    """Requested tags, keys and glob patterns that match no item on the sheet."""
    present_tags = {norm_tag(i.tag) for i in sheet.items.values()}
    missing = [f"tag {t}" for t in tags if norm_tag(t) not in present_tags]
    missing += [f"key {k}" for k in keys if str(k) not in sheet.items]
    for glob in tag_globs:
        pattern = strip_tag_prefix(glob)
        if not _matches_any(present_tags, pattern):
            missing.append(f"glob {glob}")
    return missing


def _matches_any(tags: Iterable[str], pattern: str) -> bool:
    return any(_matches(tag, [pattern]) for tag in tags)


def _is_junction(item: Item) -> bool:
    kind = item.kind.lower()
    return kind in ("junction", "spec_break") or (
        kind == "" and item.key.startswith("J")
    )


def select_pipes(
    sheet: Sheet, items: Sequence[Item], *, line_nos: Sequence[str] = ()
) -> list[Pipe]:
    """Pipes whose line number is listed or whose two ends are both selected items."""
    keys = {item.key for item in items}
    wanted = {str(n) for n in line_nos}
    pipes: list[Pipe] = []
    for pipe in sheet.pipes:
        inside = len(keys & set(pipe.members))
        if (pipe.line_no and pipe.line_no in wanted) or inside >= 2:
            pipes.append(pipe)
    return pipes


def list_rows_for_node(
    valve_rows: Sequence[Mapping[str, str]],
    sheet_id: str,
    tags: Sequence[str],
    tag_globs: Sequence[str] = (),
) -> list[dict[str, str]]:
    """Rows of a valve/instrument list that belong to a node (sheet + tag selection)."""
    wanted = {norm_tag(t) for t in tags}
    globs = [strip_tag_prefix(g) for g in tag_globs]
    rows: list[dict[str, str]] = []
    for row in valve_rows:
        if str(row.get("sheet", "")).strip() not in ("", sheet_id):
            continue
        tag = norm_tag(row.get("tag", ""))
        if tag in wanted or _matches(tag, globs):
            rows.append(dict(row))
    return rows


def seed_deviations(equipment_types: Sequence[str]) -> list[tuple[str, str]]:
    """Guide-word/parameter pairs for a node, the union over its equipment types."""
    pairs: list[tuple[str, str]] = []
    for raw in equipment_types:
        seeds = _seeds_for(raw)
        if seeds is None:
            seeds = DEFAULT_DEVIATION_SEEDS
        for pair in seeds:
            if pair not in pairs:
                pairs.append(pair)
    return pairs or list(DEFAULT_DEVIATION_SEEDS)


def _seeds_for(raw: str) -> list[tuple[str, str]] | None:
    """Seed pairs for one equipment type, or None when the type is not recognised."""
    key = normalise_equipment_type(raw)
    squeezed = re.sub(r"[\s_\-]+", "", str(raw or "").strip().lower())
    for candidate in (key, squeezed, EXTRA_TYPE_ALIASES.get(squeezed, "")):
        if candidate in EQUIPMENT_DEVIATION_SEEDS:
            return EQUIPMENT_DEVIATION_SEEDS[candidate]
        if candidate in EXTRA_DEVIATION_SEEDS:
            return EXTRA_DEVIATION_SEEDS[candidate]
    return None


def unrecognised_equipment_types(equipment_types: Sequence[str]) -> list[str]:
    """Equipment types that fall back to the two-row default seed."""
    return [str(t) for t in equipment_types if _seeds_for(t) is None]


def infer_equipment_types(items: Sequence[Item]) -> list[str]:
    """Equipment types suggested by the kinds of the selected items (deduplicated)."""
    found: list[str] = []
    for item in items:
        eq = KIND_TO_EQUIPMENT_TYPE.get(item.kind.lower())
        if eq and eq not in found:
            found.append(eq)
    return found


# --------------------------------------------------------------------------- markup
def render_markup(
    sheet: Sheet,
    items: Sequence[Item],
    pipes: Sequence[Pipe],
    out_path: str | Path,
    *,
    title: str,
    image_path: str | Path | None = None,
    max_width: int = 2400,
    colour: tuple[int, int, int] = (255, 18, 67),
    boundary_pad: float = 40.0,
    crop: bool = False,
) -> dict[str, Any]:
    """Draw the node on a copy of the drawing PNG and return the drawn box.

    Selected lines are drawn thick and translucent, selected items get a box, and a
    dashed rectangle marks the node boundary (the bounding box of the selection plus a
    margin).  The source drawing is never modified.
    """
    from PIL import Image, ImageDraw, ImageFont

    src = Path(image_path or sheet.image_path)
    out = Path(out_path)
    if out.resolve() == src.resolve():
        raise ValueError("mark-up output must not overwrite the source drawing")
    image = Image.open(src).convert("RGBA")
    if image.size != tuple(sheet.image_size):
        sx = image.size[0] / sheet.image_size[0]
        sy = image.size[1] / sheet.image_size[1]
    else:
        sx = sy = 1.0
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    pipe_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    pdraw = ImageDraw.Draw(pipe_layer)
    width = max(4, int(image.size[0] / 500))
    xs: list[float] = []
    ys: list[float] = []
    pxs: list[float] = []
    pys: list[float] = []
    for pipe in pipes:
        pts = [(x * sx, y * sy) for x, y in pipe.points]
        if len(pts) >= 2:
            pdraw.line(pts, fill=colour + (110,), width=width * 3, joint="curve")
            pxs += [p[0] for p in pts]
            pys += [p[1] for p in pts]
    for item in items:
        x0, y0, x1, y1 = (
            item.bbox[0] * sx,
            item.bbox[1] * sy,
            item.bbox[2] * sx,
            item.bbox[3] * sy,
        )
        pad = width * 2
        draw.rectangle(
            [x0 - pad, y0 - pad, x1 + pad, y1 + pad],
            outline=colour + (255,),
            width=width,
        )
        xs += [x0, x1]
        ys += [y0, y1]
    box: list[float] = []
    bxs, bys = (xs, ys) if xs and ys else (pxs, pys)
    if bxs and bys:
        pad = boundary_pad * sx
        box = [
            max(0.0, min(bxs) - pad),
            max(0.0, min(bys) - pad),
            min(float(image.size[0]), max(bxs) + pad),
            min(float(image.size[1]), max(bys) + pad),
        ]
        # lines are clipped to the node boundary so a long line does not stretch the node
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rectangle(box, fill=255)
        clipped = Image.new("RGBA", image.size, (255, 255, 255, 0))
        clipped.paste(pipe_layer, (0, 0), mask)
        overlay = Image.alpha_composite(clipped, overlay)
        draw = ImageDraw.Draw(overlay)
        dash = width * 8
        _dashed_rectangle(draw, box, colour + (255,), width * 2, dash)
        font, font_size = _load_font(max(18, int(image.size[0] / 90)), ImageFont)
        draw.rectangle(
            [
                box[0],
                max(0, box[1] - font_size * 1.6),
                box[0] + font_size * 0.62 * len(title) + 20,
                box[1],
            ],
            fill=colour + (255,),
        )
        draw.text(
            (box[0] + 10, max(0, box[1] - font_size * 1.5)),
            title,
            fill=(255, 255, 255, 255),
            font=font,
        )
    merged = Image.alpha_composite(image, overlay).convert("RGB")
    source_size = [image.size[0], image.size[1]]
    if crop and box:
        mx = image.size[0] * 0.03
        merged = merged.crop(
            (
                int(max(0, box[0] - mx)),
                int(max(0, box[1] - mx * 2)),
                int(min(image.size[0], box[2] + mx)),
                int(min(image.size[1], box[3] + mx)),
            )
        )
    if merged.size[0] > max_width:
        ratio = max_width / merged.size[0]
        merged = merged.resize((max_width, max(1, int(merged.size[1] * ratio))))
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.save(out, dpi=(200, 200))
    return {
        "file": str(out),
        "boundary_box_px": [round(v, 1) for v in box],
        "source_size_px": source_size,
        "output_size_px": [merged.size[0], merged.size[1]],
    }


def _load_font(size: int, font_module: Any) -> tuple[Any, int]:
    """A TrueType font when one is installed, else the Pillow default; with its size."""
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return font_module.truetype(name, size), size
        except OSError:
            continue
    try:
        return font_module.load_default(size=size), size
    except TypeError:
        return font_module.load_default(), 11


def _dashed_rectangle(
    draw: Any, box: Sequence[float], fill: Any, width: int, dash: int
) -> None:
    x0, y0, x1, y1 = box
    for ax, ay, bx, by in (
        (x0, y0, x1, y0),
        (x1, y0, x1, y1),
        (x1, y1, x0, y1),
        (x0, y1, x0, y0),
    ):
        length = max(1.0, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
        steps = int(length // (dash * 2)) + 1
        for i in range(steps):
            t0 = i * dash * 2 / length
            t1 = min(1.0, t0 + dash / length)
            if t0 >= 1.0:
                break
            draw.line(
                [
                    (ax + (bx - ax) * t0, ay + (by - ay) * t0),
                    (ax + (bx - ax) * t1, ay + (by - ay) * t1),
                ],
                fill=fill,
                width=width,
            )


# --------------------------------------------------------------------------- pack
def _numbers(text: Any) -> list[float]:
    return [float(v) for v in _NUMBER.findall(str(text))]


def build_node_pack(
    node_defs: Sequence[Mapping[str, Any]],
    sheets: Mapping[str, Sheet],
    *,
    valve_rows: Sequence[Mapping[str, str]] = (),
    line_rows: Sequence[Mapping[str, str]] = (),
    out_dir: str | Path | None = None,
    project_name: str = "HAZOP node pack",
    render: bool = True,
) -> dict[str, Any]:
    """Build the node pack.

    Each node definition is a mapping with

    ``node_id``, ``name``, ``design_intent``, ``boundary`` (text), ``equipment_types``
    (optional list; inferred from the item kinds when absent), ``modes`` (list of
    ``{mode, p_op_bara, t_op_c, p_design_bara, t_design_c, source, status}``),
    ``parameters`` (list of parameter strings), ``drawings`` (list of
    ``{sheet, keys, tags, tag_globs, line_nos}``), ``notes`` and ``links`` (free dict).

    Returns a dictionary with ``nodes`` (each with items, list rows, modes, seeds, marked-up
    image files), ``quality_gates`` and ``missing_evidence``.
    """
    out = Path(out_dir) if out_dir else None
    nodes: list[dict[str, Any]] = []
    missing: list[str] = []
    seen_ids: set[str] = set()
    for node in node_defs:
        if "node_id" not in node:
            raise ValueError("every node definition needs a 'node_id'")
        node_id = str(node["node_id"])
        if node_id in seen_ids:
            missing.append(f"{node_id}: node id defined more than once")
        seen_ids.add(node_id)
        result: dict[str, Any] = {
            "node_id": node_id,
            "name": node.get("name", ""),
            "design_intent": node.get("design_intent", ""),
            "boundary": node.get("boundary", ""),
            "modes": [],
            "drawings": [],
            "items": [],
            "list_rows": [],
            "line_rows": [],
            "parameters": list(node.get("parameters", [])),
            "links": dict(node.get("links", {})),
            "notes": list(node.get("notes", [])),
            "gates": [],
        }
        all_items: list[Item] = []
        for drawing in node.get("drawings", []):
            if "sheet" not in drawing:
                raise ValueError(f"{node_id}: every drawing selection needs a 'sheet'")
            sheet_id = drawing["sheet"]
            sheet = sheets.get(sheet_id)
            if sheet is None:
                missing.append(f"{node_id}: drawing {sheet_id} not loaded")
                continue
            request = {
                "tags": drawing.get("tags", ()),
                "keys": drawing.get("keys", ()),
                "tag_globs": drawing.get("tag_globs", ()),
            }
            items = select_items(sheet, **request)
            pipes = select_pipes(sheet, items, line_nos=drawing.get("line_nos", ()))
            if not items:
                missing.append(f"{node_id}: no item selected on {sheet_id}")
            for gap in unmatched_requests(sheet, **request):
                missing.append(f"{node_id}: requested {gap} not found on {sheet_id}")
            image_file = ""
            box: list[float] = []
            if render and out is not None and items:
                if sheet.image_path and Path(sheet.image_path).is_file():
                    title = f"{node_id} {node.get('name', '')}".strip()
                    info = render_markup(
                        sheet,
                        items,
                        pipes,
                        out / "markups" / f"{node_id}_{sheet_id}.png",
                        title=title[:70],
                        crop=bool(drawing.get("crop", False)),
                    )
                    image_file = info["file"]
                    box = info["boundary_box_px"]
                else:
                    missing.append(
                        f"{node_id}: no drawing image for {sheet_id}, no mark-up made"
                    )
            result["drawings"].append(
                {
                    "sheet": sheet_id,
                    "selected": len(items),
                    "pipes": len(pipes),
                    "markup": image_file,
                    "boundary_box_px": box,
                    "line_nos": sorted({p.line_no for p in pipes if p.line_no}),
                }
            )
            for item in items:
                result["items"].append(
                    {
                        "sheet": sheet_id,
                        "tag": item.tag,
                        "kind": item.kind,
                        "category": item.category,
                        "label": item.label,
                    }
                )
            all_items += items
            tags = [i.tag for i in items] + list(drawing.get("tags", ()))
            for row in list_rows_for_node(
                valve_rows, sheet_id, tags, drawing.get("tag_globs", ())
            ):
                if row not in result["list_rows"]:
                    result["list_rows"].append(row)
            wanted_lines = set(drawing.get("line_nos", ())) | {
                p.line_no for p in pipes if p.line_no
            }
            for line in line_rows:
                number = str(
                    line.get("line_number")
                    or line.get("line_no")
                    or line.get("line")
                    or ""
                ).strip()
                if (
                    str(line.get("sheet", "")).strip() in ("", sheet_id)
                    and number in wanted_lines
                    and dict(line) not in result["line_rows"]
                ):
                    result["line_rows"].append(dict(line))
        if valve_rows:
            listed = {norm_tag(r.get("tag", "")) for r in result["list_rows"]}
            unlisted = sorted(
                {
                    norm_tag(i["tag"])
                    for i in result["items"]
                    if i["category"] in ("valve", "instrument")
                    and norm_tag(i["tag"]) not in listed
                }
            )
            result["items_without_list_row"] = unlisted
            if unlisted:
                shown = ", ".join(unlisted[:10]) + (
                    " ..." if len(unlisted) > 10 else ""
                )
                missing.append(
                    f"{node_id}: {len(unlisted)} valve/instrument items without a list row ({shown})"
                )
        for mode in node.get("modes", []):
            row = dict(mode)
            row.setdefault("status", "UNVERIFIED")
            if not row["status"]:
                row["status"] = "UNVERIFIED"
            result["modes"].append(row)
        equipment_types = list(
            node.get("equipment_types") or infer_equipment_types(all_items)
        )
        result["equipment_types"] = equipment_types
        result["seed_deviations"] = [
            {"guideWord": g, "parameter": p, "hint": PARAMETER_HINTS.get(p, "")}
            for g, p in seed_deviations(equipment_types)
        ]
        result["unrecognised_equipment_types"] = unrecognised_equipment_types(
            equipment_types
        )
        if result["unrecognised_equipment_types"]:
            missing.append(
                f"{node_id}: equipment type not recognised, default seed used: "
                + ", ".join(result["unrecognised_equipment_types"])
            )
        result["gates"] = _node_gates(result)
        for gate in result["gates"]:
            if gate["status"] != "pass":
                missing.append(f"{node_id}: {gate['message']}")
        nodes.append(result)
    pack = {
        "schema": SCHEMA,
        "project_name": project_name,
        "node_count": len(nodes),
        "nodes": nodes,
        "quality_gates": [
            {
                "name": "all_nodes_have_drawing_and_items",
                "status": (
                    "pass" if nodes and all(n["items"] for n in nodes) else "missing"
                ),
            },
            {
                "name": "all_nodes_have_design_conditions",
                "status": (
                    "pass" if nodes and all(n["modes"] for n in nodes) else "missing"
                ),
            },
        ],
        "missing_evidence": sorted(set(missing)),
        "readiness_label": (
            "orientation_only_until_missing_evidence_closed"
            if missing or not nodes
            else "ready_for_hazop_facilitation"
        ),
        "assumptions": [
            "Node boundaries are the bounding box of the selected items; the facilitator confirms them on the drawing.",
            "Design and operating conditions are copied from the node definition; no value is verified by the generator.",
            "Seeded deviations are placeholders to challenge, not findings.",
        ],
    }
    if not nodes:
        pack["missing_evidence"] = ["no node defined"]
    if out is not None:
        write_node_pack(pack, out)
    return pack


def _node_gates(node: Mapping[str, Any]) -> list[dict[str, str]]:
    gates = []

    def gate(name: str, ok: bool, message: str) -> None:
        gates.append(
            {"name": name, "status": "pass" if ok else "missing", "message": message}
        )

    gate(
        "design_intent",
        bool(str(node.get("design_intent") or "").strip()),
        "design intent missing",
    )
    gate(
        "boundary",
        bool(str(node.get("boundary") or "").strip()),
        "node boundary text missing",
    )
    gate("drawing_items", bool(node.get("items")), "no drawing item selected")
    modes = node.get("modes") or []
    gate(
        "design_conditions",
        any(_first_positive(m.get("p_design_bara")) for m in modes),
        "no design pressure per mode",
    )
    gate("operating_modes", len(modes) >= 1, "no operating mode defined")
    return gates


def _first_positive(value: Any) -> bool:
    """True when the value holds a number above zero (text such as '345 (assumed)' counts)."""
    numbers = _numbers(value)
    return bool(numbers) and numbers[0] > 0


def write_node_pack(pack: Mapping[str, Any], out_dir: str | Path) -> dict[str, str]:
    """Write nodes.csv, node_items.csv, node_modes.csv, node_seeds.csv, pack.json and README.md."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {}

    def write(name: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
        path = out / name
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        files[name] = str(path)

    nodes = pack["nodes"]
    write(
        "nodes.csv",
        [
            "node_id",
            "name",
            "design_intent",
            "boundary",
            "drawings",
            "items",
            "readiness",
        ],
        [
            [
                n["node_id"],
                n["name"],
                n["design_intent"],
                n["boundary"],
                "; ".join(d["sheet"] for d in n["drawings"]),
                len(n["items"]),
                (
                    "gaps"
                    if any(g["status"] != "pass" for g in n["gates"])
                    else "complete"
                ),
            ]
            for n in nodes
        ],
    )
    write(
        "node_items.csv",
        ["node_id", "sheet", "tag", "kind", "category", "label"],
        [
            [n["node_id"], i["sheet"], i["tag"], i["kind"], i["category"], i["label"]]
            for n in nodes
            for i in n["items"]
        ],
    )
    write(
        "node_modes.csv",
        [
            "node_id",
            "mode",
            "p_op_bara",
            "t_op_c",
            "p_design_bara",
            "t_design_c",
            "source",
            "status",
        ],
        [
            [
                n["node_id"],
                m.get("mode", ""),
                m.get("p_op_bara", ""),
                m.get("t_op_c", ""),
                m.get("p_design_bara", ""),
                m.get("t_design_c", ""),
                m.get("source", ""),
                m.get("status", ""),
            ]
            for n in nodes
            for m in n["modes"]
        ],
    )
    write(
        "node_seeds.csv",
        ["node_id", "guide_word", "parameter", "hint"],
        [
            [n["node_id"], s["guideWord"], s["parameter"], s["hint"]]
            for n in nodes
            for s in n["seed_deviations"]
        ],
    )
    pack_path = out / "pack.json"
    pack_path.write_text(
        json.dumps(pack, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    files["pack.json"] = str(pack_path)
    lines = [
        f"# {pack['project_name']}",
        "",
        f"Readiness: `{pack['readiness_label']}`",
        "",
    ]
    for n in nodes:
        lines += [
            f"## {n['node_id']} {n['name']}",
            "",
            f"Design intent: {n['design_intent']}",
            "",
        ]
        lines += [f"Boundary: {n['boundary']}", ""]
        for d in n["drawings"]:
            lines.append(
                f"- {d['sheet']}: {d['selected']} items, {d['pipes']} lines, mark-up `{d['markup']}`"
            )
        lines.append("")
    if pack["missing_evidence"]:
        lines += ["## Missing evidence", ""] + [
            f"- {m}" for m in pack["missing_evidence"]
        ]
    readme = out / "README.md"
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    files["README.md"] = str(readme)
    return files
