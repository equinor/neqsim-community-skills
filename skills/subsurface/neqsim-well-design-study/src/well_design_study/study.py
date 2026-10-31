"""End-to-end well design study driver: window, seats, casing strings, validation checks and a standards register."""

from __future__ import annotations

from typing import Dict, List, Optional

from .casing_design import DesignFactors, GRADES, Pipe, StringBasis, check_string, select_string, wellhead_rating_class
from .casing_seats import PlannedSection, evaluate_plan
from .pressure import EmwCurve, PressureModel, curve_from_points
from .units import BAR_PER_SG_M

STANDARDS_REGISTER: List[Dict[str, str]] = [
    {"id": "NORSOK D-010", "topic": "Well integrity in drilling and well operations: barriers, casing design basis, well control, abandonment plugs", "status": "NEEDS_REVIEW",
     "note": "Requirements are referenced, not quoted; verify the revision and clauses against the licensed document."},
    {"id": "API TR 5C3 / ISO 10400", "topic": "Casing and tubing performance properties: collapse, burst, axial, triaxial", "status": "IMPLEMENTED_NEEDS_REVIEW",
     "note": "Collapse formulas implemented and checked against published ratings of 9-5/8 in 47 ppf N80 (see validation); verify other sizes with the vendor pipe list."},
    {"id": "API Spec 5CT / ISO 11960", "topic": "Casing and tubing grades and dimensions", "status": "NEEDS_REVIEW", "note": "Screening catalogue of nominal sizes; not a procurement list."},
    {"id": "API RP 14E / ISO 13703", "topic": "Erosional velocity in production piping", "status": "IMPLEMENTED_NEEDS_REVIEW", "note": "C factor is an assumption; sand and CRA allowances need company criteria."},
    {"id": "API RP 13D", "topic": "Rheology and hydraulics of drilling fluids", "status": "SIMPLIFIED", "note": "Bingham-plastic slot model; not a transient or eccentric annulus model."},
    {"id": "API Spec 6A / 17D", "topic": "Wellhead and subsea tree pressure classes", "status": "NEEDS_REVIEW", "note": "Pressure class selection only; temperature and material classes not assessed."},
    {"id": "API 17TR8", "topic": "HPHT design guidelines", "status": "NEEDS_REVIEW", "note": "Applicability thresholds recalled, not read in this study."},
    {"id": "ISO 16530-1", "topic": "Well integrity lifecycle governance", "status": "NEEDS_REVIEW", "note": "Referenced for completeness."},
]


def build_pressure_model(spec: Dict[str, object]) -> PressureModel:
    """Build a PressureModel from ``spec['pressure']`` with keys pore and frac, each {low|base|high: [[tvd, sg], ...]}."""
    p = spec["pressure"]
    pore = {k: curve_from_points(v) for k, v in p["pore"].items()}
    frac = {k: curve_from_points(v) for k, v in p["frac"].items()}
    ref = spec.get("reference", {})
    return PressureModel(pore, frac, float(ref.get("water_depth_m", 0.0)), float(ref.get("air_gap_m", 0.0)), list(p.get("notes", [])))


def _sections(spec) -> List[PlannedSection]:
    out = []
    prev_strength = None
    for s in spec["sections"]:
        out.append(PlannedSection(s["name"], s["hole_in"], s.get("casing_od_in") or 0.0, s["top_tvd_m"], s["shoe_tvd_m"], s["shoe_md_m"], s["mud_sg"],
                                  s.get("drill_pipe_od_in", 5.5), bool(s.get("riserless", False)), prev_strength, not s.get("casing_od_in")))
        prev_strength = s.get("shoe_strength_sg")
    return out


