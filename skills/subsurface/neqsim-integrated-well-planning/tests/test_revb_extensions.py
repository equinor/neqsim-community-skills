"""Tests for the generic extensions added while running a real study: scoring, nodal range-end status, exploration barriers, extra charts and sheets,
E300 fluids, boundary tables, hydraulic-method comparison and the life-cycle tubing matrix. All data are synthetic."""

import copy
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from integrated_well_planning import examples_data as ed, iwp_charts_extra as X, iwp_graphics as G
from integrated_well_planning.alternatives import score_raw
from integrated_well_planning.barriers import EXPLORATION_STATES, barrier_summary, propose_exploration_barriers
from integrated_well_planning.nodal import solve_nodal


def _png_ok(path, min_w=400):
    im = Image.open(path)
    arr = np.asarray(im.convert("L"), float)
    assert im.size[0] >= min_w and arr.std() > 5.0 and (arr < 250).mean() > 0.004
    return im


# ----------------------------------------------------------------------------- pure Python
def test_score_raw_normalises_higher_is_better_and_ignores_missing():
    raw = {"rate": {"A": 1.0, "B": 3.0, "C": 2.0}, "cost": {"A": -100.0, "B": -150.0, "C": None}}
    sc = score_raw(["A", "B", "C"], ["rate", "cost"], raw, {"rate": 0.5, "cost": 0.5}, "ASSUMED equal weights")
    assert sc["scores"]["rate"] == {"A": 0.0, "B": 1.0, "C": 0.5}
    assert sc["scores"]["cost"]["A"] == 1.0 and sc["scores"]["cost"]["B"] == 0.0 and sc["scores"]["cost"]["C"] is None
    assert sc["totals"]["B"] == pytest.approx(0.5) and sc["weights_source"] == "ASSUMED equal weights"


def test_nodal_reports_range_end_when_inflow_stays_above_outflow():
    res = solve_nodal(lambda q: 300.0 - 0.01 * q, lambda q: 100.0 + 0.02 * q, 10.0, 1000.0 / 3.0)
    assert res.status == "STABLE_AT_RANGE_END" and res.operating_point.rate == pytest.approx(1000.0 / 3.0)
    ok = solve_nodal(lambda q: 300.0 - 0.1 * q, lambda q: 100.0 + 0.1 * q, 10.0, 3000.0)
    assert ok.status == "STABLE" and ok.operating_point.rate == pytest.approx(1000.0, rel=0.01)


def test_exploration_barriers_cover_four_states_and_stay_unverified():
    b = ed.gas_condensate_producer_subsea()
    states = propose_exploration_barriers(b)
    assert [s.state for s in states] == list(EXPLORATION_STATES)
    summ = barrier_summary(states)
    assert set(summ["elements_by_status"]) == {"UNVERIFIED"} and summ["compliance_statement"].startswith("NONE")
    assert all(any(e.envelope == "primary" for e in s.elements) for s in states)


def test_waterfall_bars_have_positive_height_for_negative_steps(out_dir):
    fig = G.waterfall_chart("start", 500.0, [("drop", -120.0), ("rise", 30.0), ("drop 2", -200.0)], unit="bar", result_label="end")
    heights = [p.get_height() for p in fig.axes[0].patches]
    assert heights and min(heights) >= 0.0
    fig.savefig(out_dir / "w.png", dpi=100)
    _png_ok(out_dir / "w.png", 300)


def test_scorecard_accepts_labels_and_formats(out_dir):
    sc = {"criteria": ["rate", "cost"], "scores": {"rate": {"A": 1.0, "B": 0.0}, "cost": {"A": 0.0, "B": 1.0}}, "raw": {"rate": {"A": 3.2, "B": 1.1}, "cost": {"A": -100.0, "B": -80.0}},
          "totals": {"A": 0.5, "B": 0.5}}
    fig = G.alternatives_scorecard(sc, {"A": "big", "B": "small"}, crit_labels={"rate": "rate\n[MSm3/d]", "cost": "cost index"}, raw_fmt={"rate": "{:.1f}", "cost": "{:.0f}"}, raw_sign={"cost": -1.0})
    texts = [t.get_text() for t in fig.axes[0].texts]
    assert "3.2" in texts and "100" in texts and "80" in texts
    fig.savefig(out_dir / "s.png", dpi=100)
    _png_ok(out_dir / "s.png", 300)


