import math

import pytest
from subsea_hot_tap_screening import (
    HotTapCase,
    HotTapTee,
    RunPipe,
    line_velocity_ms,
    minimum_wall_m,
    screen,
)

PIPE = RunPipe(
    outer_diameter_m=0.4064, wall_m=0.0143, smys_mpa=415.0, corrosion_allowance_m=0.003
)
TEE = HotTapTee(
    cutter_diameter_m=0.15,
    pressure_rating_bar=((0.0, 250.0), (100.0, 200.0)),
    max_temperature_c=120.0,
    allowable_branch_moment_knm=30.0,
)


def case(**kwargs):
    defaults = {
        "operating_pressure_bar": 100.0,
        "temperature_c": 40.0,
        "flow_rate_m3_h": 200.0,
        "max_cutting_velocity_ms": 3.0,
        "hydrate_temperature_c": 15.0,
        "cutter_feed_mm_min": 2.0,
        "branch_weight_kn": 10.0,
        "lever_arm_m": 1.5,
    }
    defaults.update(kwargs)
    return HotTapCase(**defaults)


def test_minimum_wall_matches_hoop_formula():
    expected = 100.0 * 0.1 * 0.4064 / (2.0 * 415.0 * 0.72)
    assert minimum_wall_m(PIPE, 100.0) == pytest.approx(expected)


def test_velocity_from_flow():
    area = math.pi / 4.0 * PIPE.inner_diameter_m**2
    assert line_velocity_ms(PIPE, 360.0) == pytest.approx(0.1 / area)


def test_complete_case_passes_and_reports_cut_time():
    result = screen(PIPE, TEE, case())
    assert result.overall == "pass"
    assert result.data_gaps == ()
    assert result.checks["cutting_time"].value == pytest.approx(14.3 / 2.0)
    assert result.checks["cutting_time"].status == "info"
    assert result.checks["branch_moment"].value == pytest.approx(15.0)


def test_large_cutter_fails_branch_ratio():
    big = HotTapTee(0.3, TEE.pressure_rating_bar, 120.0)
    assert screen(PIPE, big, case()).checks["branch_ratio"].status == "fail"


def test_pressure_rating_uses_temperature_derating():
    hot = screen(PIPE, TEE, case(operating_pressure_bar=210.0, temperature_c=100.0))
    cold = screen(PIPE, TEE, case(operating_pressure_bar=210.0, temperature_c=0.0))
    assert hot.checks["pressure_rating"].status == "fail"
    assert cold.checks["pressure_rating"].status == "pass"


def test_thin_remaining_wall_fails_at_high_pressure():
    result = screen(PIPE, TEE, case(operating_pressure_bar=240.0, temperature_c=0.0))
    assert result.checks["remaining_wall"].status == "fail"


def test_hydrate_margin_fails_when_close_to_hydrate_temperature():
    assert (
        screen(PIPE, TEE, case(hydrate_temperature_c=38.0))
        .checks["hydrate_margin"]
        .status
        == "fail"
    )


def test_missing_inputs_give_data_gaps_not_pass():
    result = screen(
        PIPE,
        HotTapTee(0.15, TEE.pressure_rating_bar, 120.0),
        case(
            max_cutting_velocity_ms=None,
            hydrate_temperature_c=None,
            branch_weight_kn=None,
        ),
    )
    assert result.overall == "incomplete"
    assert {"cutting_velocity", "hydrate_margin", "branch_moment"} <= {
        name for name, c in result.checks.items() if c.status == "data_gap"
    }


def test_high_velocity_fails_cutting_check():
    assert (
        screen(PIPE, TEE, case(flow_rate_m3_h=2000.0)).checks["cutting_velocity"].status
        == "fail"
    )


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        RunPipe(0.4, 0.3, 415.0)
    with pytest.raises(ValueError):
        HotTapTee(0.15, (), 100.0)
