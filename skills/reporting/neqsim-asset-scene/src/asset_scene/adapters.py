"""Public adapters that build scene objects from NeqSim and community outputs.

None of these read company systems. Enterprise adapters (STID, Echo, live
historian data, company maps and well databases) live in a separate private
skill and call these functions with the data they fetched.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from typing import Any

from .schema import (
    PIPING_KEYS,
    AssetScene,
    box,
    box_from_bounds,
    cylinder,
    geometry_bounds,
    normalise_tag,
    point,
    polyline,
)

# NeqSim class names and layout kinds mapped to scene kinds; None = not physical.
KIND_ALIASES: dict[str, str | None] = {
    "separator": "vessel",
    "threephaseseparator": "vessel",
    "gasscrubber": "vessel",
    "gasscrubbersimple": "vessel",
    "tank": "vessel",
    "vessel": "vessel",
    "scrubber": "vessel",
    "distillationcolumn": "column",
    "simpleabsorber": "column",
    "simpleteg absorber": "column",
    "column": "column",
    "absorber": "column",
    "compressor": "compressor",
    "expander": "compressor",
    "turboexpandercompressor": "compressor",
    "pump": "pump",
    "esppump": "pump",
    "heater": "heat_exchanger",
    "cooler": "heat_exchanger",
    "heatexchanger": "heat_exchanger",
    "multistreamheatexchanger": "heat_exchanger",
    "aircooler": "heat_exchanger",
    "throttlingvalve": "valve",
    "valve": "valve",
    "controlvalve": "valve",
    "safetyvalve": "valve",
    "pipebeggsandbrills": "line",
    "adiabaticpipe": "line",
    "adiabatictwophasepipe": "line",
    "pipeline": "pipeline",
    "equipment": "equipment",
    "stream": None,
    "mixer": None,
    "splitter": None,
    "recycle": None,
    "adjuster": None,
    "setpoint": None,
    "calculator": None,
    "streamsaturatorutil": None,
}

# Placeholder sizes used only when no design data exists (recorded as assumed).
DEFAULT_SIZES: dict[str, dict[str, Any]] = {
    "vessel": {"diameter": 2.0, "length": 6.0, "orientation": "horizontal"},
    "column": {"diameter": 2.5, "length": 20.0, "orientation": "vertical"},
    "compressor": {"size": [6.0, 4.0, 4.0]},
    "pump": {"size": [2.0, 1.0, 1.2]},
    "heat_exchanger": {"diameter": 1.0, "length": 6.0, "orientation": "horizontal"},
    "valve": {"size": [0.8, 0.6, 0.8]},
    "line": {"size": [3.0, 0.4, 0.4]},
    "pipeline": {"size": [3.0, 0.4, 0.4]},
    "equipment": {"size": [2.0, 2.0, 2.0]},
}

QUALITY_ORDER = {"verified": 0, "derived": 1, "assumed": 2}


def worst_quality(*qualities: str) -> str:
    """Least reliable of several source qualities."""
    return max(qualities, key=lambda q: QUALITY_ORDER.get(q, 2))


def kind_for(name: Any) -> str | None:
    """Scene kind for a NeqSim class name or layout kind (None when not physical)."""
    key = str(name or "").replace("_", "").replace(" ", "").lower()
    if key in KIND_ALIASES:
        return KIND_ALIASES[key]
    for alias, kind in KIND_ALIASES.items():
        if alias and alias.replace(" ", "") in key:
            return kind
    return "equipment"


def _num(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) and val > 0 else None


# ------------------------------------------------------------ plant layout
def from_layout_items(
    items: Iterable[dict[str, Any]],
    scene: AssetScene | None = None,
    state: str = "proposed",
    reference: str = "neqsim layout-study",
) -> AssetScene:
    """Objects from plant-layout study items (``bounds_m`` = xmin, ymin, zmin, xmax, ymax, zmax).

    Accepts the item shape of the layout-study CAD export: ``name``, ``tag``,
    ``kind`` (equipment, deck, obstacle), ``equipment_kind``, ``deck``,
    ``bounds_m`` and ``dimension_source``.
    """
    scene = scene or AssetScene("Plant layout")
    for item in items:
        layout_kind = item.get("kind", "equipment")
        if layout_kind == "deck":
            kind, group = "deck", "structure"
        elif layout_kind == "obstacle":
            kind, group = "obstacle", "structure"
        else:
            kind, group = (
                kind_for(item.get("equipment_kind") or "equipment") or "equipment",
                "facility",
            )
        dim_source = str(item.get("dimension_source") or "layout envelope")
        quality = (
            "derived"
            if "neqsim" in dim_source.lower() or "datasheet" in dim_source.lower()
            else "assumed"
        )
        scene.add_object(
            id=str(item.get("tag") or item["name"]),
            kind=kind,
            tag=item.get("tag"),
            name=item.get("name"),
            state=item.get("state", state),
            group=group,
            geometry=box_from_bounds(item["bounds_m"]),
            source={"geometry": dim_source, "quality": quality, "reference": reference},
            attributes={"deck": item.get("deck")} if item.get("deck") else {},
        )
    return scene


# ---------------------------------------------------------- NeqSim process
def _collapse(
    edges: Sequence[tuple[str, ...]], keep: set
) -> list[tuple[str, str, str, str | None]]:
    """Bridge edges through non-physical nodes (streams, mixers, recycles).

    Edges are ``(source, target, kind[, port])``; the port of the first edge
    out of the source equipment is kept (it names the outlet nozzle).
    """
    out_map: dict[str, list[tuple[str, str, str | None]]] = {}
    for e in edges:
        s, t, k = e[0], e[1], e[2]
        out_map.setdefault(s, []).append((t, k, e[3] if len(e) > 3 else None))
    result: dict[tuple[str, str], tuple[str, str | None]] = {}
    for start in keep:
        stack = [(t, k, p) for t, k, p in out_map.get(start, [])]
        seen = set()
        while stack:
            node, kind, port = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            if node in keep:
                if node != start:
                    result.setdefault((start, node), (kind, port))
                continue
            stack.extend((t, k, port) for t, k, _ in out_map.get(node, []))
    return sorted((s, t, k, p) for (s, t), (k, p) in result.items())


def _outlet_port(unit: Any, stream: Any) -> str | None:
    """Outlet name for a NeqSim stream leaving a separator-like unit (gas, liquid or water)."""
    if unit is None or stream is None:
        return None
    for getter, port in (
        ("getGasOutStream", "gas_outlet"),
        ("getOilOutStream", "liquid_outlet"),
        ("getLiquidOutStream", "liquid_outlet"),
        ("getWaterOutStream", "water_outlet"),
    ):
        try:
            if getattr(unit, getter)() == stream:
                return port
        except Exception:  # noqa: BLE001, S112
            continue
    return None


def _design_data(unit: Any) -> dict[str, Any]:
    """Mechanical design snapshot: ``toDesignDataJson()`` or, on older NeqSim jars, the getters."""
    try:
        design = unit.getMechanicalDesign()
    except Exception:  # equipment without a mechanical design  # noqa: BLE001
        return {}
    if design is None:
        return {}
    try:
        return json.loads(str(design.toDesignDataJson()))
    except Exception:  # noqa: BLE001, S110
        pass
    geometry: dict[str, Any] = {}
    for key, getter in (
        ("innerDiameter", "getInnerDiameter"),
        ("outerDiameter", "getOuterDiameter"),
        ("tangentLength", "getTantanLength"),
        ("moduleLength", "getModuleLength"),
        ("moduleWidth", "getModuleWidth"),
        ("moduleHeight", "getModuleHeight"),
    ):
        try:
            geometry[key] = {"value": float(getattr(design, getter)()), "unit": "m"}
        except Exception:  # noqa: BLE001, S112
            continue
    basis: dict[str, Any] = {}
    try:
        basis["maximumDesignPressure"] = {
            "value": float(design.getMaxDesignPressure()) * 1e5,
            "unit": "Pa",
        }
    except Exception:  # noqa: BLE001, S110
        pass
    data: dict[str, Any] = {"geometry": geometry, "designBasis": basis}
    try:
        data["orientation"] = str(unit.getOrientation())
    except Exception:  # noqa: BLE001, S110
        pass
    return data


def equipment_records_from_neqsim(
    process: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Equipment records and connections from a run NeqSim ``ProcessSystem``.

    Sizes come from ``MechanicalDesign.toDesignDataJson()`` (metres, Pa, K). Run
    the process and ``getMechanicalDesign().calcDesign()`` first; unavailable
    quantities fall back to placeholder sizes flagged as assumed. Connections
    come from ``ProcessSystem.buildGraph()`` with streams, mixers, splitters and
    recycles bridged.
    """
    records: list[dict[str, Any]] = []
    for unit in process.getUnitOperations():
        name = str(unit.getName())
        cls = str(unit.getClass().getSimpleName())
        kind = kind_for(cls)
        if kind is None:
            continue
        rec: dict[str, Any] = {
            "tag": name,
            "kind": kind,
            "neqsim_class": cls,
            "attributes": {},
        }
        data = _design_data(unit)
        geo = data.get("geometry", {}) or {}
        basis = data.get("designBasis", {}) or {}
        diameter = _num(geo.get("outerDiameter")) or _num(geo.get("innerDiameter"))
        length = _num(geo.get("tangentLength"))
        module = [
            _num(geo.get("moduleLength")),
            _num(geo.get("moduleWidth")),
            _num(geo.get("moduleHeight")),
        ]
        cylindrical = kind in ("vessel", "column", "heat_exchanger", "line", "pipeline")
        if cylindrical and diameter and length:
            rec["diameter_m"] = diameter
            rec["length_m"] = length
            rec["size_quality"] = "derived"
            rec["size_source"] = "NeqSim mechanical design"
        elif all(module):
            rec["size_m"] = module
            rec["size_quality"] = "derived"
            rec["size_source"] = "NeqSim mechanical design module envelope"
        orientation = data.get("orientation")
        if orientation:
            rec["orientation"] = str(orientation).lower()
        # NeqSim returns configured-or-default design values; the key name says so.
        pressure = _num(basis.get("maximumDesignPressure"))
        if pressure:
            rec["attributes"]["neqsim_max_design_pressure_bara"] = round(
                pressure / 1e5, 2
            )
        temperature = _num(basis.get("maximumDesignTemperature"))
        if temperature:
            rec["attributes"]["neqsim_max_design_temperature_C"] = round(
                temperature - 273.15, 1
            )
        records.append(rec)
    keep = {r["tag"] for r in records}
    units = {str(u.getName()): u for u in process.getUnitOperations()}
    edges: list[tuple[str, ...]] = []
    try:
        graph = process.buildGraph()
        for edge in graph.getEdges():
            kind = str(edge.getEdgeType()).lower()
            if kind in ("energy", "signal"):
                continue
            src = str(edge.getSource().getName())
            try:
                stream = edge.getStream()
            except Exception:  # noqa: BLE001
                stream = None
            edges.append(
                (
                    src,
                    str(edge.getTarget().getName()),
                    kind,
                    _outlet_port(units.get(src), stream),
                )
            )
    except Exception:  # noqa: BLE001
        try:
            for conn in process.getConnections():
                edges.append(
                    (
                        str(conn.getSourceEquipment()),
                        str(conn.getTargetEquipment()),
                        "material",
                    )
                )
        except Exception:  # noqa: BLE001
            edges = []
    connections = []
    for s, t, k, port in _collapse(edges, keep):
        conn = {"from": s, "to": t, "kind": "recycle" if k == "recycle" else "process"}
        if port:
            conn["from_port"] = port
        temperature = _outlet_temperature(units.get(s), port)
        if temperature is not None:
            conn["operating_temperature_C"] = temperature
        connections.append(conn)
    return records, connections


