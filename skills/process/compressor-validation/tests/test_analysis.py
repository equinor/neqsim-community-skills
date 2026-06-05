import math

import pytest

from compressor_validation import (
    ChartTuning,
    CompressorCurve,
    Drivetrain,
    evaluate_operating_point,
    gas_power,
    polytropic_head,
)


def _curve() -> CompressorCurve:
    return CompressorCurve(
        speed_lines={
            9000: [(5000, 80_000, 0.78), (7000, 72_000, 0.80), (9000, 60_000, 0.77)],
            10000: [(5500, 99_000, 0.78), (7700, 89_000, 0.80), (9900, 74_000, 0.77)],
        }
    )


def test_polytropic_head_matches_analytic_value() -> None:
    # PR=2, k=1.28, eta_p=0.78 -> m=(0.28)/(1.28*0.78)
    head = polytropic_head(
        p_in=60.0, p_out=120.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28, eta_p=0.78
    )
    m = (1.28 - 1.0) / (1.28 * 0.78)
    expected = (0.9 * 8.314 * 313.0 / 0.020) * (1.0 / m) * (2.0 ** m - 1.0)
    assert head == pytest.approx(expected)


def test_polytropic_head_increases_with_pressure_ratio() -> None:
    low = polytropic_head(p_in=60.0, p_out=90.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28, eta_p=0.78)
    high = polytropic_head(p_in=60.0, p_out=150.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28, eta_p=0.78)
    assert high > low


def test_polytropic_head_rejects_bad_efficiency() -> None:
    with pytest.raises(ValueError, match="eta_p"):
        polytropic_head(p_in=60, p_out=120, T_in=313, MW=20, Z=0.9, k=1.28, eta_p=1.5)


def test_curve_interpolates_head_along_speed_line() -> None:
    result = _curve().evaluate(flow=6000, speed=9000)
    # halfway between (5000, 80000) and (7000, 72000) -> 76000
    assert result.head == pytest.approx(76_000.0)
    assert not result.extrapolated


def test_curve_flags_extrapolation_beyond_flow_range() -> None:
    result = _curve().evaluate(flow=20_000, speed=9000)
    assert result.extrapolated is True


def test_fan_law_scaling_increases_head_with_speed() -> None:
    base = _curve().evaluate(flow=7000, speed=9000).head
    faster = _curve().evaluate(flow=7000, speed=9900).head
    # head scales with N^2 (and flow remapped by N), so a higher speed raises head
    assert faster > base


def test_chart_tuning_head_multiplier_applies() -> None:
    base = _curve().evaluate(flow=7000, speed=9000).head
    tuned = CompressorCurve(_curve().speed_lines, tuning=ChartTuning(head_mult=1.1))
    assert tuned.evaluate(flow=7000, speed=9000).head == pytest.approx(base * 1.1)


def test_gas_power_and_drivetrain_losses() -> None:
    gp = gas_power(mass_flow=90.0, head_J_per_kg=72_000.0, efficiency=0.8)
    assert gp == pytest.approx(90.0 * 72_000.0 / 0.8)
    sp = Drivetrain(mechanical_loss_frac=0.02).shaft_power(gp)
    assert sp == pytest.approx(gp / 0.98)


def test_evaluate_operating_point_reports_deviation_and_power() -> None:
    op = evaluate_operating_point(
        _curve(), flow=7000, speed=9000, mass_flow=90.0,
        p_in=60.0, p_out=120.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28,
        drivetrain=Drivetrain(mechanical_loss_frac=0.02),
    )
    assert math.isfinite(op.head_deviation_pct)
    assert op.shaft_power_W > op.gas_power_W
    assert 0.0 < op.efficiency <= 1.0
