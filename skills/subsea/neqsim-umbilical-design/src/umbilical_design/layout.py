"""Cross-section geometry: circle packing of the functional elements and armour wire positions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from .runner import DesignResult

STRANDING_FILL = 0.9  # same compaction factor as the NeqSim conductor model


@dataclass
class PlacedCircle:
    index: int
    x: float
    y: float
    radius: float


def _tangent_positions(a: PlacedCircle, b: PlacedCircle, r: float) -> List[Tuple[float, float]]:
    """Centres of a circle of radius r that touches both a and b externally."""
    da = a.radius + r
    db = b.radius + r
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy)
    if d == 0 or d > da + db or d < abs(da - db):
        return []
    t = (da * da - db * db + d * d) / (2.0 * d)
    h2 = da * da - t * t
    if h2 < 0:
        return []
    h = math.sqrt(h2)
    mx, my = a.x + t * dx / d, a.y + t * dy / d
    return [(mx + h * dy / d, my - h * dx / d), (mx - h * dy / d, my + h * dx / d)]


def _free(x: float, y: float, r: float, placed: Sequence[PlacedCircle], tol: float = 1e-9) -> bool:
    return all(math.hypot(x - p.x, y - p.y) >= r + p.radius - tol for p in placed)


def pack_circles(diameters: Sequence[float]) -> Tuple[List[PlacedCircle], Tuple[float, float, float]]:
    """Greedy tangent packing, largest first, minimising the farthest extent from the centroid.

    Returns the placed circles (in input order) and the enclosing circle ``(cx, cy, R)``.
    """
    n = len(diameters)
    if n == 0:
        return [], (0.0, 0.0, 0.0)
    order = sorted(range(n), key=lambda i: -diameters[i])
    placed: List[PlacedCircle] = [PlacedCircle(order[0], 0.0, 0.0, diameters[order[0]] / 2.0)]
    for idx in order[1:]:
        r = diameters[idx] / 2.0
        candidates: List[Tuple[float, float]] = []
        if len(placed) == 1:
            candidates = [(placed[0].radius + r, 0.0)]
        else:
            for i in range(len(placed)):
                for j in range(i + 1, len(placed)):
                    candidates.extend(_tangent_positions(placed[i], placed[j], r))
        cx = sum(p.x * p.radius**2 for p in placed) / sum(p.radius**2 for p in placed)
        cy = sum(p.y * p.radius**2 for p in placed) / sum(p.radius**2 for p in placed)
        best = None
        best_score = float("inf")
        for x, y in candidates:
            if not _free(x, y, r, placed):
                continue
            score = max(
                [math.hypot(x - cx, y - cy) + r]
                + [math.hypot(p.x - cx, p.y - cy) + p.radius for p in placed]
            )
            if score < best_score:
                best, best_score = (x, y), score
        if best is None:
            far = max(math.hypot(p.x, p.y) + p.radius for p in placed)
            best = (far + r, 0.0)
        placed.append(PlacedCircle(idx, best[0], best[1], r))
    centre = _enclosing_centre(placed)
    for p in placed:
        p.x -= centre[0]
        p.y -= centre[1]
    placed.sort(key=lambda p: p.index)
    return placed, (0.0, 0.0, centre[2])


def _enclosing_centre(placed: Sequence[PlacedCircle]) -> Tuple[float, float, float]:
    """Badoiu-Clarkson iteration for the centre of a small enclosing circle."""
    cx = sum(p.x for p in placed) / len(placed)
    cy = sum(p.y for p in placed) / len(placed)
    for k in range(1, 400):
        far = max(placed, key=lambda p: math.hypot(p.x - cx, p.y - cy) + p.radius)
        d = math.hypot(far.x - cx, far.y - cy)
        if d == 0:
            break
        step = 1.0 / (k + 1.0)
        cx += (far.x - cx) * step
        cy += (far.y - cy) * step
    radius = max(math.hypot(p.x - cx, p.y - cy) + p.radius for p in placed)
    return cx, cy, radius


def conductor_diameter_mm(area_mm2: float) -> float:
    return math.sqrt(4.0 * area_mm2 / (math.pi * STRANDING_FILL))


def armor_wire_count(layer_diameter_mm: float, wire_diameter_mm: float, lay_angle_deg: float) -> int:
    return int(math.floor(math.pi * layer_diameter_mm * math.cos(math.radians(lay_angle_deg)) / wire_diameter_mm))


def cross_section_layout(result: DesignResult) -> Dict[str, Any]:
    """Geometry for drawing: element circles, bundle, sheaths and armour wire positions (mm).

    The element placement is an independent circle packing. ``packing_ratio`` is the packed
    bundle diameter divided by the NeqSim bundle diameter; a value above about 1.1 means the
    NeqSim packing-efficiency estimate was optimistic for this element mix.
    """
    data = result.data
    xs = data["crossSection"]
    elements = result.elements
    diameters = [float(e["outerDiameterMm"]) for e in elements]
    placed, (_, _, radius) = pack_circles(diameters)
    bundle_d = float(xs["bundleDiameterMm"])
    packed_d = 2.0 * radius

    drawn = []
    for p, e in zip(placed, elements):
        item = {
            "name": e["name"],
            "type": e["type"],
            "x": p.x,
            "y": p.y,
            "radius": p.radius,
            "cores": [],
        }
        if e["type"] == "electrical":
            d_cond = conductor_diameter_mm(float(e["conductorAreaMm2"]))
            d_core = d_cond + 2.0 * float(e["insulationThicknessMm"])
            n = int(e["cores"])
            sub, _ = pack_circles([d_core] * n)
            # centre the cores in the cable circle
            item["cores"] = [
                {"x": p.x + s.x, "y": p.y + s.y, "radius": d_core / 2.0, "conductor_radius": d_cond / 2.0}
                for s in sub
            ]
        drawn.append(item)

    core_d = bundle_d + 2.0 * float(xs["innerSheathThicknessMm"])
    layers = int(xs["armorLayers"])
    wire_d = float(xs["armorWireDiameterMm"])
    angle = float(xs["armorLayAngleDeg"])
    wires = []
    for i in range(layers):
        layer_d = core_d + wire_d * (1.0 + 2.0 * i)
        n = armor_wire_count(layer_d, wire_d, angle)
        for k in range(n):
            a = 2.0 * math.pi * k / max(n, 1) + (math.pi / max(n, 1) if i % 2 else 0.0)
            wires.append(
                {"x": layer_d / 2.0 * math.cos(a), "y": layer_d / 2.0 * math.sin(a), "radius": wire_d / 2.0, "layer": i}
            )
    return {
        "elements": drawn,
        "bundle_radius": bundle_d / 2.0,
        "packed_bundle_radius": radius,
        "packing_ratio": packed_d / bundle_d if bundle_d > 0 else float("nan"),
        "core_radius": core_d / 2.0,
        "armor_wires": wires,
        "armor_outer_radius": core_d / 2.0 + layers * wire_d,
        "overall_radius": float(xs["overallDiameterMm"]) / 2.0,
    }
