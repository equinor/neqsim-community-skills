"""Triangle meshes for scene geometries (shared by the GLB, HTML and PNG renderers)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

Vec = tuple[float, float, float]
Mesh = tuple[list[Vec], list[tuple[int, int, int]]]


def _sub(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec) -> Vec:
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 0 else (0.0, 0.0, 1.0)


def box_mesh(center: Sequence[float], size: Sequence[float]) -> Mesh:
    """Closed axis-aligned box, outward-wound triangles."""
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    v = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    f = [
        (0, 2, 1),
        (0, 3, 2),  # bottom
        (4, 5, 6),
        (4, 6, 7),  # top
        (0, 1, 5),
        (0, 5, 4),  # -y
        (1, 2, 6),
        (1, 6, 5),  # +x
        (2, 3, 7),
        (2, 7, 6),  # +y
        (3, 0, 4),
        (3, 4, 7),  # -x
    ]
    return v, f


def tube_mesh(
    start: Sequence[float],
    end: Sequence[float],
    radius: float,
    segments: int = 12,
    caps: bool = True,
) -> Mesh:
    """Cylinder between two points with optional end caps."""
    axis = _sub(end, start)
    if math.sqrt(sum(c * c for c in axis)) == 0.0:
        return [], []
    w = _norm(axis)
    helper = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm(_cross(w, helper))
    vv = _cross(w, u)
    verts: list[Vec] = []
    for base in (start, end):
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            ca, sa = math.cos(a) * radius, math.sin(a) * radius
            verts.append(
                (
                    base[0] + u[0] * ca + vv[0] * sa,
                    base[1] + u[1] * ca + vv[1] * sa,
                    base[2] + u[2] * ca + vv[2] * sa,
                )
            )
    faces: list[tuple[int, int, int]] = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j))
        faces.append((i, segments + j, segments + i))
    if caps:
        c0 = len(verts)
        verts.append(tuple(float(c) for c in start))
        c1 = len(verts)
        verts.append(tuple(float(c) for c in end))
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((c0, j, i))
            faces.append((c1, segments + i, segments + j))
    return verts, faces


def sphere_mesh(
    center: Sequence[float], radius: float, rings: int = 8, segments: int = 12
) -> Mesh:
    """Low-poly UV sphere."""
    verts: list[Vec] = []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(segments):
            th = 2.0 * math.pi * s / segments
            verts.append(
                (
                    center[0] + radius * math.sin(phi) * math.cos(th),
                    center[1] + radius * math.sin(phi) * math.sin(th),
                    center[2] + radius * math.cos(phi),
                )
            )
    faces: list[tuple[int, int, int]] = []
    for r in range(rings):
        for s in range(segments):
            a = r * segments + s
            b = r * segments + (s + 1) % segments
            c = (r + 1) * segments + (s + 1) % segments
            d = (r + 1) * segments + s
            faces.append((a, d, c))
            faces.append((a, c, b))
    return verts, faces


def octahedron_mesh(center: Sequence[float], size: float) -> Mesh:
    """Marker for point objects."""
    h = size / 2.0
    cx, cy, cz = center
    v = [
        (cx + h, cy, cz),
        (cx - h, cy, cz),
        (cx, cy + h, cz),
        (cx, cy - h, cz),
        (cx, cy, cz + h),
        (cx, cy, cz - h),
    ]
    f = [
        (0, 2, 4),
        (2, 1, 4),
        (1, 3, 4),
        (3, 0, 4),
        (2, 0, 5),
        (1, 2, 5),
        (3, 1, 5),
        (0, 3, 5),
    ]
    return v, f


def _append(target: Mesh, part: Mesh) -> None:
    offset = len(target[0])
    target[0].extend(part[0])
    target[1].extend((a + offset, b + offset, c + offset) for a, b, c in part[1])


def geometry_mesh(geometry: dict[str, Any], segments: int = 12) -> Mesh:
    """Triangle mesh of one scene geometry."""
    shape = geometry["shape"]
    if shape == "box":
        return box_mesh(geometry["center"], geometry["size"])
    if shape == "cylinder":
        c = geometry["center"]
        h = geometry["length"] / 2.0
        idx = {"x": 0, "y": 1, "z": 2}[geometry.get("axis", "z")]
        a = list(c)
        b = list(c)
        a[idx] -= h
        b[idx] += h
        return tube_mesh(a, b, geometry["diameter"] / 2.0, segments)
    if shape == "sphere":
        return sphere_mesh(
            geometry["center"], geometry["diameter"] / 2.0, segments=segments
        )
    if shape == "polyline":
        mesh: Mesh = ([], [])
        pts = geometry["points"]
        r = geometry["diameter"] / 2.0
        for a, b in itertools.pairwise(pts):
            _append(mesh, tube_mesh(a, b, r, max(6, segments // 2)))
        return mesh
    return octahedron_mesh(geometry["center"], geometry.get("size", 1.0))


def scale_z(mesh: Mesh, factor: float) -> Mesh:
    """Vertical exaggeration for presentation (wells and seabed are flat at field scale)."""
    if factor == 1.0:
        return mesh
    return [(x, y, z * factor) for x, y, z in mesh[0]], mesh[1]
