import numpy as np
import pytest

from well_design_study import (EmwCurve, Pipe, PlannedSection, PressureModel, StringBasis, calibration_points, check_string, evaluate_plan, kick_tolerance,
                               run_well_study)
from well_design_study.normalise import (approx_tvd, normalise_casing_rows, normalise_mud_rows, normalise_wellbore_rows, parse_date, parse_inches,
                                         tag_problem_sentences, write_table)
from well_design_study.offsets import load_evidence, rebase_tvd
from well_design_study.report import WellReport


def model():
    pore = {"low": EmwCurve([500, 4000], [1.03, 1.10]), "base": EmwCurve([500, 3000, 4000], [1.03, 1.05, 1.25]),
            "high": EmwCurve([500, 3000, 4000], [1.03, 1.10, 1.35])}
    frac = {"low": EmwCurve([500, 1500, 3000, 4000], [1.35, 1.55, 1.75, 1.85]), "base": EmwCurve([500, 1500, 3000, 4000], [1.45, 1.65, 1.85, 1.95]),
            "high": EmwCurve([500, 4000], [1.6, 2.1])}
    return PressureModel(pore, frac, water_depth_m=370.0, air_gap_m=30.0)


@pytest.mark.parametrize("text,expected", [("13 3/8", 13.375), ('9 7/8"', 9.875), ("36", 36.0), ("17 1/2", 17.5), ("3/4", 0.75), ("12.25", 12.25),
                                           ("  20    ", 20.0), ("", None), (None, None), ("n/a", None)])
def test_parse_inches_handles_fractions_and_blanks(text, expected):
    assert parse_inches(text) == expected


def test_parse_date_and_approx_tvd():
    assert parse_date("2014-04-08T00:00:00").isoformat() == "2014-04-08"
    assert parse_date("bad") is None
    assert approx_tvd(1000.0, 4000.0, 3999.0)["basis"] == "VERTICAL_TD_MD_EQ_TVD"
    d = approx_tvd(3000.0, 4000.0, 3500.0, kickoff_md_m=2000.0)
    assert d["tvd_m"] == pytest.approx(2750.0) and d["basis"].startswith("DERIVED")
    assert approx_tvd(1500.0, 4000.0, 3500.0, kickoff_md_m=2000.0)["basis"] == "ABOVE_KICKOFF_VERTICAL"


def test_normalise_casing_rows_types_and_zero_density():
    rows = [
        {"wlbName": "W-1", "wlbCasingType": "SURF.COND. ", "wlbCasingDiameter": "20    ", "wlbCasingDepth": "985.0", "wlbHoleDiameter": "26    ",
         "wlbLotMudDencity": "1.57", "wlbFormationTestType": "FIT"},
        {"wlbName": "W-1", "wlbCasingType": "INTERM.", "wlbCasingDiameter": "13 3/8", "wlbCasingDepth": "2100", "wlbHoleDiameter": "17 1/2",
         "wlbLotMudDencity": "1.76", "wlbFormationTestType": " "},
        {"wlbName": "W-1", "wlbCasingType": "OPEN HOLE", "wlbCasingDiameter": "", "wlbCasingDepth": "3000", "wlbHoleDiameter": "8 1/2",
         "wlbLotMudDencity": "0.0", "wlbFormationTestType": "LOT"},
    ]
    out = normalise_casing_rows(rows, {"W-1": {"td_md_m": 3000.0, "td_tvd_m": 3000.0, "rkb_m": 25.0, "water_depth_m": 300.0}}, source="unit test", date_text="2026-01-01")
    assert [r["casing_od_in"] for r in out] == [20.0, 13.375, None]
    assert out[0]["lot_fit_type"] == "FIT" and out[0]["lot_emw_sg"] == 1.57
    assert out[1]["lot_fit_type"] == "FIT"  # a test density with a blank type is kept as the weaker FIT
    assert out[2]["lot_fit_type"] == "none" and out[2]["lot_emw_sg"] is None  # zero density is no test, whatever the type says
    assert out[0]["hole_in"] == 26.0 and out[1]["hole_in"] == 17.5 and out[0]["tvd_basis"] == "VERTICAL_TD_MD_EQ_TVD"


