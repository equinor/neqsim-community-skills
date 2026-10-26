"""Bundled catalog of every Sodir DataService layer and table (ids, names, fields, descriptions)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, List, Optional

CATEGORIES: Dict[int, str] = {
    1: "Administrative (blocks, quadrants, sub-areas, area status)",
    2: "Geology (structural elements, stratigraphy)",
    3: "Licences (production licences, APA/TFO, AFEX, business arrangement areas, petreg)",
    4: "Surveys (seismic/EM/shallow acquisition, seabed-mineral surveys)",
    5: "Wellbores (headers, formation tops, DST, cores, samples, logs, mud, documents)",
    6: "Facilities and pipelines (facility, pipeline, TUF)",
    7: "Hydrocarbons (fields, discoveries, reserves, profiles, owners, operators)",
    8: "Seabed minerals",
    9: "Carbon storage (CO2 injection)",
}


def category_of(layer_id: int) -> str:
    """Return the main-category text of a layer id (the thousands digit, ``XYZZ``)."""
    return CATEGORIES.get(int(layer_id) // 1000, "Unknown")


@lru_cache(maxsize=1)
def load_catalog() -> Dict[str, Any]:
    """Load the bundled catalog JSON (see ``refresh.py`` to regenerate it from the live service)."""
    with resources.files("sodir_open_data").joinpath("data/dataservice_catalog.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def items() -> List[Dict[str, Any]]:
    """Return every layer and table entry."""
    return list(load_catalog()["items"])


def resolve_id(layer: "str | int") -> int:
    """Resolve a DataService layer/table name or id to its numeric id."""
    if isinstance(layer, int):
        return layer
    text = str(layer).strip()
    if text.isdigit():
        return int(text)
    for item in items():
        if item["name"].lower() == text.lower():
            return int(item["id"])
    raise KeyError(f"unknown Sodir DataService layer or table {layer!r}; use search() to find it")


def get(layer: "str | int") -> Dict[str, Any]:
    """Return the catalog entry of a layer or table."""
    layer_id = resolve_id(layer)
    for item in items():
        if int(item["id"]) == layer_id:
            return item
    raise KeyError(f"layer id {layer_id} is not in the bundled catalog; run refresh to update it")


def search(text: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Rank entries by how many query words hit the name, description or field names."""
    words = [w for w in text.lower().replace("_", " ").split() if w]
    scored = []
    for item in items():
        name = item["name"].lower().replace("_", " ")
        desc = (item.get("description") or "").lower()
        fields = " ".join(f["name"].lower() for f in item.get("fields", []))
        score = sum(3 * (w in name) + 1 * (w in desc) + 1 * (w in fields) for w in words)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [dict(i, score=s) for s, i in scored[:limit]]


def field_names(layer: "str | int") -> List[str]:
    """Return the attribute names of a layer or table."""
    return [f["name"] for f in get(layer).get("fields", [])]


def describe(layer: "str | int", with_fields: bool = True) -> str:
    """Return a short text description of a layer or table, optionally listing attribute descriptions."""
    item = get(layer)
    kind = item["kind"] + (f"/{item['geometry']}" if item.get("geometry") else "")
    lines = [f"{item['id']} {item['name']} [{kind}] - {category_of(item['id'])}", (item.get("description") or "").strip()]
    if with_fields:
        for f in item.get("fields", []):
            tail = f" - {f['description']}" if f.get("description") else ""
            lines.append(f"  {f['name']} ({f.get('type', '')}){tail}")
    return "\n".join(lines)


def find_key_columns(layer: "str | int") -> Optional[List[str]]:
    """Return the ``*Npdid*`` join-key columns of a layer (Sodir's stable identifiers)."""
    keys = [n for n in field_names(layer) if "npdid" in n.lower()]
    return keys or None