def _outlet_temperature(unit: Any, port: str | None) -> float | None:
    """Outlet temperature in C of the stream leaving ``unit`` (for the flexibility screen)."""
    if unit is None:
        return None
    getters = {
        "gas_outlet": "getGasOutStream",
        "liquid_outlet": "getLiquidOutStream",
        "water_outlet": "getWaterOutStream",
    }
    for getter in ([getters[port]] if port in getters else []) + ["getOutletStream"]:
        try:
            value = float(getattr(unit, getter)().getTemperature("C"))
            if math.isfinite(value):
                return round(value, 2)
        except Exception:  # noqa: BLE001, S112
            continue
    return None


def _levels(
    tags: Sequence[str], connections: Sequence[dict[str, Any]]
) -> dict[str, int]:
    """Flow-order column for each tag (longest path, recycles ignored)."""
    level = {t: 0 for t in tags}
    forward = [(c["from"], c["to"]) for c in connections if c.get("kind") != "recycle"]
    for _ in range(len(tags)):
        changed = False
        for s, t in forward:
            if s in level and t in level and level[t] < level[s] + 1:
                level[t] = level[s] + 1
                changed = True
        if not changed:
            break
    return level


def _record_geometry(
    rec: dict[str, Any], base: Sequence[float]
) -> tuple[dict[str, Any], float, float, str, str]:
    """Geometry for one record placed with its footprint centre at ``base`` (x, y, deck z)."""
    kind = rec.get("kind", "equipment")
    default = DEFAULT_SIZES.get(kind, DEFAULT_SIZES["equipment"])
    size_quality = rec.get("size_quality", "derived")
    size_source = rec.get("size_source", "supplied")
    diameter = _num(rec.get("diameter_m"))
    length = _num(rec.get("length_m"))
    size = rec.get("size_m")
    if not ((diameter and length) or (size and all(_num(v) for v in size))):
        size_quality, size_source = "assumed", f"placeholder {kind} size"
        diameter = default.get("diameter")
        length = default.get("length")
        size = default.get("size")
    if diameter and length:
        orientation = rec.get("orientation") or default.get("orientation", "vertical")
        if orientation.startswith("v"):
            geo = cylinder(
                [base[0], base[1], base[2] + length / 2.0], diameter, length, "z"
            )
            return geo, diameter, diameter, size_quality, size_source
        geo = cylinder(
            [base[0], base[1], base[2] + diameter / 2.0], diameter, length, "x"
        )
        return geo, length, diameter, size_quality, size_source
    sx, sy, sz = [float(v) for v in size]
    return (
        box([base[0], base[1], base[2] + sz / 2.0], [sx, sy, sz]),
        sx,
        sy,
        size_quality,
        size_source,
    )