def test_normalise_mud_and_wellbore_rows_and_write_roundtrip(tmp_path):
    mud = normalise_mud_rows([{"wlbName": "W-1", "wlbMD": "1000", "wlbMudWeightAtMD": "1.20", "wlbMudType": "WBM"},
                              {"wlbName": "W-1", "wlbMD": "1500", "wlbMudWeightAtMD": "0", "wlbMudType": "WBM"}], source="s")
    assert len(mud) == 1 and mud[0]["mud_weight_sg"] == 1.2
    td = normalise_wellbore_rows([{"wlbWellboreName": "W-1", "wlbEntryDate": "2020-01-01", "wlbCompletionDate": "2020-03-01", "wlbTotalDepth": "3000",
                                   "wlbDrillingFacility": "RIG A", "wlbMaxInclation": "3"}], source="s")
    assert td[0]["days_total"] == 60.0 and td[0]["days_per_1000m"] == pytest.approx(20.0)
    casing = normalise_casing_rows([{"wlbName": "W-1", "wlbCasingType": "INTERM.", "wlbCasingDiameter": "13 3/8", "wlbCasingDepth": "2000",
                                     "wlbHoleDiameter": "17 1/2", "wlbLotMudDencity": "1.8", "wlbFormationTestType": "LOT"}])
    write_table(casing, "casing_lot", tmp_path)
    write_table(mud, "mud", tmp_path)
    write_table(td, "time_depth", tmp_path)
    ev = load_evidence(tmp_path)
    cp = calibration_points(ev)
    assert len(cp.frac) == 1 and cp.frac[0]["kind"] == "LOT" and len(cp.mud) == 1 and len(ev["time_depth"]) == 1


def test_calibration_points_skip_none_and_rebase_to_equal_depth_below_mudline():
    ev = {"casing_lot": [{"well": "A", "shoe_tvd_m": "2000", "lot_emw_sg": "1.8", "lot_fit_type": "LOT"},
                         {"well": "A", "shoe_tvd_m": "3000", "lot_emw_sg": "", "lot_fit_type": "none"},
                         {"well": "B", "shoe_tvd_m": "2000", "lot_emw_sg": "1.7", "lot_fit_type": "FIT"}]}
    refs = {"A": {"rkb_m": 25.0, "water_depth_m": 300.0}, "B": {"rkb_m": 30.0, "water_depth_m": 400.0}}
    cp = calibration_points(ev, refs, {"rkb_m": 30.0, "water_depth_m": 370.0})
    assert len(cp.frac) == 2
    a = [p for p in cp.frac if p["well"] == "A"][0]
    assert a["tvd_m"] == pytest.approx(2000.0 + 75.0) and a["tvd_orig_m"] == 2000.0
    assert rebase_tvd(1000.0, None, {"rkb_m": 30.0, "water_depth_m": 370.0}) == 1000.0


def test_tag_problem_sentences_flags_and_negation():
    text = ("A pilot hole found shallow gas at 700 m. Mud losses were experienced in the 12 1/4 in section. "
            "No shallow gas was observed in the second hole. The tool got stuck during logging. Operations proceeded without significant problems.")
    tags = tag_problem_sentences("W-1", text)
    kinds = {t["event_type"]: t["negated"] for t in tags}
    assert kinds["loss"] == "False" and kinds["stuck"] == "False"
    shallow = [t for t in tags if t["event_type"] == "shallow_gas"]
    assert any(t["negated"] == "True" for t in shallow) and any(t["negated"] == "False" for t in shallow)


def sections(**kw):
    s = [PlannedSection("26 in", 26.0, 20.0, 450.0, 1300.0, 1300.0, 1.20, riserless=kw.get("riserless", False)),
         PlannedSection("17.5 in", 17.5, 13.375, 1300.0, 2500.0, 2500.0, 1.40, strength_at_top_sg=kw.get("strength")),
         PlannedSection("8.5 in", 8.5, 0.0, 2500.0, 3800.0, 3800.0, 1.50, open_hole=True)]
    return s


def test_riserless_section_has_no_kick_tolerance_and_open_hole_is_reported():
    plan = evaluate_plan(model(), sections(riserless=True))
    assert plan[0]["kt_volume_m3"] is None and plan[0]["riserless"] is True
    assert plan[1]["kt_volume_m3"] is not None and plan[2]["open_hole"] is True


