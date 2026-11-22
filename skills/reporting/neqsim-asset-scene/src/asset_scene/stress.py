"""Pipe stress analysis of routed scene pipes with NeqSim ``PipeStressModel`` (ASME B31.3).

For every routed connection that has a pipe size, the route (nozzle to nozzle)
becomes a 3D beam model in NeqSim: end nozzles are anchors (with the vendor
nozzle allowables when the end object carries them), screening support
positions are one-way rest supports with Coulomb friction, bends are long-radius
elbows with B31.3 flexibility and SIFs. NeqSim solves the operating case with
support lift-off and friction, then the sustained, expansion and occasional
cases, and checks B31.3 para. 304.1.2, 319 and 320.

The physics lives in NeqSim Java (``neqsim.process.mechanicaldesign.piping``);
this module only builds the model from the scene and collects the results. When
the installed NeqSim jar has no ``PipeStressModel`` the result says so and the
line stays a data gap.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .piping import MATERIALS, analyse_piping

# Basic allowable stress S (B31.3 Table A-1, at or below ~200 C), Pa.
ALLOWABLE_STRESS: Dict[str, float] = {
    "carbon_steel": 138.0e6,  # A106 Gr B
    "stainless_steel": 115.0e6,  # A312 TP316L
    "duplex": 207.0e6,  # A790 S31803
}
DEFAULT_CORROSION_ALLOWANCE = {"carbon_steel": 0.003, "stainless_steel": 0.0, "duplex": 0.0}
DEFAULT_FRICTION = 0.3


def neqsim_pipe_stress_class() -> Optional[Any]:
    """Return the NeqSim ``PipeStressModel`` Java class, or ``None`` when unavailable."""
    try:
        from neqsim import jneqsim  # noqa: WPS433 (optional dependency)

        return jneqsim.process.mechanicaldesign.piping.PipeStressModel
    except Exception:
        return None


def _on_segment(p: Sequence[float], a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Parameter t of point p on segment a-b, or None when p is not on it."""
    d = [b[i] - a[i] for i in range(3)]
    ll = sum(c * c for c in d)
    if ll < 1e-12:
        return None
    t = sum((p[i] - a[i]) * d[i] for i in range(3)) / ll
    if t < -1e-9 or t > 1 + 1e-9:
        return None
    off = math.sqrt(sum((a[i] + t * d[i] - p[i]) ** 2 for i in range(3)))
    return t if off < 1e-4 else None


def _polyline_with_supports(points: Sequence[Sequence[float]], supports: Sequence[Sequence[float]]) -> Tuple[List[List[float]], List[int]]:
    """Route points with the support points inserted; returns (points, indices of supports)."""
    out: List[List[float]] = [list(points[0])]
    support_idx: List[int] = []
    for a, b in zip(points[:-1], points[1:]):
        on = sorted((t, list(s)) for s in supports for t in [_on_segment(s, a, b)] if t is not None)
        for t, s in on:
            if math.dist(s, out[-1]) < 1e-3:
                if len(out) - 1 not in support_idx and len(out) > 1:
                    support_idx.append(len(out) - 1)
                continue
            if math.dist(s, b) < 1e-3:
                continue
            out.append(s)
            support_idx.append(len(out) - 1)
        if math.dist(b, out[-1]) > 1e-6:
            out.append(list(b))
    return out, support_idx


def _allowables(obj: Optional[Dict[str, Any]], port: Optional[str]) -> Optional[Dict[str, float]]:
    table = ((obj or {}).get("attributes") or {}).get("nozzle_allowables") or {}
    entry = table.get(port or "") or table.get("default")
    if entry and entry.get("force_N") and entry.get("moment_Nm"):
        return {"force_N": float(entry["force_N"]), "moment_Nm": float(entry["moment_Nm"])}
    return None


def _design_pressure_barg(scene: Any, conn: Dict[str, Any]) -> Tuple[float, str]:
    if conn.get("design_pressure_barg") is not None:
        return float(conn["design_pressure_barg"]), "connection data"
    src = scene.get(conn["from"]) or {}
    attrs = src.get("attributes") or {}
    if attrs.get("design_pressure_barg") is not None:
        return float(attrs["design_pressure_barg"]), f"design pressure of {src.get('tag') or src.get('id')}"
    if attrs.get("neqsim_max_design_pressure_bara") is not None:
        return float(attrs["neqsim_max_design_pressure_bara"]) - 1.01325, f"NeqSim design pressure of {src.get('tag') or src.get('id')}"
    return 0.0, "not supplied"


