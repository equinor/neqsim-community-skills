"""Nationwide overview of Brazilian oil and gas pipelines and their connection points.

Works on the ANP GeoANP layers cached by :func:`anp_open_data.wfs.fetch_layer`.
It builds a normalised pipeline register (one row per pipeline with origin,
destination, diameter, reported and geodesic length, operator and fluid), a
connection-point register (platforms, gas processing plants, terminals,
refineries, LNG terminals) and snaps pipeline ends to those points. Pipeline
ends that meet each other but no named installation are reported as junctions,
which is where subsea PLEMs and tie-in manifolds usually sit.

ANP publishes export, transfer and transport lines only. Infield flowlines,
risers and umbilicals are not in the open data, and snapping uses a distance
tolerance, so every connection is a screening result to confirm with the line
owner. Only the standard library is needed; ``plot_overview`` needs matplotlib.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .tools import haversine_km
from .wfs import repair_name

LAYER_CATEGORIES = {
    "gasodutos_de_escoamento": "gas_outflow",
    "gasodutos_de_transporte": "gas_transport",
    "oleodutos_de_escoamento": "oil_outflow",
    "oleodutos_de_transferencia": "oil_transfer",
    "oleodutos_de_transporte": "oil_transport",
    "unidade_de_producao": "platforms",
    "unidade_de_processamento_de_gas_natural": "gas_processing_plants",
    "terminais_gnl": "lng_terminals",
    "terminais_limite": "limit_terminals",
    "refinarias": "refineries",
    "campos_gishub_db": "fields",
    "basin_shp_geoanp": "basins",
}
"""Cached-file name fragment to category key."""

PIPELINE_CATEGORIES = ("gas_outflow", "gas_transport", "oil_outflow", "oil_transfer", "oil_transport")

PIPELINE_STYLE = {
    "gas_outflow": ("tab:red", "Gas outflow (escoamento)"),
    "gas_transport": ("darkorange", "Gas transport (transporte)"),
    "oil_outflow": ("tab:green", "Oil/product outflow (escoamento)"),
    "oil_transfer": ("tab:olive", "Oil/product transfer"),
    "oil_transport": ("tab:brown", "Oil/product transport"),
}

NODE_STYLE = {
    "platform": ("s", "tab:blue", "Production unit (UEP)"),
    "gas_processing_plant": ("^", "tab:purple", "Gas processing plant (UPGN)"),
    "limit_terminal": ("D", "black", "Terminal (limit)"),
    "refinery": ("P", "tab:gray", "Refinery"),
    "lng_terminal": ("v", "tab:cyan", "LNG terminal"),
    "junction": ("o", "white", "Pipeline junction (no named node)"),
}


def _first(props: Mapping[str, Any], keys: Sequence[str]) -> Any:
    """Return the first non-empty, non-dash value among ``keys`` (repaired)."""
    for k in keys:
        v = props.get(k)
        if v is None:
            continue
        if isinstance(v, str):
            v = repair_name(v)
            if v in ("", "-", "--", "N/A"):
                continue
        return v
    return None


def _num(value: Any) -> float | None:
    """Parse ANP numbers stored as strings (comma or dot decimals)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "")
    if not s or s in ("-", "--"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _lines(geometry: Mapping | None) -> list[list[tuple[float, float]]]:
    """Return LineString/MultiLineString coordinates as a list of (lon, lat) parts."""
    if not geometry:
        return []
    t = geometry.get("type")
    c = geometry.get("coordinates") or []
    if t == "LineString":
        parts = [c]
    elif t == "MultiLineString":
        parts = c
    else:
        return []
    return [[(float(p[0]), float(p[1])) for p in part] for part in parts if len(part) >= 2]


def _rings(geometry: Mapping | None) -> list[list[tuple[float, float]]]:
    """Return exterior rings of a Polygon/MultiPolygon as (lon, lat) lists."""
    if not geometry:
        return []
    t = geometry.get("type")
    c = geometry.get("coordinates") or []
    if t == "Polygon":
        polys = [c]
    elif t == "MultiPolygon":
        polys = c
    else:
        return []
    return [[(float(p[0]), float(p[1])) for p in poly[0]] for poly in polys if poly]


def _point(geometry: Mapping | None) -> tuple[float, float] | None:
    """Return a representative (lon, lat): the point, or the mean of polygon vertices."""
    if not geometry:
        return None
    if geometry.get("type") == "Point":
        c = geometry["coordinates"]
        return float(c[0]), float(c[1])
    rings = _rings(geometry)
    pts = [p for r in rings for p in r]
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def point_in_rings(lon: float, lat: float, rings: Iterable[Sequence[tuple[float, float]]]) -> bool:
    """Ray-casting point-in-polygon test over several exterior rings."""
    for ring in rings:
        inside = False
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-300) + xi:
                inside = not inside
            j = i
        if inside:
            return True
    return False


