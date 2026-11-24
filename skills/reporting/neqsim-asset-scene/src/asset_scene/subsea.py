"""Recognisable subsea equipment primitives: Xmas tree, PLET/PLEM, manifold, rigid jumper, flowline with field joints, SSIV/riser base and umbilical.

Builds on :mod:`asset_scene.realistic` (same ``(name, mesh, material)`` parts, metres, z up). Dimensions are typical North Sea values used for
illustration only: callers must label them *antatt/skjematisk* in the source register unless a drawing gives the real size.

Realism checklist for subsea: wellhead housing and guide frame, master and wing valves with actuators, choke body and flowline connector on a vertical
tree; mudmat with piping manifold, valves and hubs on a PLET/PLEM; headers with branch valves inside a protection frame on a manifold; jumpers as
rigid M- or W-shaped spools with 90 degree bends and connector hubs; flowline with field-joint bands every 12 m; riser base with SSIV; umbilical
(steel-tube bundle) ending in a termination head (UTA).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .mesh import Mesh, _append, box_mesh, tube_mesh
from .realistic import Part, fillet_path, flange_mesh, pipe_parts, revolve, swept_tube


def hub_parts(point: Sequence[float], direction: Sequence[float], diameter: float) -> list[Part]:
    """Clamp-connector hub: a collar with a clamp ring and bolt heads (mechanical connector)."""
    collar = tube_mesh(tuple(point[i] - 0.5 * diameter * direction[i] for i in range(3)), tuple(point[i] + 0.5 * diameter * direction[i] for i in range(3)), diameter * 0.9, 24)
    return [("hub", collar, "steel_dark"), ("clamp", flange_mesh(point, direction, diameter * 2.1, diameter * 0.35, 6), "paint_yellow")]


def xmas_tree_parts(base: Sequence[float], height: float = 4.2, heading_deg: float = 0.0) -> list[Part]:
    """Vertical Xmas tree: wellhead housing on a guide frame, production bore with lower/upper master, swab, wing valve with actuator, choke body, flowline connector hub, tree cap."""
    x, y, z = base
    h = math.radians(heading_deg)
    ux, uy = math.cos(h), math.sin(h)
    parts: list[Part] = []
    frame: Mesh = ([], [])
    for sx in (-1, 1):
        for sy in (-1, 1):
            _append(frame, tube_mesh((x + sx * 1.0, y + sy * 1.0, z), (x + sx * 1.0, y + sy * 1.0, z + height * 0.9), 0.05, 8))
    for zz in (z + 0.05, z + height * 0.9):
        for a, b in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            _append(frame, tube_mesh((x + a[0], y + a[1], zz), (x + b[0], y + b[1], zz), 0.04, 8))
    parts.append(("guide_frame", frame, "paint_yellow"))
    parts.append(("wellhead_housing", revolve([(0.55, 0.0), (0.55, 0.5), (0.4, 0.62), (0.4, 0.95)], (x, y, z), (0, 0, 1), 28), "steel_dark"))
    bore = z + 0.95
    parts.append(("bore", revolve([(0.17, 0.0), (0.17, height - 1.2)], (x, y, bore), (0, 0, 1), 20), "paint_red"))
    for frac in (0.1, 0.32, 0.72):
        zz = bore + (height - 1.2) * frac
        parts.append(("valve_block", box_mesh((x, y, zz), (0.55, 0.55, 0.38)), "paint_blue"))
        parts.append(("actuator", tube_mesh((x - ux * 0.28, y - uy * 0.28, zz), (x - ux * 0.75, y - uy * 0.75, zz), 0.16, 16), "paint_yellow"))
    wing = bore + (height - 1.2) * 0.52
    parts.append(("wing_block", box_mesh((x + ux * 0.65, y + uy * 0.65, wing), (0.5, 0.5, 0.42)), "paint_blue"))
    parts.append(("wing", tube_mesh((x, y, wing), (x + ux * 1.4, y + uy * 1.4, wing), 0.11, 14), "steel"))
    parts.append(("wing_actuator", tube_mesh((x + ux * 0.65, y + uy * 0.65, wing + 0.2), (x + ux * 0.65, y + uy * 0.65, wing + 0.9), 0.14, 16), "paint_yellow"))
    parts.append(("choke_body", box_mesh((x + ux * 1.15, y + uy * 1.15, wing - 0.28), (0.6, 0.45, 0.5)), "paint_yellow"))
    parts += [("fl_" + n, m, mat) for n, m, mat in hub_parts((x + ux * 1.75, y + uy * 1.75, wing - 0.28), (ux, uy, 0.0), 0.3)]
    parts.append(("tree_cap", revolve([(0.0, 0.0), (0.3, 0.0), (0.3, 0.14), (0.14, 0.26), (0.0, 0.3)], (x, y, bore + height - 1.2), (0, 0, 1), 20), "steel"))
    return parts


def mudmat_parts(center: Sequence[float], size: Sequence[float], skirts: bool = True) -> list[Part]:
    """Mudmat: plate with grating beams and perimeter skirt."""
    cx, cy, cz = center
    sx, sy = size[0], size[1]
    parts: list[Part] = [("mudmat", box_mesh((cx, cy, cz + 0.08), (sx, sy, 0.16)), "steel_dark")]
    beams: Mesh = ([], [])
    for i in range(1, 4):
        _append(beams, box_mesh((cx - sx / 2 + sx * i / 4, cy, cz + 0.22), (0.12, sy, 0.12)))
    for j in range(1, 3):
        _append(beams, box_mesh((cx, cy - sy / 2 + sy * j / 3, cz + 0.22), (sx, 0.12, 0.12)))
    parts.append(("mudmat_beams", beams, "paint_yellow"))
    if skirts:
        sk: Mesh = ([], [])
        for sgn in (-1, 1):
            _append(sk, box_mesh((cx + sgn * sx / 2, cy, cz - 0.1), (0.06, sy, 0.3)))
            _append(sk, box_mesh((cx, cy + sgn * sy / 2, cz - 0.1), (sx, 0.06, 0.3)))
        parts.append(("skirt", sk, "steel_dark"))
    return parts


def plet_parts(center: Sequence[float], heading_deg: float = 0.0, inline: bool = False, size: Sequence[float] = (7.0, 4.0)) -> list[Part]:
    """PLET (or inline PLEM when ``inline``): mudmat, protection frame, pipe manifold with isolation valve and two connector hubs (flowline hub, jumper hub)."""
    cx, cy, cz = center
    h = math.radians(heading_deg)
    ux, uy = math.cos(h), math.sin(h)
    vx, vy = -uy, ux
    sx, sy = size
    parts = mudmat_parts((cx, cy, cz), (sx, sy, 0.0))

    def P(a, b, z):
        return (cx + ux * a + vx * b, cy + uy * a + vy * b, z)

    # manifold: flowline hub at -x, valve, jumper hub raised at +x, vertical hub for the jumper
    zp = cz + 0.9
    pipe = fillet_path([P(-sx / 2 - 0.2, 0, zp), P(0.0, 0, zp), P(sx * 0.2, 0, zp), P(sx * 0.2, 0, zp + 0.9), P(sx * 0.2, sy * 0.25, zp + 0.9)], 0.3)
    parts.append(("manifold_pipe", swept_tube(pipe, 0.2, 16), "pipe"))
    parts += [("valve_" + n, m, mat) for n, m, mat in _gate_valve(P(0.0, 0, zp), (ux, uy, 0.0), 0.2)]
    parts += [("flowline_" + n, m, mat) for n, m, mat in hub_parts(P(-sx / 2 - 0.2, 0, zp), (ux, uy, 0.0), 0.25)]
    parts += [("jumper_" + n, m, mat) for n, m, mat in hub_parts(P(sx * 0.2, sy * 0.25, zp + 0.9), (vx, vy, 0.0), 0.25)]
    if inline:
        parts += [("outlet_" + n, m, mat) for n, m, mat in hub_parts(P(sx / 2 + 0.2, 0, zp), (ux, uy, 0.0), 0.25)]
        parts.append(("manifold_pipe2", swept_tube([P(sx * 0.2, 0, zp), P(sx / 2 + 0.2, 0, zp)], 0.2, 16), "pipe"))
    frame: Mesh = ([], [])
    top = cz + 2.4
    for a in (-1, 1):
        for b in (-1, 1):
            _append(frame, tube_mesh(P(a * sx * 0.46, b * sy * 0.46, cz), P(a * sx * 0.46, b * sy * 0.46, top), 0.08, 10))
    for k, (a, b) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        a2, b2 = ((-1, -1), (1, -1), (1, 1), (-1, 1))[(k + 1) % 4]
        _append(frame, tube_mesh(P(a * sx * 0.46, b * sy * 0.46, top), P(a2 * sx * 0.46, b2 * sy * 0.46, top), 0.06, 8))
    _append(frame, tube_mesh(P(-sx * 0.46, -sy * 0.46, top), P(sx * 0.46, sy * 0.46, top), 0.04, 8))
    _append(frame, tube_mesh(P(sx * 0.46, -sy * 0.46, top), P(-sx * 0.46, sy * 0.46, top), 0.04, 8))
    parts.append(("protection_frame", frame, "paint_yellow"))
    return parts


def _gate_valve(point: Sequence[float], direction: Sequence[float], d: float) -> list[Part]:
    from .realistic import valve_parts

    return valve_parts(point, direction, d, (0, 0, 1), "paint_blue")


def manifold_parts(center: Sequence[float], size: Sequence[float] = (14.0, 8.0, 5.0), slots: int = 4, heading_deg: float = 0.0) -> list[Part]:
    """Subsea manifold: mudmat, protection frame with roof beams, production header with a branch valve and hub per slot, and test header."""
    cx, cy, cz = center
    sx, sy, sz = size
    h = math.radians(heading_deg)
    ux, uy = math.cos(h), math.sin(h)
    vx, vy = -uy, ux

    def P(a, b, z):
        return (cx + ux * a + vx * b, cy + uy * a + vy * b, z)

    parts = mudmat_parts((cx, cy, cz), (sx * 1.1, sy * 1.1, 0.0))
    frame: Mesh = ([], [])
    for a in (-1, 1):
        for b in (-1, 1):
            _append(frame, tube_mesh(P(a * sx / 2, b * sy / 2, cz), P(a * sx / 2, b * sy / 2, cz + sz), 0.12, 12))
    for z in (cz + 0.3, cz + sz):
        for a, b, a2, b2 in ((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1)):
            _append(frame, tube_mesh(P(a * sx / 2, b * sy / 2, z), P(a2 * sx / 2, b2 * sy / 2, z), 0.09, 10))
    for i in range(1, 4):
        _append(frame, tube_mesh(P(-sx / 2 + sx * i / 4, -sy / 2, cz + sz), P(-sx / 2 + sx * i / 4, sy / 2, cz + sz), 0.06, 8))
    parts.append(("protection_frame", frame, "paint_yellow"))
    zh = cz + 1.0
    parts.append(("production_header", swept_tube([P(-sx * 0.45, -sy * 0.12, zh), P(sx * 0.45, -sy * 0.12, zh)], 0.22, 20), "pipe"))
    parts.append(("test_header", swept_tube([P(-sx * 0.45, sy * 0.12, zh + 0.5), P(sx * 0.45, sy * 0.12, zh + 0.5)], 0.14, 16), "pipe"))
    for k in range(slots):
        a = -sx * 0.36 + sx * 0.72 * k / max(1, slots - 1)
        br = fillet_path([P(a, -sy * 0.12, zh), P(a, -sy * 0.12, zh + 0.9), P(a, -sy * 0.4, zh + 0.9)], 0.3)
        parts.append(("branch", swept_tube(br, 0.12, 14), "pipe"))
        parts += [("branch_valve_" + n, m, mat) for n, m, mat in _gate_valve(P(a, -sy * 0.12, zh + 0.45), (0, 0, 1), 0.2)]
        parts += [("slot_hub_" + n, m, mat) for n, m, mat in hub_parts(P(a, -sy * 0.4, zh + 0.9), (vx, vy, 0.0), 0.2)]
    parts += [("export_" + n, m, mat) for n, m, mat in hub_parts(P(sx * 0.45 + 0.2, -sy * 0.12, zh), (ux, uy, 0.0), 0.3)]
    return parts


def jumper_path(a: Sequence[float], b: Sequence[float], shape: str = "M", rise: float = 3.0, leg: float = 1.2) -> list[tuple[float, float, float]]:
    """Waypoints of a rigid jumper between two hub points: ``"M"`` (two verticals joined by a horizontal), ``"W"`` (extra dip) or ``"U"`` (inverted U)."""
    ax, ay, az = a
    bx, by, bz = b
    mx, my = (ax + bx) / 2, (ay + by) / 2
    top = max(az, bz) + rise
    if shape == "U":
        return [tuple(a), (ax, ay, top), (bx, by, top), tuple(b)]
    if shape == "W":
        dip = min(az, bz) + 0.8
        return [tuple(a), (ax, ay, top), (mx, my, dip), (bx, by, top), tuple(b)]
    return [tuple(a), (ax, ay, top), (mx, my, top + 0.35 * rise), (bx, by, top), tuple(b)]

def jumper_parts(a: Sequence[float], b: Sequence[float], diameter: float = 0.273, shape: str = "M", rise: float = 3.0) -> list[Part]:
    """Rigid jumper with 5D bends, connector hubs at both ends and a lifting-point bar."""
    path = jumper_path(a, b, shape, rise)
    parts = [("jumper_pipe", swept_tube(fillet_path(path, 5.0 * diameter, 10), diameter / 2, 20), "pipe")]
    d0 = [path[1][i] - path[0][i] for i in range(3)]
    d1 = [path[-1][i] - path[-2][i] for i in range(3)]
    parts += [("end0_" + n, m, mat) for n, m, mat in hub_parts(path[0], d0, diameter)]
    parts += [("end1_" + n, m, mat) for n, m, mat in hub_parts(path[-1], d1, diameter)]
    mid = [(path[1][i] + path[-2][i]) / 2 for i in range(3)]
    parts.append(("lift_point", tube_mesh((mid[0], mid[1], mid[2]), (mid[0], mid[1], mid[2] + 0.5), 0.05, 8), "paint_yellow"))
    return parts


def flowline_parts(path: Sequence[Sequence[float]], diameter: float = 0.26, joint_length: float = 12.2, segments: int = 14) -> list[Part]:
    """Rigid flowline with field-joint bands every ``joint_length`` metres (coating cut-backs) and the pipe in between."""
    from .realistic import resample_path

    p = resample_path(path, 6.0)
    parts: list[Part] = [("flowline", swept_tube(p, diameter / 2, segments), "pipe")]
    cum = 0.0
    bands: Mesh = ([], [])
    nxt = joint_length
    for a, b in zip(p, p[1:]):
        d = math.dist(a, b)
        while cum + d >= nxt and d > 0:
            f = (nxt - cum) / d
            c = [a[i] + (b[i] - a[i]) * f for i in range(3)]
            dirv = [(b[i] - a[i]) / d for i in range(3)]
            _append(bands, tube_mesh(tuple(c[i] - 0.25 * dirv[i] for i in range(3)), tuple(c[i] + 0.25 * dirv[i] for i in range(3)), diameter * 0.62, 12))
            nxt += joint_length
        cum += d
    parts.append(("field_joints", bands, "paint_yellow"))
    return parts


def riser_base_parts(center: Sequence[float], heading_deg: float = 0.0, with_ssiv: bool = True) -> list[Part]:
    """Riser base structure: mudmat, gooseneck bend, SSIV valve block with actuator and the riser hub going up."""
    cx, cy, cz = center
    h = math.radians(heading_deg)
    ux, uy = math.cos(h), math.sin(h)
    parts = mudmat_parts((cx, cy, cz), (8.0, 5.0, 0.0))
    pipe = fillet_path([(cx - ux * 4.5, cy - uy * 4.5, cz + 1.0), (cx, cy, cz + 1.0), (cx, cy, cz + 5.0)], 1.2)
    parts.append(("gooseneck", swept_tube(pipe, 0.16, 18), "pipe"))
    if with_ssiv:
        parts += [("ssiv_" + n, m, mat) for n, m, mat in _gate_valve((cx - ux * 1.8, cy - uy * 1.8, cz + 1.0), (ux, uy, 0.0), 0.3)]
        parts.append(("ssiv_actuator", box_mesh((cx - ux * 1.8, cy - uy * 1.8, cz + 2.1), (0.8, 0.8, 0.9)), "paint_yellow"))
    parts += [("riser_" + n, m, mat) for n, m, mat in hub_parts((cx, cy, cz + 5.0), (0, 0, 1), 0.3)]
    return parts


def umbilical_parts(path: Sequence[Sequence[float]], diameter: float = 0.12, tube_count: int = 6) -> list[Part]:
    """Umbilical as a sheath with visible steel-tube bundle stripes (thin tubes twisted along the path)."""
    from .realistic import resample_path

    p = resample_path(path, 8.0)
    parts: list[Part] = [("umbilical", swept_tube(p, diameter / 2, 14), "paint_blue")]
    return parts


def uta_parts(center: Sequence[float], heading_deg: float = 0.0) -> list[Part]:
    """Umbilical termination assembly: mudmat, termination head with hydraulic plate and flying-lead stabs."""
    cx, cy, cz = center
    parts = mudmat_parts((cx, cy, cz), (3.0, 2.2, 0.0))
    parts.append(("uth", box_mesh((cx, cy, cz + 0.9), (1.4, 1.2, 1.2)), "paint_blue"))
    for k in range(4):
        parts.append(("stab", tube_mesh((cx - 0.45 + 0.3 * k, cy + 0.62, cz + 0.9), (cx - 0.45 + 0.3 * k, cy + 1.0, cz + 0.9), 0.05, 8), "steel"))
    return parts


__all__ = ["flowline_parts", "hub_parts", "jumper_parts", "jumper_path", "manifold_parts", "mudmat_parts", "plet_parts", "riser_base_parts", "umbilical_parts", "uta_parts", "xmas_tree_parts"]
