"""Stitch drawing records of several sheets into one network through matching off-page connectors.

A connector on sheet A that references sheet B is paired with the connector on sheet B that
references sheet A and has the opposite direction. Ties are broken by the line number and fluid code
of the attached pipe runs, then by the service words in the labels. Each pair is joined by a
``sheet_link`` edge without drawn geometry; sheets are laid out side by side in one coordinate frame.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .extract import SCHEMA_VERSION

_SERVICE_WORDS = ("GAS", "OIL", "WATER", "CONDENSATE", "DRAIN", "FLARE", "LIQUID", "STEAM", "AIR")


def stitch_records(sheets: list[dict[str, Any]], gap: float = 120.0) -> dict[str, Any]:
    """Combines per-sheet records into one ``neqsim_pid_drawing_records.v1`` with sheet links."""
    if not sheets:
        raise ValueError("No sheets to stitch")
    out: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "nodes": [], "edges": [], "instruments": [],
                           "warnings": [], "assumptions": [], "sheets": [], "links": [],
                           "reviewStatus": "REVIEW_REQUIRED",
                           "governance": "Draft topology stitched from several drawings; verify each sheet and every "
                                         "sheet link against the controlled revisions."}
    offset = 0.0
    height = 0.0
    numbers = []
    for k, rec in enumerate(sheets):
        prefix = "S%d-" % (k + 1)
        src = rec["source"]
        number = src.get("drawingNumber") or src.get("file", "sheet%d" % (k + 1))
        numbers.append(number)
        out["sheets"].append({"index": k + 1, "prefix": prefix, "drawingNumber": number, "file": src.get("file", ""),
                              "sha256": src.get("sha256", ""), "xOffset": offset,
                              "pageWidth": src.get("pageWidth", 0.0), "pageHeight": src.get("pageHeight", 0.0)})
        for node in rec["nodes"]:
            n = copy.deepcopy(node)
            n["node_id"] = prefix + n["node_id"]
            n["sheet"] = number
            n["bbox"] = [n["bbox"][0] + offset, n["bbox"][1], n["bbox"][2] + offset, n["bbox"][3]]
            for p in n.get("ports", []):
                p["port_id"] = prefix + p["port_id"]
                p["x"] = round(p["x"] + offset, 2)
            out["nodes"].append(n)
        for edge in rec["edges"]:
            e = copy.deepcopy(edge)
            e["edge_id"] = prefix + e["edge_id"]
            for key in ("from_node", "to_node", "from_port", "to_port"):
                if e.get(key):
                    e[key] = prefix + e[key]
            e["path"] = [[x + offset, y] for x, y in e["path"]]
            for item in e.get("inline_items", []):
                item["x"] = round(item["x"] + offset, 2)
            e["sheet"] = number
            out["edges"].append(e)
        for inst in rec.get("instruments", []):
            i = copy.deepcopy(inst)
            i["node_id"] = prefix + i["node_id"]
            i["x"] = round(i["x"] + offset, 2)
            out["instruments"].append(i)
        out["warnings"].extend("[%s] %s" % (number, w) for w in rec.get("warnings", []))
        for a in rec.get("assumptions", []):
            if a not in out["assumptions"]:
                out["assumptions"].append(a)
        offset += float(src.get("pageWidth", 0.0)) + gap
        height = max(height, float(src.get("pageHeight", 0.0)))
    out["source"] = {"file": " + ".join(s["file"] for s in out["sheets"]), "pageWidth": offset - gap,
                     "pageHeight": height, "units": "pt", "drawingNumber": " + ".join(numbers),
                     "raster": any(s["source"].get("raster") for s in sheets)}
    _link(out, set(numbers))
    out["counts"] = {"sheets": len(sheets), "nodes": len(out["nodes"]), "edges": len(out["edges"]),
                     "sheetLinks": sum(1 for lk in out["links"] if lk["kind"] == "process"),
                     "signalLinks": sum(1 for lk in out["links"] if lk["kind"] == "signal"),
                     "normalFlowEdges": sum(1 for e in out["edges"] if e["normal_flow"])}
    return out


def _link(out: dict[str, Any], numbers: set[str]) -> None:
    connectors = [n for n in out["nodes"] if n["kind"] == "off_page_connector"]
    edges_at: dict[str, list[dict[str, Any]]] = {}
    for e in out["edges"]:
        edges_at.setdefault(e["from_node"], []).append(e)
        edges_at.setdefault(e["to_node"], []).append(e)
    candidates = []
    for a in connectors:
        if a["direction"] != "out" or a["tag"] not in numbers or a["tag"] == a["sheet"]:
            continue
        for b in connectors:
            if b["direction"] != "in" or b["sheet"] != a["tag"] or b["tag"] != a["sheet"]:
                continue
            candidates.append((_score(a, b, edges_at), a["node_id"], b["node_id"]))
    used: set[str] = set()
    nodes = {n["node_id"]: n for n in connectors}
    for score, a_id, b_id in sorted(candidates, reverse=True):
        if a_id in used or b_id in used or score < 0:
            continue
        a, b = nodes[a_id], nodes[b_id]
        used.update((a_id, b_id))
        signal = "signal" in (a.get("service"), b.get("service"))
        link = {"from": a_id, "to": b_id, "kind": "signal" if signal else "process", "score": score,
                "fromLabel": a.get("label", ""), "toLabel": b.get("label", "")}
        out["links"].append(link)
        a.setdefault("attributes", {})["linkedTo"] = b_id
        b.setdefault("attributes", {})["linkedTo"] = a_id
        if signal:
            continue
        upstream = edges_at.get(a_id, [])
        downstream = edges_at.get(b_id, [])
        normal = any(e["normal_flow"] for e in upstream) and any(e["normal_flow"] for e in downstream)
        line = next((e["line_number"] for e in upstream + downstream if e.get("line_number")), "")
        fluid = next((e["fluid_code"] for e in upstream + downstream if e.get("fluid_code")), "")
        out["edges"].append({"edge_id": "L-%d" % len(out["links"]), "from_node": a_id, "from_port": "",
                             "to_node": b_id, "to_port": "", "line_number": line, "fluid_code": fluid,
                             "normal_flow": normal, "path": [], "length": 0.0, "inline_items": [], "gap_count": 0,
                             "confidence": round(min(a.get("confidence", 0.7), b.get("confidence", 0.7)), 3),
                             "kind": "sheet_link"})
    for n in connectors:
        if n["node_id"] not in used and n["tag"] in numbers and n["tag"] != n["sheet"]:
            out["warnings"].append("Connector %s on %s (%s) references a stitched sheet but has no matching "
                                   "connector there." % (n["tag"], n["sheet"], n.get("label") or "no label"))


def _score(a: dict[str, Any], b: dict[str, Any], edges_at: dict[str, list[dict[str, Any]]]) -> int:
    score = 0
    la = {e.get("line_number") for e in edges_at.get(a["node_id"], []) if e.get("line_number")}
    lb = {e.get("line_number") for e in edges_at.get(b["node_id"], []) if e.get("line_number")}
    fa = {e.get("fluid_code") for e in edges_at.get(a["node_id"], []) if e.get("fluid_code")}
    fb = {e.get("fluid_code") for e in edges_at.get(b["node_id"], []) if e.get("fluid_code")}
    if la & lb:
        score += 4
    if fa & fb:
        score += 2
    if fa and fb and not fa & fb:
        score -= 3
    wa = {w for w in _SERVICE_WORDS if re.search(r"\b%s" % w, a.get("label", "").upper())}
    wb = {w for w in _SERVICE_WORDS if re.search(r"\b%s" % w, b.get("label", "").upper())}
    score += len(wa & wb)
    if wa and wb and not wa & wb:
        score -= 2
    if a.get("service") == b.get("service"):
        score += 1
    return score
