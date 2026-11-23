"""Engineering review of extracted drawing records.

``review_items`` lists everything a reviewer must confirm (assumed flow directions, untraced
connectors, normally closed items, low-confidence runs and items, raster/OCR provenance).
``apply_corrections`` applies a reviewer's corrections file as traceable operations and records who
reviewed, when, and whether the topology is approved. Records only reach ``reviewStatus = APPROVED``
through a named reviewer with ``approved: true``; the extractor itself never approves.

Corrections file (JSON)::

    {"reviewer": "A. Engineer", "date": "2026-11-24", "approved": true,
     "corrections": [
       {"op": "reverse", "edge": "E-12", "reason": "flow is towards the vessel"},
       {"op": "set_normal_flow", "edge": "E-30", "value": false},
       {"op": "set_valve", "edge": "E-9", "index": 0, "normal_position": "open", "tag": "XV-0631"},
       {"op": "set_role", "node": "EQ-1", "port": "EQ-1-P6", "role": "GasOutlet"},
       {"op": "set_connector", "node": "OPC-7", "direction": "in", "service": "utility"},
       {"op": "set_tag", "node": "EQ-1", "tag": "20VA001"},
       {"op": "remove_edge", "edge": "E-44"},
       {"op": "add_edge", "from_node": "OPC-3", "to_node": "EQ-1", "to_port": "EQ-1-P1",
        "normal_flow": true, "line_number": "20L00001-0600PG"}]}
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

LOW_CONFIDENCE = 0.6
_OPS = {"reverse", "set_normal_flow", "set_valve", "set_role", "set_connector", "set_tag", "remove_edge", "add_edge"}


def review_items(records: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns the review checklist, most important first."""
    items: list[dict[str, Any]] = []
    nodes = {n["node_id"]: n for n in records["nodes"]}
    linked = {e["from_node"] for e in records["edges"]} | {e["to_node"] for e in records["edges"]}

    def add(severity: str, kind: str, ref: str, message: str, where: Any = None) -> None:
        items.append({"id": "R-%d" % (len(items) + 1), "severity": severity, "kind": kind, "ref": ref,
                      "message": message, "location": where})

    if records.get("source", {}).get("raster"):
        add("high", "raster", "sheet", "Sheet read from an image: check every tag (OCR) and every run; diagonal "
                                       "symbols were not recovered.")
    for e in records["edges"]:
        name = "%s -> %s" % (_name(nodes, e["from_node"]), _name(nodes, e["to_node"]))
        where = e["path"][len(e["path"]) // 2] if e.get("path") else None
        if e.get("direction_source") == "assumed":
            add("high" if e["normal_flow"] else "medium", "direction", e["edge_id"],
                "Flow direction of %s was assumed (outward from equipment); confirm or reverse." % name, where)
        for k, item in enumerate(e.get("inline_items", [])):
            if item.get("normal_position") == "closed":
                add("high" if item.get("blocks_process_run") else "low", "closed_item", "%s#%d" % (e["edge_id"], k),
                    "%s %s on %s read as normally closed (%s); this run is excluded from the flowsheet."
                    % (item["kind"], item.get("tag") or "", name, item.get("position_source", "")),
                    [item["x"], item["y"]])
            elif item.get("confidence", 1.0) < LOW_CONFIDENCE:
                add("low", "item", "%s#%d" % (e["edge_id"], k), "Low-confidence %s on %s; confirm the symbol."
                    % (item["kind"], name), [item["x"], item["y"]])
        if e.get("confidence", 1.0) < LOW_CONFIDENCE and e["normal_flow"]:
            add("medium", "run", e["edge_id"], "Low-confidence normal-flow run %s (%d gaps bridged)."
                % (name, e.get("gap_count", 0)), where)
        if e.get("kind") == "sheet_link":
            add("medium", "sheet_link", e["edge_id"], "Sheet link %s: confirm the continuation." % name)
    for n in records["nodes"]:
        if n["kind"] == "off_page_connector" and n["node_id"] not in linked and n.get("service") != "signal":
            add("medium", "untraced", n["node_id"], "Connector %s (%s) is not traced to the network."
                % (n["tag"], n.get("label") or "no label"), n["bbox"][:2])
        if n["kind"] not in ("off_page_connector", "tee"):
            outlets = [p for p in n.get("ports", []) if p.get("normal_flow") and not p.get("role")]
            for p in outlets:
                add("high", "role", p["port_id"], "Nozzle %s of %s carries flow but has no process role."
                    % (p.get("label") or p["port_id"], n["tag"]), [p["x"], p["y"]])
    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda i: order[i["severity"]])
    for k, item in enumerate(items):
        item["id"] = "R-%d" % (k + 1)
    return items