def analyse_pipe_stress(
    scene: Any,
    report: Optional[Dict[str, Any]] = None,
    seismic_g: float = 0.0,
    wind_pressure_pa: float = 0.0,
    install_temperature_C: float = 20.0,
) -> Dict[str, Any]:
    """Run NeqSim ``PipeStressModel`` for every sized, routed pipe and attach ``row["stress"]``.

    ``report`` is the result of ``analyse_piping`` (computed when not given).
    Connection keys used: ``diameter`` (OD, m), ``wall_thickness_m``,
    ``corrosion_allowance_m``, ``material``, ``fluid_density_kg_m3``,
    ``design_pressure_barg``, ``friction`` (support friction, default 0.3),
    ``allowable_stress_Pa``. Nozzle allowables come from the end objects'
    ``attributes["nozzle_allowables"]`` keyed by port (or ``default``) with
    ``force_N`` and ``moment_Nm``.
    """
    report = report or analyse_piping(scene)
    cls = neqsim_pipe_stress_class()
    summary = {"analysed": 0, "pass": 0, "fail": 0, "unavailable": 0, "not_sized": 0}
    if cls is None:
        for row in report["connections"]:
            row["stress"] = {"status": "unavailable", "reason": "NeqSim PipeStressModel not in the installed jar (needs NeqSim >= 3.29.0)"}
        summary["unavailable"] = len(report["connections"])
        report["stress_summary"] = summary
        return report
    conns = {c["id"]: c for c in scene.connections}
    for row in report["connections"]:
        conn = conns[row["id"]]
        if not row.get("od_m") or row["mode"] == "seabed":
            row["stress"] = {"status": "not_analysed", "reason": "no pipe size" if not row.get("od_m") else "subsea line"}
            summary["not_sized"] += 1
            continue
        material = conn.get("material") or "carbon_steel"
        mat = MATERIALS.get(material, MATERIALS["carbon_steel"])
        allow = float(conn.get("allowable_stress_Pa") or ALLOWABLE_STRESS.get(material, ALLOWABLE_STRESS["carbon_steel"]))
        ca = conn.get("corrosion_allowance_m")
        ca_basis = "supplied" if ca is not None else "assumed default for material"
        ca = float(ca) if ca is not None else DEFAULT_CORROSION_ALLOWANCE.get(material, 0.0)
        wall = float(row["wall_m"])
        if wall - ca <= 0.0005:
            ca = max(0.0, wall - 0.0005)
            ca_basis += " (capped below wall)"
        pressure, p_basis = _design_pressure_barg(scene, conn)
        temp = (row.get("flexibility") or {}).get("temperature_C", install_temperature_C)
        friction = float(conn.get("friction", DEFAULT_FRICTION))
        pts, sup = _polyline_with_supports(row["points"], row.get("supports") or [])

        model = cls(str(row.get("line_number") or row["id"]))
        model.setPipe(float(row["od_m"]), wall, ca)
        model.setMaterial(mat["E"], 0.3, mat["rho"], mat["alpha"])
        model.setAllowables(allow, allow, 1.0)
        model.setContents(float(row.get("fluid_density_kg_m3") or 1000.0), 0.0)
        model.setConditions(pressure * 1e5, install_temperature_C, float(temp))
        model.setOccasionalLoads(float(seismic_g), float(wind_pressure_pa), 0.7)
        for k, p in enumerate(pts):
            model.addNode(f"P{k}", float(p[0]), float(p[1]), float(p[2]))
        for k in range(len(pts) - 1):
            model.addElement(f"P{k}", f"P{k + 1}")
        ends = {}
        for label, node, obj_id, port in (
            ("A_from", "P0", conn["from"], conn.get("from_port")),
            ("A_to", f"P{len(pts) - 1}", conn["to"], conn.get("to_port")),
        ):
            anchor = model.addRestraint(label, node, cls.RestraintType.ANCHOR, 0.0)
            allowed = _allowables(scene.get(obj_id), port)
            if allowed:
                model.setNozzleAllowables(anchor, allowed["force_N"], allowed["moment_Nm"])
            ends[label] = obj_id
        for k, idx in enumerate(sup):
            model.addRestraint(f"S{k + 1}", f"P{idx}", cls.RestraintType.REST, friction)
        try:
            res = model.run()
        except Exception as exc:  # unstable model or solver failure
            row["stress"] = {"status": "error", "reason": str(exc)}
            summary["fail"] += 1
            continue
        nozzles = []
        for label, obj_id in ends.items():
            r = res.getRestraint(label)
            nozzles.append(
                {
                    "object": obj_id,
                    "force_N": round(float(r.getResultantForceN()), 1),
                    "moment_Nm": round(float(r.getResultantMomentNm()), 1),
                    "status": str(r.getNozzleStatus()),
                }
            )
        supports = []
        for k in range(len(sup)):
            r = res.getRestraint(f"S{k + 1}")
            ope = [float(v) for v in r.getOperating()]
            sus = [float(v) for v in r.getSustained()]
            supports.append(
                {
                    "id": f"S{k + 1}",
                    "position_m": pts[sup[k]],
                    "state": str(r.getState()),
                    "vertical_ope_N": round(ope[2], 1),
                    "vertical_sus_N": round(sus[2], 1),
                    "horizontal_ope_N": round(math.hypot(ope[0], ope[1]), 1),
                }
            )
        max_disp = max(
            math.sqrt(sum(float(c) ** 2 for c in res.getOperatingDisplacement(f"P{k}"))) for k in range(len(pts))
        )
        status = str(res.getStatus())
        row["stress"] = {
            "status": status,
            "standard": str(res.getStandard()),
            "converged": bool(res.isConverged()),
            "sustained_ratio": round(float(res.getMaxSustainedRatio()), 3),
            "expansion_ratio": round(float(res.getMaxExpansionRatio()), 3),
            "occasional_ratio": round(float(res.getMaxOccasionalRatio()), 3),
            "pressure_design": str(res.getPressureDesignStatus()),
            "required_wall_m": round(float(res.getRequiredWallThicknessM()), 5),
            "design_pressure_barg": pressure,
            "design_pressure_basis": p_basis,
            "corrosion_allowance_m": ca,
            "corrosion_allowance_basis": ca_basis,
            "allowable_stress_Pa": allow,
            "bend_sif": round(float(res.getBendSif()), 3),
            "lift_off": [str(s) for s in res.getLiftOff()],
            "sliding": [str(s) for s in res.getSliding()],
            "max_operating_displacement_m": round(max_disp, 4),
            "nozzles": nozzles,
            "supports": supports,
            "limitations": [str(s) for s in res.getLimitations()],
        }
        summary["analysed"] += 1
        summary["pass" if status == "pass" else "fail"] += 1
    report["stress_summary"] = summary
    return report