def test_strength_override_changes_kick_tolerance_and_reports_limits():
    base = evaluate_plan(model(), sections())[1]
    strong = evaluate_plan(model(), sections(strength=1.90))[1]
    assert strong["kt_strength_sg"] == 1.90 and strong["kt_volume_m3"] > base["kt_volume_m3"]
    assert "kt_limited_by_open_hole" in base and base["kt_open_length_m"] == pytest.approx(1200.0)


def test_pore_based_kick_basis_gives_larger_tolerance_when_mud_is_overbalanced():
    heavy = [PlannedSection("17.5 in", 17.5, 13.375, 1300.0, 2500.0, 2500.0, 1.55)]
    seat = [PlannedSection("26 in", 26.0, 20.0, 450.0, 1300.0, 1300.0, 1.20)] + heavy
    legacy = evaluate_plan(model(), seat, kick_basis="mud")[1]["kt_volume_m3"]
    pore = evaluate_plan(model(), seat, kick_basis="pore")[1]["kt_volume_m3"]
    assert pore > legacy
    kt = kick_tolerance(1300.0, 2500.0, 1.2, 1.7, 0.1, 0.06, 0.25, formation_sg=1.10)
    assert kt["formation_pressure_bar"] == pytest.approx(1.10 * 0.0980665 * 2500.0)


def test_liner_hang_load_uses_hanger_depth_not_mudline():
    common = dict(name="liner", od_in=9.875, shoe_tvd_m=3500.0, shoe_md_m=3500.0, toc_tvd_m=2800.0, mud_sg=1.5, next_td_tvd_m=3500.0, next_mud_sg=1.5,
                  next_pore_sg=1.3, frac_shoe_sg=1.9, water_depth_m=370.0, air_gap_m=30.0, max_temp_c=100.0)
    pipe = Pipe(9.875, 0.625, "P110")
    full = check_string(pipe, StringBasis(top_tvd_m=400.0, **common))
    liner = check_string(pipe, StringBasis(top_tvd_m=2600.0, **common))
    assert liner["tension_load_kn"] < full["tension_load_kn"]
    assert liner["string_weight_t"] == pytest.approx(pipe.weight_kg_per_m * 900.0 / 1000.0)


def test_run_well_study_open_hole_production_flag_and_fixed_pipe():
    pore = {k: EmwCurve([400, 4000], v) for k, v in {"low": [1.03, 1.10], "base": [1.03, 1.20], "high": [1.03, 1.30]}.items()}
    frac = {k: EmwCurve([400, 1500, 4000], v) for k, v in {"low": [1.35, 1.60, 1.85], "base": [1.45, 1.70, 1.95], "high": [1.6, 1.85, 2.1]}.items()}
    spec = {"name": "t", "reference": {"water_depth_m": 370.0, "air_gap_m": 30.0},
            "pressure": {"pore": {k: list(zip(v.tvd_m, v.sg)) for k, v in pore.items()}, "frac": {k: list(zip(v.tvd_m, v.sg)) for k, v in frac.items()}},
            "sections": [
                {"name": "20 in", "hole_in": 26.0, "casing_od_in": 20.0, "top_tvd_m": 400.0, "shoe_tvd_m": 1400.0, "shoe_md_m": 1400.0, "mud_sg": 1.2,
                 "riserless": True, "grades": ["L80", "P110"], "toc_tvd_m": 400.0, "shoe_strength_sg": 1.6},
                {"name": "9-5/8 in", "hole_in": 12.25, "casing_od_in": 9.625, "top_tvd_m": 1400.0, "shoe_tvd_m": 3000.0, "shoe_md_m": 3000.0, "mud_sg": 1.4,
                 "grades": ["P110"], "production": True, "string_top_tvd_m": 1300.0, "toc_tvd_m": 2500.0,
                 "fixed_pipe": {"od_in": 9.625, "wall_in": 0.595, "grade": "P110"}},
                {"name": "8.5 in", "hole_in": 8.5, "casing_od_in": None, "top_tvd_m": 3000.0, "shoe_tvd_m": 3800.0, "shoe_md_m": 3800.0, "mud_sg": 1.5},
            ],
            "kick": {"intensity_sg": 0.06, "influx_sg": 0.25, "kt_min_m3": 4.0},
            "completion": {"shut_in_wellhead_bar": 300.0, "max_surface_pressure_bar": 320.0},
            "max_temp_c": 120.0}
    res = run_well_study(spec)
    assert [s["string"] for s in res["strings"]] == ["20 in", "9-5/8 in"]
    prod = res["strings"][1]
    assert prod["status"] in ("FIXED_PASSES", "FIXED_FAILS") and prod["checked"]["pipe"].startswith('9.625"')
    assert res["strings"][1]["basis"].shut_in_wellhead_bar == 300.0 and res["strings"][0]["basis"].shut_in_wellhead_bar is None
    assert res["plan"][0]["kt_volume_m3"] is None and res["plan"][2]["open_hole"] is True
    assert res["plan"][1]["kt_strength_sg"] == 1.6