def from_equipment_records(
    records: Sequence[dict[str, Any]],
    connections: Sequence[dict[str, Any]] = (),
    scene: AssetScene | None = None,
    state: str = "existing",
    origin: Sequence[float] = (0.0, 0.0, 0.0),
    spacing_m: float = 4.0,
    group: str = "facility",
    reference: str = "NeqSim process model",
) -> AssetScene:
    """Process equipment objects from records (see SKILL.md for the record keys).

    Records with ``position_m`` keep it: footprint centre x, y and base z, or the
    object centre when ``position_reference`` is ``"centre"`` (STID coordinates).
    The rest are laid out in flow order: one column per process level, left to
    right, which is an illustration placement recorded as ``assumed``.
    """
    scene = scene or AssetScene("Process equipment")
    tags = [r["tag"] for r in records]
    level = _levels(tags, connections)
    cursor_x: dict[int, float] = {}
    col_x: dict[int, float] = {}
    x = float(origin[0])
    by_level: dict[int, list[dict[str, Any]]] = {}
    for rec in records:
        by_level.setdefault(level.get(rec["tag"], 0), []).append(rec)
    for lvl in sorted(by_level):
        widths = [_record_geometry(r, (0, 0, 0))[1] for r in by_level[lvl]]
        col_x[lvl] = x + max(widths) / 2.0
        x += max(widths) + spacing_m
        cursor_x[lvl] = float(origin[1])
    auto_used = False
    for rec in records:
        lvl = level.get(rec["tag"], 0)
        if rec.get("position_m"):
            base = [float(v) for v in rec["position_m"]]
            pos_quality = rec.get("position_quality", "verified")
            pos_source = rec.get("position_source", "supplied position")
        else:
            _, _, depth, _, _ = _record_geometry(rec, (0, 0, 0))
            base = [col_x[lvl], cursor_x[lvl] + depth / 2.0, float(origin[2])]
            cursor_x[lvl] += depth + spacing_m
            pos_quality, pos_source = "assumed", "flow-order auto layout"
            auto_used = True
        geo, _, _, size_quality, size_source = _record_geometry(rec, base)
        if rec.get("position_m") and rec.get("position_reference", "base") == "centre":
            lo, hi = geometry_bounds(geo)[2], geometry_bounds(geo)[5]
            geo["center"][2] -= (hi - lo) / 2.0
        quality = worst_quality(size_quality, pos_quality)
        scene.add_object(
            id=str(rec.get("id") or rec["tag"]),
            kind=rec.get("kind", "equipment"),
            tag=rec.get("tag"),
            name=rec.get("name"),
            state=rec.get("state", state),
            group=rec.get("group", group),
            geometry=geo,
            source={
                "geometry": f"size: {size_source}; position: {pos_source}",
                "quality": quality,
                "size_quality": size_quality,
                "position_quality": pos_quality,
                "reference": rec.get("reference", reference),
            },
            attributes=rec.get("attributes"),
            nozzles=rec.get("nozzles"),
            results=rec.get("results"),
        )
        if size_quality == "assumed":
            scene.add_gap(
                f"No design size for {rec['tag']}",
                reference,
                "Shown with a placeholder envelope; not to scale",
                assumed=f"placeholder {rec.get('kind', 'equipment')} size",
            )
    ids = {o["id"] for o in scene.objects}
    for conn in connections:
        if conn["from"] in ids and conn["to"] in ids:
            scene.add_connection(
                conn["from"],
                conn["to"],
                kind=conn.get("kind", "process"),
                state=conn.get("state", state),
                line_number=conn.get("line_number"),
                diameter=conn.get("diameter_m"),
                quality=conn.get("quality", "derived"),
                reference=conn.get("reference", reference),
                route=conn.get("route_m"),
                route_reference=conn.get("route_reference"),
                **{k: conn[k] for k in PIPING_KEYS if conn.get(k) is not None},
            )
    if auto_used:
        text = "Equipment without a surveyed position is placed in process-flow order for illustration only."
        if text not in scene.assumptions:
            scene.assumptions.append(text)
    return scene