def load_cached_layers(cache_dir: str | Path) -> dict[str, list[dict]]:
    """Load cached ``anp_wfs_*.geojson`` files into ``{category: features}``.

    Args:
        cache_dir: Folder written by :func:`anp_open_data.wfs.fetch_layer`.

    Returns:
        Mapping from :data:`LAYER_CATEGORIES` values to feature lists. Unknown
        files are ignored; when several files map to one category the features
        are concatenated.
    """
    out: dict[str, list[dict]] = {}
    for f in sorted(Path(cache_dir).glob("anp_wfs_*.geojson")):
        cat = next((v for k, v in LAYER_CATEGORIES.items() if k in f.name), None)
        if cat is None:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        out.setdefault(cat, []).extend(data.get("features", []))
    return out


def polyline_length_km(parts: Sequence[Sequence[tuple[float, float]]]) -> float:
    """Geodesic (haversine) length of a multi-part polyline in km."""
    total = 0.0
    for part in parts:
        for a, b in zip(part[:-1], part[1:]):
            total += haversine_km(a[0], a[1], b[0], b[1])
    return total


def _endpoints(parts: Sequence[Sequence[tuple[float, float]]]) -> tuple:
    """Return the two outermost ends of a multi-part line (first start, last end)."""
    return parts[0][0], parts[-1][-1]