def test_report_landscape_callout_and_appendix(tmp_path):
    rep = WellReport("t", "s", "ID-1", "DRAFT")
    rep.h1("One")
    rep.callout("Answer", ["**bold** and [ASSUMED] label"])
    rep.landscape()
    assert rep.usable_cm > 20
    rep.table([["a", "b"], ["1", "2"]], "wide")
    rep.portrait()
    assert rep.usable_cm < 20
    rep.appendix("Tables")
    out = rep.save(tmp_path / "r.docx")
    assert out.exists() and out.stat().st_size > 5000
    from docx import Document
    doc = Document(str(out))
    assert any("Appendix A" in p.text for p in doc.paragraphs)
    assert len(doc.sections) == 3 and doc.sections[1].orientation == 1


def test_check_tubing_burst_collapse_and_grade_effect():
    from well_design_study import check_tubing
    lo = check_tubing(Pipe(7.0, 0.408, "L80"), 400.0, 3900.0, 370.0, 350.0, 0.025, max_temp_c=140.0)
    hi = check_tubing(Pipe(7.0, 0.408, "P110"), 400.0, 3900.0, 370.0, 350.0, 0.025, max_temp_c=140.0)
    assert hi["burst_df"] > lo["burst_df"] and hi["collapse_df"] > lo["collapse_df"]
    assert lo["burst_case"] == "shut_in" and lo["collapse_case"] == "evacuated"
    heavy = check_tubing(Pipe(7.0, 0.408, "P110"), 400.0, 3900.0, 370.0, 600.0, 0.025, max_temp_c=140.0)
    assert heavy["burst_df"] < hi["burst_df"]
    assert hi["tension_df"] > 1.0 and "triaxial_df" in hi


def test_common_sigma_widens_the_total_time_spread_and_keeps_median():
    from well_design_study import CostBasis, SectionTime, monte_carlo
    secs = [SectionTime("a", 8, 10, 13), SectionTime("b", 15, 20, 28), SectionTime("c", 5, 8, 12)]
    cost = CostBasis(2.0, 50.0, 80.0)
    narrow = monte_carlo(secs, [], cost, n=20000)
    wide = monte_carlo(secs, [], cost, n=20000, common_sigma=0.30)
    spread_n = narrow["days_total"]["p90"] - narrow["days_total"]["p10"]
    spread_w = wide["days_total"]["p90"] - wide["days_total"]["p10"]
    assert spread_w > 1.5 * spread_n
    assert wide["days_total"]["p50"] == pytest.approx(narrow["days_total"]["p50"], rel=0.08)


def test_pore_kick_basis_lowers_gas_kick_load_on_casing_when_mud_is_heavy():
    base = dict(name="x", od_in=9.625, top_tvd_m=400.0, shoe_tvd_m=2500.0, shoe_md_m=2500.0, toc_tvd_m=1800.0, mud_sg=1.4, next_td_tvd_m=3800.0,
                next_pore_sg=1.3, frac_shoe_sg=1.9, water_depth_m=370.0, air_gap_m=30.0, max_temp_c=100.0, cap_gas_at_frac=False)
    from well_design_study import load_cases
    heavy = load_cases(StringBasis(next_mud_sg=1.70, **base))["gas_kick"]["pi"].max()
    pore = load_cases(StringBasis(next_mud_sg=1.30, **base))["gas_kick"]["pi"].max()
    assert pore < heavy