def scene_from_neqsim_process(
    process: Any, name: str = "NeqSim process", **kwargs: Any
) -> AssetScene:
    """Convenience: ``equipment_records_from_neqsim`` + ``from_equipment_records``."""
    records, connections = equipment_records_from_neqsim(process)
    scene = from_equipment_records(
        records, connections, scene=AssetScene(name), **kwargs
    )
    scene.provenance.append({"source": "NeqSim ProcessSystem", "objects": len(records)})
    return scene


# ------------------------------------------------------------------ subsea
SUBSEA_SIZES: dict[str, list[float]] = {
    "well": [4.0, 4.0, 4.0],
    "template": [20.0, 15.0, 6.0],
    "manifold": [12.0, 8.0, 5.0],
    "plem": [8.0, 5.0, 3.0],
    "plet": [6.0, 4.0, 2.5],
    "structure": [10.0, 10.0, 5.0],
}

NODE_KINDS = {
    "host": "host",
    "well": "well",
    "template": "template",
    "manifold": "manifold",
    "plem": "plem",
    "plet": "plet",
    "riser_base": "marker",
    "tie_in": "marker",
    "ssiv": "structure",
}


def local_projector(lons: Sequence[float], lats: Sequence[float]) -> tuple[Any, str]:
    """Equirectangular projection about the mean point (screening accuracy, metres)."""
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)
    k = math.pi / 180.0 * 6371000.0
    coslat = math.cos(math.radians(lat0))

    def project(lon: float, lat: float) -> tuple[float, float]:
        return ((float(lon) - lon0) * k * coslat, (float(lat) - lat0) * k)

    note = (
        f"Geographic coordinates projected to a local equirectangular frame about "
        f"({lat0:.4f} N, {lon0:.4f} E); distances are screening accuracy, not survey grade."
    )
    return project, note