def run_well_study(spec: Dict[str, object]) -> Dict[str, object]:
    """Run window, seat, kick-tolerance and casing-string design from a specification dict.

    ``spec`` keys: ``name``, ``reference`` (water_depth_m, air_gap_m), ``pressure``, ``sections`` (name, hole_in,
    casing_od_in, top_tvd_m, shoe_tvd_m, shoe_md_m, mud_sg, toc_tvd_m, grades, optional load settings), ``kick`` (intensity_sg,
    influx_sg, kt_min_m3, gas_sg, basis), ``margins``, ``design_factors``, ``max_temp_c`` and ``completion`` (shut_in_wellhead_bar, packer_fluid_sg,
    test_pressure_bar, max_surface_pressure_bar).

    Section options: ``casing_od_in`` of ``None`` marks an open-hole section (window and kick tolerance only, no string); ``riserless`` skips
    the kick tolerance; ``shoe_strength_sg`` is a planned or measured leak-off EMW at the section shoe that replaces the model fracture in
    the kick tolerance of the next section and in the gas-kick load cap; ``production`` marks the string that carries the shut-in wellhead
    pressure (default: the last cased section); ``fixed_pipe`` (od_in, wall_in, grade) checks an existing design instead of selecting one;
    ``string_top_tvd_m`` is the hanger depth of a liner.
    """
    model = build_pressure_model(spec)
    kick = spec.get("kick", {})
    mar = spec.get("margins", {})
    dfs = DesignFactors(**spec.get("design_factors", {}))
    secs = _sections(spec)
    plan = evaluate_plan(model, secs, kick.get("intensity_sg", 0.06), kick.get("influx_sg", 0.25), kick.get("kt_min_m3", 8.0),
                         pore_case=mar.get("pore_case", "high"), frac_case=mar.get("frac_case", "low"),
                         trip_margin_sg=mar.get("trip_margin_sg", 0.04), frac_margin_sg=mar.get("frac_margin_sg", 0.03),
                         kick_basis=kick.get("basis", "mud"))
    strings: List[Dict[str, object]] = []
    comp = spec.get("completion", {})
    max_t = float(spec.get("max_temp_c", 20.0))
    sections = spec["sections"]
    cased = [i for i, s in enumerate(sections) if s.get("casing_od_in")]
    flagged = [i for i in cased if sections[i].get("production")]
    prod_idx = flagged[-1] if flagged else (cased[-1] if cased else -1)
    for i, s in enumerate(sections):
        if not s.get("casing_od_in"):
            continue
        is_prod = i == prod_idx
        nxt = sections[i + 1] if i + 1 < len(sections) else None
        next_td = nxt["shoe_tvd_m"] if nxt else s["shoe_tvd_m"]
        next_mud = nxt["mud_sg"] if nxt else model.pore_sg(s["shoe_tvd_m"], "high")
        if nxt and kick.get("basis", "mud") == "pore":
            next_mud = model.pore_sg(next_td, mar.get("pore_case", "high"))
        shoe_frac = s.get("shoe_strength_sg") or model.frac_sg(s["shoe_tvd_m"], "low")
        basis = StringBasis(
            name=s["name"], od_in=s["casing_od_in"], top_tvd_m=s.get("string_top_tvd_m", model.mudline_tvd_m), shoe_tvd_m=s["shoe_tvd_m"],
            shoe_md_m=s["shoe_md_m"], toc_tvd_m=s.get("toc_tvd_m", s["shoe_tvd_m"] - 300.0), mud_sg=s["mud_sg"], next_td_tvd_m=next_td,
            next_mud_sg=next_mud, next_pore_sg=model.pore_sg(next_td, "high"), frac_shoe_sg=shoe_frac,
            pore_sg_at=(lambda z, m=model: m.pore_sg(z, "base")), gas_sg=kick.get("gas_sg", 0.25), kick_intensity_sg=kick.get("intensity_sg", 0.06),
            packer_fluid_sg=comp.get("packer_fluid_sg", 1.20), shut_in_wellhead_bar=comp.get("shut_in_wellhead_bar") if is_prod else None,
            test_pressure_bar=s.get("test_pressure_bar"), evacuation_fraction=s.get("evacuation_fraction", 0.5),
            evacuation_basis=s.get("evacuation_basis", spec.get("evacuation_basis", "fraction")),
            evacuation_external=s.get("evacuation_external", spec.get("evacuation_external", "mud_or_pore")),
            water_depth_m=model.water_depth_m, air_gap_m=model.air_gap_m, max_temp_c=min(max_t, s.get("max_temp_c", max_t)),
            overpull_kn=s.get("overpull_kn", 400.0), cap_gas_at_frac=not is_prod or bool(s.get("cap_gas_at_frac", False)),
        )
        grades = s.get("grades", ["L80", "P110"])
        if s.get("fixed_pipe"):
            fp = s["fixed_pipe"]
            res = check_string(Pipe(fp["od_in"], fp["wall_in"], fp["grade"]), basis, dfs)
            strings.append({"string": s["name"], "od_in": s["casing_od_in"], "selected": res if res["passes"] else None, "candidates": [res],
                            "status": "FIXED_PASSES" if res["passes"] else "FIXED_FAILS", "basis": basis, "checked": res})
        else:
            sel = select_string(basis, grades, dfs)
            sel["basis"] = basis
            strings.append(sel)
    wh = None
    if comp.get("max_surface_pressure_bar"):
        wh = wellhead_rating_class(float(comp["max_surface_pressure_bar"]), margin=comp.get("wellhead_margin", 1.0))
    checks = validation_checks(model, plan, strings, wh)
    blocked = [c for c in checks if c["status"] == "FAIL"]
    return {"name": spec.get("name", "well"), "model": model, "plan": plan, "strings": strings, "wellhead": wh, "design_factors": dfs.__dict__,
            "checks": checks, "readiness": "BLOCKED_BY_FAILED_CHECKS" if blocked else "SCREENING_READY_FOR_HUMAN_REVIEW", "standards": STANDARDS_REGISTER}

