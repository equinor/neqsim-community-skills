"""Produce all charts and drawing sheets of a study into ``drawings/`` with a drawings register and provenance sidecars."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import iwp_graphics as G
from .barriers import BarrierState, BarrierElement, propose_barriers
from .basis import load_basis
from .iwp_drawings import barrier_schematic_sheet, render_sheet, well_schematic_sheet
from .planning_extras import build_risks, decision_tree_nodes, schedule_tasks, time_depth
from .registers import Registers, get_path
from .study import load_json, study_paths


def _states_from(res: Dict[str, Any]) -> List[BarrierState]:
    out = []
    for s in res["barriers"]["states"]:
        out.append(BarrierState(s["state"], s["description"], [BarrierElement(**e) for e in s["elements"]], s.get("notes", [])))
    return out


def make_drawings(root: Path, formats_charts=("png",)) -> Dict[str, Any]:
    """Render every available chart and sheet. Missing inputs skip that figure and are listed in the register with the reason."""
    paths = study_paths(root)
    d = paths["drawings"]
    d.mkdir(parents=True, exist_ok=True)
    basis = load_basis(paths["basis"] / "planning_basis.yaml")
    res = load_json(paths["results"] / "model_results.json")
    alt = load_json(paths["results"] / "alternatives.json") if (paths["results"] / "alternatives.json").exists() else None
    regs = Registers.load(paths["registers"])
    well = get_path(basis, "well.id")
    sid = get_path(basis, "study.id")
    synthetic = bool(get_path(basis, "study.synthetic"))
    register: List[Dict[str, str]] = []

    def note(fig_id: str, title: str, files: Optional[Dict[str, str]], status: str, reason: str = "", dwg: str = "") -> None:
        register.append({"id": fig_id, "title": title, "drawing_no": dwg, "status": status, "files": ";".join(Path(v).name for k, v in (files or {}).items() if k != "provenance"), "note": reason})

    survey = res["trajectory"]["survey"]
    fig = well_schematic_sheet(basis, survey, "{}-DWG-001".format(sid))
    note("F01", "Well schematic (A3)", render_sheet(fig, d / "well_schematic", "well_schematic", basis, "{}-DWG-001".format(sid), "Well schematic with depth tracks", synthetic, ["L13"]), "RENDERED", dwg="{}-DWG-001".format(sid))
    states = _states_from(res)
    fig = barrier_schematic_sheet(states, basis, "{}-DWG-002".format(sid))
    note("F02", "Barrier schematics per well state (A3)", render_sheet(fig, d / "barrier_schematics", "barrier_schematic", res["barriers"], "{}-DWG-002".format(sid), "Proposed barrier envelopes, elements UNVERIFIED", synthetic,
                                                                    ["L13"]), "RENDERED", dwg="{}-DWG-002".format(sid))
    prod = (res.get("producer") or {})
    inj = (res.get("injector") or {})
    if prod:
        fam = res["charts"]["nodal_family"]
        ops = {c: {"q_op": prod[c].get("q_op"), "bhp_op": prod[c].get("bhp_op")} for c in prod}
        unit = get_path(basis, "targets.rate.kind") or "Sm3/d"
        w = G.render("nodal", d / "nodal_analysis", {"fam": fam, "ops": ops}, "Nodal analysis: IPR (low-high band) and VLP family", synthetic, formats_charts, ["L02", "L04", "L05"], family=fam, ops=ops,
                     target_rate=prod["base"]["target_rate"], rate_label="Rate [{}]".format(unit), ipr_band={"low": fam["ipr_low"], "high": fam["ipr_high"]},
                     outflow_min_rate=prod["base"]["nodal"].get("outflow_min_rate") if res["meta"]["gas_well"] else None, title="Nodal analysis - base case")
        note("F03", "Nodal analysis", w, "RENDERED")
        w = G.render("wellbore_profiles", d / "wellbore_profiles", prod["base"].get("profile"), "Pressure, temperature, holdup and velocity profiles", synthetic, formats_charts, ["L01", "L02"],
                     profile=prod["base"]["profile"], hydrate=(res.get("flow_assurance", {}).get("hydrate") or {}).get("profile"))
        note("F04", "Wellbore profiles (tracks on one depth axis)", w, "RENDERED")
    if inj:
        base = inj["base"]
        if base.get("profile"):
            prof = base["profile"]
            fig = G.plt.figure(figsize=(7.2, 5.0))
            ax = fig.add_subplot(121)
            ax.plot(prof["temperature_C"], prof["tvd_m"], color=G.PALETTE["temperature"], lw=2)
            ax.invert_yaxis()
            ax.set_xlabel("Temperature [C]")
            ax.set_ylabel("TVD below tree [m]")
            ax.set_title("Injection temperature", fontsize=9)
            ax2 = fig.add_subplot(122, sharey=ax)
            ax2.plot(prof["density_kg_m3"], prof["tvd_density_m"], color=G.PALETTE["water"] if get_path(basis, "well.type") == "water_injector" else G.PALETTE["gas"], lw=2)
            ax2.set_xlabel("Density [kg/m3]")
            ax2.set_title("Injectate density", fontsize=9)
            from .iwp_style import provenance_record, save_figure

            w = save_figure(fig, d / "injection_profiles", provenance_record("injection_profiles", "Injection profiles", "iwp_graphics", prof, "Injection temperature and density", synthetic, [], ["L06"]), formats_charts)
            note("F03", "Injection temperature and density profiles", w, "RENDERED")
        curve = (res.get("charts") or {}).get("injectivity_curve", {}).get("base")
        if curve and "rate_m3d" in curve[0]:
            fig, ax = G.plt.subplots(figsize=(6.4, 4.4))
            ax.plot([r["rate_m3d"] for r in curve], [r["whp_bara"] for r in curve], color=G.PALETTE["pressure"], lw=2, marker="o")
            ax.axhline(base["whp_required_bara"], color=G.PALETTE["limit"], ls="--", lw=1)
            G.direct_label(ax, ax.get_xlim()[0], base["whp_required_bara"], "required WHP at target", G.PALETTE["limit"], dx=4, dy=6, size=7.5)
            ax.set_xlabel("Matrix injection rate [m3/d]")
            ax.set_ylabel("Wellhead pressure [bara]")
            ax.set_title("Injectivity: wellhead pressure versus rate", loc="left")
            from .iwp_style import provenance_record, save_figure

            w = save_figure(fig, d / "injectivity_curve", provenance_record("injectivity_curve", "Injectivity curve", "iwp_graphics", curve, "NeqSim InjectionWellHydraulics operating points", synthetic, [], ["L06"]), formats_charts)
            note("F04", "Injectivity curve", w, "RENDERED")
    rows = res["envelope"]["rows"]
    if rows:
        note("F05", "Operating-envelope chart", G.render("operating_envelope", d / "operating_envelope", rows, "Utilisation of limits (hatched = limit not approved)", synthetic, formats_charts, ["L14"], rows=rows), "RENDERED")
        note("F06", "Operating-envelope table", G.render("envelope_table", d / "operating_envelope_table", rows, "Operating-envelope table", synthetic, formats_charts, ["L14"], rows=rows), "RENDERED")
    if alt:
        labels = alt["labels"]
        note("F07", "Alternatives scorecard", G.render("alternatives_scorecard", d / "alternatives_scorecard", alt["scorecard"], "Normalised scores; weights " + alt["scorecard"]["weights_source"], synthetic, formats_charts, ["L15"],
                                                       sc=alt["scorecard"], labels=labels), "RENDERED")
        note("F08", "Alternatives radar", G.render("alternatives_radar", d / "alternatives_radar", alt["scorecard"]["totals"], "Radar of normalised scores", synthetic, formats_charts, ["L15"], sc=alt["scorecard"], labels=labels), "RENDERED")
        pts = {k: tuple(v) for k, v in alt["pareto_points"].items()}
        xl, yl = ("Lift gas [Sm3/d]", "Rate at operating point [Sm3/d]") if prod else ("Power [kW]", "Required wellhead pressure [bara]")
        note("F09", "Pareto view", G.render("pareto", d / "pareto", pts, "Non-dominated alternatives", synthetic, formats_charts, ["L15"], points=pts, front=alt["pareto_front"], labels=labels, xlabel=xl, ylabel=yl), "RENDERED")
        if prod:
            ref = alt["alternatives"][0]
            steps = [(r["label"][:22], (r["q_op"]["base"] or 0.0) - (ref["q_op"]["base"] or 0.0)) for r in alt["alternatives"][1:]]
            note("F10", "Waterfall from the reference alternative", G.render("waterfall", d / "waterfall", steps, "Operating-rate change vs reference", synthetic, formats_charts, ["L15"],
                                                                         reference_label=ref["label"][:22], reference_value=ref["q_op"]["base"] or 0.0, steps=steps), "RENDERED")
        if alt.get("tornado"):
            note("F11", "Tornado", G.render("tornado", d / "tornado", alt["tornado"], "One-at-a-time sensitivity", synthetic, formats_charts, ["L04"], t=alt["tornado"]), "RENDERED")
        if alt.get("sensitivity_grid"):
            note("F12", "Sensitivity heat-map", G.render("sensitivity_heatmap", d / "sensitivity_heatmap", alt["sensitivity_grid"], "Operating rate vs tubing ID and host pressure", synthetic, formats_charts, ["L04"],
                                                       g=alt["sensitivity_grid"], target=prod["base"]["target_rate"] if prod else None), "RENDERED")
        if alt.get("deliverability_profile"):
            p = alt["deliverability_profile"]
            note("F13", "Deliverability versus time", G.render("profile_bands", d / "deliverability_profile", p, "Low/base/high deliverability", synthetic, formats_charts, ["L25"], years=p["years"], cases=p["cases"], target=p["target"],
                                                            unit=get_path(basis, "targets.rate.kind") or "Sm3/d"), "RENDERED")
        nodes = decision_tree_nodes(alt)
        note("F14", "Decision tree", G.render("decision_tree", d / "decision_tree", nodes, "Completion selection decision tree", synthetic, formats_charts, ["L15"], nodes=nodes), "RENDERED")
    else:
        note("F07-F14", "Alternatives charts", None, "SKIPPED", "run the alternatives step first")
    tasks = schedule_tasks(basis)
    note("F15", "Schedule Gantt", G.render("gantt", d / "gantt", tasks, "Schedule with low-high whiskers (synthetic unless basis.schedule is supplied)", synthetic, formats_charts, [], tasks=tasks), "RENDERED")
    td = time_depth(basis)
    note("F16", "Time-depth chart", G.render("time_depth", d / "time_depth", td, "Time-depth derived from the schedule", synthetic, formats_charts, [], curves=td, band_curves=("low", "high")), "RENDERED")
    risks = build_risks(basis, res, regs.gaps)
    (paths["results"] / "risk_register.json").write_text(__import__("json").dumps(risks, indent=2), encoding="utf-8")
    note("F17", "Risk matrix", G.render("risk_matrix", d / "risk_matrix", risks, "Qualitative scoring ASSUMED", synthetic, formats_charts, [], risks=risks), "RENDERED")
    note("F18", "Risk register heat-map", G.render("risk_register", d / "risk_register", risks, "Risk register", synthetic, formats_charts, [], risks=risks), "RENDERED")
    note("F19", "Trajectory plan / section", G.render("trajectory_views", d / "trajectory_views", survey, "Minimum-curvature survey (synthetic path)", synthetic, formats_charts, ["L22"], survey=survey), "RENDERED")
    renderer = G.trajectory_3d(survey, d / "trajectory_3d.png")
    note("F20", "Trajectory 3D view ({})".format(renderer), {"png": str(d / "trajectory_3d.png")}, "RENDERED")
    with (d / "drawings_register.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "title", "drawing_no", "status", "files", "note"])
        w.writeheader()
        w.writerows(register)
    return {"register": register, "folder": str(d)}
