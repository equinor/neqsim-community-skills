import math

import numpy as np
import pytest

from well_design_study import (CostBasis, DesignFactors, EmwCurve, FlowSection, MudRheology, NptEvent, Pipe, PlannedSection, PressureModel, SectionTime,
                               StringBasis, StringComponent, build_and_hold, calibration_points, check_string, circulation, collapse_rating_psi,
                               burst_rating_psi, envelope, erosional_velocity_ms, evaluate_plan, kick_tolerance, minimum_curvature, monte_carlo,
                               overburden_sg, propose_seats_bottom_up, run_well_study, select_string, time_depth_stats, torque_and_drag,
                               turner_critical_velocity_ms, wellhead_rating_class)
from well_design_study.casing_design import GRADES, yield_psi
from well_design_study.units import BAR_PER_SG_M, bar_to_psi


def model():
    pore = {"low": EmwCurve([500, 4000], [1.03, 1.10]), "base": EmwCurve([500, 3000, 4000], [1.03, 1.05, 1.25]),
            "high": EmwCurve([500, 3000, 4000], [1.03, 1.10, 1.35])}
    frac = {"low": EmwCurve([500, 1500, 3000, 4000], [1.35, 1.55, 1.75, 1.85]), "base": EmwCurve([500, 1500, 3000, 4000], [1.45, 1.65, 1.85, 1.95]),
            "high": EmwCurve([500, 4000], [1.6, 2.1])}
    return PressureModel(pore, frac, water_depth_m=370.0, air_gap_m=30.0)


def test_api_5c3_published_ratings():
    yp = yield_psi(GRADES["N80"])
    assert collapse_rating_psi(9.625, 0.472, yp) == pytest.approx(4760.0, rel=0.01)
    assert burst_rating_psi(9.625, 0.472, yp) == pytest.approx(6870.0, rel=0.01)
    # 13-3/8 72 ppf N80 published collapse 2670 psi and burst 5380 psi
    assert collapse_rating_psi(13.375, 0.514, yp) == pytest.approx(2670.0, rel=0.03)
    assert burst_rating_psi(13.375, 0.514, yp) == pytest.approx(5380.0, rel=0.01)
    # 7 in 29 ppf P110 published collapse 8530 psi and burst 11220 psi
    yp110 = yield_psi(GRADES["P110"])
    assert collapse_rating_psi(7.0, 0.408, yp110) == pytest.approx(8530.0, rel=0.03)
    assert burst_rating_psi(7.0, 0.408, yp110) == pytest.approx(11220.0, rel=0.01)


def test_collapse_regimes_are_continuous():
    yp = yield_psi(GRADES["L80"])
    vals = [collapse_rating_psi(9.625, 9.625 / dt, yp) for dt in np.linspace(8, 60, 400)]
    assert all(b <= a * 1.01 for a, b in zip(vals, vals[1:]))


def test_pipe_weight_matches_catalogue_ppf():
    assert Pipe(9.625, 0.472, "N80").weight_lbft == pytest.approx(47.0, rel=0.02)
    assert Pipe(13.375, 0.514, "N80").weight_lbft == pytest.approx(72.0, rel=0.02)


def test_kick_tolerance_increases_with_shoe_strength_and_falls_with_kick_intensity():
    base = kick_tolerance(2000.0, 3000.0, 1.3, 1.80, 0.03, 0.06)
    stronger = kick_tolerance(2000.0, 3000.0, 1.3, 1.95, 0.03, 0.06)
    bigger_kick = kick_tolerance(2000.0, 3000.0, 1.3, 1.80, 0.03, 0.12)
    assert stronger["volume_m3"] > base["volume_m3"] > bigger_kick["volume_m3"]
    assert base["h_max_m"] <= 1000.0


def test_kick_tolerance_zero_when_shoe_too_weak():
    kt = kick_tolerance(2000.0, 3500.0, 1.6, 1.62, 0.03, 0.06)
    assert kt["ok_to_shut_in"] is False and kt["volume_m3"] == 0.0


def test_window_and_plan_flags_mud_weight_outside_window():
    m = model()
    secs = [PlannedSection("17.5 in", 17.5, 13.375, 400.0, 1500.0, 1500.0, 1.20), PlannedSection("12.25 in", 12.25, 9.625, 1500.0, 3000.0, 3000.0, 1.10)]
    res = evaluate_plan(m, secs)
    assert res[1]["mud_below_min_sg"] > 0.0 and res[1]["window_ok"] is False