def _to_local(
    nodes: Sequence[dict[str, Any]], coordinate_system: str
) -> tuple[Any, str | None]:
    if coordinate_system == "cartesian":
        return (lambda x, y: (float(x), float(y))), None
    if coordinate_system != "geographic":
        raise ValueError(
            "coordinate_system must be cartesian (metres) or geographic (lon/lat degrees)"
        )
    return local_projector(
        [float(n["x"]) for n in nodes], [float(n["y"]) for n in nodes]
    )


def from_subsea_nodes(
    nodes: Sequence[dict[str, Any]],
    lines: Sequence[dict[str, Any]] = (),
    scene: AssetScene | None = None,
    coordinate_system: str = "cartesian",
    host_size_m: Sequence[float] = (60.0, 40.0, 30.0),
    default_state: str = "existing",
    default_quality: str = "assumed",
    reference: str = "subsea layout",
) -> AssetScene:
    """Subsea objects from the ``neqsim-subsea-layout-geometry`` node shape plus lines.

    Nodes: ``name``, ``x``, ``y``, ``water_depth_m``, ``kind``; optional ``state``,
    ``quality``, ``reference``. Seabed z = -water depth; the host sits at z = 0.
    Lines: ``from``, ``to``, ``kind`` (flowline, pipeline, umbilical, riser),
    optional ``id``, ``diameter_m``, ``state``, ``quality``, ``route`` (list of
    [x, y] or [x, y, z] in the same coordinate system). A line ending at the host
    gets a vertical riser from the seabed to sea level.
    """
    scene = scene or AssetScene("Subsea layout")
    project, note = _to_local(nodes, coordinate_system)
    xy = {n["name"]: project(n["x"], n["y"]) for n in nodes}
    if note:
        scene.assumptions.append(note)
        scene.frame["description"] = "local frame projected from geographic coordinates"
    depth = {n["name"]: float(n.get("water_depth_m") or 0.0) for n in nodes}
    kinds = {}
    for n in nodes:
        kind = NODE_KINDS.get(str(n.get("kind", "structure")).lower(), "structure")
        kinds[n["name"]] = kind
        x, y = xy[n["name"]]
        z = -depth[n["name"]]
        if kind == "host":
            hx, hy, hz = host_size_m
            geo = box([x, y, hz / 2.0], [hx, hy, hz])
            group = "facility"
        elif kind == "marker":
            geo = point([x, y, z + 1.0], 3.0)
            group = "subsea"
        else:
            sx, sy, sz = SUBSEA_SIZES.get(kind, SUBSEA_SIZES["structure"])
            geo = box([x, y, z + sz / 2.0], [sx, sy, sz])
            group = "subsea"
        scene.add_object(
            id=str(n["name"]),
            kind=kind,
            tag=n.get("tag") or n["name"],
            name=n.get("label") or n["name"],
            state=n.get("state", default_state),
            group=group,
            geometry=geo,
            source={
                "geometry": n.get(
                    "geometry_source", "supplied coordinates; envelope size typical"
                ),
                "quality": n.get("quality", default_quality),
                "reference": n.get("reference", reference),
            },
            attributes={"water_depth_m": depth[n["name"]]} if depth[n["name"]] else {},
        )
    for i, line in enumerate(lines):
        a, b = line["from"], line["to"]
        if a not in xy or b not in xy:
            raise ValueError(f"line {line.get('id', i)} references unknown node")
        za, zb = -depth[a], -depth[b]
        if kinds[a] == "host":
            za = -depth[a] if depth[a] else zb
        if kinds[b] == "host":
            zb = -depth[b] if depth[b] else za
        route = line.get("route")
        if route:
            pts2 = [project(p[0], p[1]) for p in route]
            zs = [float(p[2]) if len(p) > 2 else None for p in route]
            n_pts = len(pts2)
            pts = [
                [
                    pts2[j][0],
                    pts2[j][1],
                    (
                        zs[j]
                        if zs[j] is not None
                        else za + (zb - za) * j / max(1, n_pts - 1)
                    ),
                ]
                for j in range(n_pts)
            ]
        else:
            pts = [[xy[a][0], xy[a][1], za], [xy[b][0], xy[b][1], zb]]
        if kinds[a] == "host":
            pts.insert(0, [xy[a][0], xy[a][1], 0.0])
        if kinds[b] == "host":
            pts.append([xy[b][0], xy[b][1], 0.0])
        kind = str(line.get("kind", "flowline")).lower()
        if kind not in ("flowline", "pipeline", "umbilical", "riser", "line"):
            kind = "flowline"
        scene.add_object(
            id=str(line.get("id") or f"{kind}:{a}-{b}"),
            kind=kind,
            tag=line.get("tag"),
            name=line.get("name") or f"{kind} {a}-{b}",
            state=line.get("state", default_state),
            group="subsea",
            geometry=polyline(
                pts,
                float(line.get("diameter_m") or (0.15 if kind == "umbilical" else 0.3)),
            ),
            source={
                "geometry": "routed survey" if route else "straight link between nodes",
                "quality": line.get("quality", default_quality if route else "assumed"),
                "reference": line.get("reference", reference),
            },
            attributes={
                k: line[k]
                for k in ("function", "status", "length_km", "from_inst", "to_inst")
                if k in line
            },
        )
    return scene


