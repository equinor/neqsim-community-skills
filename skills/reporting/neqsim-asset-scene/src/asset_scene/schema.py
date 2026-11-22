"""Asset scene contract (``neqsim_asset_scene.v1``).

A scene is a plain, JSON-serialisable description of physical objects (process
equipment, lines, subsea structures, wells, reservoir boxes) in one local metric
frame, each tagged with its state (existing, proposed, modified, removed), the
quality of its geometry source, and optional engineering attributes, NeqSim
results and live values. Renderers in this package turn a scene into GLB,
an offline interactive HTML viewer and PNG figures.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA = "neqsim_asset_scene.v1"

KINDS = (
    "equipment",
    "vessel",
    "column",
    "compressor",
    "pump",
    "heat_exchanger",
    "valve",
    "instrument",
    "line",
    "pipeline",
    "flowline",
    "riser",
    "umbilical",
    "well",
    "template",
    "manifold",
    "plem",
    "plet",
    "host",
    "structure",
    "deck",
    "obstacle",
    "reservoir",
    "area",
    "marker",
    "support",
)

STATES = ("existing", "proposed", "modified", "removed")

# verified: controlled source (STID, as-built survey, as-laid route)
# derived: calculated (NeqSim mechanical design, minimum-curvature survey)
# assumed: placeholder geometry or placement chosen for the illustration
QUALITIES = ("verified", "derived", "assumed")

SHAPES = ("box", "cylinder", "sphere", "polyline", "point")

PIPING_KEYS = (
    "from_port",
    "to_port",
    "min_slope",
    "wall_thickness_m",
    "operating_temperature_C",
    "fluid_density_kg_m3",
    "material",
    "design_pressure_barg",
    "corrosion_allowance_m",
    "friction",
    "allowable_stress_Pa",
)

AXES = ("x", "y", "z")


def _finite(values: Iterable[Any]) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def box(center: Sequence[float], size: Sequence[float]) -> Dict[str, Any]:
    """Axis-aligned box geometry, centre and full size in metres."""
    return {"shape": "box", "center": [float(v) for v in center], "size": [float(v) for v in size]}


def box_from_bounds(bounds: Sequence[float]) -> Dict[str, Any]:
    """Box geometry from ``[xmin, ymin, zmin, xmax, ymax, zmax]`` in metres."""
    xmin, ymin, zmin, xmax, ymax, zmax = [float(v) for v in bounds]
    return box(
        [(xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0],
        [xmax - xmin, ymax - ymin, zmax - zmin],
    )


def cylinder(center: Sequence[float], diameter: float, length: float, axis: str = "z") -> Dict[str, Any]:
    """Cylinder geometry: centre, outer diameter and length in metres along ``axis``."""
    return {
        "shape": "cylinder",
        "center": [float(v) for v in center],
        "diameter": float(diameter),
        "length": float(length),
        "axis": axis,
    }


def sphere(center: Sequence[float], diameter: float) -> Dict[str, Any]:
    """Sphere geometry (spherical tanks, markers)."""
    return {"shape": "sphere", "center": [float(v) for v in center], "diameter": float(diameter)}


def polyline(points: Sequence[Sequence[float]], diameter: float) -> Dict[str, Any]:
    """Tube along a 3D path (lines, risers, wells); diameter in metres."""
    return {"shape": "polyline", "points": [[float(c) for c in p] for p in points], "diameter": float(diameter)}


def point(center: Sequence[float], size: float = 1.0) -> Dict[str, Any]:
    """Small marker at a location (a tag with a position but no size)."""
    return {"shape": "point", "center": [float(v) for v in center], "size": float(size)}


def geometry_anchor(geometry: Dict[str, Any]) -> List[float]:
    """Representative point of a geometry (centre, or path midpoint)."""
    if geometry.get("shape") == "polyline":
        pts = geometry["points"]
        return list(pts[len(pts) // 2])
    return list(geometry["center"])


def geometry_bounds(geometry: Dict[str, Any]) -> List[float]:
    """Axis-aligned bounds ``[xmin, ymin, zmin, xmax, ymax, zmax]`` of a geometry."""
    shape = geometry.get("shape")
    if shape == "polyline":
        r = geometry.get("diameter", 0.0) / 2.0
        xs, ys, zs = zip(*geometry["points"])
        return [min(xs) - r, min(ys) - r, min(zs) - r, max(xs) + r, max(ys) + r, max(zs) + r]
    cx, cy, cz = geometry["center"]
    if shape == "box":
        dx, dy, dz = [v / 2.0 for v in geometry["size"]]
    elif shape == "cylinder":
        r = geometry["diameter"] / 2.0
        h = geometry["length"] / 2.0
        dx, dy, dz = {"x": (h, r, r), "y": (r, h, r), "z": (r, r, h)}[geometry.get("axis", "z")]
    elif shape == "sphere":
        dx = dy = dz = geometry["diameter"] / 2.0
    else:
        dx = dy = dz = geometry.get("size", 1.0) / 2.0
    return [cx - dx, cy - dy, cz - dz, cx + dx, cy + dy, cz + dz]


def _validate_geometry(geometry: Any) -> List[str]:
    if not isinstance(geometry, dict):
        return ["geometry must be a dict"]
    shape = geometry.get("shape")
    if shape not in SHAPES:
        return [f"unknown shape {shape!r}"]
    issues: List[str] = []
    if shape == "polyline":
        pts = geometry.get("points") or []
        if len(pts) < 2:
            issues.append("polyline needs at least two points")
        elif not all(len(p) == 3 and _finite(p) for p in pts):
            issues.append("polyline points must be finite [x, y, z]")
        if not _finite([geometry.get("diameter")]) or geometry.get("diameter", 0) <= 0:
            issues.append("polyline diameter must be positive")
        return issues
    center = geometry.get("center")
    if not center or len(center) != 3 or not _finite(center):
        issues.append("center must be finite [x, y, z]")
    if shape == "box":
        size = geometry.get("size")
        if not size or len(size) != 3 or not _finite(size) or min(size) <= 0:
            issues.append("box size must be three positive numbers")
    elif shape == "cylinder":
        for key in ("diameter", "length"):
            if not _finite([geometry.get(key)]) or geometry.get(key, 0) <= 0:
                issues.append(f"cylinder {key} must be positive")
        if geometry.get("axis", "z") not in AXES:
            issues.append("cylinder axis must be x, y or z")
    elif shape == "sphere":
        if not _finite([geometry.get("diameter")]) or geometry.get("diameter", 0) <= 0:
            issues.append("sphere diameter must be positive")
    return issues


class AssetScene:
    """Mutable container for a ``neqsim_asset_scene.v1`` document."""

    def __init__(
        self,
        name: str,
        frame: Optional[Dict[str, Any]] = None,
        classification: Optional[str] = None,
    ) -> None:
        self.name = name
        self.frame = {"crs": "local", "units": "m", "z_up": True, "description": "local engineering frame"}
        if frame:
            self.frame.update(frame)
        self.classification = classification
        self.objects: List[Dict[str, Any]] = []
        self.connections: List[Dict[str, Any]] = []
        self.assumptions: List[str] = []
        self.data_gaps: List[Dict[str, Any]] = []
        self.provenance: List[Dict[str, Any]] = []

    # ----------------------------------------------------------------- objects
    def add_object(
        self,
        id: str,
        kind: str,
        geometry: Dict[str, Any],
        state: str = "existing",
        tag: Optional[str] = None,
        name: Optional[str] = None,
        group: str = "facility",
        source: Optional[Dict[str, Any]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        results: Optional[Dict[str, Any]] = None,
        live: Optional[Dict[str, Any]] = None,
        media: Optional[List[Dict[str, Any]]] = None,
        nozzles: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Add an object and return it; raises ``ValueError`` on invalid input.

        ``nozzles`` maps a nozzle id or service (``N1``, ``gas_outlet``) to
        ``{"offset_m": [dx, dy, dz]}`` from the object centre or
        ``{"position_m": [x, y, z]}`` in the scene frame, optional
        ``"direction": [ux, uy, uz]`` (outward) and ``"service"``. Connections
        that name a nozzle as ``from_port``/``to_port`` start or end there.
        """
        if self.get(id) is not None:
            raise ValueError(f"duplicate object id {id!r}")
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}; use one of {KINDS}")
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}; use one of {STATES}")
        issues = _validate_geometry(geometry)
        if issues:
            raise ValueError(f"object {id!r}: " + "; ".join(issues))
        for nid, noz in (nozzles or {}).items():
            vec = noz.get("offset_m", noz.get("position_m"))
            if vec is None or len(vec) != 3 or not _finite(vec):
                raise ValueError(f"object {id!r} nozzle {nid!r}: needs finite offset_m or position_m [x, y, z]")
            if noz.get("direction") is not None and (len(noz["direction"]) != 3 or not _finite(noz["direction"])):
                raise ValueError(f"object {id!r} nozzle {nid!r}: direction must be [ux, uy, uz]")
        src = {"geometry": "unspecified", "quality": "assumed", "reference": None}
        if source:
            src.update(source)
        if src["quality"] not in QUALITIES:
            raise ValueError(f"unknown source quality {src['quality']!r}; use one of {QUALITIES}")
        obj = {
            "id": id,
            "tag": tag,
            "name": name or tag or id,
            "kind": kind,
            "state": state,
            "group": group,
            "geometry": geometry,
            "source": src,
            "attributes": dict(attributes or {}),
            "results": dict(results or {}),
            "live": dict(live or {}),
            "media": list(media or []),
        }
        if nozzles:
            obj["nozzles"] = {k: dict(v) for k, v in nozzles.items()}
        self.objects.append(obj)
        return obj

    def add_connection(
        self,
        source: str,
        target: str,
        kind: str = "process",
        state: str = "existing",
        id: Optional[str] = None,
        line_number: Optional[str] = None,
        diameter: Optional[float] = None,
        quality: str = "assumed",
        reference: Optional[str] = None,
        route: Optional[Sequence[Sequence[float]]] = None,
        route_reference: Optional[str] = None,
        **piping: Any,
    ) -> Dict[str, Any]:
        """Connect two objects.

        ``route`` is the pipe path in the scene frame ([[x, y, z], ...], at least
        two points) from an isometric, a 3D model export or a survey; it is joined
        to the equipment faces. Without it the renderer routes the pipe
        automatically and records that as assumed.

        Optional piping data (keyword arguments, see ``PIPING_KEYS``):
        ``from_port``/``to_port`` (nozzle id or service such as ``gas_outlet``),
        ``min_slope`` (fall per metre toward the target, e.g. 0.005 = 1:200),
        ``wall_thickness_m``, ``operating_temperature_C``,
        ``fluid_density_kg_m3``, ``material`` (``carbon_steel``,
        ``stainless_steel``, ``duplex``).
        """
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        if route is not None:
            pts = [list(p) for p in route]
            if len(pts) < 2 or not all(len(p) == 3 and _finite(p) for p in pts):
                raise ValueError("route needs at least two finite [x, y, z] points")
            route = [[float(c) for c in p] for p in pts]
        conn = {
            "id": id or f"{source}->{target}",
            "from": source,
            "to": target,
            "kind": kind,
            "state": state,
            "line_number": line_number,
            "diameter": diameter,
            "source": {"quality": quality, "reference": reference},
        }
        if route is not None:
            conn["route"] = route
            conn["route_reference"] = route_reference
        for key, val in (piping or {}).items():
            if key not in PIPING_KEYS:
                raise ValueError(f"unknown piping key {key!r}; use one of {PIPING_KEYS}")
            conn[key] = val
        self.connections.append(conn)
        return conn

    def get(self, object_id: str) -> Optional[Dict[str, Any]]:
        """Object by id, or ``None``."""
        for obj in self.objects:
            if obj["id"] == object_id:
                return obj
        return None

    def find_by_tag(self, tag: str) -> Optional[Dict[str, Any]]:
        """Object by tag (case-insensitive, ignores spaces), or ``None``."""
        key = normalise_tag(tag)
        for obj in self.objects:
            if obj.get("tag") and normalise_tag(obj["tag"]) == key:
                return obj
        return None

    def add_gap(self, gap: str, source: str, effect: str, status: str = "open", assumed: str = "") -> None:
        """Record a data gap in the task ``results.json`` shape."""
        entry = {"gap": gap, "source": source, "status": status, "assumed": assumed, "effect": effect}
        if entry not in self.data_gaps:
            self.data_gaps.append(entry)

    # ------------------------------------------------------------- transforms
    def translate(self, dx: float, dy: float, dz: float) -> "AssetScene":
        """Move every object by a fixed offset in place and return self."""
        offset = (float(dx), float(dy), float(dz))
        for obj in self.objects:
            geo = obj["geometry"]
            if geo["shape"] == "polyline":
                geo["points"] = [[p[i] + offset[i] for i in range(3)] for p in geo["points"]]
            else:
                geo["center"] = [geo["center"][i] + offset[i] for i in range(3)]
            for noz in (obj.get("nozzles") or {}).values():
                if "position_m" in noz:
                    noz["position_m"] = [noz["position_m"][i] + offset[i] for i in range(3)]
        for conn in self.connections:
            if conn.get("route"):
                conn["route"] = [[p[i] + offset[i] for i in range(3)] for p in conn["route"]]
        return self

    def merge(self, other: "AssetScene", prefix: str = "") -> "AssetScene":
        """Append the objects and connections of ``other`` (ids prefixed when given)."""
        for obj in other.objects:
            new = copy.deepcopy(obj)
            new["id"] = prefix + obj["id"]
            if self.get(new["id"]) is not None:
                raise ValueError(f"duplicate object id {new['id']!r} on merge; pass a prefix")
            self.objects.append(new)
        for conn in other.connections:
            new = copy.deepcopy(conn)
            new["id"] = prefix + conn["id"]
            new["from"] = prefix + conn["from"]
            new["to"] = prefix + conn["to"]
            self.connections.append(new)
        for text in other.assumptions:
            if text not in self.assumptions:
                self.assumptions.append(text)
        for gap in other.data_gaps:
            if gap not in self.data_gaps:
                self.data_gaps.append(gap)
        self.provenance.extend(other.provenance)
        return self

    def subset(self, groups: Optional[Sequence[str]] = None, states: Optional[Sequence[str]] = None) -> "AssetScene":
        """Copy holding only the chosen groups and/or states (connections kept when both ends remain)."""
        out = AssetScene(self.name, dict(self.frame), self.classification)
        for obj in self.objects:
            if groups and obj["group"] not in groups:
                continue
            if states and obj["state"] not in states:
                continue
            out.objects.append(copy.deepcopy(obj))
        ids = {o["id"] for o in out.objects}
        out.connections = [copy.deepcopy(c) for c in self.connections if c["from"] in ids and c["to"] in ids]
        out.assumptions = list(self.assumptions)
        out.data_gaps = copy.deepcopy(self.data_gaps)
        out.provenance = copy.deepcopy(self.provenance)
        return out

    def bounds(self) -> List[float]:
        """Scene bounds ``[xmin, ymin, zmin, xmax, ymax, zmax]``."""
        if not self.objects:
            return [0.0] * 6
        all_b = [geometry_bounds(o["geometry"]) for o in self.objects]
        return [min(b[i] for b in all_b) for i in range(3)] + [max(b[i] for b in all_b) for i in range(3, 6)]

    # --------------------------------------------------------------- validate
    def validate(self) -> List[str]:
        """Return a list of contract violations (empty when the scene is valid)."""
        issues: List[str] = []
        if self.frame.get("units") != "m":
            issues.append("frame units must be metres")
        seen = set()
        for obj in self.objects:
            oid = obj.get("id")
            if oid in seen:
                issues.append(f"duplicate object id {oid!r}")
            seen.add(oid)
            if obj.get("kind") not in KINDS:
                issues.append(f"{oid}: unknown kind {obj.get('kind')!r}")
            if obj.get("state") not in STATES:
                issues.append(f"{oid}: unknown state {obj.get('state')!r}")
            if obj.get("source", {}).get("quality") not in QUALITIES:
                issues.append(f"{oid}: unknown source quality")
            issues.extend(f"{oid}: {msg}" for msg in _validate_geometry(obj.get("geometry")))
        for conn in self.connections:
            for end in ("from", "to"):
                if conn.get(end) not in seen:
                    issues.append(f"connection {conn.get('id')}: unknown {end} object {conn.get(end)!r}")
            route = conn.get("route")
            if route is not None and (len(route) < 2 or not all(len(p) == 3 and _finite(p) for p in route)):
                issues.append(f"connection {conn.get('id')}: route needs at least two finite [x, y, z] points")
        return issues

    # ------------------------------------------------------------- serialise
    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready dict."""
        return {
            "schema": SCHEMA,
            "name": self.name,
            "frame": self.frame,
            "classification": self.classification,
            "objects": self.objects,
            "connections": self.connections,
            "assumptions": self.assumptions,
            "data_gaps": self.data_gaps,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssetScene":
        """Load from a dict; raises ``ValueError`` on another schema."""
        if data.get("schema") != SCHEMA:
            raise ValueError(f"expected schema {SCHEMA}, got {data.get('schema')!r}")
        scene = cls(data.get("name", "scene"), data.get("frame"), data.get("classification"))
        scene.objects = copy.deepcopy(data.get("objects", []))
        scene.connections = copy.deepcopy(data.get("connections", []))
        scene.assumptions = list(data.get("assumptions", []))
        scene.data_gaps = copy.deepcopy(data.get("data_gaps", []))
        scene.provenance = copy.deepcopy(data.get("provenance", []))
        return scene

    def save(self, path: Any) -> Path:
        """Write the scene as JSON and return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: Any) -> "AssetScene":
        """Read a scene JSON file."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def normalise_tag(tag: Any) -> str:
    """Upper-case tag with whitespace removed, for matching across sources."""
    return "".join(str(tag).split()).upper()