def test_propose_seats_walks_upward_and_returns_ok_statuses():
    seats = propose_seats_bottom_up(model(), 4000.0, 600.0, kt_min_m3=5.0)
    assert seats and seats[0]["section_bottom_tvd_m"] == 4000.0
    assert all(s["status"] in ("OK", "NO_SEAT_FOUND") for s in seats)


def _basis(od=9.625, shoe=3000.0):
    return StringBasis(name="x", od_in=od, top_tvd_m=400.0, shoe_tvd_m=shoe, shoe_md_m=shoe, toc_tvd_m=shoe - 500.0, mud_sg=1.30, next_td_tvd_m=4000.0,
                       next_mud_sg=1.45, next_pore_sg=1.35, frac_shoe_sg=1.85, pore_sg_at=lambda z: 1.10, water_depth_m=370.0, air_gap_m=30.0, max_temp_c=120.0)


def test_select_string_picks_lightest_passing_pipe_and_is_monotone_in_load():
    light = select_string(_basis(), ["L80", "P110"])
    assert light["selected"] is not None
    heavy_basis = _basis()
    heavy_basis.next_td_tvd_m = 4500.0
    heavy_basis.next_mud_sg = 1.8
    heavy = select_string(heavy_basis, ["L80", "P110"])
    if heavy["selected"] is not None:
        assert heavy["selected"]["weight_kg_per_m"] >= light["selected"]["weight_kg_per_m"]


def test_check_string_reports_all_design_factors_and_failure_on_light_pipe():
    res = check_string(Pipe(9.625, 0.352, "J55"), _basis(), DesignFactors())
    for k in ("burst_df", "collapse_df", "tension_df", "triaxial_df"):
        assert math.isfinite(res[k])
    assert res["passes"] is False


def test_wellhead_class_selection():
    assert wellhead_rating_class(600.0)["class_psi"] == 10000.0
    assert wellhead_rating_class(300.0)["class_psi"] == 5000.0


def test_minimum_curvature_closes_on_build_and_hold_target():
    st = build_and_hold(4000.0, 1500.0, 800.0, 2.5)
    assert st[-1].tvd == pytest.approx(4000.0, abs=1.0)
    assert math.hypot(st[-1].north, st[-1].east) == pytest.approx(1500.0, abs=2.0)


def test_vertical_well_hookload_equals_buoyed_weight_and_no_torque():
    st = minimum_curvature([__import__("well_design_study").Station(0, 0, 0), __import__("well_design_study").Station(2000, 0, 0)])
    string = [StringComponent("dp", 2000.0, 30.0, 5.0, 4.276)]
    r = torque_and_drag(st, string, 1.3, 0.2, 0.3, 1500.0, operation="trip_out")
    w = 30.0 * 9.80665 / 1000.0 * (1 - 1.3 * 1000 / 7850.0) * 2000.0
    assert r["hook_load_kn"] == pytest.approx(w, rel=1e-6)


def test_drag_increases_pickup_and_reduces_slackoff_in_deviated_well():
    st = build_and_hold(3500.0, 1500.0, 500.0, 3.0)
    string = [StringComponent("dp", st[-1].md, 30.0, 5.0, 4.276)]
    out = torque_and_drag(st, string, 1.3, 0.2, 0.3, st[-1].md * 0.6, operation="trip_out")["hook_load_kn"]
    inn = torque_and_drag(st, string, 1.3, 0.2, 0.3, st[-1].md * 0.6, operation="trip_in")["hook_load_kn"]
    off = torque_and_drag(st, string, 1.3, 0.2, 0.3, st[-1].md * 0.6, operation="rotate_off")["hook_load_kn"]
    assert out > off > inn


def test_circulation_ecd_exceeds_static_and_grows_with_flow():
    secs = [FlowSection("12.25", 5.5, 4.67, 12.25, 3000.0)]
    mud = MudRheology(1.30, 20.0, 12.0)
    lo = circulation(secs, mud, 1500.0)
    hi = circulation(secs, mud, 3000.0)
    assert lo["ecd_bottom_sg"] > 1.30 and hi["ecd_bottom_sg"] > lo["ecd_bottom_sg"]
    assert hi["pump_pressure_bar"] > lo["pump_pressure_bar"]


def test_erosional_and_turner_velocities_in_expected_range():
    assert erosional_velocity_ms(200.0, 100.0) == pytest.approx(0.3048 * 100.0 / math.sqrt(200.0 * 0.062428), rel=1e-9)
    assert 0.3 < turner_critical_velocity_ms(150.0, 700.0, 0.02) < 6.0
    assert turner_critical_velocity_ms(20.0, 700.0, 0.02) > turner_critical_velocity_ms(150.0, 700.0, 0.02)


