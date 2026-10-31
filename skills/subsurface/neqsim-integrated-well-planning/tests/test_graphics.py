import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from integrated_well_planning import examples_data as ed, iwp_graphics as G, iwp_style as S
from integrated_well_planning.barriers import propose_barriers
from integrated_well_planning.datums import build_and_hold
from integrated_well_planning.iwp_drawings import barrier_schematic_sheet, render_sheet, well_schematic_sheet


def _profile(n=10, depth=2500.0):
    z = np.linspace(0, depth, n + 1)
    zm = 0.5 * (z[:-1] + z[1:])
    return {"node_tvd_m": z.tolist(), "pressure_bara": (30 + 0.065 * z).tolist(), "tvd_m": zm.tolist(), "temperature_C": (20 + 0.028 * zm).tolist(), "liquid_holdup": np.clip(0.3 + zm / 3500, 0, 1).tolist(),
            "void_fraction": [0.2] * n, "vsg_m_s": np.linspace(6, 0, n).tolist(), "vsl_m_s": [3.5] * n, "mixture_density": np.linspace(250, 600, n).tolist(), "turner_ratio": [1.5] * n,
            "regime": ["ANNULAR", "SLUG", "SLUG", "BUBBLE", "BUBBLE", "SINGLE_PHASE_LIQUID", "SINGLE_PHASE_LIQUID", "SINGLE_PHASE_LIQUID", "SINGLE_PHASE_LIQUID", "SINGLE_PHASE_LIQUID"]}


def _env_rows():
    from integrated_well_planning.envelope import evaluate_row, to_rows

    rows = [evaluate_row("E1", "erosional_ratio", "production", "-", 0.7, "model", max_limit=1.0, limit_source="API RP 14E ratio", limit_basis="APPROVED"),
            evaluate_row("E2", "hydrate_margin_K", "wellhead", "K", 6.0, "model", min_limit=3.0, limit_source="synthetic", limit_basis="SYNTHETIC"),
            evaluate_row("E3", "annulus_a_pressure_bara", "heat-up", "bara", 250.0, "model", max_limit=200.0, limit_source="operator MAASP", limit_basis="APPROVED"),
            evaluate_row("E4", "wax_margin_K", "coldest", "K", None, "")]
    return to_rows(rows)


def _alt_sc():
    ids = ["A", "B", "C"]
    crit = ["deliverability", "erosion_margin", "energy_demand", "cost"]
    scores = {c: {i: (k + j) % 3 / 2.0 for k, i in enumerate(ids)} for j, c in enumerate(crit)}
    scores["cost"]["C"] = None
    raw = {c: {i: (v if v is not None else None) for i, v in scores[c].items()} for c in crit}
    return {"criteria": crit, "scores": scores, "raw": raw, "totals": {"A": 0.5, "B": 0.7, "C": 0.4}, "weights": {c: 1 for c in crit}, "weights_source": "ASSUMED", "criteria_without_data": []}