def pipeline_register(layers: Mapping[str, list[dict]]) -> list[dict]:
    """Normalise all ANP pipeline layers into one register.

    Args:
        layers: Output of :func:`load_cached_layers`.

    Returns:
        One dict per pipeline: ``category, name, origin, destination,
        diameter_in, length_km_reported, length_km_geodesic, operator, owner,
        fluid, status, capacity`` plus ``offshore_fraction`` (share of vertices
        inside maritime basin polygons, None when no basin layer) and private
        keys ``_parts`` / ``_ends`` used for plotting and snapping.
    """
    maritime = []
    for f in layers.get("basins", []):
        p = f.get("properties", {})
        sit = str(repair_name(p.get("SITUAÇÃO") or p.get("SITUACAO") or "")).lower()
        if sit.startswith("mar"):
            maritime.extend(_rings(f.get("geometry")))
    rows = []
    for cat in PIPELINE_CATEGORIES:
        for i, f in enumerate(layers.get(cat, [])):
            p = f.get("properties", {})
            parts = _lines(f.get("geometry"))
            if not parts:
                continue
            verts = [pt for part in parts for pt in part]
            off = None
            if maritime:
                step = max(1, len(verts) // 50)
                sample = verts[::step]
                off = round(sum(point_in_rings(x, y, maritime) for x, y in sample) / len(sample), 2)
            rows.append(
                {
                    "id": "%s_%03d" % (cat, i),
                    "category": cat,
                    "name": _first(p, ("NOME_DUTO", "DUTO", "NOME", "TRECHO", "DUTO_ID", "ID")),
                    "segment": _first(p, ("TRECHO",)),
                    "origin": _first(p, ("INST_ORIGEM", "INST_ORIG", "INST_ORIGE", "CONC_ORIG", "MUN_ORIG", "MUN_ORIGEM")),
                    "destination": _first(p, ("INST_DEST", "CONC_DEST", "MUN_DEST")),
                    "diameter_in": _num(_first(p, ("DIAM_POL",))),
                    "length_km_reported": _num(_first(p, ("EXTENS_KM", "EXTENSAOKM"))),
                    "length_km_geodesic": round(polyline_length_km(parts), 2),
                    "operator": _first(p, ("NOME_OPER", "OPERADOR")),
                    "owner": _first(p, ("PROPRIET",)),
                    "fluid": _first(p, ("FLUIDO", "TIPO_DUTO")),
                    "status": _first(p, ("ESTADO", "CLASSIFICA", "TIPO")),
                    "capacity": _first(p, ("CP_NOMINAL", "CAPAC_M3")),
                    "offshore_fraction": off,
                    "_parts": parts,
                    "_ends": _endpoints(parts),
                }
            )
    return rows


def node_register(layers: Mapping[str, list[dict]]) -> list[dict]:
    """Build the named connection points (installations and terminals).

    Args:
        layers: Output of :func:`load_cached_layers`.

    Returns:
        One dict per node: ``node_id, kind, name, lon, lat, water_depth_m,
        operator, capacity, detail``.
    """
    spec = (
        ("platforms", "platform", ("NOM_INSTALACAO", "NOM_FANTASIA", "SIG_INSTALACAO"), ("NOM_PROPRIETARIO",)),
        ("gas_processing_plants", "gas_processing_plant", ("NOME",), ("TITULARIDA",)),
        ("limit_terminals", "limit_terminal", ("TERMINAL_NOME", "NOME"), ("OPERADOR_NOME_REDUZIDO",)),
        ("refineries", "refinery", ("NOME", "SIGLA"), ()),
        ("lng_terminals", "lng_terminal", ("NOME",), ()),
    )
    nodes = []
    for cat, kind, name_keys, op_keys in spec:
        for i, f in enumerate(layers.get(cat, [])):
            pt = _point(f.get("geometry"))
            if pt is None:
                continue
            p = f.get("properties", {})
            if kind == "platform":
                cap = "oil %s m3/d; gas %s m3/d" % (
                    _first(p, ("QTD_PROCESSAMENTO_PETROLEO",)),
                    _first(p, ("QTD_PROCESSAMENTO_GAS",)),
                )
                detail = _first(p, ("DESC_TIPO_UEP",))
                fields = _first(p, ("DESC_ATENDIMENTOS",))
                if fields:
                    detail = "%s; serves %s" % (detail, fields)
            else:
                cap = _first(p, ("CAPACIDADE", "CAPAC_BPD"))
                detail = _first(p, ("TERMINAL_TIPO", "TIPO", "SITUACAO_A", "MUNICIPIO", "UF", "ESTADO"))
            nodes.append(
                {
                    "node_id": "%s_%03d" % (kind, i),
                    "kind": kind,
                    "name": _first(p, name_keys),
                    "lon": round(pt[0], 5),
                    "lat": round(pt[1], 5),
                    "water_depth_m": _num(_first(p, ("MED_DISTANCIA_LAMINA",))) if kind == "platform" else None,
                    "operator": _first(p, op_keys) if op_keys else None,
                    "capacity": cap,
                    "detail": detail,
                }
            )
    return nodes


def connect_pipelines(
    pipes: list[dict], nodes: list[dict], snap_km: float = 5.0, junction_km: float = 1.0
) -> dict[str, list[dict]]:
    """Snap pipeline ends to named nodes and cluster the remaining ends into junctions.

    Args:
        pipes: Output of :func:`pipeline_register` (updated in place with
            ``from_node``, ``to_node``, ``from_km``, ``to_km``).
        nodes: Output of :func:`node_register`.
        snap_km: Largest end-to-node distance accepted as a connection.
        junction_km: Ends of different pipelines within this distance that do not
            snap to a named node form one junction node.

    Returns:
        ``{"pipes": pipes, "nodes": nodes_plus_junctions}``. Each node gets
        ``n_pipelines`` and ``pipelines`` (pipeline names, ``;``-joined).
    """
    all_nodes = [dict(n) for n in nodes]
    loose: list[tuple[dict, str, tuple[float, float]]] = []
    for pipe in pipes:
        for side, end in zip(("from", "to"), pipe["_ends"]):
            best, dbest = None, None
            for n in all_nodes:
                d = haversine_km(end[0], end[1], n["lon"], n["lat"])
                if dbest is None or d < dbest:
                    best, dbest = n, d
            if best is not None and dbest <= snap_km:
                pipe[side + "_node"] = best["node_id"]
                pipe[side + "_km"] = round(dbest, 2)
            else:
                pipe[side + "_node"] = None
                pipe[side + "_km"] = None
                loose.append((pipe, side, end))
    clusters: list[dict] = []
    for pipe, side, end in loose:
        hit = None
        for c in clusters:
            if haversine_km(end[0], end[1], c["lon"], c["lat"]) <= junction_km:
                hit = c
                break
        if hit is None:
            hit = {"members": [], "lon": end[0], "lat": end[1]}
            clusters.append(hit)
        hit["members"].append((pipe, side))
    k = 0
    for c in clusters:
        names = {m[0]["id"] for m in c["members"]}
        if len(names) < 2:
            continue
        nid = "junction_%03d" % k
        k += 1
        label = sorted({str(m[0]["name"]) for m in c["members"]})
        all_nodes.append(
            {
                "node_id": nid,
                "kind": "junction",
                "name": "Junction of " + " / ".join(label[:3]),
                "lon": round(c["lon"], 5),
                "lat": round(c["lat"], 5),
                "water_depth_m": None,
                "operator": None,
                "capacity": None,
                "detail": "pipeline ends meet with no named installation (PLEM/tee likely)",
            }
        )
        for pipe, side in c["members"]:
            pipe[side + "_node"] = nid
            pipe[side + "_km"] = 0.0
    by_id = {n["node_id"]: n for n in all_nodes}
    for n in all_nodes:
        n["n_pipelines"] = 0
        n["pipelines"] = []
    for pipe in pipes:
        for side in ("from", "to"):
            nid = pipe.get(side + "_node")
            if nid in by_id and pipe["name"] not in by_id[nid]["pipelines"]:
                by_id[nid]["n_pipelines"] += 1
                by_id[nid]["pipelines"].append(str(pipe["name"]))
    for n in all_nodes:
        n["pipelines"] = "; ".join(n["pipelines"])
    return {"pipes": pipes, "nodes": all_nodes}


def summarise(pipes: list[dict], conns: Mapping[str, list[dict]]) -> dict:
    """Summary statistics for a report: counts, lengths and best-connected nodes."""
    by_cat: dict[str, dict] = {}
    for p in pipes:
        c = by_cat.setdefault(p["category"], {"count": 0, "length_km": 0.0})
        c["count"] += 1
        c["length_km"] = round(c["length_km"] + p["length_km_geodesic"], 1)
    offshore = [p for p in pipes if (p.get("offshore_fraction") or 0) >= 0.5]
    nodes = conns["nodes"]
    unnamed = sum(1 for p in pipes for s in ("from", "to") if p.get(s + "_node") is None)
    top = sorted(nodes, key=lambda n: -n["n_pipelines"])[:15]
    return {
        "pipeline_count": len(pipes),
        "by_category": by_cat,
        "offshore_pipelines": {
            "count": len(offshore),
            "length_km": round(sum(p["length_km_geodesic"] for p in offshore), 1),
        },
        "node_count": {k: sum(1 for n in nodes if n["kind"] == k) for k in NODE_STYLE},
        "connected_nodes": sum(1 for n in nodes if n["n_pipelines"] > 0),
        "unnamed_endpoints": unnamed,
        "top_connected_nodes": [
            {"name": n["name"], "kind": n["kind"], "n_pipelines": n["n_pipelines"]} for n in top
        ],
    }


def write_csv(path: str | Path, rows: list[dict]) -> Path:
    """Write rows to CSV (UTF-8 with BOM for Excel), skipping private ``_`` keys."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for r in rows:
        for k in r:
            if not k.startswith("_") and k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})
    return path


def plot_overview(
    ax: Any,
    layers: Mapping[str, list[dict]],
    pipes: list[dict],
    conns: Mapping[str, list[dict]],
    bbox: Sequence[float] | None = None,
    label_nodes: bool = False,
    min_label_pipelines: int = 2,
) -> Any:
    """Draw basins, fields, pipelines by category and connection points on ``ax``.

    Args:
        ax: Matplotlib axes.
        layers: Output of :func:`load_cached_layers`.
        pipes: Output of :func:`pipeline_register`.
        conns: Output of :func:`connect_pipelines`.
        bbox: Optional ``(min_lon, max_lon, min_lat, max_lat)`` view.
        label_nodes: Label named nodes with at least ``min_label_pipelines`` lines.
        min_label_pipelines: Threshold for labels.

    Returns:
        The axes.
    """

    def inside(lon: float, lat: float) -> bool:
        return bbox is None or (bbox[0] <= lon <= bbox[1] and bbox[2] <= lat <= bbox[3])

    for f in layers.get("basins", []):
        sit = str(repair_name(f["properties"].get("SITUAÇÃO") or "")).lower()
        for r in _rings(f.get("geometry")):
            ax.fill(*zip(*r), color="#e3f0fb" if sit.startswith("mar") else "#f3efe6", lw=0.3, ec="#9bb", zorder=0)
    first_field = True
    for f in layers.get("fields", []):
        for r in _rings(f.get("geometry")):
            ax.fill(*zip(*r), color="#c9e7c0", ec="#5a8f4e", lw=0.3, zorder=1,
                    label="Fields (ANP)" if first_field else None)
            first_field = False
    seen = set()
    for p in pipes:
        col, lab = PIPELINE_STYLE[p["category"]]
        for part in p["_parts"]:
            ax.plot(*zip(*part), color=col, lw=1.1, zorder=3, label=None if p["category"] in seen else lab)
            seen.add(p["category"])
    seen_k = set()
    for n in conns["nodes"]:
        if not inside(n["lon"], n["lat"]):
            continue
        mk, col, lab = NODE_STYLE[n["kind"]]
        ax.plot(n["lon"], n["lat"], marker=mk, color=col, mec="k", mew=0.5,
                ms=5 if n["kind"] != "junction" else 4, ls="none", zorder=5,
                label=None if n["kind"] in seen_k else lab)
        seen_k.add(n["kind"])
        if label_nodes and n["kind"] != "junction" and n["n_pipelines"] >= min_label_pipelines:
            ax.annotate(str(n["name"])[:28], (n["lon"], n["lat"]), fontsize=5.5, xytext=(3, 3),
                        textcoords="offset points", zorder=6)
    if bbox is not None:
        ax.set_xlim(bbox[0], bbox[1])
        ax.set_ylim(bbox[2], bbox[3])
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude (deg, SIRGAS 2000)")
    ax.set_ylabel("Latitude (deg)")
    ax.grid(alpha=0.3)
    return ax