def test_offsets_calibration_and_time_depth(tmp_path):
    ev = {"casing_lot": [{"well": "A", "shoe_tvd_m": "1500", "lot_emw_sg": "1.72", "lot_fit_type": "LOT"}, {"well": "B", "shoe_tvd_m": "1520", "lot_emw_sg": "1.60", "lot_fit_type": "FIT"}],
          "pressure": [{"well": "A", "tvd_m": "3000", "pore_pressure_bar": "330"}],
          "mud": [{"well": "A", "tvd_m": "3000", "mud_weight_sg": "1.2"}],
          "time_depth": [{"well": "A", "days_per_1000m": "20"}, {"well": "B", "days_per_1000m": "30"}, {"well": "C", "days_per_1000m": "25"}]}
    cp = calibration_points(ev)
    assert len(cp.frac) == 2 and cp.pore[0]["emw_sg"] == pytest.approx(330 / (BAR_PER_SG_M * 3000), rel=1e-9)
    env = envelope(cp.frac, "emw_sg")
    assert env[0]["min"] == 1.60 and env[0]["max"] == 1.72
    td = time_depth_stats(ev["time_depth"])
    assert td["days_per_1000m_p10"] < td["days_per_1000m_p50"] < td["days_per_1000m_p90"]


def test_monte_carlo_percentiles_ordered_and_reproducible():
    secs = [SectionTime("a", 5, 8, 14), SectionTime("b", 10, 15, 28)]
    npt = [NptEvent("loss", 0.3, 1, 3, 8)]
    c = CostBasis(3.0, 120.0, 90.0)
    r1 = monte_carlo(secs, npt, c, n=4000, seed=1)
    r2 = monte_carlo(secs, npt, c, n=4000, seed=1)
    assert r1["days_total"]["p10"] < r1["days_total"]["p50"] < r1["days_total"]["p90"]
    assert r1["cost_mnok"]["p50"] == r2["cost_mnok"]["p50"]
    assert r1["days_productive"]["p50"] == pytest.approx(23.0, rel=0.1)


def test_overburden_between_water_and_rock_density():
    ob = overburden_sg(3000.0, 370.0, 30.0)
    assert 1.8 < ob < 2.4


SPEC = {
    "name": "test well", "reference": {"water_depth_m": 370.0, "air_gap_m": 30.0},
    "pressure": {"pore": {"low": [[500, 1.03], [4000, 1.10]], "base": [[500, 1.03], [3000, 1.05], [4000, 1.25]], "high": [[500, 1.03], [3000, 1.10], [4000, 1.35]]},
                 "frac": {"low": [[500, 1.35], [1500, 1.55], [3000, 1.75], [4000, 1.85]], "base": [[500, 1.45], [4000, 1.95]], "high": [[500, 1.6], [4000, 2.1]]}},
    "kick": {"intensity_sg": 0.06, "kt_min_m3": 5.0}, "max_temp_c": 150.0,
    "completion": {"shut_in_wellhead_bar": 380.0, "max_surface_pressure_bar": 400.0},
    "sections": [
        {"name": "26 in", "hole_in": 26, "casing_od_in": 20.0, "top_tvd_m": 400.0, "shoe_tvd_m": 1000.0, "shoe_md_m": 1000.0, "mud_sg": 1.10, "grades": ["L80", "P110"]},
        {"name": "17.5 in", "hole_in": 17.5, "casing_od_in": 13.375, "top_tvd_m": 1000.0, "shoe_tvd_m": 2000.0, "shoe_md_m": 2000.0, "mud_sg": 1.25, "grades": ["L80", "P110"]},
        {"name": "12.25 in", "hole_in": 12.25, "casing_od_in": 9.625, "top_tvd_m": 2000.0, "shoe_tvd_m": 3500.0, "shoe_md_m": 3500.0, "mud_sg": 1.35, "grades": ["L80", "P110"]},
    ],
}


def test_run_well_study_returns_checks_and_strings():
    res = run_well_study(SPEC)
    assert len(res["plan"]) == 3 and len(res["strings"]) == 3
    assert res["readiness"] in ("BLOCKED_BY_FAILED_CHECKS", "SCREENING_READY_FOR_HUMAN_REVIEW")
    assert any(c["check"].startswith("API 5C3 collapse") and c["status"] == "PASS" for c in res["checks"])
