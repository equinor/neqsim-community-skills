import math

import pytest

from reservoir_facility_value_chain import (
    Gas,
    GasTank,
    PressureCapacityCurve,
    RSDeliverability,
    capacity_from_sweep,
    fit_pz_line,
    flow_balance,
    maximise_rate,
    static_bottomhole_pressure,
    z_factor,
)

T_RES = 343.15
LEAN = {"N2": 0.015, "CO2": 0.004, "C1": 0.929, "C2": 0.036, "C3": 0.005, "iC4": 0.0038, "nC4": 0.0007, "iC5": 0.0008}


def test_z_factor_lean_gas_range():
    gas = Gas(LEAN)
    assert z_factor(1.0, T_RES, gas.tc, gas.pc) == pytest.approx(1.0, abs=0.01)
    assert 0.84 < gas.z(150.0, T_RES) < 0.93
    assert gas.z(60.0, T_RES) > gas.z(150.0, T_RES)


def test_tank_pressure_follows_pz_and_support_slows_decline():
    gas = Gas(LEAN)
    tank = GasTank(gas, T_RES, 171.6, 1000.0)
    p0 = tank.pressure()
    assert p0 / gas.z(p0, T_RES) == pytest.approx(171.6, rel=1e-6)
    tank.produce(400.0)
    p1 = tank.pressure()
    assert p1 < p0 and p1 / gas.z(p1, T_RES) == pytest.approx(171.6 * 0.6, rel=1e-6)
    supported = GasTank(gas, T_RES, 171.6, 1000.0, support=0.4)
    supported.produce(400.0)
    assert supported.pressure() > p1


def test_pz_fit_recovers_giip_and_rejects_outlier():
    giip, pz_i, n = 1090.0, 171.6, 14
    gp = [giip * 0.6 * i / (n - 1) for i in range(n)]
    pz = [pz_i * (1 - g / giip) + (0.6 if i % 2 == 0 else -0.6) for i, g in enumerate(gp)]
    pz[5] = 40.0
    a, b, g, rms, keep = fit_pz_line(gp, pz, 2.0)
    assert g == pytest.approx(giip, rel=0.03)
    assert not keep[5] and sum(keep) == n - 1


def test_static_column_raises_pressure_about_ten_percent():
    gas = Gas(LEAN)
    pbh = static_bottomhole_pressure(100.0, gas, 1400.0, 315.0)
    assert 108.0 < pbh < 118.0


def test_rs_fit_recovers_law_and_clips_exponent():
    truth = RSDeliverability(0.008, 0.72)
    pr = [55.0 + i for i in range(40)]
    whp = [36.0 + 0.3 * (i % 7) for i in range(40)]
    q = [truth.rate(a, b) for a, b in zip(pr, whp)]
    fit = RSDeliverability.fit(pr, whp, q)
    assert fit.n == pytest.approx(0.72, abs=1e-6) and fit.c == pytest.approx(0.008, rel=1e-4)
    assert fit.whp_for_rate(80.0, 1.5) == pytest.approx(truth.whp_for_rate(80.0, 1.5), abs=1e-6)
    steep = RSDeliverability.fit(pr, whp, [1e-9 * a ** 3 for a in pr])
    assert 0.5 <= steep.n <= 1.0


def test_capacity_from_sweep_cases():
    assert capacity_from_sweep([80, 100, 120], [0.8, 0.95, 1.1])["capacity"] == pytest.approx(106.67, abs=0.01)
    assert capacity_from_sweep([80, 100], [1.15, 1.15])["status"] == "infeasible"
    assert capacity_from_sweep([80, 100], [0.5, 0.7])["status"] == "not_reached"


def test_maximise_rate_crossing_and_edges():
    cap = PressureCapacityCurve([20.0, 30.0, 40.0], [40.0, 60.0, 80.0])
    p, q, bind = maximise_rate(lambda p: 100.0 - p, cap, 20.0, 40.0)
    assert p == pytest.approx(100.0 / 3.0, abs=1e-6) and q == pytest.approx(200.0 / 3.0, abs=1e-6)
    assert maximise_rate(lambda p: 30.0 - 0.1 * p, cap, 20.0, 40.0)[2] == "SUPPLY"
    assert maximise_rate(lambda p: 200.0, cap, 20.0, 40.0) == (40.0, 80.0, "FACILITY")


def test_flow_balance_converges_where_fixed_point_collapses():
    law = RSDeliverability(0.008, 0.72)
    q = flow_balance(lambda whp: law.rate(52.0, whp), 31.0, 4.4, 57.0)
    assert q > 0
    whp = 31.0 + 4.4 * (q / 57.0) ** 2
    assert law.rate(52.0, whp) == pytest.approx(q, rel=1e-6)
    assert flow_balance(lambda whp: law.rate(30.0, whp), 40.0, 4.4, 57.0) == 0.0
    assert math.isfinite(q)