# ------------------------------------------------------------------- wells
_ALIASES = {
    "md": ("md_m", "md", "measuredDepth", "MD"),
    "inc": ("inc_deg", "inc", "inclination", "INC"),
    "azi": ("azi_deg", "azi", "azimuth", "AZI"),
    "tvd": ("tvd_m", "tvd", "TVD"),
    "north": ("north_m", "north", "ns_m", "N"),
    "east": ("east_m", "east", "ew_m", "E"),
}


def _pick(station: dict[str, Any], key: str) -> float | None:
    for alias in _ALIASES[key]:
        if alias in station and station[alias] is not None:
            return float(station[alias])
    return None


def minimum_curvature(
    md: Sequence[float], inc_deg: Sequence[float], azi_deg: Sequence[float]
) -> list[tuple[float, float, float]]:
    """(north, east, tvd) in metres from a survey by the minimum-curvature method."""
    n, e, v = 0.0, 0.0, 0.0
    out = [(0.0, 0.0, 0.0)]
    for i in range(1, len(md)):
        dmd = md[i] - md[i - 1]
        i1, i2 = math.radians(inc_deg[i - 1]), math.radians(inc_deg[i])
        a1, a2 = math.radians(azi_deg[i - 1]), math.radians(azi_deg[i])
        cos_dl = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (
            1.0 - math.cos(a2 - a1)
        )
        dl = math.acos(max(-1.0, min(1.0, cos_dl)))
        rf = 1.0 if dl < 1e-9 else 2.0 / dl * math.tan(dl / 2.0)
        n += (
            dmd / 2.0 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf
        )
        e += (
            dmd / 2.0 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf
        )
        v += dmd / 2.0 * (math.cos(i1) + math.cos(i2)) * rf
        out.append((n, e, v))
    return out