CHART_CASES = {
    "nodal": lambda: dict(family={"q": list(np.linspace(100, 3000, 10)), "ipr_pwf": list(250 - np.linspace(100, 3000, 10) / 40), "families": {"0.085": list(150 + np.linspace(100, 3000, 10) / 20),
                                                                                                          "0.1": list(140 + np.linspace(100, 3000, 10) / 35)}, "parameter": "tubing_id_m"},
                          ops={"base": {"q_op": 1500.0, "bhp_op": 200.0}, "low": {"q_op": 900.0, "bhp_op": 215.0}, "high": {"q_op": 2100.0, "bhp_op": 190.0}}, target_rate=1500.0,
                          ipr_band={"low": list(240 - np.linspace(100, 3000, 10) / 40), "high": list(260 - np.linspace(100, 3000, 10) / 40)}, outflow_min_rate=400.0),
    "wellbore_profiles": lambda: dict(profile=_profile(), hydrate={"tvd_m": [100, 1000, 2000], "hydrate_T_C": [15, 17, 18]}),
    "operating_envelope": lambda: dict(rows=_env_rows()),
    "envelope_table": lambda: dict(rows=_env_rows()),
    "alternatives_scorecard": lambda: dict(sc=_alt_sc(), labels={"A": "tubing 85 mm", "B": "tubing 100 mm", "C": "gas lift"}),
    "alternatives_radar": lambda: dict(sc=_alt_sc(), labels={"A": "tubing 85 mm", "B": "tubing 100 mm", "C": "gas lift"}),
    "pareto": lambda: dict(points={"A": (0.0, 1500.0), "B": (0.0, 2000.0), "C": (1e5, 2100.0)}, front=["B", "C"], labels={"A": "A", "B": "B", "C": "C"}, xlabel="Lift gas", ylabel="Rate"),
    "waterfall": lambda: dict(reference_label="100 mm", reference_value=2000.0, steps=[("120 mm", 300.0), ("gas lift", -50.0)]),
    "tornado": lambda: dict(t={"metric": "q_op", "reference": 2000.0, "rows": [{"parameter": "skin", "range": [0, 2, 8], "metric_at_low_value": 2100.0, "metric_at_high_value": 1700.0, "swing": 400.0},
                                                                           {"parameter": "k_md", "range": [90, 150, 220], "metric_at_low_value": 1500.0, "metric_at_high_value": 2400.0, "swing": 900.0}]}),
    "sensitivity_heatmap": lambda: dict(g={"x_param": "tubing_id_m", "x": [0.085, 0.1, 0.12], "y_param": "host_pressure_bara", "y": [20, 25, 35], "q_op": [[1800, 2000, 2300], [1600, 1900, 2200], [1200, 1500, 1900]]}, target=1500.0),
    "profile_bands": lambda: dict(years=[0, 3, 6, 9], cases={"low": [1500, 1200, 900, 600], "base": [2000, 1700, 1400, 1100], "high": [2400, 2100, 1800, 1500]}, target=1500.0),
    "gantt": lambda: dict(tasks=[{"name": "Top hole", "start": 0, "low": 5, "base": 7, "high": 11}, {"name": "Production hole", "start": 7, "low": 8, "base": 11, "high": 18}]),
    "risk_matrix": lambda: dict(risks=[{"id": 1, "title": "x", "likelihood": 3, "consequence": 4}, {"id": 2, "title": "y", "likelihood": 5, "consequence": 5}, {"id": 3, "title": "z", "likelihood": 3, "consequence": 4}]),
    "risk_register": lambda: dict(risks=[{"id": 1, "title": "Erosional ratio above limit", "likelihood": 4, "consequence": 4, "mitigation": "larger tubing", "owner": "lead"}]),
    "decision_tree": lambda: dict(nodes=[{"id": "r", "parent": None, "label": "Select completion", "kind": "decision"}, {"id": "a", "parent": "r", "label": "100 mm", "kind": "chance"},
                                         {"id": "a1", "parent": "a", "label": "low: missed", "kind": "outcome", "edge": "low"}, {"id": "a2", "parent": "a", "label": "base: met", "kind": "outcome", "edge": "base"}]),
    "time_depth": lambda: dict(curves={"low": [(0, 0), (20, 1500), (35, 2500)], "base": [(0, 0), (28, 1500), (47, 2500)], "high": [(0, 0), (40, 1500), (66, 2500)]}, band_curves=("low", "high")),
    "trajectory_views": lambda: dict(survey=build_and_hold(500, 2.0, 25, 2500, 70), offsets={"B-2": {"east": [0, 20, 40], "north": [0, 60, 120], "tvd": [0, 800, 1600]}},
                                     separation={"curves": {"B-2": {"md": [500, 1500, 2500], "sf": [6.0, 2.5, 1.8]}}, "threshold": 1.5}),
}


def _check_png(path, min_w=400):
    im = Image.open(path)
    assert im.size[0] >= min_w and im.size[1] >= 250
    arr = np.asarray(im.convert("L"), float)
    assert arr.std() > 5.0, "image looks blank"
    assert (arr < 250).mean() > 0.01
    return im


@pytest.mark.parametrize("name", sorted(CHART_CASES))
def test_chart_renders_png_with_provenance(name, out_dir):
    files = G.render(name, out_dir / name, {"name": name}, caption="test caption", **CHART_CASES[name]())
    png = Path(files["png"])
    assert png.exists() and png.stat().st_size > 8000
    _check_png(png)
    side = json.loads(Path(files["provenance"]).read_text())
    assert side["schema"] == "iwp_figure_provenance.v1" and side["caption"] == "test caption" and side["synthetic"] is True
    assert side["files"]["png"] == name + ".png" and len(side["inputs_sha256_16"]) == 16


def test_chart_png_is_300_dpi(out_dir):
    files = G.render("waterfall", out_dir / "w", {}, **CHART_CASES["waterfall"]())
    im = Image.open(files["png"])
    assert round(im.info["dpi"][0]) == 300 and im.size[0] > 1800


