import itertools
import math

import numpy as np
import pytest
from well_trajectory_anticollision import (
    ErrorModel,
    SFRule,
    Wellpath,
    add_model_covariance,
    check_slot,
    compare_growth,
    curve_hold,
    dogleg_severity,
    governing,
    group_by_surface,
    minimum_curvature,
    plan_from_surface,
    plan_sidetrack,
    pull_back_search,
    scan,
    separation_factor,
    summarize,
)

MODEL = ErrorModel()
RULE = SFRule()


def vertical(name, e, n, top=0.0, depth=2500.0, step=30.0, cov=True):
    md = np.arange(0.0, depth + 1e-9, step)
    wp = Wellpath.from_survey(
        name, md, np.zeros_like(md), np.zeros_like(md), start_xyz=(e, n, top)
    )
    return add_model_covariance(wp, MODEL) if cov else wp


def test_minimum_curvature_matches_circular_arc():
    r = 30.0 / math.radians(3.0)
    md = np.linspace(0.0, 900.0, 91)
    inc = np.degrees(md / r)
    pos = minimum_curvature(md, inc, np.full_like(md, 90.0))
    th = md[-1] / r
    assert pos[-1, 0] == pytest.approx(r * (1 - math.cos(th)), abs=1e-6)
    assert pos[-1, 2] == pytest.approx(r * math.sin(th), abs=1e-6)
    assert pos[-1, 1] == pytest.approx(0.0, abs=1e-9)
    assert dogleg_severity(md, inc, np.full_like(md, 90.0))[1:] == pytest.approx(
        3.0, rel=1e-9
    )


def test_curve_hold_hits_target_with_constant_dls():
    target = np.array([1200.0, 900.0, 2000.0])
    wp = plan_from_surface((0.0, 0.0, 0.0), 500.0, target, 2.5, step=10.0)
    assert np.linalg.norm(wp.xyz[-1] - target) < 0.05
    s = summarize(wp)
    assert s["max_dls_deg_per_30m"] == pytest.approx(2.5, abs=0.02)
    assert s["hold_az_deg"] == pytest.approx(
        math.degrees(math.atan2(1200.0, 900.0)), abs=0.01
    )


def test_unreachable_target_raises():
    p0, t0 = np.zeros(3), np.array([0.0, 0.0, 1.0])
    with pytest.raises(ValueError):
        curve_hold(p0, t0, np.array([300.0, 0.0, 50.0]), 1.0)


def test_separation_factor_formula():
    rule = SFRule(
        k_sigma=3.5,
        surface_margin_m=0.3,
        sigma_pa_m=0.5,
        ref_radius_m=0.1,
        offset_radius_m=0.1,
    )
    sf = separation_factor(20.0, 4.0, rule)
    assert sf == pytest.approx((20.0 - 0.5) / (3.5 * math.sqrt(4.25)))
    assert (
        rule.classify(0.9) == "STOP"
        and rule.classify(1.2) == "CAUTION"
        and rule.classify(2.0) == "OK"
    )


def test_parallel_vertical_wells_sf_decreases_with_depth():
    ref = vertical("A", 0.0, 0.0)
    off = vertical("B", 15.0, 0.0)
    res = scan(ref, [off], RULE)
    sfs = [p["min_sf"] for p in res["profile"]]
    assert all(b <= a + 1e-9 for a, b in itertools.pairwise(sfs))
    row = res["offsets"][0]
    # vertical wells: along-hole (vertical) depth error dominates, so the governing SF may lie on a
    # diagonal separation vector rather than the 15 m horizontal one
    assert row["cc_m"] >= 15.0 - 1e-6
    assert row["sf"] <= separation_factor(15.0, 0.0, RULE)
    assert row["ref_md"] > 2000.0


def test_offset_without_covariance_is_modelled_with_warning():
    res = scan(vertical("A", 0.0, 0.0), [vertical("B", 50.0, 0.0, cov=False)], RULE)
    assert any("no survey covariance" in w for w in res["warnings"])
    assert res["offsets"][0]["sf"] > 0


def test_sidetrack_parent_exit_and_governing_excludes_parent():
    parent = add_model_covariance(
        plan_from_surface(
            (0.0, 0.0, 0.0),
            400.0,
            (300.0, 1500.0, 2000.0),
            2.0,
            name="P-1 H",
            step=30.0,
        ),
        MODEL,
    )
    tie = float(parent.md[np.argmin(abs(parent.md - 700.0))])
    st = add_model_covariance(
        plan_sidetrack(parent, tie, (1500.0, 1200.0, 2000.0), 3.0, name="P-1 AH"), MODEL
    )
    assert st.parent == "P-1 H" and st.tie_md == tie
    res = scan(st, [parent, vertical("Far", 4000.0, 4000.0)], RULE)
    prow = next(r for r in res["offsets"] if r["wellbore"] == "P-1 H")
    assert prow["parent_bore"] and prow["status"] == "STOP"
    assert tie < prow["last_md_below_caution"] < tie + 600.0
    assert governing(res)["wellbore"] == "Far"


def test_pull_back_clears_close_offset():
    blocker = vertical("X", 1000.0, 1000.0, depth=2600.0)
    target = np.array([990.0, 990.0, 2000.0])

    def plan(t):
        return add_model_covariance(
            plan_from_surface((0.0, 0.0, 0.0), 400.0, t, 3.0), MODEL
        )

    out = pull_back_search(
        plan, target, (0.0, 0.0), [blocker], RULE, distances=(0, 50, 100, 200, 300, 400)
    )
    assert out["sweep"][0]["governing_sf"] < 1.0
    assert out["chosen"] is not None and out["chosen"]["pull_back_m"] > 0
    assert out["chosen"]["governing_sf"] >= RULE.caution_below


def test_compare_growth_identity_and_scaled_model():
    ref = add_model_covariance(
        plan_from_surface((0.0, 0.0, 0.0), 300.0, (800.0, 800.0, 1800.0), 2.0), MODEL
    )
    rows = compare_growth(ref, MODEL)
    assert all(r["ratio"] == pytest.approx(1.0, abs=0.01) for r in rows)
    loose = ErrorModel(
        terms={k: (kind, 2 * sig) for k, (kind, sig) in MODEL._resolved.items()}
    )
    assert all(
        r["ratio"] == pytest.approx(2.0, abs=0.02) for r in compare_growth(ref, loose)
    )


def test_slot_occupancy():
    slots = group_by_surface(
        [
            {
                "name": "S-1 H",
                "easting": 0.0,
                "northing": 0.0,
                "status": "producing",
                "slot": "01",
            },
            {
                "name": "S-2 H",
                "easting": 2.4,
                "northing": 0.0,
                "status": "closed",
                "slot": "02",
            },
            {
                "name": "S-2 AH",
                "easting": 2.4,
                "northing": 0.1,
                "status": "plugged",
                "parent": "S-2 H",
            },
            {
                "name": "S-3 H",
                "easting": 5.0,
                "northing": 0.0,
                "status": "plugged",
                "slot": "03",
            },
            {
                "name": "S-3 AH",
                "easting": 5.0,
                "northing": 0.0,
                "status": "planning",
                "parent": "S-3 H",
            },
        ]
    )
    assert len(slots) == 3
    assert check_slot(slots, slot="01")["status"] == "OCCUPIED"
    assert check_slot(slots, slot="02")["status"] == "RECOVERABLE"
    assert check_slot(slots, slot="03")["status"] == "RESERVED"
    assert check_slot(slots, slot="04")["status"] == "FREE"