def from_well_trajectory(
    name: str,
    stations: Sequence[dict[str, Any]],
    wellhead_xy: Sequence[float],
    datum_z: float,
    scene: AssetScene | None = None,
    state: str = "existing",
    quality: str = "verified",
    diameter_m: float = 0.3,
    reference: str = "well survey",
    tag: str | None = None,
) -> AssetScene:
    """Well path from survey stations.

    Stations use ``md_m``/``inc_deg``/``azi_deg`` (aliases ``md``, ``inc``,
    ``azi`` accepted) or explicit ``north_m``/``east_m``/``tvd_m``. ``datum_z``
    is the elevation of the depth reference (MD = 0), for example RKB +40 m or
    the seabed -320 m; z = datum_z - TVD. East maps to x and north to y.
    """
    scene = scene or AssetScene(f"Well {name}")
    if len(stations) < 2:
        raise ValueError("a trajectory needs at least two stations")
    explicit = all(
        _pick(s, "north") is not None
        and _pick(s, "east") is not None
        and _pick(s, "tvd") is not None
        for s in stations
    )
    if explicit:
        neu = [(_pick(s, "north"), _pick(s, "east"), _pick(s, "tvd")) for s in stations]
        method = "supplied north/east/TVD"
    else:
        md = [_pick(s, "md") for s in stations]
        inc = [_pick(s, "inc") for s in stations]
        azi = [_pick(s, "azi") for s in stations]
        if any(v is None for v in md + inc + azi):
            raise ValueError("stations need md/inc/azi or north/east/tvd")
        neu = minimum_curvature(md, inc, azi)  # type: ignore[arg-type]
        method = "minimum curvature from MD/INC/AZI"
        quality = worst_quality(quality, "derived")
    pts = [[wellhead_xy[0] + e, wellhead_xy[1] + n, datum_z - v] for n, e, v in neu]  # type: ignore[operator]
    scene.add_object(
        id=str(name),
        kind="well",
        tag=tag or name,
        state=state,
        group="well",
        geometry=polyline(pts, diameter_m),
        source={"geometry": method, "quality": quality, "reference": reference},
        attributes={"td_tvd_m": round(neu[-1][2], 1), "datum_z_m": datum_z},  # type: ignore[index]
    )
    return scene