def validation_checks(model: PressureModel, plan: List[Dict[str, object]], strings: List[Dict[str, object]], wellhead: Optional[Dict[str, float]]) -> List[Dict[str, str]]:
    """Fail-closed checks: geometry, window, kick tolerance, casing selection and a published-rating cross-check."""
    out: List[Dict[str, str]] = []

    def add(name: str, ok: Optional[bool], detail: str) -> None:
        out.append({"check": name, "status": "PASS" if ok else ("N/A" if ok is None else "FAIL"), "detail": detail})

    ref = Pipe(9.625, 0.472, "N80").ratings(20.0)
    from .units import bar_to_psi
    c_psi, b_psi = bar_to_psi(ref["collapse_bar"]), bar_to_psi(ref["burst_bar"])
    add("API 5C3 collapse 9-5/8 47 ppf N80 vs published 4760 psi", abs(c_psi - 4760.0) / 4760.0 < 0.02, f"computed {c_psi:.0f} psi")
    add("API 5C3 burst 9-5/8 47 ppf N80 vs published 6870 psi", abs(b_psi - 6870.0) / 6870.0 < 0.02, f"computed {b_psi:.0f} psi")
    prev = None
    ok_geo = True
    for r in plan:
        if prev is not None and abs(float(r["top_tvd_m"]) - prev) > 1e-6:
            ok_geo = False
        prev = float(r["bottom_tvd_m"])
    add("Sections are contiguous (top = previous shoe)", ok_geo, "")
    for r in plan:
        add(f'Window: {r["section"]}', bool(r["window_ok"]),
            f'planned {float(r["mud_sg_planned"]):.2f} sg, window {float(r["min_mw_required_sg"]):.2f}-{float(r["max_mw_allowed_sg"]):.2f} sg')
        if r.get("kt_ok") is not None:
            add(f'Kick tolerance: {r["section"]}', bool(r["kt_ok"]), f'{float(r["kt_volume_m3"]):.1f} m3 vs {float(r["kt_required_m3"]):.0f} m3 required')
    for s in strings:
        add(f'Casing selected: {s["string"]}', s["status"] in ("SELECTED", "FIXED_PASSES"), s["status"])
    if wellhead is not None:
        add("Wellhead pressure class found", wellhead["class_psi"] == wellhead["class_psi"], f'{wellhead["class_psi"]:.0f} psi, utilisation {wellhead["utilisation"]:.2f}')
    return out
