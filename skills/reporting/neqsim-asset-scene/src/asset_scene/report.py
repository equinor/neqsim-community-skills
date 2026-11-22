"""Captions, coverage tables and ``results.json`` fragments for task reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .routing import describe_routing
from .schema import AssetScene
from .style import ColorBy

STATE_WORD = {
    "existing": "grey = existing",
    "proposed": "blue = proposed",
    "modified": "orange = modified",
    "removed": "translucent red = removed",
}


def scene_summary(scene: AssetScene) -> Dict[str, Any]:
    """Counts by state, kind, group and geometry quality."""
    return {
        "objects": len(scene.objects),
        "connections": len(scene.connections),
        "connections_with_route": sum(1 for c in scene.connections if c.get("route")),
        "by_state": dict(Counter(o["state"] for o in scene.objects)),
        "by_kind": dict(Counter(o["kind"] for o in scene.objects)),
        "by_group": dict(Counter(o["group"] for o in scene.objects)),
        "by_quality": dict(Counter(o["source"]["quality"] for o in scene.objects)),
        "with_results": sum(1 for o in scene.objects if o.get("results")),
        "with_live": sum(1 for o in scene.objects if o.get("live")),
        "with_media": sum(1 for o in scene.objects if o.get("media")),
    }


def scene_caption(
    scene: AssetScene,
    color_by: Optional[ColorBy] = None,
    view: str = "iso",
    vertical_exaggeration: float = 1.0,
    enlarged: bool = False,
    routing: Optional[Dict[str, int]] = None,
) -> str:
    """Provenance caption: what is shown, colour meaning, geometry sources, limits."""
    s = scene_summary(scene)
    q = s["by_quality"]
    parts = [f"Schematic 3D illustration of {scene.name} ({view} view, {s['objects']} objects)."]
    if color_by is not None:
        parts.append(f"Objects {color_by.describe()}.")
    else:
        present = [STATE_WORD[st] for st in STATE_WORD if s["by_state"].get(st)]
        if present:
            parts.append("Colours: " + ", ".join(present) + ".")
    parts.append(
        "Geometry: {v} verified from controlled sources, {d} derived from calculations, {a} assumed for illustration.".format(
            v=q.get("verified", 0), d=q.get("derived", 0), a=q.get("assumed", 0)
        )
    )
    if s["with_live"]:
        parts.append(f"{s['with_live']} objects carry live values (timestamps in the viewer).")
    if vertical_exaggeration != 1.0:
        parts.append(f"Vertical scale exaggerated x{vertical_exaggeration:g}.")
    if enlarged:
        parts.append("Small structures are drawn enlarged as symbols so they stay visible at field scale.")
    routing_text = describe_routing(routing or {})
    if routing_text:
        parts.append(routing_text)
    parts.append("Not for measurement.")
    return " ".join(parts)


def coverage_table(scene: AssetScene) -> Dict[str, Any]:
    """Per-object provenance table in the ``results.json`` table shape."""
    rows: List[List[Any]] = []
    for o in scene.objects:
        rows.append(
            [
                o.get("tag") or o["id"],
                o["kind"],
                o["state"],
                o["source"].get("quality"),
                o["source"].get("geometry"),
                "yes" if o.get("results") else "-",
                "yes" if o.get("live") else "-",
                len(o.get("media") or []),
            ]
        )
    return {
        "title": f"Objects shown in {scene.name} and the source of their geometry",
        "headers": ["Tag", "Kind", "State", "Geometry quality", "Geometry source", "NeqSim result", "Live value", "Pictures"],
        "rows": rows,
    }


def stale_live_values(scene: AssetScene, max_age_s: float, now: Optional[datetime] = None) -> List[str]:
    """Object ids with a live value older than ``max_age_s`` (ISO 8601 timestamps)."""
    now = now or datetime.now(timezone.utc)
    stale = []
    for o in scene.objects:
        for entry in o.get("live", {}).values():
            stamp = entry.get("timestamp") if isinstance(entry, dict) else None
            if not stamp:
                continue
            try:
                t = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            except ValueError:
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if (now - t).total_seconds() > max_age_s:
                stale.append(o["id"])
                break
    return stale


def results_fragment(scene: AssetScene, render_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge-ready keys for a task ``results.json`` (captions, table, assumptions, gaps)."""
    captions: Dict[str, str] = {}
    for png in (render_result or {}).get("png", []):
        captions[Path(png["path"]).name] = png["caption"]
    s = scene_summary(scene)
    gaps = list(scene.data_gaps)
    assumed = s["by_quality"].get("assumed", 0)
    auto_routed = sum(1 for c in scene.connections if not c.get("route"))
    if auto_routed:
        gaps.append(
            {
                "gap": f"{auto_routed} of {len(scene.connections)} connections in {scene.name} have no piping route",
                "source": "isometrics / 3D piping model / line survey",
                "status": "open",
                "assumed": "automatic pipe-rack or seabed route",
                "effect": "Pipe paths show how equipment connects, not where the pipes run",
            }
        )
    if assumed:
        gaps.append(
            {
                "gap": f"{assumed} of {s['objects']} objects in {scene.name} have assumed geometry",
                "source": "neqsim-asset-scene",
                "status": "open",
                "assumed": "placeholder size or illustrative placement",
                "effect": "Figure is schematic; positions and sizes of these objects are not evidence",
            }
        )
    assumptions = list(scene.assumptions) + [
        "3D figures are schematic illustrations built from the listed sources and are not for measurement."
    ]
    fragment: Dict[str, Any] = {
        "figure_captions": captions,
        "tables": [coverage_table(scene)],
        "assumptions": assumptions,
        "data_gaps": gaps,
    }
    if render_result:
        fragment["key_results"] = {
            "asset_scene_html": render_result.get("html"),
            "asset_scene_glb": render_result.get("glb"),
            "asset_scene_objects": s["objects"],
        }
    return fragment


def merge_into_results(results: Dict[str, Any], fragment: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a fragment into an existing ``results.json`` dict without dropping keys.

    A table whose title is already present replaces the old one, so re-packaging a scene updates its
    tables instead of duplicating them.
    """
    results.setdefault("figure_captions", {}).update(fragment.get("figure_captions", {}))
    tables = results.setdefault("tables", [])
    for table in fragment.get("tables", []):
        same = [i for i, t in enumerate(tables) if isinstance(t, dict) and t.get("title") == table.get("title")]
        if same:
            tables[same[0]] = table
        else:
            tables.append(table)
    for key in ("assumptions", "data_gaps"):
        existing = results.setdefault(key, [])
        for item in fragment.get(key, []):
            if item not in existing:
                existing.append(item)
    if fragment.get("key_results"):
        results.setdefault("key_results", {}).update(fragment["key_results"])
    return results