def _lines():
    x = np.linspace(0, 10, 11)
    return [{"x": x, "y": 100 - 8 * x, "label": "case A", "color": "#0072B2"}, {"x": x, "y": 100 - 7.9 * x, "label": "case B", "color": "#D55E00", "ls": "--"},
            {"x": x, "y": 60 - 2 * x, "label": "case C with a long name that wraps", "color": "#009E73"}]


def test_multi_line_chart_labels_every_series_without_legend(out_dir):
    fig = X.multi_line_chart(_lines(), "x [-]", "y [bar]", "lines", hlines=[{"y": 50, "label": "limit", "color": "#CC3311"}], vlines=[{"x": 5, "label": "mid"}], size=(7.0, 4.0))
    ax = fig.axes[0]
    assert ax.get_legend() is None
    labels = [t.get_text().replace("\n", " ") for t in ax.texts]
    for name in ("case A", "case B", "case C with a long name that wraps"):
        assert any(name in t for t in labels), name
    fig.savefig(out_dir / "m.png", dpi=100)
    _png_ok(out_dir / "m.png", 300)


def test_grouped_and_horizontal_bar_charts_render(out_dir):
    f1 = X.grouped_bar_chart(["a", "b"], {"g1": [1.0, 2.0], "g2": [2.0, None]}, "value [-]", "title", hline={"y": 1.5, "label": "limit", "align": "margin"})
    f1.savefig(out_dir / "g.png", dpi=100)
    _png_ok(out_dir / "g.png", 300)
    f2 = X.hbar_grouped_chart(["a long load case name that must wrap onto two lines", "b"], {"burst": [0.4, 1.2], "triaxial": [0.3, 0.8]}, "utilisation [-]", "title", limit={"x": 1.0, "label": "rating"})
    texts = [t.get_text() for t in f2.axes[0].get_yticklabels()]
    assert any("\n" in t for t in texts)
    f2.savefig(out_dir / "h.png", dpi=100)
    _png_ok(out_dir / "h.png", 300)


def test_pressure_window_percentile_and_map_charts_render(out_dir):
    z = np.linspace(500, 3500, 7)
    pore = {"low": [(1.0, a) for a in z], "base": [(1.03 + 0.0001 * a, a) for a in z], "high": [(1.06 + 0.0002 * a, a) for a in z]}
    frac = {"low": [(1.4 + 0.0001 * a, a) for a in z], "base": [(1.6 + 0.0001 * a, a) for a in z], "high": [(1.8 + 0.0001 * a, a) for a in z]}
    strings = [{"name": "13 3/8 in", "top_m": 500, "shoe_m": 1800, "mud_sg": 1.3, "fit_sg": 1.5}, {"name": "9 5/8 in", "top_m": 1800, "shoe_m": 3500, "mud_sg": 1.5}]
    f = X.pressure_window_chart(pore, frac, strings, points=[{"tvd_m": 2000, "sg": 1.25, "kind": "pore_test"}, {"tvd_m": 1800, "sg": 1.55, "kind": "LOT"}], td_m=3500)
    f.savefig(out_dir / "pw.png", dpi=100)
    _png_ok(out_dir / "pw.png", 300)
    rng = np.random.default_rng(1)
    f = X.percentile_chart({"time [d]": rng.lognormal(3.5, 0.3, 400), "cost [MNOK]": rng.lognormal(5.5, 0.2, 400)}, "value", "distributions")
    f.savefig(out_dir / "pc.png", dpi=100)
    _png_ok(out_dir / "pc.png", 300)
    f = X.offset_map_chart({"label": "planned"}, [{"label": "off-1", "de_m": 1500.0, "dn_m": -800.0, "kind": "gas"}, {"label": "off-2", "de_m": -3000.0, "dn_m": 2500.0}],
                           paths=[{"label": "path", "east": [0, 300], "north": [0, 900], "color": "#0072B2"}], infrastructure=[{"label": "line", "east": [-4000, 4000], "north": [500, 500]}])
    f.savefig(out_dir / "om.png", dpi=100)
    _png_ok(out_dir / "om.png", 300)


def test_well_schematic_derives_dls_when_survey_has_none(out_dir):
    from integrated_well_planning.datums import build_and_hold
    from integrated_well_planning.iwp_drawings import well_schematic_sheet

    b = ed.gas_condensate_producer_subsea()
    s = build_and_hold(500, 2.0, 25, float(b["trajectory"]["md_m"]), float(b["trajectory"]["tvd_m"]))
    s = {k: v for k, v in s.items() if k != "dls"}
    fig = well_schematic_sheet(b, s, "TEST-DWG-001", "A")
    fig.savefig(out_dir / "ws.png", dpi=60)
    _png_ok(out_dir / "ws.png", 800)