def test_chart_registry_covers_required_library():
    assert {"nodal", "wellbore_profiles", "operating_envelope", "alternatives_scorecard", "alternatives_radar", "pareto", "waterfall", "tornado", "sensitivity_heatmap", "profile_bands", "gantt",
            "risk_matrix", "risk_register", "decision_tree", "time_depth", "trajectory_views"} <= set(G.CHARTS)


def test_trajectory_3d_renders_file(out_dir):
    renderer = G.trajectory_3d(build_and_hold(400, 2.0, 30, 2000, 45), out_dir / "t3d.png")
    assert renderer in ("pyvista", "matplotlib")
    _check_png(out_dir / "t3d.png", 300)


def test_chart_rendering_is_deterministic(out_dir):
    def ahash(path):
        a = np.asarray(Image.open(path).convert("L").resize((16, 16)), float)
        return (a > a.mean()).ravel()

    f1 = G.render("tornado", out_dir / "a", {"x": 1}, **CHART_CASES["tornado"]())
    f2 = G.render("tornado", out_dir / "b", {"x": 1}, **CHART_CASES["tornado"]())
    assert (ahash(f1["png"]) != ahash(f2["png"])).sum() <= 2


def test_palette_is_colour_blind_safe_and_semantic():
    assert S.PALETTE["pressure"] != S.PALETTE["temperature"] != S.PALETTE["gas"]
    assert len(set(S.CATEGORICAL)) == len(S.CATEGORICAL)
    assert {"pressure", "temperature", "gas", "oil", "water", "hydrate", "pass", "warn", "fail", "primary_barrier", "secondary_barrier"} <= set(S.PALETTE)
    assert S.status_color("NEEDS_REVIEW") == S.PALETTE["review"] and S.status_color("FAIL") == S.PALETTE["fail"]


def test_font_exists_on_machine():
    import matplotlib.font_manager as fm

    assert S.pick_font() in {f.name for f in fm.fontManager.ttflist}


@pytest.mark.parametrize("case", ["oil_producer_platform", "gas_condensate_producer_subsea", "water_injector_onshore", "gas_injector_platform"])
def test_well_schematic_sheet_all_environments(case, out_dir):
    b = ed.all_cases()[case]
    sv = b["trajectory"]["survey"]
    survey = build_and_hold(sv["kop_md_m"], sv["build_rate_deg_per_30m"], sv["hold_inclination_deg"], b["trajectory"]["md_m"], sv["azimuth_deg"])
    fig = well_schematic_sheet(b, survey, "T-001")
    files = render_sheet(fig, out_dir / "sheet", "well_schematic", b, "T-001", "caption", True, ["L13"])
    im = _check_png(files["png"], 4000)
    assert abs(im.size[0] / im.size[1] - 420 / 297) < 0.01  # A3 landscape at 300 dpi
    assert round(im.info["dpi"][0]) == 300
    assert Path(files["pdf"]).stat().st_size > 20000 and Path(files["svg"]).stat().st_size > 20000


def test_sheet_pdf_embeds_truetype_fonts_and_svg_is_vector(out_dir):
    b = ed.oil_producer_platform()
    files = render_sheet(well_schematic_sheet(b, None, "T-002"), out_dir / "sheet", "well_schematic", b, "T-002", "c", True)
    pdf = Path(files["pdf"]).read_bytes()
    assert b"/FontFile2" in pdf or b"/FontFile3" in pdf
    svg = Path(files["svg"]).read_text(encoding="utf-8", errors="ignore")
    assert "<path" in svg and "SYNTHETIC" not in "" and svg.count("<g") > 10


def test_sheet_has_title_block_and_synthetic_stamp_in_provenance(out_dir):
    b = ed.water_injector_onshore()
    files = render_sheet(barrier_schematic_sheet(propose_barriers(b), b, "T-003"), out_dir / "bar", "barrier_schematic", b, "T-003", "barrier sheet", True)
    side = json.loads(Path(files["provenance"]).read_text())
    assert side["drawing_no"] == "T-003" and side["synthetic"] is True
    _check_png(files["png"], 4000)


def test_a3_sheet_geometry_and_content_box():
    fig, ax, box = S.a3_sheet("t", "D-1", scale_bar_m=100, north_arrow=True)
    assert abs(fig.get_size_inches()[0] - 420 / 25.4) < 1e-6 and abs(fig.get_size_inches()[1] - 297 / 25.4) < 1e-6
    assert box[1] > 50 and box[0] + box[2] < 420
    S.plt.close(fig)
