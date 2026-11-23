"""Screening checks on routed pipes: support spacing, slope, thermal flexibility and clashes.

These are public, screening-level checks to show where a routed pipe needs
attention. They are not a pipe stress analysis and do not replace one.

- **Support spacing**: simply supported span limited by mid-span sag of 2.5 mm
  and a sustained bending stress of 15.9 MPa (the basis of the common
  MSS SP-69 style span tables), for a pipe filled with the stated fluid
  (water by default, which is the table basis). Supports are placed at both
  ends of every horizontal run and at equal spacing not exceeding that span.
- **Slope**: every horizontal run of a line with ``min_slope`` must fall at
  least that much per metre in the flow direction.
- **Thermal flexibility**: ASME B31.3 para. 319.4.1 simplified check
  D*y/(L-U)^2 <= 208.3 (D in mm, y in mm, L and U in m) for a line between two
  anchors (its end nozzles). y = alpha * |T - T_install| * U. The temperature
  comes from the connection, else the NeqSim result of the source equipment,
  else it is a data gap. The check applies to uniform-size lines with no
  intermediate restraints and is not valid for severe cyclic service; a fail
  means "needs a stress analysis", not "unacceptable".
- **Clashes**: pipe-to-pipe and pipe-to-equipment, from ``routing.check_clashes``.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

from .routing import check_clashes, route_connections, route_length
from .schema import AssetScene, box, geometry_bounds

G = 9.81
SAG_LIMIT_M = 0.0025
SPAN_STRESS_PA = 15.9e6
# Theory gives 3.47 / 5.61 / 7.49 / 9.11 m for 2 / 6 / 12 / 24 in standard-wall water-filled carbon
# steel against MSS SP-69 table values 3.0 / 5.2 / 7.0 / 9.4 m (checked 2026-11-22). The tables round
# down for practice, so the allowable span is the theoretical span times 0.9 (3.1 / 5.0 / 6.7 / 8.2 m).
SPAN_PRACTICE_FACTOR = 0.9
B313_K1_SI = 208.3
HORIZONTAL_TOL = 0.2  # |dz| / horizontal length below this counts as a horizontal run

MATERIALS: dict[str, dict[str, float]] = {
    "carbon_steel": {"E": 203e9, "alpha": 12.0e-6, "rho": 7850.0},
    "stainless_steel": {"E": 195e9, "alpha": 16.5e-6, "rho": 7900.0},
    "duplex": {"E": 200e9, "alpha": 13.0e-6, "rho": 7800.0},
}


def assumed_wall_thickness(od_m: float) -> float:
    """Wall thickness close to schedule 40 for 2-12 inch carbon steel (screening placeholder)."""
    return 0.0021 + 0.025 * od_m


def max_span(
    od_m: float,
    wall_m: float,
    fluid_density: float = 1000.0,
    material: str = "carbon_steel",
) -> dict[str, float]:
    """Allowable simply supported span by sag and by bending stress (metres)."""
    m = MATERIALS.get(material, MATERIALS["carbon_steel"])
    id_m = max(od_m - 2.0 * wall_m, 0.0)
    a_steel = math.pi / 4.0 * (od_m**2 - id_m**2)
    a_bore = math.pi / 4.0 * id_m**2
    w = G * (a_steel * m["rho"] + a_bore * fluid_density)
    inertia = math.pi / 64.0 * (od_m**4 - id_m**4)
    z = 2.0 * inertia / od_m
    l_sag = (SAG_LIMIT_M * 384.0 * m["E"] * inertia / (5.0 * w)) ** 0.25
    l_stress = math.sqrt(8.0 * z * SPAN_STRESS_PA / w)
    return {
        "sag_m": l_sag,
        "stress_m": l_stress,
        "span_m": SPAN_PRACTICE_FACTOR * min(l_sag, l_stress),
        "weight_N_per_m": w,
    }


def b313_flexibility(
    od_m: float,
    developed_m: float,
    anchor_m: float,
    delta_t: float,
    material: str = "carbon_steel",
) -> dict[str, Any]:
    """ASME B31.3 319.4.1 screening ratio for a line between two anchors."""
    alpha = MATERIALS.get(material, MATERIALS["carbon_steel"])["alpha"]
    y_mm = alpha * abs(delta_t) * anchor_m * 1000.0
    slack = developed_m - anchor_m
    ratio = float("inf") if slack <= 1e-6 else od_m * 1000.0 * y_mm / slack**2
    return {
        "y_mm": round(y_mm, 2),
        "developed_length_m": round(developed_m, 2),
        "anchor_distance_m": round(anchor_m, 2),
        "ratio": round(ratio, 1) if math.isfinite(ratio) else None,
        "limit": B313_K1_SI,
        "status": "pass" if ratio <= B313_K1_SI else "needs_stress_analysis",
    }


def _temperature(scene: AssetScene, conn: dict[str, Any]) -> dict[str, Any] | None:
    if conn.get("operating_temperature_C") is not None:
        return {
            "value": float(conn["operating_temperature_C"]),
            "basis": "connection data",
        }
    src = scene.get(conn["from"]) or {}
    entry = (src.get("results") or {}).get("temperature")
    if isinstance(entry, dict) and entry.get("value") is not None:
        unit = str(entry.get("unit", "C")).upper()
        value = float(entry["value"]) - (273.15 if unit == "K" else 0.0)
        return {
            "value": value,
            "basis": f"NeqSim result of {src.get('tag') or src.get('id')}",
        }
    live = (src.get("live") or {}).get("temperature")
    if isinstance(live, dict) and live.get("value") is not None:
        return {
            "value": float(live["value"]),
            "basis": f"live value of {src.get('tag') or src.get('id')}",
        }
    return None


def _horizontal_runs(points: Sequence[Sequence[float]]) -> list[dict[str, Any]]:
    """Horizontal-ish runs, excluding the nozzle stubs at both ends."""
    segs = list(itertools.pairwise(points))
    inner = segs[1:-1] if len(segs) > 2 else segs
    runs = []
    for p, q in inner:
        h = math.hypot(q[0] - p[0], q[1] - p[1])
        if h > 1e-6 and abs(q[2] - p[2]) / h <= HORIZONTAL_TOL:
            runs.append(
                {
                    "start": list(p),
                    "end": list(q),
                    "horizontal_m": h,
                    "fall_per_m": (p[2] - q[2]) / h,
                }
            )
    return runs


def _support_points(runs: Sequence[dict[str, Any]], span: float) -> list[list[float]]:
    pts: list[list[float]] = []
    for run in runs:
        n = max(1, math.ceil(run["horizontal_m"] / span))
        for k in range(n + 1):
            f = k / n
            p = [
                run["start"][i] + f * (run["end"][i] - run["start"][i])
                for i in range(3)
            ]
            if not any(sum((p[i] - o[i]) ** 2 for i in range(3)) < 0.01 for o in pts):
                pts.append(p)
    return pts


def analyse_piping(
    scene: AssetScene,
    routing: str = "auto",
    install_temperature_C: float = 20.0,
    default_diameter_m: float | None = None,
) -> dict[str, Any]:
    """Route every connection and run the screening checks.

    Returns ``{"connections": [...], "clashes": [...], "summary": {...}, "basis": [...]}``.
    A connection without ``diameter`` is routed for the picture but gets no
    span or flexibility result (``no_size``), because the drawn thickness is
    not a pipe size.
    """
    from .render import _default_connection_diameter

    visual_d = default_diameter_m or _default_connection_diameter(scene)
    routes = route_connections(scene, visual_d, routing)
    clashes = check_clashes(scene, routes, visual_d)
    rows: list[dict[str, Any]] = []
    for conn in scene.connections:
        route = routes.get(conn["id"])
        if route is None:
            continue
        pts = route["points"]
        row: dict[str, Any] = {
            "id": conn["id"],
            "line_number": conn.get("line_number"),
            "state": conn.get("state"),
            "mode": route["mode"],
            "ends": route.get("ends"),
            "length_m": round(route_length(pts), 2),
            "points": pts,
            "clashes": [c for c in clashes if conn["id"] in (c["a"], c.get("b"))],
        }
        material = conn.get("material") or "carbon_steel"
        od = conn.get("diameter")
        runs = (
            _horizontal_runs(pts) if route["mode"] in ("orthogonal", "supplied") else []
        )
        if od:
            od = float(od)
            wall = conn.get("wall_thickness_m")
            row["wall_basis"] = "supplied" if wall else "assumed (about schedule 40)"
            wall = float(wall) if wall else assumed_wall_thickness(od)
            fluid = float(conn.get("fluid_density_kg_m3") or 1000.0)
            span = max_span(od, wall, fluid, material)
            row.update(
                {
                    "od_m": od,
                    "wall_m": round(wall, 4),
                    "fluid_density_kg_m3": fluid,
                    "max_span_m": round(span["span_m"], 2),
                    "span_governed_by": (
                        "sag" if span["sag_m"] <= span["stress_m"] else "stress"
                    ),
                    "supports": _support_points(runs, span["span_m"]) if runs else [],
                }
            )
            temp = _temperature(scene, conn)
            if route["mode"] == "seabed":
                row["flexibility"] = {
                    "status": "not_applicable",
                    "reason": "subsea line; use pipeline expansion analysis",
                }
            elif temp is None:
                row["flexibility"] = {"status": "no_temperature"}
            else:
                anchor = math.dist(pts[0], pts[-1])
                flex = b313_flexibility(
                    od,
                    route_length(pts),
                    anchor,
                    temp["value"] - install_temperature_C,
                    material,
                )
                flex.update(
                    {
                        "temperature_C": round(temp["value"], 1),
                        "temperature_basis": temp["basis"],
                    }
                )
                row["flexibility"] = flex
        else:
            row.update(
                {
                    "supports": [],
                    "flexibility": {"status": "no_size"},
                    "max_span_m": None,
                }
            )
        need = float(conn.get("min_slope") or 0.0)
        if need > 0 and runs:
            worst = min(r["fall_per_m"] for r in runs)
            row["slope"] = {
                "required": need,
                "minimum_achieved": round(worst, 5),
                "status": "pass" if worst >= need - 1e-9 else "fail",
            }
        elif need > 0:
            row["slope"] = {"required": need, "status": "no_horizontal_run"}
        rows.append(row)
    ends = [b for r in rows for b in (r.get("ends") or [])]
    summary = {
        "connections": len(rows),
        "with_size": sum(1 for r in rows if r.get("od_m")),
        "supports": sum(len(r["supports"]) for r in rows),
        "flexibility_pass": sum(
            1 for r in rows if r["flexibility"].get("status") == "pass"
        ),
        "flexibility_needs_analysis": sum(
            1 for r in rows if r["flexibility"].get("status") == "needs_stress_analysis"
        ),
        "slope_fail": sum(
            1 for r in rows if (r.get("slope") or {}).get("status") == "fail"
        ),
        "pipe_clashes": sum(1 for c in clashes if c["type"] == "pipe"),
        "equipment_clashes": sum(1 for c in clashes if c["type"] == "object"),
        "ends_at_nozzle": ends.count("nozzle"),
        "ends_by_port_convention": ends.count("port_convention"),
        "ends_at_face": ends.count("face"),
    }
    basis = [
        f"Support spans: simply supported, sag <= {SAG_LIMIT_M * 1000:.1f} mm and bending stress <= {SPAN_STRESS_PA / 1e6:.1f} MPa, fluid-filled, times {SPAN_PRACTICE_FACTOR} (at or below MSS SP-69 water-filled table spans).",
        f"Thermal flexibility: ASME B31.3 319.4.1 screening D*y/(L-U)^2 <= {B313_K1_SI} (SI), end nozzles taken as anchors, installation {install_temperature_C:g} C.",
        "Slope: fall per metre of every horizontal run in the flow direction.",
        "Clashes: segment distances against the sum of radii plus 50 mm; envelopes for equipment.",
        "Screening only; not a pipe stress analysis, support design or clash check of an as-built model.",
    ]
    return {"connections": rows, "clashes": clashes, "summary": summary, "basis": basis}


def add_pipe_supports(
    scene: AssetScene, report: dict[str, Any], ground_z: float | None = None
) -> list[str]:
    """Add the screening support positions as ``support`` objects (posts down to ``ground_z``)."""
    if ground_z is None:
        zs = [
            geometry_bounds(o["geometry"])[2]
            for o in scene.objects
            if o["kind"] != "support"
        ]
        ground_z = min(zs) if zs else 0.0
    added: list[str] = []
    for row in report["connections"]:
        od = row.get("od_m") or 0.1
        for k, p in enumerate(row["supports"]):
            bottom = p[2] - od / 2.0
            height = max(bottom - ground_z, 0.1)
            sid = f"support:{row['id']}:{k + 1}"
            if scene.get(sid) is not None:
                continue
            scene.add_object(
                sid,
                "support",
                box(
                    [p[0], p[1], ground_z + height / 2.0],
                    [max(0.15, 1.5 * od), 0.15, height],
                ),
                state=row.get("state") or "proposed",
                name=f"Support {k + 1} of {row.get('line_number') or row['id']}",
                group="structure",
                source={
                    "geometry": f"support spacing screening (max span {row.get('max_span_m')} m)",
                    "quality": "assumed",
                },
                attributes={"line": row.get("line_number") or row["id"]},
            )
            added.append(sid)
    return added


def piping_fragment(
    report: dict[str, Any], scene_name: str = "scene"
) -> dict[str, Any]:
    """``results.json`` table, assumptions and data gaps for the piping screening."""
    rows = []
    gaps: list[dict[str, Any]] = []
    for r in report["connections"]:
        flex = r["flexibility"]
        flex_text = flex.get("status")
        if flex.get("ratio") is not None:
            flex_text = f"{flex['ratio']} / {flex['limit']} ({flex['status']})"
        slope = r.get("slope") or {}
        rows.append(
            [
                r.get("line_number") or r["id"],
                r["mode"],
                "/".join(r.get("ends") or []),
                r["length_m"],
                r.get("od_m") or "-",
                r.get("max_span_m") or "-",
                len(r["supports"]),
                slope.get("status", "-"),
                flex_text,
                len(r["clashes"]),
            ]
        )
        name = r.get("line_number") or r["id"]
        if not r.get("od_m"):
            gaps.append(
                {
                    "gap": f"No pipe size for {name}",
                    "source": "line list / P&ID",
                    "status": "open",
                    "assumed": "drawn size only",
                    "effect": "No support spacing or flexibility screening",
                }
            )
        elif r.get("wall_basis", "").startswith("assumed"):
            gaps.append(
                {
                    "gap": f"No wall thickness for {name}",
                    "source": "piping class (e.g. TR2000)",
                    "status": "open",
                    "assumed": "about schedule 40",
                    "effect": "Support span is approximate",
                }
            )
        if flex.get("status") == "no_temperature":
            gaps.append(
                {
                    "gap": f"No operating temperature for {name}",
                    "source": "NeqSim result or line list",
                    "status": "open",
                    "assumed": "",
                    "effect": "Thermal flexibility not screened",
                }
            )
        if flex.get("status") == "needs_stress_analysis":
            gaps.append(
                {
                    "gap": f"{name} fails the B31.3 319.4.1 flexibility screen",
                    "source": "piping screening",
                    "status": "open",
                    "assumed": "",
                    "effect": "Formal pipe stress analysis needed",
                }
            )
        if slope.get("status") == "fail":
            gaps.append(
                {
                    "gap": f"{name} does not meet its required slope {slope['required']}",
                    "source": "piping screening",
                    "status": "open",
                    "assumed": "",
                    "effect": "Route must be re-graded or pockets drained",
                }
            )
        for end in r.get("ends") or []:
            if end in ("face", "port_convention"):
                gaps.append(
                    {
                        "gap": f"Nozzle position not supplied for {name}",
                        "source": "datasheet nozzle schedule",
                        "status": "open",
                        "assumed": f"pipe end at the {end.replace('_', ' ')}",
                        "effect": "End of the pipe is approximate",
                    }
                )
                break
    for c in report["clashes"]:
        gaps.append(
            {
                "gap": f"Clash between {c['a']} and {c['b']}",
                "source": "piping screening",
                "status": "open",
                "assumed": "",
                "effect": "Route needs adjustment or a supplied as-built route",
            }
        )
    return {
        "tables": [
            {
                "title": f"Piping screening for {scene_name}",
                "headers": [
                    "Line",
                    "Route",
                    "Ends",
                    "Length [m]",
                    "OD [m]",
                    "Max span [m]",
                    "Supports",
                    "Slope",
                    "B31.3 319.4.1 ratio / limit",
                    "Clashes",
                ],
                "rows": rows,
            }
        ],
        "assumptions": list(report["basis"]),
        "data_gaps": gaps,
    }
