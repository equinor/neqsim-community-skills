import math

import pytest

from control_authority_screening import ControlAuthorityModel, PeriodObservation


def _saturated_case():
    return {
        "controller_output": [62.0, 78.0, 95.0, 100.0, 100.0, 100.0, 88.0, 71.0],
        "controlled_variable": [18.2, 18.9, 20.4, 22.1, 23.6, 24.9, 21.0, 19.1],
        "disturbance": [11.0, 11.4, 12.2, 12.9, 13.5, 14.1, 12.6, 11.5],
    }


def test_saturation_fraction_counts_only_samples_on_the_stop():
    model = ControlAuthorityModel()
    result = model.evaluate(**_saturated_case())
    assert result.sample_count == 8
    assert result.saturation_fraction == pytest.approx(3 / 8)
    assert result.upper_saturation_fraction == pytest.approx(3 / 8)
    assert result.lower_saturation_fraction == 0.0
    assert result.modulating_fraction == pytest.approx(5 / 8)


def test_lower_stop_counts_as_lost_authority():
    model = ControlAuthorityModel()
    result = model.evaluate(
        controller_output=[0.0, 0.5, 0.0, 40.0],
        controlled_variable=[10.0, 10.2, 10.1, 11.0],
    )
    assert result.lower_saturation_fraction == pytest.approx(0.75)
    assert result.authority_status == "authority-lost"


def test_authority_status_thresholds():
    model = ControlAuthorityModel()
    retained = model.evaluate(
        controller_output=[40.0, 45.0, 50.0, 55.0, 100.0],
        controlled_variable=[10.0, 10.1, 10.2, 10.3, 10.4],
    )
    marginal = model.evaluate(
        controller_output=[40.0, 45.0, 50.0, 55.0, 60.0, 100.0, 100.0, 100.0],
        controlled_variable=[10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7],
    )
    lost = model.evaluate(
        controller_output=[100.0, 100.0, 100.0, 50.0],
        controlled_variable=[10.0, 10.1, 10.2, 10.4],
    )
    assert retained.authority_status == "authority-retained"
    assert marginal.authority_status == "authority-marginal"
    assert lost.authority_status == "authority-lost"


def test_variance_ratio_shows_rejection_lost_while_saturated():
    model = ControlAuthorityModel()
    result = model.evaluate(**_saturated_case())
    assert result.saturated.sample_count == 3
    assert result.modulating.sample_count == 5
    assert result.variance_ratio > 1.0


def test_disturbance_gain_fitted_per_regime():
    model = ControlAuthorityModel()
    result = model.evaluate(**_saturated_case())
    assert math.isfinite(result.saturated.disturbance_gain)
    assert math.isfinite(result.modulating.disturbance_gain)
    assert result.saturated.disturbance_r_squared > 0.9


def test_disturbance_omitted_gives_undefined_gain():
    model = ControlAuthorityModel()
    case = _saturated_case()
    case.pop("disturbance")
    result = model.evaluate(**case)
    assert math.isnan(result.saturated.disturbance_gain)
    assert math.isnan(result.gain_ratio)


def test_large_gain_on_a_poor_fit_does_not_raise_the_undamped_warning():
    model = ControlAuthorityModel()
    result = model.evaluate(
        controller_output=[100.0] * 8,
        controlled_variable=[19.0, 21.5, 19.3, 22.4, 19.1, 22.8, 19.4, 23.1],
        disturbance=[11.0, 11.2, 11.4, 11.6, 11.8, 12.0, 12.2, 12.4],
    )
    assert result.saturated.disturbance_r_squared < 0.5
    assert not any("undamped" in line for line in result.warnings)
    assert any("explains only" in line for line in result.warnings)


def test_off_set_point_fraction():
    model = ControlAuthorityModel()
    result = model.evaluate(
        controller_output=[50.0, 60.0, 70.0, 80.0],
        controlled_variable=[10.0, 12.0, 13.0, 10.2],
        set_point=10.0,
        set_point_tolerance=0.5,
    )
    assert result.off_set_point_fraction == pytest.approx(0.5)