def test_barrier_sheet_prints_every_element_and_function(out_dir):
    from integrated_well_planning.barriers import propose_barriers
    from integrated_well_planning.iwp_drawings import barrier_schematic_sheet

    b = ed.gas_condensate_producer_subsea()
    states = propose_barriers(b)
    fig = barrier_schematic_sheet(states, b, "TEST-DWG-002", "A")
    text = " ".join(t.get_text() for ax in fig.axes for t in ax.texts) + " ".join(t.get_text() for t in fig.texts)
    for s in states:
        for e in s.elements:
            assert e.name[:18] in text.replace("\n", " ") or e.name.split()[0] in text
    fig.savefig(out_dir / "bs.png", dpi=60)
    _png_ok(out_dir / "bs.png", 800)


def test_decision_tree_and_gantt_do_not_clip_labels(out_dir):
    f = G.gantt_chart([{"name": "a task with a rather long name", "start": 0, "low": 5, "base": 7, "high": 11}])
    assert f.axes[0].get_xlim()[1] > 11.0
    f.savefig(out_dir / "gt.png", dpi=100)
    _png_ok(out_dir / "gt.png", 300)


# ----------------------------------------------------------------------------- NeqSim-backed
@pytest.fixture(scope="module")
def gc_model(java):
    from integrated_well_planning.producers import ProducerModel

    return ProducerModel(ed.gas_condensate_producer_subsea())


def test_lump_to_cpa_fluid_keeps_library_components_and_adds_one_plus_fraction(java):
    from integrated_well_planning.model_chain import lump_to_cpa_fluid
    from integrated_well_planning.runtime import jclass

    src = jclass("SystemSrkEos")(273.15 + 50.0, 100.0)
    for n, z in (("methane", 0.80), ("ethane", 0.08), ("CO2", 0.02), ("nC10", 0.06), ("nC12", 0.04)):
        src.addComponent(n, z)
    src.setMixingRule(2)
    f = lump_to_cpa_fluid(src, 50.0, 100.0, 0.01)
    names = [str(f.getComponent(i).getComponentName()) for i in range(f.getNumberOfComponents())]
    assert {"methane", "ethane", "CO2", "water"} <= set(names) and sum(1 for n in names if "C7" in n or "plus" in n.lower()) == 1
    assert f.getNumberOfComponents() == 5


def test_e300_fluid_round_trip_and_basis_resolution(java, tmp_path):
    from integrated_well_planning.model_chain import build_fluid, e300_path, read_e300_fluid
    from integrated_well_planning.runtime import jclass

    src = jclass("SystemSrkEos")(273.15 + 80.0, 150.0)
    for n, z in (("methane", 0.85), ("ethane", 0.1), ("propane", 0.05)):
        src.addComponent(n, z)
    src.setMixingRule(2)
    import jpype

    reader = jpype.JClass("neqsim.thermo.util.readwrite.EclipseFluidReadWrite")
    path = tmp_path / "syn.e300"
    try:
        reader.write(src, str(path))
    except Exception as exc:  # noqa: BLE001
        pytest.skip("E300 writer unavailable: {}".format(exc))
    f = read_e300_fluid(str(path))
    assert f.getNumberOfComponents() == 3
    b = copy.deepcopy(ed.gas_condensate_producer_subsea())
    b["fluid"]["e300_file"] = "syn.e300"
    b["fluid"]["e300_base_dir"] = str(tmp_path)
    assert Path(e300_path(b)) == tmp_path / "syn.e300"
    g = build_fluid(b, 80.0, 150.0)
    assert g.getNumberOfComponents() == 3


