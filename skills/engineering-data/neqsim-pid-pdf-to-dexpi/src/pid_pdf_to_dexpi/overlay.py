"""Review overlay: draws the extracted topology on top of the source PDF sheet."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_COLORS = [(0.85, 0.1, 0.1), (0.1, 0.45, 0.85), (0.1, 0.6, 0.2), (0.8, 0.45, 0.0), (0.55, 0.15, 0.7),
           (0.0, 0.6, 0.6), (0.75, 0.6, 0.0), (0.9, 0.2, 0.6)]


def render_overlay(pdf_path: str | Path, records: dict[str, Any], out_png: str | Path, dpi: int = 72,
                   page_index: int = 0) -> Path:
    """Writes a PNG of the sheet with traced edges, nodes, ports and inline valves highlighted.

    Normal-flow edges are drawn solid and thick; no-flow branches dashed. Untraced connectors are
    boxed in grey so a reviewer sees what the extraction did not connect.
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    shape = page.new_shape()
    connected = {e["from_node"] for e in records["edges"]} | {e["to_node"] for e in records["edges"]}
    for k, edge in enumerate(records["edges"]):
        color = _COLORS[k % len(_COLORS)]
        pts = [fitz.Point(x, y) for x, y in edge["path"]]
        if len(pts) >= 2:
            shape.draw_polyline(pts)
            shape.finish(color=color, width=4.0 if edge["normal_flow"] else 2.0,
                         dashes=None if edge["normal_flow"] else "[6 4] 0", stroke_opacity=0.55,
                         closePath=False)
        for item in edge.get("inline_items", []):
            shape.draw_circle(fitz.Point(item["x"], item["y"]), 7)
            shape.finish(color=color, width=2.0)
    for node in records["nodes"]:
        r = fitz.Rect(*node["bbox"])
        if node["node_id"] in connected:
            color = (0.1, 0.6, 0.2) if node["kind"] != "off_page_connector" else (0.1, 0.3, 0.9)
        else:
            color = (0.5, 0.5, 0.5)
        shape.draw_rect(r)
        shape.finish(color=color, width=3.0)
        for port in node.get("ports", []):
            shape.draw_circle(fitz.Point(port["x"], port["y"]), 5)
            shape.finish(color=(0.9, 0.0, 0.0), fill=(0.9, 0.0, 0.0))
            if port.get("role"):
                shape.insert_text(fitz.Point(port["x"] + 6, port["y"] - 6), port["role"], fontsize=11,
                                  color=(0.9, 0.0, 0.0))
    shape.commit()
    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=dpi).save(str(out))
    return out