def test_time_to_limit_uses_the_largest_observed_rate():
    model = ControlAuthorityModel()
    result = model.evaluate(
        controller_output=[100.0, 100.0, 100.0],
        controlled_variable=[20.0, 25.0, 23.0],
        sample_interval_h=0.5,
        limit_value=26.0,
    )
    # Largest step is 5 K over 0.5 h, and the margin from the last sample is 3 K.
    assert result.max_rate_per_hour == pytest.approx(10.0)
    assert result.margin_to_limit == pytest.approx(3.0)
    assert result.time_to_limit_h == pytest.approx(0.3)


def test_flat_controlled_variable_gives_no_time_to_limit():
    model = ControlAuthorityModel()
    result = model.evaluate(
        controller_output=[100.0, 100.0, 100.0],
        controlled_variable=[20.0, 20.0, 20.0],
        limit_value=26.0,
    )
    assert math.isnan(result.time_to_limit_h)
    assert any("time-to-limit" in line for line in result.warnings)


def test_flat_disturbance_with_rising_saturation_is_authority_loss():
    model = ControlAuthorityModel()
    trend = model.compare_periods(
        [
            PeriodObservation("year 1", 0.25, 1.03),
            PeriodObservation("year 2", 0.45, 0.70),
            PeriodObservation("year 3", 0.53, 0.98),
            PeriodObservation("year 4", 0.78, 1.11),
        ]
    )
    assert trend.verdict == "control-authority-loss"
    assert trend.saturation_change == pytest.approx(0.53)
    assert abs(trend.disturbance_relative_change) < 0.25
    assert "lost authority" in trend.narrative


def test_growing_disturbance_with_flat_saturation():
    model = ControlAuthorityModel()
    trend = model.compare_periods(
        [
            PeriodObservation("year 1", 0.20, 1.00),
            PeriodObservation("year 2", 0.22, 1.90),
        ]
    )
    assert trend.verdict == "disturbance-growth"


def test_both_effects_present():
    model = ControlAuthorityModel()
    trend = model.compare_periods(
        [
            PeriodObservation("year 1", 0.20, 1.00),
            PeriodObservation("year 2", 0.70, 1.90),
        ]
    )
    assert trend.verdict == "both"


def test_missing_disturbance_measure_is_reported_not_assumed():
    model = ControlAuthorityModel()
    trend = model.compare_periods(
        [
            PeriodObservation("year 1", 0.20),
            PeriodObservation("year 2", 0.22),
        ]
    )
    assert trend.verdict == "indeterminate"
    assert any("disturbance" in line for line in trend.warnings)


def test_assumptions_present():
    model = ControlAuthorityModel()
    result = model.evaluate(**_saturated_case())
    assert result.assumptions
    assert any("screening" in line.lower() for line in result.assumptions)


def test_mismatched_series_length_raises():
    model = ControlAuthorityModel()
    with pytest.raises(ValueError, match="equal length"):
        model.evaluate(
            controller_output=[10.0, 20.0, 30.0],
            controlled_variable=[1.0, 2.0],
        )


def test_invalid_output_span_raises():
    model = ControlAuthorityModel()
    with pytest.raises(ValueError, match="output_max"):
        model.evaluate(
            controller_output=[10.0, 20.0],
            controlled_variable=[1.0, 2.0],
            output_min=100.0,
            output_max=0.0,
        )


def test_saturation_band_wider_than_half_the_span_raises():
    model = ControlAuthorityModel()
    with pytest.raises(ValueError, match="saturation_band"):
        model.evaluate(
            controller_output=[10.0, 20.0],
            controlled_variable=[1.0, 2.0],
            saturation_band=60.0,
        )


def test_single_period_comparison_raises():
    model = ControlAuthorityModel()
    with pytest.raises(ValueError, match="at least two"):
        model.compare_periods([PeriodObservation("year 1", 0.25, 1.0)])


def test_invalid_threshold_configuration_raises():
    with pytest.raises(ValueError, match="marginal_saturation_fraction"):
        ControlAuthorityModel(
            marginal_saturation_fraction=0.6,
            lost_saturation_fraction=0.4,
        )
