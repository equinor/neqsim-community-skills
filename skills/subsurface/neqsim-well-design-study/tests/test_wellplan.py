"""Tests for the well-plan graphics, charts, professional report builder and the casing load-basis helpers (synthetic data only)."""

import datetime as dt
import math
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("docx")

from well_design_study import (DesignFactors, Pipe, StringBasis, alternative_pipes, check_string, collapse_basis_comparison, drift_diameter_in,
                               max_evacuation_level_for_collapse, run_well_study)
from well_design_study import wellplan_charts as wc
from well_design_study import wellplan_graphics as wg
from well_design_study.report import WellPlanReport, _is_numeric_cell


def _png_ok(path, min_w=1200):
    from PIL import Image

    with Image.open(path) as im:
        assert im.width >= min_w and im.height >= 600
        return im.size


def _liner_basis(**kw):
    base = dict(name="liner", od_in=17.0, top_tvd_m=1300.0, shoe_tvd_m=1700.0, shoe_md_m=1700.0, toc_tvd_m=1300.0, mud_sg=1.40, next_td_tvd_m=2700.0, next_mud_sg=1.50,
                next_pore_sg=1.25, frac_shoe_sg=1.60, pore_sg_at=lambda z: 1.03, water_depth_m=350.0, air_gap_m=25.0, max_temp_c=50.0, evacuation_basis="pore_balance")
    base.update(kw)
    return StringBasis(**base)


def test_dodge_keeps_order_and_gap():
    out = wg.dodge([100.0, 105.0, 110.0, 400.0], 30.0)
    assert out[0] < out[1] < out[2] < out[3]
    assert all(b - a >= 30.0 - 1e-9 for a, b in zip(sorted(out), sorted(out)[1:]))
    capped = wg.dodge([900.0, 905.0, 910.0], 30.0, hi=920.0)
    assert max(capped) <= 920.0 and min(capped) < 900.0


def test_well_schematic_sheet_renders(tmp_path):
    z = np.arange(400.0, 4100.0, 50.0)
    spec = {
        "well": "SYN-1", "subtitle": "synthetic example", "rig": "semi-submersible (assumed)", "water_depth_m": 350.0, "air_gap_m": 25.0, "td_md_m": 4000.0, "td_tvd_m": 4000.0,
        "strings": [
            {"name": "conductor", "casing_od_in": 36.0, "hole_in": 42.0, "top_tvd_m": 375.0, "shoe_tvd_m": 450.0, "toc_tvd_m": 375.0, "mud_type": "seawater", "mud_sg": 1.03, "riserless": True, "status": "ASSUMED"},
            {"name": "surface", "casing_od_in": 20.0, "hole_in": 26.0, "top_tvd_m": 450.0, "shoe_tvd_m": 1300.0, "toc_tvd_m": 375.0, "mud_type": "WBM", "mud_sg": 1.20, "status": "DERIVED", "pipe": "grade X"},
            {"name": "liner", "casing_od_in": 13.375, "hole_in": 17.5, "top_tvd_m": 1250.0, "shoe_tvd_m": 2600.0, "toc_tvd_m": 1250.0, "liner": True, "mud_type": "OBM", "mud_sg": 1.40, "status": "VERIFIED"},
            {"name": "open hole", "casing_od_in": None, "hole_in": 8.5, "top_tvd_m": 2600.0, "shoe_tvd_m": 4000.0, "mud_type": "OBM", "mud_sg": 1.60, "status": "UNVERIFIED-SOURCE"},
        ],
        "tops": [("Top A", 1800.0), ("Top B", 2900.0), ("Top C", 3500.0)], "target": ("Reservoir", 3800.0),
        "tracks": {"z": z, "pore_low": np.full_like(z, 1.03), "pore_base": np.linspace(1.03, 1.25, z.size), "pore_high": np.linspace(1.03, 1.4, z.size),
                   "frac_low": np.linspace(1.4, 1.8, z.size), "frac_base": np.linspace(1.5, 1.9, z.size), "frac_high": np.linspace(1.6, 2.0, z.size),
                   "extras": [{"label": "measured", "x": [1.3, 1.35], "y": [2800.0, 3300.0], "marker": "D"}]},
        "bop": {"label": "BOP (assumed 15 ksi)"}, "notes": ["All numbers are synthetic.", "No design value."],
        "title_block": {"title": "Well schematic", "subtitle": "synthetic", "doc_id": "SYN-001", "rev": "A", "date": "2026-01-01", "status": "DRAFT", "classification": "PUBLIC"},
        "revisions": [("A", "2026-01-01", "first issue", "-")],
    }
    p = wg.well_schematic_sheet(spec, tmp_path / "sheet.png")
    w, h = _png_ok(p, 3000)
    assert abs(w / h - 420 / 297) < 0.02


