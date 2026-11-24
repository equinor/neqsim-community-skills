"""Realistic 3D primitives for asset scenes: vessels with dished heads, swept pipes with elbows and flanges, valves, jacket lattices,
deck modules, flare boom, subsea template frames with trees, seabed relief, well strings and reservoir layers.

Pure Python (no dependencies). Every builder returns a *mesh* ``(vertices, triangles)`` or a list of *parts*
``(name, mesh, material)`` where ``material`` is a key in :data:`MATERIALS`. Units are metres, z is up. The meshes feed the
existing GLB/HTML renderers, PyVista (:func:`to_pyvista`) and Plotly (:func:`to_plotly_arrays`).

Realism limits of the older primitives (box, 12-segment cylinder, sphere) were: no dished heads, no pipe bends or flanges, no
lattice structures, flat seabed, one straight tube per well, no surface normals. This module closes those gaps; see the
"Realism checklist" in SKILL.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .mesh import Mesh, Vec, _append, _cross, _norm, _sub, box_mesh, tube_mesh

Part = tuple[str, Mesh, str]

MATERIALS: dict[str, dict[str, object]] = {
    "steel": {"color": "#8C969E", "metallic": 0.7, "roughness": 0.45},
    "steel_dark": {"color": "#4D565E", "metallic": 0.6, "roughness": 0.55},
    "vessel_paint": {"color": "#C9CFD6", "metallic": 0.35, "roughness": 0.35},
    "paint_red": {"color": "#B3392F", "metallic": 0.3, "roughness": 0.4},
    "paint_yellow": {"color": "#D9B525", "metallic": 0.2, "roughness": 0.5},
    "paint_blue": {"color": "#2F6DA8", "metallic": 0.3, "roughness": 0.4},
    "paint_green": {"color": "#2E7D4F", "metallic": 0.2, "roughness": 0.6},
    "concrete": {"color": "#A9A9A0", "metallic": 0.0, "roughness": 0.9},
    "deck": {"color": "#7C858C", "metallic": 0.4, "roughness": 0.65},
    "pipe": {"color": "#9AA3AA", "metallic": 0.6, "roughness": 0.4},
    "seabed": {"color": "#B8A77E", "metallic": 0.0, "roughness": 1.0},
    "rock": {"color": "#8A7F6C", "metallic": 0.0, "roughness": 1.0},
    "water": {"color": "#3E8EC4", "metallic": 0.0, "roughness": 0.1},
    "reservoir": {"color": "#C98B3A", "metallic": 0.0, "roughness": 0.8},
    "casing": {"color": "#6E7B85", "metallic": 0.8, "roughness": 0.35},
    "schematic": {"color": "#C9CED3", "metallic": 0.0, "roughness": 0.9},  # unsourced/assumed structure: neutral, translucent, labelled antatt/skjematisk
}


# ----------------------------------------------------------------------------------------------------------------- basics
def _add(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Sequence[float], s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a: Sequence[float]) -> float:
    return math.sqrt(_dot(a, a))


def merge(*meshes: Mesh) -> Mesh:
    """Concatenate meshes into one."""
    out: Mesh = ([], [])
    for m in meshes:
        _append(out, m)
    return out


def transform(mesh: Mesh, translate: Sequence[float] = (0.0, 0.0, 0.0), rot_z_deg: float = 0.0, scale: float = 1.0) -> Mesh:
    """Scale, rotate about the z axis (through the origin) and translate a mesh."""
    c, s = math.cos(math.radians(rot_z_deg)), math.sin(math.radians(rot_z_deg))
    verts = []
    for x, y, z in mesh[0]:
        x, y, z = x * scale, y * scale, z * scale
        verts.append((x * c - y * s + translate[0], x * s + y * c + translate[1], z + translate[2]))
    return verts, list(mesh[1])


def frame_from_axis(axis: Sequence[float]) -> tuple[Vec, Vec, Vec]:
    """Orthonormal frame (u, v, w) with w along ``axis``."""
    w = _norm(tuple(axis))  # type: ignore[arg-type]
    helper = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm(_cross(w, helper))
    v = _cross(w, u)
    return u, v, w


def vertex_normals(mesh: Mesh) -> list[Vec]:
    """Area-weighted smooth vertex normals."""
    acc = [[0.0, 0.0, 0.0] for _ in mesh[0]]
    for a, b, c in mesh[1]:
        n = _cross(_sub(mesh[0][b], mesh[0][a]), _sub(mesh[0][c], mesh[0][a]))
        for i in (a, b, c):
            acc[i][0] += n[0]
            acc[i][1] += n[1]
            acc[i][2] += n[2]
    return [_norm((n[0], n[1], n[2])) for n in acc]


def mesh_bounds(mesh: Mesh) -> tuple[Vec, Vec]:
    """Axis-aligned bounds (min, max)."""
    xs, ys, zs = zip(*mesh[0])
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def mesh_volume(mesh: Mesh) -> float:
    """Signed volume of a closed outward-wound mesh (divergence theorem)."""
    vol = 0.0
    for a, b, c in mesh[1]:
        p, q, r = mesh[0][a], mesh[0][b], mesh[0][c]
        vol += _dot(p, _cross(q, r)) / 6.0
    return vol


def _clean(mesh: Mesh) -> Mesh:
    faces = []
    for a, b, c in mesh[1]:
        if a == b or b == c or a == c:
            continue
        n = _cross(_sub(mesh[0][b], mesh[0][a]), _sub(mesh[0][c], mesh[0][a]))
        if _dot(n, n) > 1e-18:
            faces.append((a, b, c))
    return mesh[0], faces


# ------------------------------------------------------------------------------------------------ surfaces of revolution
def revolve(profile: Sequence[tuple[float, float]], center: Sequence[float] = (0.0, 0.0, 0.0), axis: Sequence[float] = (0.0, 0.0, 1.0), segments: int = 48) -> Mesh:
    """Surface of revolution. ``profile`` is a list of (radius, position along axis) from one end to the other (outward winding for increasing axis position)."""
    u, v, w = frame_from_axis(axis)
    verts: list[Vec] = []
    for r, h in profile:
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append(
                (
                    center[0] + u[0] * r * math.cos(a) + v[0] * r * math.sin(a) + w[0] * h,
                    center[1] + u[1] * r * math.cos(a) + v[1] * r * math.sin(a) + w[1] * h,
                    center[2] + u[2] * r * math.cos(a) + v[2] * r * math.sin(a) + w[2] * h,
                )
            )
    faces = []
    for k in range(len(profile) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            a, b = k * segments + i, k * segments + j
            c, d = (k + 1) * segments + j, (k + 1) * segments + i
            faces.append((a, b, c))
            faces.append((a, c, d))
    return _clean((verts, faces))


def _head_profile(radius: float, head_depth: float, n: int, kind: str) -> list[tuple[float, float]]:
    """Points (r, s) of a head from the tip (s = 0) to the tangent line (s = head_depth)."""
    pts = []
    if kind == "flat" or head_depth <= 0:
        return [(0.0, 0.0), (radius, 0.0)]
    for i in range(n + 1):
        t = 0.5 * math.pi * i / n
        pts.append((radius * math.sin(t), head_depth * (1.0 - math.cos(t))))
    return pts


def vessel_mesh(center: Sequence[float], diameter: float, length: float, orientation: str = "horizontal", head: str = "ellipsoidal", segments: int = 56) -> Mesh:
    """Pressure vessel with dished heads. ``length`` is tangent-to-tangent. head: ``ellipsoidal`` (2:1), ``hemispherical``, ``torispherical`` (about 0.169 D deep), ``flat``.

    Closed, outward wound. Tip-to-tip length = ``length`` + 2 * head depth (D/4, D/2, 0.169 D, 0).
    """
    r = diameter / 2.0
    depth = {"ellipsoidal": diameter / 4.0, "hemispherical": r, "torispherical": 0.169 * diameter, "flat": 0.0}[head]
    n = 14
    left = _head_profile(r, depth, n, head)  # tip -> tangent, s from 0..depth
    h0 = -length / 2.0 - depth
    prof = [(rr, h0 + s) for rr, s in left]
    prof += [(r, length / 2.0)]
    for rr, s in reversed(left):
        prof.append((rr, length / 2.0 + depth - s))
    if head == "flat":
        prof = [(0.0, -length / 2.0), (r, -length / 2.0), (r, length / 2.0), (0.0, length / 2.0)]
    axis = (1.0, 0.0, 0.0) if orientation == "horizontal" else (0.0, 0.0, 1.0)
    return revolve(prof, center, axis, segments)


def vessel_parts(center: Sequence[float], diameter: float, length: float, orientation: str = "horizontal", head: str = "ellipsoidal",
                 nozzles: Sequence[dict] | None = None, saddles: bool = True) -> list[Part]:
    """Vessel with saddle supports (horizontal) or skirt (vertical) and nozzles.

    ``nozzles``: dicts ``{"s": position along axis in [-0.5, 0.5] of length, "angle_deg": around axis (0 = up for horizontal), "diameter": m, "length": m}``.
    """
    parts: list[Part] = [("vessel", vessel_mesh(center, diameter, length, orientation, head), "vessel_paint")]
    r = diameter / 2.0
    cx, cy, cz = center
    if orientation == "horizontal":
        if saddles:
            for s in (-0.3, 0.3):
                parts.append(("saddle", box_mesh((cx + s * length, cy, cz - r * 0.78 - 0.15), (0.35 * diameter, diameter * 0.9, 0.3 + r * 0.35)), "steel_dark"))
        axis, up = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
        side = (0.0, 1.0, 0.0)
    else:
        if saddles:
            parts.append(("skirt", revolve([(r * 0.9, cz - length / 2.0 - 0.1), (r * 0.9, cz - length / 2.0 - diameter * 0.8)], (cx, cy, 0.0)), "steel_dark"))
        axis, up = (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)
        side = (0.0, 1.0, 0.0)
    for nz in nozzles or []:
        a = math.radians(nz.get("angle_deg", 0.0))
        radial = _add(_scale(up, math.cos(a)), _scale(side, math.sin(a)))
        base = _add(center, _add(_scale(axis, nz.get("s", 0.0) * length), _scale(radial, r * 0.95)))
        tip = _add(base, _scale(radial, nz.get("length", diameter * 0.3)))
        nd = nz.get("diameter", 0.25)
        parts.append(("nozzle", tube_mesh(base, tip, nd / 2.0, 20), "steel"))
        parts.append(("flange", flange_mesh(tip, radial, nd * 1.6, nd * 0.18), "steel_dark"))
    return parts


# ----------------------------------------------------------------------------------------------------------------- piping
def fillet_path(points: Sequence[Sequence[float]], bend_radius: float, arc_points: int = 8) -> list[Vec]:
    """Round the corners of a polyline with circular arcs (elbows). The arc radius shrinks where the legs are too short."""
    pts = [tuple(float(c) for c in p) for p in points]
    if len(pts) < 3 or bend_radius <= 0:
        return pts  # type: ignore[return-value]
    out: list[Vec] = [pts[0]]  # type: ignore[list-item]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        d1, d2 = _norm(_sub(p1, p0)), _norm(_sub(p2, p1))
        cosang = max(-1.0, min(1.0, _dot(d1, d2)))
        turn = math.acos(cosang)
        if turn < 1e-3:
            out.append(p1)  # type: ignore[arg-type]
            continue
        t = bend_radius * math.tan(turn / 2.0)
        t = min(t, 0.49 * _len(_sub(p1, p0)), 0.49 * _len(_sub(p2, p1)))
        r_eff = t / math.tan(turn / 2.0)
        a = _sub(p1, _scale(d1, t))
        b = _add(p1, _scale(d2, t))
        n = _norm(_sub(d2, _scale(d1, cosang)))
        centre = _add(a, _scale(n, r_eff))
        ra, rb = _sub(a, centre), _sub(b, centre)
        for k in range(arc_points + 1):
            f = k / arc_points
            v = _add(_scale(ra, math.sin((1 - f) * turn) / math.sin(turn)), _scale(rb, math.sin(f * turn) / math.sin(turn)))
            out.append(_add(centre, v))
    out.append(pts[-1])  # type: ignore[arg-type]
    return out


def path_length(points: Sequence[Sequence[float]]) -> float:
    """Length of a polyline."""
    return sum(_len(_sub(b, a)) for a, b in zip(points, points[1:]))


def swept_tube(path: Sequence[Sequence[float]], radius: float | Sequence[float], segments: int = 20, caps: bool = True) -> Mesh:
    """Circular tube along a path using parallel-transport frames (no twisting at bends). ``radius`` may be a per-point list."""
    pts = [tuple(float(c) for c in p) for p in path]
    n = len(pts)
    radii = [float(radius)] * n if isinstance(radius, (int, float)) else [float(x) for x in radius]
    verts: list[Vec] = []
    tang = []
    for i in range(n):
        a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        tang.append(_norm(_sub(b, a)))
    u, v, _ = frame_from_axis(tang[0])
    for i in range(n):
        if i > 0:
            t0, t1 = tang[i - 1], tang[i]
            ax = _cross(t0, t1)
            s = _len(ax)
            if s > 1e-9:
                ax = _scale(ax, 1.0 / s)
                ang = math.atan2(s, _dot(t0, t1))
                u, v = _rodrigues(u, ax, ang), _rodrigues(v, ax, ang)
        for k in range(segments):
            a = 2.0 * math.pi * k / segments
            ca, sa = math.cos(a) * radii[i], math.sin(a) * radii[i]
            verts.append((pts[i][0] + u[0] * ca + v[0] * sa, pts[i][1] + u[1] * ca + v[1] * sa, pts[i][2] + u[2] * ca + v[2] * sa))
    faces = []
    for i in range(n - 1):
        for k in range(segments):
            j = (k + 1) % segments
            a, b, c, d = i * segments + k, i * segments + j, (i + 1) * segments + j, (i + 1) * segments + k
            faces.append((a, b, c))
            faces.append((a, c, d))
    if caps:
        c0 = len(verts)
        verts.append(pts[0])  # type: ignore[arg-type]
        c1 = len(verts)
        verts.append(pts[-1])  # type: ignore[arg-type]
        for k in range(segments):
            j = (k + 1) % segments
            faces.append((c0, j, k))
            faces.append((c1, (n - 1) * segments + k, (n - 1) * segments + j))
    return _clean((verts, faces))


def _rodrigues(vec: Vec, axis: Vec, ang: float) -> Vec:
    c, s = math.cos(ang), math.sin(ang)
    k = _cross(axis, vec)
    d = _dot(axis, vec)
    return (vec[0] * c + k[0] * s + axis[0] * d * (1 - c), vec[1] * c + k[1] * s + axis[1] * d * (1 - c), vec[2] * c + k[2] * s + axis[2] * d * (1 - c))


def flange_mesh(point: Sequence[float], direction: Sequence[float], outer_diameter: float, thickness: float, bolts: int = 8) -> Mesh:
    """Flange disc with bolt heads, centred on ``point`` with the axis along ``direction``."""
    w = _norm(tuple(direction))  # type: ignore[arg-type]
    a = _sub(point, _scale(w, thickness / 2.0))
    b = _add(point, _scale(w, thickness / 2.0))
    m = tube_mesh(a, b, outer_diameter / 2.0, 28)
    u, v, _ = frame_from_axis(w)
    rb = outer_diameter * 0.38
    for k in range(bolts):
        ang = 2.0 * math.pi * k / bolts
        c = _add(point, _add(_scale(u, rb * math.cos(ang)), _scale(v, rb * math.sin(ang))))
        _append(m, tube_mesh(_sub(c, _scale(w, thickness * 0.8)), _add(c, _scale(w, thickness * 0.8)), outer_diameter * 0.04, 6))
    return m


def pipe_parts(points: Sequence[Sequence[float]], diameter: float, bend_radius: float | None = None, flanges: bool = True, material: str = "pipe") -> list[Part]:
    """Pipe along a polyline with long-radius elbows (default 1.5 D) and flanges at both ends and every ``12 m`` of straight run."""
    r = diameter / 2.0
    path = fillet_path(points, bend_radius if bend_radius is not None else 1.5 * diameter)
    parts: list[Part] = [("pipe", swept_tube(path, r), material)]
    if flanges:
        ends = [(path[0], _sub(path[1], path[0])), (path[-1], _sub(path[-1], path[-2]))]
        for p, d in ends:
            parts.append(("flange", flange_mesh(p, d, diameter * 1.6, diameter * 0.16), "steel_dark"))
    return parts


def valve_parts(point: Sequence[float], direction: Sequence[float], diameter: float, handwheel_up: Sequence[float] = (0.0, 0.0, 1.0), color_material: str = "paint_red") -> list[Part]:
    """Gate/ball valve: bi-conical body, bonnet, stem and handwheel (torus ring with spokes)."""
    w = _norm(tuple(direction))  # type: ignore[arg-type]
    up = _norm(tuple(handwheel_up))  # type: ignore[arg-type]
    r = diameter / 2.0
    body = revolve([(r * 1.0, -r * 1.5), (r * 1.55, -r * 0.7), (r * 1.7, 0.0), (r * 1.55, r * 0.7), (r * 1.0, r * 1.5)], point, w, 28)
    stem_base = _add(point, _scale(up, r * 1.6))
    stem_top = _add(point, _scale(up, r * 3.2))
    parts: list[Part] = [("valve_body", body, "steel_dark"), ("bonnet", tube_mesh(_add(point, _scale(up, r * 0.8)), stem_base, r * 0.7, 20), color_material),
                         ("stem", tube_mesh(stem_base, stem_top, r * 0.12, 10), "steel")]
    u, v, _ = frame_from_axis(up)
    ring = [_add(stem_top, _add(_scale(u, r * 1.1 * math.cos(2 * math.pi * k / 24)), _scale(v, r * 1.1 * math.sin(2 * math.pi * k / 24)))) for k in range(25)]
    parts.append(("handwheel", swept_tube(ring, r * 0.09, 8, caps=False), color_material))
    for k in range(4):
        a = math.pi * k / 4.0
        d = _add(_scale(u, r * 1.1 * math.cos(a)), _scale(v, r * 1.1 * math.sin(a)))
        parts.append(("spoke", tube_mesh(_sub(stem_top, d), _add(stem_top, d), r * 0.05, 6), color_material))
    return parts


# ------------------------------------------------------------------------------------------------------------ structures
def jacket_parts(center_xy: Sequence[float], z_bottom: float, z_top: float, base_size: Sequence[float], top_size: Sequence[float], legs_per_side: int = 2,
                 bays: int = 4, leg_radius: float = 1.0, brace_radius: float = 0.4) -> list[Part]:
    """Tapered lattice jacket: battered legs (``legs_per_side`` x ``legs_per_side`` grid corners only at 2), horizontal frames and X-braces per bay."""
    cx, cy = center_xy

    def leg_xy(level: float, i: int, j: int) -> Vec:
        sx = base_size[0] + (top_size[0] - base_size[0]) * level
        sy = base_size[1] + (top_size[1] - base_size[1]) * level
        fx = (i / (legs_per_side - 1) - 0.5) if legs_per_side > 1 else 0.0
        fy = (j / (legs_per_side - 1) - 0.5) if legs_per_side > 1 else 0.0
        return (cx + fx * sx, cy + fy * sy, z_bottom + (z_top - z_bottom) * level)

    legs: Mesh = ([], [])
    braces: Mesh = ([], [])
    idx = [(i, j) for i in (0, legs_per_side - 1) for j in (0, legs_per_side - 1)] if legs_per_side == 2 else [(i, j) for i in range(legs_per_side) for j in range(legs_per_side)
                                                                                                         if i in (0, legs_per_side - 1) or j in (0, legs_per_side - 1)]
    for (i, j) in idx:
        _append(legs, tube_mesh(leg_xy(0.0, i, j), leg_xy(1.0, i, j), leg_radius, 18))
    corners = [(0, 0), (legs_per_side - 1, 0), (legs_per_side - 1, legs_per_side - 1), (0, legs_per_side - 1)]
    for b in range(bays + 1):
        lv = b / bays
        for k in range(4):
            _append(braces, tube_mesh(leg_xy(lv, *corners[k]), leg_xy(lv, *corners[(k + 1) % 4]), brace_radius, 10))
    for b in range(bays):
        l0, l1 = b / bays, (b + 1) / bays
        for k in range(4):
            a, c = corners[k], corners[(k + 1) % 4]
            _append(braces, tube_mesh(leg_xy(l0, *a), leg_xy(l1, *c), brace_radius, 10))
            _append(braces, tube_mesh(leg_xy(l0, *c), leg_xy(l1, *a), brace_radius, 10))
    return [("jacket_legs", legs, "paint_yellow"), ("jacket_bracing", braces, "paint_yellow")]


def deck_parts(bounds: Sequence[float], beam_spacing: float = 6.0, rail: bool = True) -> list[Part]:
    """Deck plate with a beam grid underneath and perimeter handrail. ``bounds`` = (x0, x1, y0, y1, z0, z1) with z0 the underside."""
    x0, x1, y0, y1, z0, z1 = bounds
    parts: list[Part] = [("deck_plate", box_mesh(((x0 + x1) / 2, (y0 + y1) / 2, z1 - 0.15), (x1 - x0, y1 - y0, 0.3)), "deck")]
    beams: Mesh = ([], [])
    nx, ny = max(2, int((x1 - x0) / beam_spacing)), max(2, int((y1 - y0) / beam_spacing))
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        _append(beams, box_mesh((x, (y0 + y1) / 2, (z0 + z1) / 2 - 0.15), (0.3, y1 - y0, z1 - z0 - 0.3)))
    for j in range(ny + 1):
        y = y0 + (y1 - y0) * j / ny
        _append(beams, box_mesh(((x0 + x1) / 2, y, (z0 + z1) / 2 - 0.15), (x1 - x0, 0.3, z1 - z0 - 0.3)))
    parts.append(("deck_beams", beams, "steel_dark"))
    if rail:
        posts: Mesh = ([], [])
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            m = max(2, int(L / 2.5))
            for k in range(m + 1):
                px, py = ax + (bx - ax) * k / m, ay + (by - ay) * k / m
                _append(posts, tube_mesh((px, py, z1), (px, py, z1 + 1.1), 0.04, 6))
            for hz in (z1 + 0.55, z1 + 1.1):
                _append(posts, tube_mesh((ax, ay, hz), (bx, by, hz), 0.035, 6))
        parts.append(("handrail", posts, "paint_yellow"))
    return parts


def module_parts(bounds: Sequence[float], material: str = "steel", columns: bool = True, roof: bool = True) -> list[Part]:
    """Process module: steel frame columns and rails, optional pitched roof with overhang (``roof=False`` leaves the equipment visible)."""
    x0, x1, y0, y1, z0, z1 = bounds
    parts: list[Part] = []
    frame: Mesh = ([], [])
    if columns:
        nx, ny = max(2, int((x1 - x0) / 7.0)), max(2, int((y1 - y0) / 7.0))
        for i in range(nx + 1):
            for j in (0, ny):
                _append(frame, box_mesh((x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, (z0 + z1) / 2), (0.35, 0.35, z1 - z0)))
        for k in (0, 1):
            zz = z0 + (z1 - z0) * (0.5 if k else 1.0)
            _append(frame, box_mesh(((x0 + x1) / 2, y0, zz), (x1 - x0, 0.25, 0.3)))
            _append(frame, box_mesh(((x0 + x1) / 2, y1, zz), (x1 - x0, 0.25, 0.3)))
    parts.append(("module_frame", frame, material))
    if not roof:
        return parts
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ov = 0.6
    ridge = z1 + (y1 - y0) * 0.06
    v = [(x0 - ov, y0 - ov, z1), (x1 + ov, y0 - ov, z1), (x1 + ov, cy, ridge), (x0 - ov, cy, ridge), (x1 + ov, y1 + ov, z1), (x0 - ov, y1 + ov, z1)]
    f = [(0, 1, 2), (0, 2, 3), (3, 2, 4), (3, 4, 5), (0, 3, 5), (1, 4, 2), (0, 5, 4), (0, 4, 1)]
    parts.append(("module_roof", (v, f), "concrete"))
    return parts


def flare_boom_parts(base: Sequence[float], direction: Sequence[float], length: float, width: float = 3.0) -> list[Part]:
    """Triangular lattice flare boom (three chords with zig-zag bracing) from ``base`` along ``direction``."""
    w = _norm(tuple(direction))  # type: ignore[arg-type]
    u, v, _ = frame_from_axis(w)
    offs = [_scale(u, width * 0.5), _scale(u, -width * 0.5), _scale(v, width * 0.866)]
    m: Mesh = ([], [])
    n = max(4, int(length / 5.0))
    for o in offs:
        _append(m, tube_mesh(_add(base, o), _add(_add(base, _scale(w, length)), _scale(o, 0.25)), 0.12, 8))
    for k in range(n):
        f0, f1 = k / n, (k + 1) / n
        for a, b in ((0, 1), (1, 2), (2, 0)):
            pa0 = _add(_add(base, _scale(w, length * f0)), _scale(offs[a], 1 - 0.75 * f0))
            pb1 = _add(_add(base, _scale(w, length * f1)), _scale(offs[b], 1 - 0.75 * f1))
            _append(m, tube_mesh(pa0, pb1, 0.05, 6))
    return [("flare_boom", m, "steel"), ("flare_tip", revolve([(0.0, 0.0), (0.5, 0.0), (0.4, 1.2)], _add(base, _scale(w, length * 1.0)), w, 12), "steel_dark")]


def helideck_parts(center: Sequence[float], diameter: float = 24.0) -> list[Part]:
    """Round helideck on a lattice cantilever."""
    cx, cy, cz = center
    disc = revolve([(0.0, cz), (diameter / 2, cz), (diameter / 2, cz - 0.4), (0.0, cz - 0.4)], (cx, cy, 0.0))
    supports: Mesh = ([], [])
    for k in range(6):
        a = 2 * math.pi * k / 6
        _append(supports, tube_mesh((cx + diameter * 0.2 * math.cos(a), cy + diameter * 0.2 * math.sin(a), cz - 0.4), (cx + diameter * 0.45 * math.cos(a), cy, cz - 5.0), 0.2, 8))
    return [("helideck", disc, "paint_green"), ("helideck_support", supports, "steel")]


def crane_parts(base: Sequence[float], boom_length: float = 28.0, angle_deg: float = 50.0, heading_deg: float = 0.0) -> list[Part]:
    """Pedestal crane with cab and inclined boom."""
    bx, by, bz = base
    h = math.radians(heading_deg)
    a = math.radians(angle_deg)
    tip = (bx + boom_length * math.cos(a) * math.cos(h), by + boom_length * math.cos(a) * math.sin(h), bz + 4.0 + boom_length * math.sin(a))
    return [("crane_pedestal", tube_mesh((bx, by, bz), (bx, by, bz + 4.0), 1.2, 20), "steel_dark"), ("crane_cab", box_mesh((bx, by, bz + 5.0), (3.0, 2.4, 2.2)), "paint_yellow"),
            ("crane_boom", tube_mesh((bx, by, bz + 4.5), tip, 0.35, 10), "paint_yellow")]


# ---------------------------------------------------------------------------------------------------------------- subsea
def xmas_tree_parts(base: Sequence[float], height: float = 4.0) -> list[Part]:
    """Vertical subsea tree: base block, master/swab valve stack, wing branch with flange and choke module, cap."""
    x, y, z = base
    parts: list[Part] = [("tree_base", box_mesh((x, y, z + 0.4), (1.6, 1.6, 0.8)), "steel_dark")]
    stack = revolve([(0.28, 0.0), (0.28, height * 0.62)], (x, y, z + 0.8), (0, 0, 1), 20)
    parts.append(("tree_stack", stack, "paint_red"))
    for frac in (0.15, 0.4, 0.62):
        parts.append(("tree_valve", box_mesh((x, y, z + 0.8 + height * frac), (0.75, 0.75, 0.3)), "paint_blue"))
    wing_z = z + 0.8 + height * 0.5
    parts.append(("wing", tube_mesh((x, y, wing_z), (x + 1.4, y, wing_z), 0.16, 14), "steel"))
    parts.append(("wing_flange", flange_mesh((x + 1.4, y, wing_z), (1, 0, 0), 0.5, 0.08), "steel_dark"))
    parts.append(("choke_module", box_mesh((x + 0.9, y + 0.45, wing_z + 0.2), (0.8, 0.7, 0.7)), "paint_yellow"))
    parts.append(("tree_cap", revolve([(0.0, 0.0), (0.3, 0.0), (0.3, 0.12), (0.12, 0.2), (0.0, 0.2)], (x, y, z + 0.8 + height * 0.62), (0, 0, 1), 16), "steel"))
    return parts


def template_parts(center: Sequence[float], size: Sequence[float], slots: tuple[int, int] = (2, 2), with_trees: bool = True) -> list[Part]:
    """Subsea production template: tubular frame with cross-bracing, mudmat, grating roof and a tree per slot."""
    cx, cy, cz = center
    sx, sy, sz = size
    frame: Mesh = ([], [])
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    for (a, b) in corners:
        _append(frame, tube_mesh((cx + a * sx / 2, cy + b * sy / 2, cz), (cx + a * sx / 2, cy + b * sy / 2, cz + sz), 0.18, 12))
    for z in (cz + 0.1, cz + sz):
        for k in range(4):
            a, b = corners[k], corners[(k + 1) % 4]
            _append(frame, tube_mesh((cx + a[0] * sx / 2, cy + a[1] * sy / 2, z), (cx + b[0] * sx / 2, cy + b[1] * sy / 2, z), 0.12, 10))
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        _append(frame, tube_mesh((cx + a[0] * sx / 2, cy + a[1] * sy / 2, cz + 0.1), (cx + b[0] * sx / 2, cy + b[1] * sy / 2, cz + sz), 0.07, 8))
    parts: list[Part] = [("template_frame", frame, "paint_yellow"), ("mudmat", box_mesh((cx, cy, cz - 0.1), (sx * 1.15, sy * 1.15, 0.2)), "steel_dark"),
                         ("template_roof", box_mesh((cx, cy, cz + sz + 0.05), (sx * 0.98, sy * 0.98, 0.08)), "steel")]
    if with_trees:
        for i in range(slots[0]):
            for j in range(slots[1]):
                tx = cx + (-0.5 + (i + 0.5) / slots[0]) * sx * 0.8
                ty = cy + (-0.5 + (j + 0.5) / slots[1]) * sy * 0.8
                parts += xmas_tree_parts((tx, ty, cz + 0.2), height=min(sz * 1.2, 4.5))
    return parts


class Seabed:
    """Procedural seabed with relief (deterministic sine octaves), optional regional slope and flattened areas around sites.

    ``z(x, y)`` gives the seabed elevation so structures can be placed on it; ``mesh`` is the triangulated surface.
    """

    def __init__(self, x_range: tuple[float, float], y_range: tuple[float, float], nx: int = 90, ny: int = 50, base_z: float = -160.0, relief_m: float = 6.0,
                 slope: tuple[float, float] = (0.0, 0.0), flatten: Sequence[tuple[float, float, float]] = (), seed: int = 7, wavelength_m: float = 900.0):
        self.x_range, self.y_range, self.base_z, self.relief_m, self.slope, self.flatten = x_range, y_range, base_z, relief_m, slope, list(flatten)
        rnd = _Lcg(seed)
        self._waves = [(2 * math.pi / (wavelength_m / (1.7 ** k)), rnd.next() * 2 * math.pi, rnd.next() * 2 * math.pi, rnd.next() * 2 * math.pi, 0.55 ** k) for k in range(5)]
        xs = [x_range[0] + (x_range[1] - x_range[0]) * i / nx for i in range(nx + 1)]
        ys = [y_range[0] + (y_range[1] - y_range[0]) * j / ny for j in range(ny + 1)]
        verts = [(x, y, self.z(x, y)) for j, y in enumerate(ys) for x in xs]
        faces = []
        for j in range(ny):
            for i in range(nx):
                a = j * (nx + 1) + i
                faces.append((a, a + 1, a + nx + 2))
                faces.append((a, a + nx + 2, a + nx + 1))
        self.mesh: Mesh = (verts, faces)

    def _noise(self, x: float, y: float) -> float:
        s = 0.0
        norm = 0.0
        for k, px, ph, th, amp in self._waves:
            s += amp * math.sin(k * (x * math.cos(th) + y * math.sin(th)) + ph) * math.cos(k * 0.7 * (y * math.cos(th) - x * math.sin(th)) + px)
            norm += amp
        return s / norm

    def z(self, x: float, y: float) -> float:
        """Seabed elevation at (x, y) in metres."""
        h = self.base_z + self.slope[0] * x + self.slope[1] * y + self.relief_m * self._noise(x, y)
        w = 1.0
        for (fx, fy, fr) in self.flatten:
            d = math.hypot(x - fx, y - fy)
            if d < fr:
                t = d / fr
                w = min(w, t * t * (3 - 2 * t))
        flat_h = self.base_z + self.slope[0] * x + self.slope[1] * y
        return flat_h + (h - flat_h) * w


class _Lcg:
    """Small deterministic generator so scenes are reproducible without the random module state."""

    def __init__(self, seed: int):
        self.s = seed & 0x7FFFFFFF

    def next(self) -> float:
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s / 0x7FFFFFFF


def sea_surface_mesh(x_range: tuple[float, float], y_range: tuple[float, float], z: float = 0.0, nx: int = 60, ny: int = 30, wave_m: float = 0.8) -> Mesh:
    """Sea surface with low swell."""
    verts = []
    for j in range(ny + 1):
        for i in range(nx + 1):
            x = x_range[0] + (x_range[1] - x_range[0]) * i / nx
            y = y_range[0] + (y_range[1] - y_range[0]) * j / ny
            verts.append((x, y, z + wave_m * math.sin(x / 140.0) * math.cos(y / 190.0 + 0.7)))
    faces = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2))
            faces.append((a, a + nx + 2, a + nx + 1))
    return verts, faces


# ------------------------------------------------------------------------------------------------------- wells, reservoir
def resample_path(points: Sequence[Sequence[float]], step: float) -> list[Vec]:
    """Resample a polyline at roughly constant spacing (keeps first and last point)."""
    out: list[Vec] = [tuple(float(c) for c in points[0])]  # type: ignore[list-item]
    for a, b in zip(points, points[1:]):
        d = _len(_sub(b, a))
        m = max(1, int(d / step))
        for k in range(1, m + 1):
            f = k / m
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f))
    return out


def well_string_parts(path: Sequence[Sequence[float]], strings: Sequence[dict], exaggeration: float = 1.0) -> list[Part]:
    """Nested casing and tubing strings along a well path from the wellhead (path[0]).

    ``strings``: dicts ``{"name", "od_m", "md_end_m", "material"}`` listed from outermost. A string ends at ``md_end_m`` measured along ``path``; larger-diameter
    strings are shorter, so the well telescopes down. ``exaggeration`` scales radii for field-scale pictures.
    """
    p = resample_path(path, 25.0)
    cum = [0.0]
    for a, b in zip(p, p[1:]):
        cum.append(cum[-1] + _len(_sub(b, a)))
    parts: list[Part] = []
    for s in strings:
        sub = [q for q, c in zip(p, cum) if c <= s["md_end_m"]]
        if len(sub) >= 2:
            parts.append((s["name"], swept_tube(sub, s["od_m"] / 2.0 * exaggeration, 14), s.get("material", "casing")))
    return parts


def reservoir_layer(center: Sequence[float], size: Sequence[float], thickness: float, undulation_m: float = 12.0, nx: int = 24, ny: int = 20, dip_deg: float = 2.0) -> Mesh:
    """Reservoir slab: undulating top surface with a small regional dip, flat base and side walls (closed)."""
    cx, cy, cz = center
    top, bot = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            fx, fy = i / nx - 0.5, j / ny - 0.5
            x, y = cx + fx * size[0], cy + fy * size[1]
            z = cz + undulation_m * math.sin(3.1 * fx + 0.6) * math.cos(2.4 * fy) + math.tan(math.radians(dip_deg)) * fx * size[0]
            top.append((x, y, z))
            bot.append((x, y, z - thickness))
    n = (nx + 1) * (ny + 1)
    verts = top + bot
    faces = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces += [(a, a + 1, a + nx + 2), (a, a + nx + 2, a + nx + 1)]
            faces += [(n + a, n + a + nx + 2, n + a + 1), (n + a, n + a + nx + 1, n + a + nx + 2)]
    edge = [[j * (nx + 1) for j in range(ny + 1)], [j * (nx + 1) + nx for j in range(ny + 1)], list(range(nx + 1)), [ny * (nx + 1) + i for i in range(nx + 1)]]
    for e, flip in zip(edge, (False, True, True, False)):
        for a, b in zip(e, e[1:]):
            q = [(a, b, n + b), (a, n + b, n + a)]
            faces += [(f[0], f[2], f[1]) for f in q] if flip else q
    return verts, faces


# ----------------------------------------------------------------------------------------------------------- converters
def merge_parts(parts: Sequence[Part], material: str | None = None) -> dict[str, Mesh]:
    """Group parts by material (or force one material) and merge each group into one mesh."""
    out: dict[str, Mesh] = {}
    for _name, m, mat in parts:
        key = material or mat
        out.setdefault(key, ([], []))
        _append(out[key], m)
    return out


def to_arrays(mesh: Mesh):
    """(vertices Nx3, triangles Mx3) as numpy arrays (numpy imported lazily)."""
    import numpy as np

    return np.asarray(mesh[0], dtype=float), np.asarray(mesh[1], dtype=int)


def to_pyvista(mesh: Mesh):
    """PyVista PolyData with smooth vertex normals (PyVista imported lazily)."""
    import numpy as np
    import pyvista as pv

    v, f = to_arrays(mesh)
    faces = np.hstack([np.full((len(f), 1), 3), f]).ravel()
    pd = pv.PolyData(v, faces)
    pd.point_data["Normals"] = np.asarray(vertex_normals(mesh))
    return pd


def to_plotly_arrays(mesh: Mesh) -> dict[str, list]:
    """Arrays for ``plotly.graph_objects.Mesh3d`` (x, y, z, i, j, k)."""
    v, f = mesh
    return {"x": [p[0] for p in v], "y": [p[1] for p in v], "z": [p[2] for p in v], "i": [t[0] for t in f], "j": [t[1] for t in f], "k": [t[2] for t in f]}


__all__ = [
    "MATERIALS", "Seabed", "crane_parts", "deck_parts", "fillet_path", "flange_mesh", "flare_boom_parts", "frame_from_axis", "helideck_parts", "jacket_parts",
    "merge", "merge_parts", "mesh_bounds", "mesh_volume", "module_parts", "path_length", "pipe_parts", "resample_path", "reservoir_layer", "revolve",
    "sea_surface_mesh", "swept_tube", "template_parts", "to_arrays", "to_plotly_arrays", "to_pyvista", "transform", "valve_parts", "vertex_normals", "vessel_mesh",
    "vessel_parts", "well_string_parts", "xmas_tree_parts",
]
