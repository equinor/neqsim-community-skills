import math

import pytest
from control_valve_cv_screening.capacity import (
    cv_from_gas_flow,
    gas_flow_sm3h,
    verify_stop_capacity,
)

T = 353.15
M = 17.8
Z = 0.88


def test_inverse_round_trip():
    q = gas_flow_sm3h(250.0, 190.0, 136.0, T, M, Z)
    assert cv_from_gas_flow(q, 190.0, 136.0, T, M, Z) == pytest.approx(250.0, rel=1e-12)


def test_flow_increases_with_pressure_drop_until_choked():
    q1 = gas_flow_sm3h(250.0, 200.0, 180.0, T, M, Z)
    q2 = gas_flow_sm3h(250.0, 200.0, 140.0, T, M, Z)
    q3 = gas_flow_sm3h(250.0, 200.0, 20.0, T, M, Z)
    q4 = gas_flow_sm3h(250.0, 200.0, 5.0, T, M, Z)
    assert q1 < q2 < q3
    assert q3 == pytest.approx(q4, rel=1e-9)  # choked: no more flow with lower p2


def test_stop_capacity_limit_case():
    q_test = gas_flow_sm3h(240.0, 190.0, 136.0, T, M, Z)
    res = verify_stop_capacity(
        [{"q_sm3h": q_test, "p1_bara": 190.0, "p2_bara": 136.0}],
        cv_max=600.0,
        stop_fraction=0.38,
        temperature_k=T,
        molar_mass=M,
        z=Z,
        limit_case={"p1_bara": 214.0, "p2_bara": 192.0, "q_limit_sm3h": 700000.0},
    )
    assert res.cv_effective[0] == pytest.approx(240.0, rel=1e-9)
    assert res.implied_opening_fraction[0] == pytest.approx(0.4, rel=1e-9)
    assert res.ratio_to_nominal[0] == pytest.approx(240.0 / 228.0, rel=1e-9)
    assert res.flow_at_limit_case_sm3h < 700000.0  # the stop passes less than the limit
    assert res.opening_fraction_for_limit > 0.38
    assert not math.isnan(res.flow_at_limit_case_sm3h)


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        gas_flow_sm3h(100.0, 50.0, 60.0, T, M)
    with pytest.raises(ValueError):
        verify_stop_capacity([], cv_max=1.0, stop_fraction=0.5, temperature_k=T, molar_mass=M, characteristic="eq%")