# ------------------------------------------------------------------ values
def attach_values(
    scene: AssetScene,
    values: dict[str, dict[str, Any]],
    channel: str = "results",
    match: str = "tag",
) -> list[str]:
    """Attach NeqSim results (``channel='results'``) or live data (``'live'``) per object.

    ``values`` maps a tag (or id) to ``{quantity: number | {"value", "unit", ...}}``.
    Returns the keys that matched no object so the caller can report them.
    """
    if channel not in ("results", "live", "attributes"):
        raise ValueError("channel must be results, live or attributes")
    unmatched = []
    for key, quantities in values.items():
        obj = scene.find_by_tag(key) if match == "tag" else scene.get(key)
        if obj is None:
            unmatched.append(key)
            continue
        for qname, val in quantities.items():
            obj[channel][qname] = val if isinstance(val, dict) else {"value": val}
    return unmatched


def neqsim_results(
    process: Any, quantities: Sequence[str] = ("utilisation",)
) -> dict[str, dict[str, Any]]:
    """Per-equipment values from a run ``ProcessSystem`` for ``attach_values``.

    ``utilisation`` uses ``getMaxUtilization()`` (highest ratio over the enabled
    capacity constraints; 0.0 means no constraint is defined and is skipped).
    Pressure and temperature use the outlet stream when present.
    """
    out: dict[str, dict[str, Any]] = {}
    for unit in process.getUnitOperations():
        name = str(unit.getName())
        if kind_for(unit.getClass().getSimpleName()) is None:
            continue
        entry: dict[str, Any] = {}
        if "utilisation" in quantities:
            try:
                val = float(unit.getMaxUtilization())
                if math.isfinite(val) and val > 0.0:
                    entry["utilisation"] = {"value": val, "unit": "-"}
            except Exception:  # noqa: BLE001, S110
                pass
        for q, getter, unit_name in (
            ("pressure", "getPressure", "bara"),
            ("temperature", "getTemperature", "C"),
        ):
            if q not in quantities:
                continue
            try:
                stream = unit.getOutletStream()
                val = float(getattr(stream, getter)(unit_name))
                entry[q] = {"value": val, "unit": unit_name}
            except Exception:  # noqa: BLE001, S110
                pass
        if entry:
            out[name] = entry
    return out


def tags_in(scene: AssetScene) -> list[str]:
    """Normalised tags present in a scene."""
    return [normalise_tag(o["tag"]) for o in scene.objects if o.get("tag")]