def write_review_sheet(records: dict[str, Any], path: str | Path) -> Path:
    """Writes the review checklist as Markdown for a reviewer."""
    items = review_items(records)
    lines = ["# P&ID extraction review: %s" % records.get("source", {}).get("drawingNumber", ""), "",
             "Status: **%s**. Confirm each item against the controlled revision, then record corrections in a "
             "corrections file (see `review.py`)." % records.get("reviewStatus", "REVIEW_REQUIRED"), "",
             "| ID | Severity | Kind | Ref | Item |", "| --- | --- | --- | --- | --- |"]
    for i in items:
        lines.append("| %s | %s | %s | %s | %s |" % (i["id"], i["severity"], i["kind"], i["ref"],
                                                      i["message"].replace("|", "/")))
    if records.get("assumptions"):
        lines += ["", "## Extraction assumptions", ""] + ["- " + a for a in records["assumptions"]]
    p = Path(path)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def apply_corrections(records: dict[str, Any], corrections: dict[str, Any] | str | Path) -> dict[str, Any]:
    """Applies a reviewer's corrections; returns new records with the review recorded."""
    if not isinstance(corrections, dict):
        corrections = json.loads(Path(corrections).read_text(encoding="utf-8"))
    reviewer = str(corrections.get("reviewer", "")).strip()
    if not reviewer:
        raise ValueError("Corrections need a named reviewer")
    out = copy.deepcopy(records)
    nodes = {n["node_id"]: n for n in out["nodes"]}
    edges = {e["edge_id"]: e for e in out["edges"]}
    log = []
    for k, op in enumerate(corrections.get("corrections", [])):
        kind = op.get("op")
        if kind not in _OPS:
            raise ValueError("Correction %d: unknown op %r" % (k, kind))
        if kind in ("reverse", "set_normal_flow", "set_valve", "remove_edge") and op.get("edge") not in edges:
            raise ValueError("Correction %d: unknown edge %r" % (k, op.get("edge")))
        if kind in ("set_role", "set_connector", "set_tag") and op.get("node") not in nodes:
            raise ValueError("Correction %d: unknown node %r" % (k, op.get("node")))
        if kind == "reverse":
            e = edges[op["edge"]]
            e["from_node"], e["to_node"] = e["to_node"], e["from_node"]
            e["from_port"], e["to_port"] = e.get("to_port", ""), e.get("from_port", "")
            e["path"] = list(reversed(e["path"]))
            e["inline_items"] = list(reversed(e.get("inline_items", [])))
            e["direction_source"] = "reviewer"
        elif kind == "set_normal_flow":
            edges[op["edge"]]["normal_flow"] = bool(op["value"])
        elif kind == "set_valve":
            items = edges[op["edge"]].get("inline_items", [])
            idx = int(op.get("index", 0))
            if not 0 <= idx < len(items):
                raise ValueError("Correction %d: edge %s has no inline item %d" % (k, op["edge"], idx))
            item = items[idx]
            for key in ("normal_position", "tag", "component_class", "kind", "locking"):
                if key in op:
                    item[key] = op[key]
            item["position_source"] = "reviewer"
            item["confidence"] = 1.0
        elif kind == "set_role":
            port = next((p for p in nodes[op["node"]].get("ports", []) if p["port_id"] == op.get("port")), None)
            if port is None:
                raise ValueError("Correction %d: unknown port %r" % (k, op.get("port")))
            port["role"] = op["role"]
        elif kind == "set_connector":
            for key in ("direction", "service", "label"):
                if key in op:
                    nodes[op["node"]][key] = op[key]
            if "direction" in op:
                nodes[op["node"]]["component_class"] = ("FlowInPipeOffPageConnector" if op["direction"] == "in"
                                                        else "FlowOutPipeOffPageConnector")
        elif kind == "set_tag":
            nodes[op["node"]]["tag"] = op["tag"]
        elif kind == "remove_edge":
            out["edges"] = [e for e in out["edges"] if e["edge_id"] != op["edge"]]
            edges.pop(op["edge"])
        elif kind == "add_edge":
            for key in ("from_node", "to_node"):
                if op.get(key) not in nodes:
                    raise ValueError("Correction %d: unknown node %r" % (k, op.get(key)))
            edge = {"edge_id": op.get("edge_id") or "RV-%d" % (k + 1), "from_node": op["from_node"],
                    "from_port": op.get("from_port", ""), "to_node": op["to_node"], "to_port": op.get("to_port", ""),
                    "line_number": op.get("line_number", ""), "fluid_code": op.get("fluid_code", ""),
                    "normal_flow": bool(op.get("normal_flow", True)), "path": op.get("path", []),
                    "length": 0.0, "inline_items": op.get("inline_items", []), "gap_count": 0, "confidence": 1.0,
                    "kind": "process", "direction_source": "reviewer"}
            out["edges"].append(edge)
            edges[edge["edge_id"]] = edge
        log.append({"op": kind, "ref": op.get("edge") or op.get("node") or op.get("edge_id", ""),
                    "reason": op.get("reason", "")})
    approved = bool(corrections.get("approved"))
    digest = hashlib.sha256(json.dumps(corrections, sort_keys=True).encode("utf-8")).hexdigest()
    out["review"] = {"reviewer": reviewer, "date": str(corrections.get("date") or date.today().isoformat()),
                     "approved": approved, "correctionCount": len(log), "corrections": log,
                     "correctionsSha256": digest}
    out["reviewStatus"] = "APPROVED" if approved else "REVIEW_IN_PROGRESS"
    out["openReviewItems"] = len([i for i in review_items(out) if i["severity"] == "high"])
    return out