def stress_fragment(report: Dict[str, Any], scene_name: str = "scene") -> Dict[str, Any]:
    """``results.json`` table and data gaps for the NeqSim pipe stress analysis."""
    rows = []
    gaps: List[Dict[str, Any]] = []
    for r in report["connections"]:
        s = r.get("stress") or {}
        name = r.get("line_number") or r["id"]
        if s.get("status") in ("pass", "fail") and "sustained_ratio" in s:
            noz = "/".join(n["status"] for n in s["nozzles"])
            rows.append(
                [name, s["status"], s["sustained_ratio"], s["expansion_ratio"], s["occasional_ratio"],
                 s["pressure_design"], len(s["lift_off"]), len(s["sliding"]),
                 round(s["max_operating_displacement_m"] * 1000, 1), noz]
            )
            if s["status"] == "fail":
                gaps.append({"gap": f"{name} fails the B31.3 stress analysis", "source": "NeqSim PipeStressModel",
                             "status": "open", "assumed": "", "effect": "Re-route, add flexibility or supports before design freeze"})
            if any(n["status"] == "no_allowable" for n in s["nozzles"]):
                gaps.append({"gap": f"No nozzle load allowables for {name}", "source": "equipment vendor / API 610, API 617, WRC 297",
                             "status": "open", "assumed": "", "effect": "Nozzle loads are reported but not checked"})
            if s["design_pressure_basis"] == "not supplied":
                gaps.append({"gap": f"No design pressure for {name}", "source": "line list", "status": "open",
                             "assumed": "0 barg", "effect": "Pressure design and pressure stress not checked"})
            if s["corrosion_allowance_basis"].startswith("assumed"):
                gaps.append({"gap": f"No corrosion allowance for {name}", "source": "piping class", "status": "open",
                             "assumed": f"{s['corrosion_allowance_m'] * 1000:.0f} mm", "effect": "Sustained stress uses an assumed corroded wall"})
        elif s.get("status") == "unavailable":
            gaps.append({"gap": f"Pipe stress not analysed for {name}", "source": "NeqSim version", "status": "open",
                         "assumed": "", "effect": s.get("reason", "")})
    tables = [
        {
            "title": f"Pipe stress analysis (ASME B31.3, NeqSim PipeStressModel) for {scene_name}",
            "headers": ["Line", "Status", "S_L/S_h", "S_E/S_A", "Occasional", "Pressure design",
                        "Supports lifted off", "Supports sliding", "Max displacement [mm]", "Nozzles"],
            "rows": rows,
        }
    ] if rows else []
    return {
        "tables": tables,
        "assumptions": [
            "Pipe stress: NeqSim PipeStressModel, 3D beam model nozzle to nozzle, end nozzles anchored, "
            "supports as one-way rest supports with Coulomb friction, long-radius elbows with B31.3 flexibility and SIFs, "
            "OPE/SUS/EXP/OCC load cases per B31.3 319 and 320.",
        ],
        "data_gaps": gaps,
    }
