"""Well-planning report (Word + Markdown) assembled from the study folder.

Fail-closed labelling: the readiness label is NOT READY when the basis validation has errors or a blocking gap is open; otherwise the report
is labelled SCREENING - FOR REVIEW. The report never contains a compliance or approval statement.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .basis import basis_to_registers, load_basis, validate_basis
from .ledger import JAVA_FOLLOW_UPS, ledger_rows
from .registers import Registers, get_path
from .standards import seed_register, summarise as std_summary
from .study import load_json, study_paths

SECTIONS = [
    "Executive summary and recommended concept", "Design basis, sources, assumptions and standards", "Reservoir and fluid description", "Alternatives and selection rationale",
    "Performance calculations and operating envelopes", "Trajectory, drilling, completion and integrity interfaces", "Flow-assurance and operational assessments",
    "Risks, uncertainties, data gaps and follow-up", "Cost and schedule", "Validation evidence and calculation records", "Appendices", "Revision control",
]


def readiness(basis: Dict[str, Any], regs: Registers) -> str:
    """Return the readiness label (never an approval)."""
    rep = validate_basis(basis)
    if rep.errors or regs.blocking_gaps():
        return "NOT READY - basis errors or blocking gaps"
    return "SCREENING - FOR REVIEW (synthetic demonstration)" if get_path(basis, "study.synthetic") else "SCREENING - FOR REVIEW"


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return "{:.{nd}g}".format(v, nd=nd)
    return str(v)


def executive_summary(basis: Dict[str, Any], res: Dict[str, Any], alt: Optional[Dict[str, Any]]) -> List[str]:
    """Answer-first paragraphs built from the numbers."""
    wtype = get_path(basis, "well.type")
    lines = ["Purpose: {}.".format(get_path(basis, "study.purpose") or get_path(basis, "study.title"))]
    prod, inj = res.get("producer"), res.get("injector")
    if prod:
        b = prod["base"]
        lines.append("Base case: the well {} the target of {} {} (operating rate {} at BHP {} bara, drawdown {} bar; surplus at target {} bar). Low case: target {}; high case: target {}.".format(
            "meets" if b["target_met"] else "does NOT meet", _fmt(b["target_rate"]), get_path(basis, "targets.rate.kind"), _fmt(b.get("q_op")), _fmt(b.get("bhp_op")), _fmt(b.get("drawdown_bar")),
            _fmt(b["surplus_at_target_bar"]), "met" if prod["low"]["target_met"] else "missed", "met" if prod["high"]["target_met"] else "missed"))
        tub = b.get("tubing", {})
        lines.append("Tubing: erosional ratio {} (API RP 14E basis, C-factor input), wellhead {} bara / {} C.".format(_fmt(tub.get("erosional_ratio_max")), _fmt((b.get("wellhead") or {}).get("pressure_bara")),
                                                                                                             _fmt((b.get("wellhead") or {}).get("temperature_C"))))
    if inj:
        b = inj["base"]
        lines.append("Base case: required wellhead pressure {} bara for {} (bottom-hole {} bara, fracture margin {} bar, surface duty {} kW).".format(_fmt(b.get("whp_required_bara")), _fmt(b.get("rate")),
                                                                                                                                         _fmt(b.get("bhp_bara")), _fmt(b.get("fracture_margin_bar")), _fmt(b.get("power_kw"))))
    if alt and alt.get("recommendation"):
        r = alt["recommendation"]
        lines.append("Recommended concept (screening): {} - {}. Weights: {}. Deliverability basis only; recovery and project value are not inferred.".format(r["label"], r["basis"], r.get("weights", "n/a")))
    s = res["envelope"]["summary"]
    lines.append("Operating envelope: {} rows - {}. Rows are NEEDS_REVIEW until approved limits with sources are supplied.".format(sum(s.values()), ", ".join("{} {}".format(v, k) for k, v in s.items() if v)))
    return lines


def build_report(root: Path) -> Dict[str, str]:
    """Write report/well_planning_report.docx and .md; returns the paths."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm, Pt, RGBColor

    paths = study_paths(root)
    basis = load_basis(paths["basis"] / "planning_basis.yaml")
    res = load_json(paths["results"] / "model_results.json")
    alt = load_json(paths["results"] / "alternatives.json") if (paths["results"] / "alternatives.json").exists() else None
    regs = Registers.load(paths["registers"])
    if not regs.items:
        regs = basis_to_registers(basis)
    gaps = regs.gaps
    risks = load_json(paths["results"] / "risk_register.json") if (paths["results"] / "risk_register.json").exists() else []
    dreg = []
    if (paths["drawings"] / "drawings_register.csv").exists():
        import csv

        dreg = list(csv.DictReader((paths["drawings"] / "drawings_register.csv").open(encoding="utf-8")))
    label = readiness(basis, regs)
    sid, well = get_path(basis, "study.id"), get_path(basis, "well.id")
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.0)
    md: List[str] = []

    def h(text: str, level: int = 1) -> None:
        doc.add_heading(text, level)
        md.append("\n{} {}\n".format("#" * (level + 1), text))

    def p(text: str, bold: bool = False) -> None:
        para = doc.add_paragraph()
        run = para.add_run(text)
        run.bold = bold
        md.append(("**{}**" if bold else "{}").format(text) + "\n")

    def table(headers: List[str], rows: List[List[Any]], widths: Optional[List[float]] = None) -> None:
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Light Grid Accent 1"
        for i, hd in enumerate(headers):
            t.rows[0].cells[i].text = hd
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = _fmt(v) if not isinstance(v, str) else v
        for row in t.rows:
            for c in row.cells:
                for para in c.paragraphs:
                    for run in para.runs:
                        run.font.size = Pt(8)
        md.append("| " + " | ".join(headers) + " |\n|" + "---|" * len(headers))
        for r in rows:
            md.append("| " + " | ".join((_fmt(v) if not isinstance(v, str) else v).replace("|", "/") for v in r) + " |")
        md.append("")

    def fig(stem: str, caption: str, width_cm: float = 15.5) -> None:
        f = paths["drawings"] / (stem + ".png")
        if f.exists():
            doc.add_picture(str(f), width=Cm(width_cm))
            cp = doc.add_paragraph(caption)
            cp.runs[0].italic = True
            md.append("![{}](../drawings/{}.png)\n\n*{}*\n".format(caption, stem, caption))

    # cover
    t = doc.add_heading("Well planning report", 0)
    md.append("# Well planning report\n")
    p("{} - {}".format(well, get_path(basis, "study.title")), True)
    p("Study {} revision {} - {} - tool integrated_well_planning {}".format(sid, get_path(basis, "study.revision"), _dt.date.today().isoformat(), __version__))
    p("Readiness label: " + label, True)
    if get_path(basis, "study.synthetic"):
        r = doc.add_paragraph().add_run("SYNTHETIC DEMONSTRATION: every input is a demonstration assumption. Nothing in this report is field data or a design approval.")
        r.bold = True
        r.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
        md.append("**SYNTHETIC DEMONSTRATION: every input is a demonstration assumption. Nothing here is field data or a design approval.**\n")
    p("Human review is required. This report does not replace detailed well design, well-control, geomechanics, drilling, cementing or specialist integrity assessments, and makes no compliance statement.")
    # 1
    h("1. " + SECTIONS[0])
    for line in executive_summary(basis, res, alt):
        p(line)
    # 2
    h("2. " + SECTIONS[1])
    p("Planning basis: maturity {}, well type {}, environment {}. Depth reference {} ({} m above MSL); MD, TVD and TVDSS follow the reference; pressures {}; standard conditions {}.".format(
        get_path(basis, "study.maturity"), get_path(basis, "well.type"), get_path(basis, "well.environment"), get_path(basis, "datums.reference") or "RKB", get_path(basis, "datums.reference_elevation_msl_m"),
        get_path(basis, "datums.pressure_reference") or "bara", json.dumps(get_path(basis, "datums.standard_conditions") or {"temperature_C": 15, "pressure_bara": 1.01325})))
    h("2.1 Source and assumptions register", 2)
    counts = regs.provenance_counts()
    p("Provenance counts: " + ", ".join("{} {}".format(v, k) for k, v in counts.items()) + ". Full register: registers/source_register.csv.")
    table(["Key", "Value", "Class", "Source"], [[k, str(i.value)[:40], i.provenance, i.source[:50]] for k, i in list(regs.items.items())[:18]])
    h("2.2 Standards and acceptance basis", 2)
    std = seed_register(get_path(basis, "standards.jurisdiction") or "TO_BE_IDENTIFIED")
    p("Standards register status: {}. Editions, amendments, applicability and exclusions are NOT verified by this tool; design factors, ratings and acceptance limits are never defaulted.".format(std_summary(std)))
    table(["ID", "Topic", "Source document", "Assessment area", "Status"], [[s.id, s.requirement_topic[:70], s.source_document[:44], s.assessment_area, s.status] for s in std])
    # 3
    h("3. " + SECTIONS[2])
    p("Reservoir: pressure {} bara, temperature {} C, permeability {} mD, thickness {} m, skin {}, drainage radius {} m. Fluid: {} EOS, {} components (see source register).".format(
        json.dumps(get_path(basis, "reservoir.pressure_bara")), get_path(basis, "reservoir.temperature_C"), json.dumps(get_path(basis, "reservoir.permeability_md")), get_path(basis, "reservoir.thickness_m"),
        json.dumps(get_path(basis, "reservoir.skin")), get_path(basis, "reservoir.drainage_radius_m"), get_path(basis, "fluid.eos") or "SRK", len(get_path(basis, "fluid.components") or [])))
    table(["Component", "Mole fraction", "Origin"], [[c["name"], c["mole_fraction"], c.get("origin", "")] for c in get_path(basis, "fluid.components")])
    p("Thermodynamic model: {} equation of state, classic (or CPA where water is present) mixing rules, uncalibrated to laboratory PVT unless supplied (data gap if empty). Validity: reservoir and tubing conditions of this study only.".format(get_path(basis, "fluid.eos") or "SRK"))
    # 4
    h("4. " + SECTIONS[3])
    if alt:
        table(["Alternative", "Base rate / WHP", "Target met (L/B/H)", "Binding constraint", "Score"], [[r["label"], _fmt((r.get("q_op") or {}).get("base") if "q_op" in r else (r.get("whp_required") or {}).get("base")),
              "/".join("Y" if (r.get("target_met", {}).get(c) if "target_met" in r else r["status"][c] == "OK") else "N" for c in ("low", "base", "high")), r.get("binding_constraint", ""),
              _fmt(alt["scorecard"]["totals"][r["id"]], 2)] for r in alt["alternatives"]])
        p("Weights: {}. Criteria without data (excluded from totals): {}. {}".format(alt["scorecard"]["weights_source"], ", ".join(alt["scorecard"]["criteria_without_data"]) or "none", alt["statement"]))
        fig("alternatives_scorecard", "Figure: alternatives scorecard")
        fig("pareto", "Figure: non-dominated alternatives")
        fig("tornado", "Figure: one-at-a-time sensitivity")
        fig("decision_tree", "Figure: completion decision tree")
    else:
        p("Alternatives step not run.")
    # 5
    h("5. " + SECTIONS[4])
    if res.get("producer"):
        table(["Case", "Status", "Operating rate", "BHP [bara]", "Drawdown [bar]", "Surplus at target [bar]", "Target met"], [[c, r["status"], r.get("q_op"), r.get("bhp_op"), r.get("drawdown_bar"), r["surplus_at_target_bar"],
              r["target_met"]] for c, r in res["producer"].items()])
        fig("nodal_analysis", "Figure: nodal analysis")
        fig("wellbore_profiles", "Figure: wellbore profiles")
    if res.get("injector"):
        table(["Case", "Status", "Rate", "BHP req. [bara]", "WHP req. [bara]", "Fracture margin [bar]", "Duty [kW]"], [[c, r["status"], r.get("rate"), r.get("bhp_required_bara"), r.get("whp_required_bara"),
              r.get("fracture_margin_bar"), r.get("power_kw")] for c, r in res["injector"].items()])
        fig("injection_profiles", "Figure: injection temperature and density")
        fig("injectivity_curve", "Figure: injectivity curve")
    if alt and alt.get("deliverability_profile"):
        fig("deliverability_profile", "Figure: deliverability versus time (capacity, not a forecast)")
    h("5.1 Operating-envelope table", 2)
    p("Limits come from the basis with their source; NEEDS_REVIEW means the limit is missing or not approved. Calculated values are kept separate from verified ratings and approved limits.")
    table(["ID", "Parameter", "Condition", "Min", "Max", "Basis", "Predicted", "Margin", "Status", "Action"], [[r["id"], r["parameter"], r["condition"][:30], r["min_limit"], r["max_limit"], r["limit_basis"], r["predicted"],
          r["margin_to_limit"], r["status"] + (" [" + r["indicative_status"] + "]" if r["status"] == "NEEDS_REVIEW" else ""), r["action"][:46]] for r in res["envelope"]["rows"]])
    fig("operating_envelope", "Figure: utilisation of limits")
    # 6
    h("6. " + SECTIONS[5])
    tr = res["trajectory"]
    p("Trajectory: {} (TD {:.0f} m MD / {:.0f} m TVD, max inclination {:.1f} deg, max DLS {:.2f} deg/30 m, DLS limit status {}). Datum consistency: {}.".format(
        tr["source"], tr["summary"]["td_md_m"], tr["summary"]["td_tvd_m"], tr["summary"]["max_inclination_deg"], tr["summary"]["max_dls_deg_per_30m"], tr["summary"]["dls_limit_status"], tr["status"]))
    fig("well_schematic", "Figure: well schematic (see drawing {}-DWG-001)".format(sid), 16.0)
    fig("trajectory_views", "Figure: trajectory plan and section")
    p("Casing programme formula ratings (API TR 5C3 formulas; no loads applied):")
    table(["String", "OD [in]", "Grade", "Burst [bar]", "Collapse [bar]"], [[c["string"], c.get("od_in"), c.get("grade"), c.get("burst_bar"), c.get("collapse_bar")] for c in res["casing_ratings"]])
    pw = res["pressure_window"]
    if pw.get("rows"):
        p("Pressure window at casing shoes (arithmetic only; margins not defined): " + pw["status"])
    h("6.1 Integrity (screening)", 2)
    integ = res.get("integrity", {})
    if integ.get("tubing"):
        table(["State", "Burst load [bar]", "Burst util.", "Collapse load [bar]", "Collapse util.", "Design-factor status"], [[t["state"], t.get("burst_load_bar"), t.get("burst_utilisation"), t.get("collapse_load_bar"),
              t.get("collapse_utilisation"), t.get("burst_status", "")[:40]] for t in integ["tubing"]])
    if integ.get("apb"):
        a = integ["apb"]
        p("Annular pressure build-up (annulus A, free-standing outer string): {} bar for a mean temperature change of {} K (rigid limit {} bar).".format(_fmt(a["delta_pressure_bar"]), _fmt(a["delta_t_mean_K"]), _fmt(a["rigid_limit_bar"])))
    for mv in integ.get("tubing_movement", []):
        p("Tubing movement ({} packer, {}): free {} m (piston {}, balloon {}, temperature {}, buckling {}), axial force change {} kN.".format(mv["packer_mode"], mv["state"], _fmt(mv["free_movement_m"]), _fmt(mv["piston_m"]),
                                                                                                                       _fmt(mv["balloon_m"]), _fmt(mv["temperature_m"]), _fmt(mv["buckling_m"]), _fmt(mv["axial_force_change_kn"])))
    p("Barrier schematics: elements proposed per well state, all {} - no compliance statement.".format("UNVERIFIED"))
    fig("barrier_schematics", "Figure: barrier schematics (see drawing {}-DWG-002)".format(sid), 16.0)
    h("6.2 Interface specifications (UNRESOLVED assessments)", 2)
    table(["ID", "Assessment", "Receiver", "Inputs missing", "Status"], [[s["id"], s["assessment"][:50], s["receiver"][:46], ", ".join(s["inputs_missing"])[:70], s["status"]] for s in res["interface_specs"]])
    # 7
    h("7. " + SECTIONS[6])
    fa = res.get("flow_assurance", {})
    hy = fa.get("hydrate")
    if hy and hy.get("status") == "SCREENING":
        p("Hydrate (CPA): wellhead margin {} K, minimum margin along the well {} K; MEG governing station '{}' requires {} wt% lean basis {}, lean solution {} m3/h. Shut-in cooldown: {}. {}".format(
            _fmt(hy["wellhead_margin_K"]), _fmt(hy["min_margin_K"]), hy["inhibitor"]["governing_station"], _fmt(hy["inhibitor"]["required_weight_fraction"] * 100.0), _fmt(hy["inhibitor"]["lean_weight_fraction"]),
            _fmt(hy["inhibitor"]["lean_solution_m3_per_h"]), json.dumps(hy.get("shut_in_cooldown")), hy["basis_note"]))
    for k in ("wax", "scale", "transient", "contaminants", "loading_erosion"):
        if k in fa:
            p("{}: {}".format(k.replace("_", " ").capitalize(), json.dumps(fa[k], default=str)[:420]))
    # 8
    h("8. " + SECTIONS[7])
    table(["Key", "Severity", "Description", "Consequence"], [[g.key, g.severity, g.description[:60], g.consequence[:70]] for g in gaps])
    fig("risk_matrix", "Figure: risk matrix (qualitative, ASSUMED scoring)", 11.0)
    fig("risk_register", "Figure: risk register")
    p("Open actions: {}".format("; ".join("{} {}".format(a.id, a.description) for a in regs.open_actions()) or "none"))
    # 9
    h("9. " + SECTIONS[8])
    p("Cost: {}. Schedule: durations are {} (see Gantt). Currency {}; cost exclusions: reservoir recovery, project value, drilling cost unless supplied.".format(
        json.dumps(get_path(basis, "cost")) if get_path(basis, "cost") else "NOT SUPPLIED - no cost estimate is made", "supplied by the basis" if get_path(basis, "schedule") else "a labelled synthetic default", get_path(basis, "study.currency") or "n/a"))
    fig("gantt", "Figure: schedule with low-high whiskers")
    fig("time_depth", "Figure: time-depth chart")
    # 10
    h("10. " + SECTIONS[9])
    p("Calculation records: results/model_results.json; re-run with models/rerun_model.py. Runtime: wellplanning classes available = {}.".format(res["meta"]["runtime"]["wellplanning_available"]))
    p("Capability ledger (status of every calculation):")
    table(["ID", "Calculation", "Status", "Implementation", "Available"], [[r["id"], r["calculation"][:70], r["status"], r["implementation"][:50], r["available"]] for r in ledger_rows()])
    p("Java follow-ups recorded: " + " | ".join(JAVA_FOLLOW_UPS))
    # 11
    h("11. " + SECTIONS[10])
    h("A. Drawings register", 2)
    table(["ID", "Title", "Drawing no.", "Status", "Files"], [[d["id"], d["title"], d["drawing_no"], d["status"], d["files"][:60]] for d in dreg])
    h("B. Decision and action log", 2)
    table(["ID", "Decision", "Status", "Date"], [[d.id, d.title + ": " + d.decision[:60], d.status, d.date] for d in regs.decisions])
    table(["ID", "Action", "Owner", "Status"], [[a.id, a.description[:80], a.owner, a.status] for a in regs.actions])
    h("C. Hand-off register", 2)
    hdir = paths["results"] / "handoffs"
    table(["Message", "File"], [[f.stem, f.name] for f in sorted(hdir.glob("*.json"))] if hdir.exists() else [])
    # 12
    h("12. " + SECTIONS[11])
    table(["Rev", "Date", "Description", "Author"], [[get_path(basis, "study.revision") or "A", _dt.date.today().isoformat(), "Issued for review - " + label, get_path(basis, "study.author") or "neqsim-community"]])
    paths["report"].mkdir(parents=True, exist_ok=True)
    docx_path = paths["report"] / "well_planning_report.docx"
    md_path = paths["report"] / "well_planning_report.md"
    doc.save(str(docx_path))
    md_path.write_text("\n".join(md), encoding="utf-8")
    return {"docx": str(docx_path), "md": str(md_path), "readiness": label}