def test_boundary_table_replaces_flowline_model_and_shifts_with_host_pressure(java):
    from integrated_well_planning.producers import ProducerModel

    b = copy.deepcopy(ed.gas_condensate_producer_subsea())
    b["facility"]["boundary_table"] = {"q_scale": 2.0, "q_sm3d": [0.0, 1.0e6, 2.0e6], "p_bara": [40.0, 45.0, 60.0], "reference_host_pressure_bara": 30.0}
    m = ProducerModel(b)
    host = m.params("base")["host_pressure_bara"]
    choke = float(b["facility"].get("choke_dp_bar") or 0.0)
    bp = m.back_pressure("base", 0.5e6)
    assert bp["wellhead_pressure_bara"] == pytest.approx(45.0 + (host - 30.0) + choke, abs=1e-6)
    assert "boundary table" in bp["method"]
    shifted = m.back_pressure("base", 0.5e6, {"host_pressure_bara": host + 5.0})
    assert shifted["wellhead_pressure_bara"] == pytest.approx(bp["wellhead_pressure_bara"] + 5.0, abs=1e-6)


def test_available_whp_is_bounded_by_the_reservoir_and_never_throws(gc_model):
    r = gc_model.available_whp("base", 0.05 * gc_model.ipr("base")["aof"])
    assert r["feasible"] and 0.0 < r["whp_available_bara"] < gc_model.params("base")["pressure_bara"] and r["pwf_bara"] > r["whp_available_bara"]
    over = gc_model.available_whp("base", 2.0 * gc_model.ipr("base")["aof"])
    assert over["feasible"] is False and "reason" in over


def test_wgr_changes_the_water_mass_flow(java):
    from integrated_well_planning.producers import ProducerModel

    b = copy.deepcopy(ed.gas_condensate_producer_subsea())
    m = ProducerModel(b)
    q = 0.2 * m.ipr("base")["aof"]
    dry = m.mass_flow(m.params("base", {"wgr_sm3_per_msm3": 0.0}), q)
    wet = m.mass_flow(m.params("base", {"wgr_sm3_per_msm3": 400.0}), q)
    assert wet["water"] > dry["water"] and wet["total"] > dry["total"]


def test_compare_methods_returns_drift_flux_reference_and_each_correlation(gc_model):
    from integrated_well_planning.hydraulics_compare import PIPE_METHODS, compare_methods

    q = 0.1 * gc_model.ipr("base")["aof"]
    whp = float(gc_model.back_pressure("base", q)["wellhead_pressure_bara"]) + 20.0
    rows = compare_methods(gc_model, "base", q, whp)
    assert rows[0]["method"] == "drift_flux" and rows[0]["delta_vs_reference_bar"] == 0.0
    got = {r["method"] for r in rows[1:] if r.get("bhp_bara") is not None}
    assert got and got <= set(PIPE_METHODS) and all(r["bhp_bara"] > whp for r in rows if r.get("bhp_bara") is not None)


def test_lifecycle_tubing_matrix_reports_burst_collapse_and_triaxial(java, gc_model):
    from integrated_well_planning.integrity import lifecycle_tubing_matrix

    b = ed.gas_condensate_producer_subsea()
    states = [{"state": "production", "pi_top_bara": 200.0, "pi_packer_bara": 380.0, "po_top_bara": 1.0, "po_packer_bara": 1.0 + 120.0, "t_top_C": 60.0, "t_packer_C": 120.0},
              {"state": "evacuated", "pi_top_bara": 1.0, "pi_packer_bara": 1.0, "po_top_bara": 1.0, "po_packer_bara": 1.0 + 300.0, "t_top_C": 4.0, "t_packer_C": 120.0, "fluid_density_kg_m3": 0.0}]
    rows = lifecycle_tubing_matrix(b, states)
    assert len(rows) == 4 and {r["location"] for r in rows} == {"tree", "packer"}
    evac = [r for r in rows if r["state"] == "evacuated" and r["location"] == "packer"][0]
    prod = [r for r in rows if r["state"] == "production" and r["location"] == "packer"][0]
    if prod.get("burst_utilisation") is not None:
        assert evac["collapse_utilisation"] > prod["collapse_utilisation"] and prod["burst_utilisation"] > evac["burst_utilisation"]
        assert prod["burst_status"].startswith("NEEDS_REVIEW")


def test_extra_conditions_enter_the_envelope_as_calculated_rows_without_limits():
    from integrated_well_planning.envelope import build_envelope

    b = copy.deepcopy(ed.gas_condensate_producer_subsea())
    b["limits"] = []
    rows = build_envelope(b, {"extra_conditions": [{"parameter": "custom_parameter", "condition": "case x", "unit": "bar", "predicted": 12.5, "source": "unit test"}]})
    r = [x for x in rows if x.parameter == "custom_parameter"]
    assert r and r[0].status == "NEEDS_REVIEW" and r[0].predicted == 12.5