def test_bop_and_barrier_and_trajectory(tmp_path):
    bop = wg.bop_stack_sketch({"title": "BOP", "elements": [{"label": "wellhead", "kind": "wellhead", "rating": "10 ksi"}, {"label": "pipe ram", "kind": "ram", "rating": "15 ksi"},
                                                         {"label": "annular", "kind": "annular", "rating": "10 ksi"}, {"label": "flex joint", "kind": "flex"}], "lines": ["synthetic"]}, tmp_path / "bop.png")
    _png_ok(bop, 1000)
    bar = wg.barrier_schematic({"title": "abandon", "water_depth_m": 350.0, "air_gap_m": 25.0, "td_m": 3000.0,
                                "strings": [{"label": "20 in", "od_in": 20.0, "top_m": 375.0, "shoe_m": 1000.0}, {"label": "9 5/8 in", "od_in": 9.625, "top_m": 375.0, "shoe_m": 2500.0}],
                                "plugs": [{"label": "reservoir plug", "top_m": 2300.0, "bottom_m": 2500.0, "role": "primary"}, {"label": "secondary", "top_m": 1800.0, "bottom_m": 2000.0, "role": "secondary"},
                                          {"label": "surface plug", "top_m": 380.0, "bottom_m": 480.0, "role": "environmental"}], "zones": [("reservoir", 2600.0, 2900.0)],
                                "cap_rock": ("cap rock", 2300.0, 2600.0), "cut_depth_m": 5.0, "footer": "synthetic"}, tmp_path / "bar.png")
    _png_ok(bar, 1000)
    n = np.linspace(0, 1500, 50)
    tr = wg.trajectory_plan_section({"plan A": {"e": n * 0.5, "n": n * 0.8, "tvd": np.linspace(0, 3000, 50)}, "plan B": {"e": -n, "n": n * 0.1, "tvd": np.linspace(0, 3000, 50)}}, tmp_path / "traj.png",
                                    offsets=[{"name": "OFF-1", "e": 1000.0, "n": -800.0}, {"name": "OFF-2", "e": 1005.0, "n": -790.0}], rings_m=[500.0, 1000.0])
    _png_ok(tr, 1200)
    sw = wg.anticollision_sweep_plot(list(range(0, 360, 30)), [1500, 1400, 1000, 500, 300, 800, 1200, 1500, 1500, 1500, 1500, 1500], [50, 40, 20, 5, 2, 10, 30, 50, 60, 60, 60, 60], tmp_path / "sw.png")
    _png_ok(sw, 1000)


