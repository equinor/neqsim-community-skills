import math

import pytest

from erd_reach_screening import DrillString, WellEnvironment, build_hold_profile, reach_limit, screen_reach, survey, torque_and_drag

ENV = WellEnvironment()
STRING = DrillString()


def test_path_closes_on_tvd_and_departure():
    mds, incs, _ = survey(3500.0, 10000.0, ENV, step=1.0)
    tvd = sum((mds[k] - mds[k - 1]) * math.cos(math.radians(0.5 * (incs[k] + incs[k - 1]))) for k in range(1, len(mds)))
    dep = sum((mds[k] - mds[k - 1]) * math.sin(math.radians(0.5 * (incs[k] + incs[k - 1]))) for k in range(1, len(mds)))
    assert tvd == pytest.approx(3500.0, rel=2e-3)
    assert dep == pytest.approx(10000.0, rel=1e-2)


def test_vertical_hook_load_is_buoyed_weight():
    mds = [10.0 * k for k in range(0, 301)]
    incs = [0.0] * len(mds)
    weights = [40.0] * (len(mds) - 1)
    load, torque = torque_and_drag(mds, incs, STRING, ENV, "pickup", weights)
    assert load == pytest.approx(40.0 * 3000.0 * 9.81 * ENV.buoyancy / 1000.0, rel=1e-6)
    assert torque == 0.0


def test_horizontal_drag_and_torque_follow_coulomb():
    mds = [10.0 * k for k in range(0, 201)]
    incs = [90.0] * len(mds)
    weights = [40.0] * (len(mds) - 1)
    env = WellEnvironment(ff_cased=0.25, ff_open=0.25)
    weight = 40.0 * 2000.0 * 9.81 * env.buoyancy
    pickup, _ = torque_and_drag(mds, incs, STRING, env, "pickup", weights)
    _, torque = torque_and_drag(mds, incs, STRING, env, "rotate", weights)
    assert pickup == pytest.approx(0.25 * weight / 1000.0, rel=1e-6)
    assert torque == pytest.approx(0.25 * weight * STRING.tool_joint_radius_m / 1000.0, rel=1e-6)


def test_capstan_on_weightless_arc():
    n = 90
    mds = [math.pi / 2.0 * 500.0 * k / n for k in range(n + 1)]
    incs = [90.0 * k / n for k in range(n + 1)]
    env = WellEnvironment(ff_cased=0.3, ff_open=0.3)
    load, _ = torque_and_drag(mds, incs, STRING, env, "pickup", [1e-6] * n, preload_kn=100.0)
    assert load == pytest.approx(100.0 * math.exp(0.3 * math.pi / 2.0), rel=1e-2)


def test_reach_limit_falls_with_friction_and_grows_with_torque_rating():
    low = reach_limit(3500.0, STRING, WellEnvironment(ff_cased=0.15, ff_open=0.20))
    high = reach_limit(3500.0, STRING, WellEnvironment(ff_cased=0.30, ff_open=0.35))
    strong = reach_limit(3500.0, DrillString(torque_limit_knm=85.0, tool_joint_radius_m=0.0953, dp_kg_per_m=49.0), WellEnvironment(ff_cased=0.15, ff_open=0.20))
    assert high < low < strong


def test_screen_reach_flags_limit_and_invalid_input():
    far = screen_reach(3500.0, 14000.0, STRING, ENV)
    assert far is not None and not far.torque_ok and far.limiting == "torque"
    assert screen_reach(3500.0, 3000.0, STRING, ENV).limiting == "none"
    with pytest.raises(ValueError):
        build_hold_profile(500.0, 1000.0, ENV)
