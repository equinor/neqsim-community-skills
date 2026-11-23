"""Synthetic example: build a HAZOP node pack from a small P&ID layout.

The example draws a blank sheet with Pillow, writes a ``neqsim.pfd_layout.v1`` layout
beside it, selects one node by tag, and writes the node tables and the marked-up PNG.
Run it with ``python hazop_node_pack_example.py [output-folder]``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from hazop_node_pack import (
    build_node_pack,
    sheet_from_layout,
)
from PIL import Image, ImageDraw

SHEET = "SYN-PID-001"
IMAGE_SIZE = (1600, 1200)


def _node(key: str, kind: str, x: float, y: float, tag: str | None, w=40, h=40) -> dict:
    return {"id": key, "kind": kind, "tag": tag, "bbox": [x, y, w, h]}


def write_synthetic_drawing(folder: Path) -> tuple[Path, Path]:
    """Write a small layout JSON and a blank PNG of the same sheet; return both paths."""
    nodes = [
        _node("B-IN", "boundary", 20, 280, None, 60, 40),
        _node("EV1", "esdv", 120, 280, "EV-9101*"),
        _node("J1", "junction", 200, 295, None, 10, 10),
        _node("PT1", "instrument", 190, 200, "PT-9101"),
        _node("RCV", "pig_receiver", 320, 270, "PR-9101", 80, 60),
        _node("PSV1", "psv", 340, 160, "PSV-9101"),
        _node("B-OUT", "boundary", 600, 280, None, 60, 40),
    ]
    edges = [
        {"id": "L1", "from": "B-IN", "to": "EV1", "points": [[80, 300], [120, 300]]},
        {"id": "L2", "from": "EV1", "to": "J1", "points": [[160, 300], [200, 300]]},
        {"id": "L3", "from": "J1", "to": "RCV", "points": [[210, 300], [320, 300]]},
        {"id": "L4", "from": "J1", "to": "PT1", "points": [[205, 295], [205, 240]]},
        {"id": "L5", "from": "RCV", "to": "PSV1", "points": [[360, 270], [360, 200]]},
        {"id": "L6", "from": "RCV", "to": "B-OUT", "points": [[400, 300], [600, 300]]},
    ]
    layout = {
        "schema": "neqsim.pfd_layout.v1",
        "name": SHEET,
        "canvas": {"width": 800, "height": 600, "unit": "px"},
        "nodes": nodes,
        "edges": edges,
    }
    layout_path = folder / f"{SHEET}.layout.json"
    layout_path.write_text(json.dumps(layout), encoding="utf-8")
    image = Image.new("RGB", IMAGE_SIZE, "white")
    ImageDraw.Draw(image).line([(40, 600), (1500, 600)], fill=(0, 0, 0), width=4)
    png_path = folder / f"{SHEET}.png"
    image.save(png_path)
    return layout_path, png_path


def build_example(work_dir: Path) -> dict:
    """Build the node pack for one node of the synthetic sheet and return the pack."""
    layout_path, png_path = write_synthetic_drawing(work_dir)
    sheet = sheet_from_layout(layout_path, IMAGE_SIZE, image_path=png_path)
    node = {
        "node_id": "N1",
        "name": "Receiver inlet",
        "design_intent": "Receive pigs and gas from the riser at the platform boundary",
        "boundary": "From the inlet boundary to the receiver, incl. relief valve",
        "modes": [
            {
                "mode": "normal",
                "p_op_bara": 80,
                "t_op_c": 40,
                "p_design_bara": 120,
                "t_design_c": 90,
                "source": "synthetic design basis",
                "status": "",
            }
        ],
        "drawings": [
            {"sheet": SHEET, "tags": ["GR-EV-9101"], "tag_globs": ["GR-P*-9101"]}
        ],
    }
    return build_node_pack(
        [node],
        {SHEET: sheet},
        valve_rows=[
            {"sheet": SHEET, "tag": "GR-EV-9101", "type": "esdv"},
            {"sheet": SHEET, "tag": "GR-PT-9101", "type": "instrument"},
            {"sheet": SHEET, "tag": "GR-PSV-9101", "type": "psv"},
        ],
        out_dir=work_dir / "pack",
        project_name="Synthetic HAZOP node pack",
    )


def main() -> None:
    """Build the example in the given folder (default: a temporary folder) and print it."""
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="hazop_node_pack_"))
    pack = build_example(work_dir)
    summary = {
        "readiness": pack["readiness_label"],
        "missing_evidence": pack["missing_evidence"],
        "markup": pack["nodes"][0]["drawings"][0]["markup"],
        "seeds": [
            f"{s['guideWord']} {s['parameter']}"
            for s in pack["nodes"][0]["seed_deviations"]
        ],
    }
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