def test_charts_render(tmp_path):
    acts = [{"name": "Mobilise", "p50": 3, "kind": "wait", "p10": 2, "p90": 5}, {"name": "36 in", "p50": 4, "p10": 3, "p90": 6, "group": "A"}, {"name": "Log", "p50": 5, "kind": "evaluation", "p10": 4, "p90": 8},
            {"name": "P&A", "p50": 6, "kind": "abandon", "p10": 5, "p90": 9}, {"name": "NPT allowance", "p50": 4, "kind": "npt", "p10": 0, "p90": 14}]
    _png_ok(wc.gantt_chart(acts, tmp_path / "g.png", spud_date=dt.date(2027, 5, 1), total={"p10": 14, "p50": 22, "p90": 40}), 1200)
    risks = [{"id": f"R{i:02d}", "event": f"event {i}", "likelihood": 1 + i % 5, "severity": 1 + (i * 2) % 5, "res_likelihood": max(1, i % 5), "res_severity": 1 + (i * 2) % 5} for i in range(1, 11)]
    _png_ok(wc.risk_matrix(risks, tmp_path / "r.png"), 1200)
    tree = {"label": "Loss of returns?", "kind": "question", "children": [{"edge": "partial", "node": {"label": "LCM pill, reduce rate", "kind": "action"}},
                                                                       {"edge": "total", "node": {"label": "Set contingency liner", "kind": "contingency",
                                                                                                    "children": [{"edge": "ok", "node": {"label": "continue", "kind": "outcome"}},
                                                                                                                 {"edge": "fail", "node": {"label": "sidetrack or abandon", "kind": "stop"}}]}}]}
    _png_ok(wc.decision_tree(tree, tmp_path / "t.png"), 1000)
    rng = np.random.default_rng(1)
    _png_ok(wc.s_curve_plot({"days": rng.lognormal(4, 0.3, 2000), "cost": rng.lognormal(5, 0.2, 2000)}, tmp_path / "s.png", {"days": "d", "cost": "MNOK"}), 1500)
    p10 = [(0, 0), (10, 1000), (20, 2000)]
    p50 = [(0, 0), (14, 1000), (28, 2000)]
    p90 = [(0, 0), (20, 1000), (40, 2000)]
    _png_ok(wc.time_depth_band_plot({"OFF-1": [(0, 0), (30, 2000)]}, {"P10": p10, "P50": p50, "P90": p90}, tmp_path / "td.png", milestones=[("shoe", 14, 1000)]), 1000)
    _png_ok(wc.cost_breakdown_chart([{"name": "rig", "p50": 100, "p10": 80, "p90": 130}, {"name": "total", "p50": 200, "p10": 160, "p90": 260, "total": True}], tmp_path / "c.png"), 1000)
    pts = [{"name": "PLAN", "e": 0.0, "n": 0.0, "role": "planned"}] + [{"name": f"OFF-{i}", "e": 1000.0 * math.cos(i), "n": 1000.0 * math.sin(i) + 50 * i, "role": "offset"} for i in range(1, 7)]
    _png_ok(wc.location_map(pts, tmp_path / "m.png", rings_km=[1.0, 2.0]), 1000)
    _png_ok(wc.offset_comparison_chart([{"name": "A", "days": 40, "td_m": 4000, "distance_km": 3.2}, {"name": "B", "days": 90, "flag": "HPHT analogue"}], tmp_path / "o.png", plan={"p10": 40, "p50": 60, "p90": 90}), 1000)


def test_report_structure_and_fields(tmp_path):
    from docx import Document

    img = tmp_path / "f.png"
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot([0, 1], [0, 1])
    fig.savefig(img, dpi=170)
    plt.close(fig)
    rep = WellPlanReport("Well Plan", "synthetic well", "SYN-001", "A", "2026-01-01", "DRAFT", "PUBLIC", organisation="Example", notice="synthetic")
    rep.h1("Summary", page_break=False)
    rep.key_data_box("Key data", [("Well", "SYN-1"), ("Depth", "4000 m"), ("Days", "40 / 60 / 90"), ("Cost", "class 5")])
    rep.table([["Item", "Value", "Unit"], ["a", "1.25", "m"], ["b", "10", "m"], ["c", "3.5", "m"]], "Numbers", note="synthetic")
    rep.figure(img, "A line", "provenance line")
    rep.sheet_page(img, "A sheet", "prov")
    rep.h1("Next")
    rep.para("text [ASSUMED]")
    out = rep.save(tmp_path / "r.docx")
    doc = Document(str(out))
    xml = doc.element.xml
    assert "SEQ Figure" in xml and "SEQ Table" in xml and 'TOC \\h \\z \\c "Figure"' in xml
    assert "NUMPAGES" in doc.sections[1].footer._element.xml
    assert len(doc.sections) >= 3
    a3 = [s for s in doc.sections if abs(s.page_width.cm - 42.0) < 0.1]
    assert len(a3) == 1 and a3[0].orientation == 1
    for s in doc.sections[1:]:
        assert not s.header.is_linked_to_previous and "SYN-001" in s.header.paragraphs[0].text
    assert rep.fig_n == 2 and rep.tab_n == 2
    n_tables = len(doc.tables)
    rep2 = WellPlanReport("Well Plan", "synthetic", "SYN-002", "A", "2026-01-01", "DRAFT", "PUBLIC")
    base = len(Document(str(rep2.save(tmp_path / "r2.docx"))).tables)
    rep2.callout("Box", ["line one [ASSUMED]", "line two"])
    after = len(Document(str(rep2.save(tmp_path / "r3.docx"))).tables)
    assert after == base and n_tables >= 1
    t = [t for t in doc.tables if t.rows[0].cells[0].text == "Item"][0]
    assert t.rows[1].cells[1].paragraphs[0].alignment == 2


