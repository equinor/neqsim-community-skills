"""Rebuild the bundled catalog from the live DataService (run when Sodir adds layers or fields).

    python -m sodir_open_data.refresh [output.json]
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .client import Fetch, default_fetch
from .downloads import DATASERVICE_DATA, DATASERVICE_METADATA

_MAX_DESC = 400


def _get(fetch: Fetch, url: str) -> Dict[str, Any]:
    return json.loads(fetch(url, 120.0).decode("utf-8"))


def _metadata(fetch: Fetch, table_id: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        params = {"where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json",
                  "resultOffset": offset, "resultRecordCount": 2000}
        payload = _get(fetch, f"{DATASERVICE_METADATA}/{table_id}/query?" + urllib.parse.urlencode(params))
        feats = payload.get("features", [])
        rows.extend(f["attributes"] for f in feats)
        if not feats or not payload.get("exceededTransferLimit"):
            return rows
        offset += len(feats)


def build_catalog(fetch: Fetch = default_fetch) -> Dict[str, Any]:
    """Return the catalog dict (layers, tables, fields, descriptions) read from the live service."""
    root = _get(fetch, DATASERVICE_DATA + "?f=json")
    table_desc = {str(r["id"]): r.get("Description") for r in _metadata(fetch, 10)}
    attr_desc: Dict[str, Dict[str, str]] = {}
    for r in _metadata(fetch, 11):
        attr_desc.setdefault(str(r["id"]), {})[r["Tag"]] = r.get("Description") or r.get("DisplayText") or ""
    entries: List[Dict[str, Any]] = []
    for kind, listing in (("layer", root.get("layers", [])), ("table", root.get("tables", []))):
        for ref in listing:
            lid = int(ref["id"])
            detail = _get(fetch, f"{DATASERVICE_DATA}/{lid}?f=json")
            descs = attr_desc.get(str(lid), {})
            entries.append({
                "id": lid,
                "name": ref["name"],
                "kind": kind,
                "geometry": (detail.get("geometryType") or "").replace("esriGeometry", "") or None,
                "description": (table_desc.get(str(lid)) or detail.get("description") or "")[:_MAX_DESC],
                "fields": [{"name": f["name"], "type": f.get("type", "").replace("esriFieldType", ""),
                            "description": (descs.get(f["name"]) or "")[:200]}
                           for f in detail.get("fields", []) if f["name"] != "OBJECTID" and not f["name"].startswith("SHAPE")],
            })
    entries.sort(key=lambda e: e["id"])
    return {
        "source": DATASERVICE_DATA,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id_scheme": "XYZZ: X main category (1 admin, 2 geology, 3 licences, 4 surveys, 5 wellbore, 6 facilities, "
                     "7 hydrocarbons, 8 seabed minerals, 9 carbon storage), Y sub category, ZZ layer (00 = mother table)",
        "geometry_crs": "EPSG:4230 (ED50) unless outSR is requested",
        "items": entries,
    }


def main(argv: List[str]) -> int:
    """Write the refreshed catalog to the bundled data file or to ``argv[0]``."""
    target = Path(argv[0]) if argv else Path(__file__).parent / "data" / "dataservice_catalog.json"
    data = build_catalog()
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(data['items'])} entries to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