def process_connections(records: dict[str, Any]) -> set[tuple[str, str, str]]:
    """(connector reference, equipment tag, nozzle role) reachable along normal-flow runs through tees/links."""
    nodes = {n["node_id"]: n for n in records["nodes"]}
    ports = {p["port_id"]: p for n in records["nodes"] for p in n.get("ports", [])}
    adj: dict[str, list[tuple[str, str]]] = {}
    for e in records["edges"]:
        if not e["normal_flow"]:
            continue
        for a, b, port in ((e["from_node"], e["to_node"], e.get("to_port", "")),
                           (e["to_node"], e["from_node"], e.get("from_port", ""))):
            adj.setdefault(a, []).append((b, port))
    out = set()
    for n in records["nodes"]:
        if n["kind"] != "off_page_connector" or n.get("service") != "process":
            continue
        seen, stack = {n["node_id"]}, [n["node_id"]]
        while stack:
            cur = stack.pop()
            for nxt, port in adj.get(cur, []):
                kind = nodes[nxt]["kind"]
                if kind == "tee" or (kind == "off_page_connector" and nodes[nxt].get("attributes", {}).get("linkedTo")):
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
                elif kind != "off_page_connector":
                    out.add((n["tag"], nodes[nxt]["tag"], ports.get(port, {}).get("role", "")))
    return out


def compare_records(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compares process connections of two extractions (e.g. raster vs vector, or two revisions)."""
    ref, cand = process_connections(reference), process_connections(candidate)
    found = ref & cand
    return {"reference": sorted(map(list, ref)), "candidate": sorted(map(list, cand)),
            "matched": sorted(map(list, found)), "missing": sorted(map(list, ref - cand)),
            "extra": sorted(map(list, cand - ref)),
            "recall": round(len(found) / len(ref), 3) if ref else None,
            "precision": round(len(found) / len(cand), 3) if cand else None}


def _name(nodes: dict[str, Any], node_id: str) -> str:
    n = nodes.get(node_id, {})
    return (n.get("label") or n.get("tag") or node_id)[:40]