def test_numeric_cell_detection():
    for ok in ("12", "1.25", "-3.4", "10 %", "~12", "1 200", "4 m"):
        assert _is_numeric_cell(ok), ok
    for bad in ("", "pass", "13 5/8 in casing", "abc 12"):
        assert not _is_numeric_cell(bad), bad


def test_collapse_basis_ordering_and_cementing():
    pipe = Pipe(17.0, 0.435, "P110")
    rows = {r["basis"]: r["collapse_df"] for r in collapse_basis_comparison(pipe, _liner_basis())}
    assert rows["set_cement"] > rows["mud_or_pore"] > rows["cement_slurry"] > 0.0
    light = check_string(pipe, _liner_basis(displacement_sg=1.03, evacuation_external="set_cement"))
    heavy = check_string(pipe, _liner_basis(displacement_sg=1.40, evacuation_external="set_cement"))
    assert light["collapse_case"] == "cementing" and light["collapse_df"] < heavy["collapse_df"]


def test_evacuation_level_limit_and_alternatives():
    pipe = Pipe(17.0, 0.435, "P110")
    b = _liner_basis(evacuation_external="mud_or_pore")
    lim = max_evacuation_level_for_collapse(pipe, b)
    assert lim["collapse_df_full_evacuation"] < 1.0
    assert 0.0 <= lim["allowed_evacuated_length_m"] <= b.shoe_tvd_m - b.top_tvd_m
    ok_at_level = check_string(pipe, replace(b, evacuation_level_tvd_m=lim["level_tvd_m"]))
    assert ok_at_level["collapse_df"] >= 1.0 - 1e-3
    alts = alternative_pipes(b, ["P110"], DesignFactors(), bit_od_in=16.0, grade_cost_factor={"P110": 1.2})
    walls = [a["wall_in"] for a in alts]
    assert walls == sorted(walls)
    thick = [a for a in alts if a["wall_in"] >= 0.5][0]
    thin = alts[0]
    assert thick["collapse_df_conservative"] > thin["collapse_df_conservative"] and thick["id_in"] < thin["id_in"]
    assert not thick["bit_passes"] and thin["bit_passes"]
    assert thick["cost_index"] > thin["cost_index"]
    assert math.isclose(drift_diameter_in(pipe, 0.125), pipe.id_in - 0.125)


def test_pore_basis_keeps_planned_mud_in_evacuation_case():
    """Pore-based kick convention must not replace the fluid left in the pipe after loss of returns (skill 0.2.0 did)."""
    from well_design_study import curve_from_points, PressureModel

    z = [0.0, 400.0, 4000.0]
    pm = PressureModel({k: curve_from_points([(0, 1.0), (400, 1.03), (4000, 1.2)]) for k in ("low", "base", "high")},
                       {k: curve_from_points([(0, 1.1), (400, 1.5), (4000, 1.9)]) for k in ("low", "base", "high")}, 350.0, 25.0)
    secs = [{"name": "surface", "hole_in": 17.5, "casing_od_in": 13.375, "top_tvd_m": 375.0, "shoe_tvd_m": 1500.0, "shoe_md_m": 1500.0, "mud_sg": 1.30, "toc_tvd_m": 400.0, "evacuation_basis": "pore_balance",
             "fixed_pipe": {"od_in": 13.375, "wall_in": 0.48, "grade": "L80"}},
            {"name": "open", "hole_in": 12.25, "casing_od_in": None, "top_tvd_m": 1500.0, "shoe_tvd_m": 3000.0, "shoe_md_m": 3000.0, "mud_sg": 1.45}]
    spec = {"reference": {"water_depth_m": 350.0, "air_gap_m": 25.0}, "pressure": {"pore": {k: list(zip(c.tvd_m, c.sg)) for k, c in pm.pore.items()}, "frac": {k: list(zip(c.tvd_m, c.sg)) for k, c in pm.frac.items()}},
            "sections": secs, "kick": {"basis": "pore"}, "evacuation_basis": "pore_balance"}
    new = run_well_study(spec)["strings"][0]["basis"]
    old = run_well_study(dict(spec, legacy_evacuation_fluid=True))["strings"][0]["basis"]
    assert new.next_mud_sg == pytest.approx(1.45) and old.next_mud_sg < 1.45
    assert new.kick_mud_sg == pytest.approx(old.next_mud_sg)
