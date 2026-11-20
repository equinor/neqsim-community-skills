import math

import numpy as np
import pytest
from flare_helideck_dispersion import (
    ModelParameters,
    Release,
    ReleaseCase,
    choked_tip,
    jet_consistency_check,
    sigmas,
)
from flare_helideck_dispersion.model import P_AMB_PA, wind_frame

TIP = np.array([0.0, 0.0, 124.0])


def make_release(t0=190.0, mdot=150.0, **params):
    case = ReleaseCase("t", mdot, 0.0215, 1.25, t0, 0.04, 0.96, 0.6)
    return Release(case, ModelParameters(**params))


def test_choked_flow_limits():
    tip = choked_tip(150.0, 0.0215, 1.25, 273.15, 0.6)
    assert tip["choked"] is True
    assert tip["mach_throat"] == 1.0
    assert tip["p0_bara"] > 1.9 * P_AMB_PA / 1e5
    # a small flow through a large exit stays subsonic at ambient pressure
    low = choked_tip(1.0, 0.0215, 1.25, 273.15, 0.6)
    assert low["choked"] is False
    assert low["p0_bara"] == pytest.approx(P_AMB_PA / 1e5)
    assert low["mach_throat"] < 1.0
    # notional nozzle conserves mass
    area = math.pi * tip["d_eff_m"] ** 2 / 4.0
    assert tip["rho_exp"] * tip["v_exit_ms"] * area == pytest.approx(150.0, rel=1e-12)


def test_cold_gas_is_denser_than_air():
    assert make_release(190.0).tip["rho_ratio_to_air"] > 1.0
    assert make_release(400.0).tip["rho_ratio_to_air"] < 1.0


def test_plume_is_symmetric_in_crosswind_and_zero_upwind():
    rel = make_release()
    pts_pos = np.array([[400.0, 80.0, 120.0]])
    pts_neg = np.array([[400.0, -80.0, 120.0]])
    a = rel.pct_lfl(pts_pos, 270.0, 5.0, "D", TIP)
    b = rel.pct_lfl(pts_neg, 270.0, 5.0, "D", TIP)
    assert a[0] == pytest.approx(b[0], rel=1e-12)
    upwind = np.array([[-400.0, 0.0, 124.0]])
    assert rel.pct_lfl(upwind, 270.0, 5.0, "D", TIP)[0] == 0.0
    assert np.all(
        rel.pct_lfl(np.array([[400.0, 0.0, 124.0]]), 270.0, 5.0, "D", TIP) >= 0.0
    )


def test_concentration_decreases_with_distance_in_far_field():
    rel = make_release(400.0, mdot=30.0)
    xs = np.array([800.0, 1600.0, 3200.0])
    pts = np.column_stack([xs, np.zeros(3), np.full(3, 124.0)])
    values = rel.pct_lfl(pts, 270.0, 5.0, "D", TIP, "none")
    assert values[0] > values[1] > values[2] > 0.0


def test_wind_from_versus_travel_convention():
    rel = make_release()
    east = np.array([[500.0, 0.0, 124.0]])
    # wind FROM west (270) carries gas toward the east; wind FROM east carries it away
    assert rel.pct_lfl(east, 270.0, 3.0, "E", TIP, "none")[0] > 0.0
    assert rel.pct_lfl(east, 90.0, 3.0, "E", TIP, "none")[0] == 0.0
    x, y = wind_frame(np.array([[0.0, 100.0]]), 180.0)  # wind from south, travel north
    assert x[0] == pytest.approx(100.0)
    assert y[0] == pytest.approx(0.0, abs=1e-9)


def test_stable_air_caps_reduce_momentum_rise():
    rel = make_release(400.0, mdot=150.0)
    xs = np.array([200.0, 500.0, 1500.0])
    neutral = rel.centreline_height(xs, 1.5, 124.0, "briggs", "D")
    stable = rel.centreline_height(xs, 1.5, 124.0, "briggs", "F")
    assert np.all(stable <= neutral + 1e-12)
    assert stable[-1] < 0.5 * neutral[-1]
    assert np.all(rel.centreline_height(xs, 1.5, 124.0, "none", "F") == 0.0)


def test_dense_gas_sinks_relative_to_warm_gas():
    xs = np.array([800.0])
    dense = make_release(190.0).centreline_height(xs, 3.0, 124.0, "briggs", "E")
    light = make_release(400.0).centreline_height(xs, 3.0, 124.0, "briggs", "E")
    assert dense[0] < light[0]


def test_flatter_tip_lifts_less():
    xs = np.array([600.0])
    steep = make_release(tilt_deg=70.0).centreline_height(xs, 5.0, 124.0, "briggs", "D")
    flat = make_release(tilt_deg=20.0).centreline_height(xs, 5.0, 124.0, "briggs", "D")
    assert flat[0] < steep[0]


def test_sigmas_and_parameter_validation():
    sy, sz = sigmas(np.array([100.0, 1000.0]), "D")
    assert np.all(np.diff(sy) > 0) and np.all(np.diff(sz) > 0)
    with pytest.raises(ValueError):
        sigmas(100.0, "Z")
    with pytest.raises(ValueError):
        ModelParameters(tilt_deg=0.0)
    with pytest.raises(ValueError):
        ReleaseCase("bad", -1.0, 0.02, 1.2, 300.0, 0.04, 0.96)
    with pytest.raises(ValueError):
        ReleaseCase("bad", 1.0, 20.0, 1.2, 300.0, 0.04, 0.96)
    with pytest.raises(ValueError):
        make_release().pct_lfl(np.array([[1.0, 0.0, 1.0]]), 0.0, 3.0, "D", TIP, "nope")


def test_free_jet_distance_and_consistency_check():
    rel = make_release()
    d20, d10 = rel.jet_distance_to(0.2), rel.jet_distance_to(0.1)
    assert d10 == pytest.approx(2.0 * d20)
    chk = jet_consistency_check(rel, 1.5, "F", 124.0, 0.2)
    assert set(chk) >= {
        "gaussian_last_crossing_m",
        "free_jet_axial_m",
        "gaussian_shorter_than_free_jet",
    }
    assert chk["free_jet_axial_m"] == pytest.approx(d20)


def test_tip_override_replaces_notional_jet():
    case = ReleaseCase(
        "o",
        20.0,
        0.0215,
        1.25,
        300.0,
        0.04,
        0.96,
        0.6,
        tip_override={"velocity_m_s": 80.0, "diameter_m": 0.6, "density_kg_m3": 0.8},
    )
    rel = Release(case)
    assert rel.tip["v_exit_ms"] == 80.0
    assert rel.tip["rho_ratio_to_air"] == pytest.approx(0.8 / rel.rho_air)
    with pytest.raises(ValueError):
        ReleaseCase(
            "o",
            20.0,
            0.0215,
            1.25,
            300.0,
            0.04,
            0.96,
            tip_override={"velocity_m_s": 1.0},
        )