def test_riserless_window_uses_seawater_head_and_vertical_well_gets_drag_from_tortuosity():
    from well_design_study import StringComponent, build_and_hold, torque_and_drag
    m = model()
    plan = evaluate_plan(m, [PlannedSection("26 in", 26.0, 20.0, 400.0, 1300.0, 1300.0, 1.10, riserless=True)])[0]
    # the effective gradient of a 1.10 sg mud under 370 m of seawater is lower than 1.10, so the required mud weight is higher than the EMW
    assert plan["min_mw_required_sg"] > 1.05
    riser = evaluate_plan(m, [PlannedSection("26 in", 26.0, 20.0, 400.0, 1300.0, 1300.0, 1.10)])[0]
    assert plan["max_mw_allowed_sg"] > riser["max_mw_allowed_sg"]
    st = build_and_hold(2000.0, 0.0, 0.0, 0.0)
    comps = [StringComponent("dp", 2000.0, 30.0, 5.5, 4.7, 7.0)]
    flat = torque_and_drag(st, comps, 1.3, 0.2, 0.25, 1500.0, operation="rotate_off", hole_in=8.5)
    wobble = torque_and_drag(st, comps, 1.3, 0.2, 0.25, 1500.0, operation="rotate_off", hole_in=8.5, tortuosity_deg_per_30m=0.4)
    assert flat["surface_torque_knm"] == 0.0 and wobble["surface_torque_knm"] > 0.0
    pick = torque_and_drag(st, comps, 1.3, 0.2, 0.25, 1500.0, operation="trip_out", tortuosity_deg_per_30m=0.4)["hook_load_kn"]
    slack = torque_and_drag(st, comps, 1.3, 0.2, 0.25, 1500.0, operation="trip_in", tortuosity_deg_per_30m=0.4)["hook_load_kn"]
    assert pick > slack


def test_evacuation_pore_balance_is_milder_than_half_string_for_a_liner():
    from well_design_study import load_cases
    base = dict(name="liner", od_in=17.0, top_tvd_m=1325.0, shoe_tvd_m=1690.0, shoe_md_m=1690.0, toc_tvd_m=1325.0, mud_sg=1.40, next_td_tvd_m=2690.0,
                next_mud_sg=1.50, next_pore_sg=1.1, frac_shoe_sg=1.7, water_depth_m=370.0, air_gap_m=30.0, max_temp_c=60.0, pore_sg_at=lambda z: 1.04)
    half = load_cases(StringBasis(**base))["evacuation"]
    bal = load_cases(StringBasis(evacuation_basis="pore_balance", **base))["evacuation"]
    assert (half["po"] - half["pi"]).max() > (bal["po"] - bal["pi"]).max()


def test_hydrostatic_pressure_excludes_air_gap_and_pressure_points_give_emw():
    from well_design_study import emw_curve_from_pressure_points, hydrostatic_pressure_bar
    p = hydrostatic_pressure_bar(1030.0, 1.04, 30.0, 370.0)
    assert p == pytest.approx(0.0980665 * (1.03 * 370.0 + 1.04 * 630.0))
    assert p / (0.0980665 * 1030.0) < 1.03  # EMW at RKB depth is below the water gradient
    c = emw_curve_from_pressure_points([(1000.0, 100.0), (2000.0, 250.0)])
    assert c.at(1000.0) == pytest.approx(100.0 / (0.0980665 * 1000.0))


def test_set_cement_evacuation_external_is_not_heavier_than_mud_column():
    from well_design_study import load_cases
    base = dict(name="liner", od_in=17.0, top_tvd_m=1325.0, shoe_tvd_m=1690.0, shoe_md_m=1690.0, toc_tvd_m=1325.0, mud_sg=1.40, next_td_tvd_m=2690.0,
                next_mud_sg=1.50, next_pore_sg=1.1, frac_shoe_sg=1.7, water_depth_m=370.0, air_gap_m=30.0, max_temp_c=60.0, pore_sg_at=lambda z: 1.04)
    legacy = load_cases(StringBasis(**base))["evacuation"]
    cem = load_cases(StringBasis(evacuation_external="set_cement", **base))["evacuation"]
    assert cem["po"].max() <= legacy["po"].max() + 1e-9
