from __future__ import annotations

import pytest

from uncertainty_quantification.summary_stats import (
    StatisticsError,
    mean_standard_error,
    percentile,
    probability_below,
    split_half_drift_pct,
    summarise,
)


def test_percentile_matches_numpy_linear_interpolation():
    data = [1.0, 2.0, 3.0, 4.0]
    assert percentile(data, 0.0) == pytest.approx(1.0)
    assert percentile(data, 0.5) == pytest.approx(2.5)
    assert percentile(data, 1.0) == pytest.approx(4.0)
    assert percentile(data, 0.25) == pytest.approx(1.75)


def test_percentile_is_order_independent():
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.5) == pytest.approx(2.5)


def test_percentile_of_a_single_sample_is_that_sample():
    assert percentile([7.0], 0.9) == 7.0


def test_percentile_rejects_an_empty_sample_and_a_bad_fraction():
    with pytest.raises(StatisticsError):
        percentile([], 0.5)
    with pytest.raises(StatisticsError):
        percentile([1.0], 50.0)


def test_percentiles_are_ascending_as_the_task_gate_requires():
    data = [float(i) for i in range(100)]
    assert percentile(data, 0.10) < percentile(data, 0.50) < percentile(data, 0.90)


def test_probability_below_counts_the_correct_fraction():
    assert probability_below([-1.0, -2.0, 3.0, 4.0]) == pytest.approx(50.0)
    assert probability_below([1.0, 2.0], 0.0) == pytest.approx(0.0)


def test_probability_below_uses_a_custom_threshold():
    assert probability_below([1.0, 2.0, 3.0, 4.0], 3.0) == pytest.approx(50.0)


def test_standard_error_shrinks_with_the_square_root_of_n():
    small = mean_standard_error([1.0, 2.0, 3.0, 4.0] * 25)
    large = mean_standard_error([1.0, 2.0, 3.0, 4.0] * 100)
    assert large == pytest.approx(small / 2.0, rel=0.01)


def test_standard_error_needs_two_samples():
    with pytest.raises(StatisticsError):
        mean_standard_error([1.0])


def test_split_half_drift_is_zero_for_a_stationary_sample():
    assert split_half_drift_pct([5.0] * 100) == pytest.approx(0.0)


def test_split_half_drift_detects_a_trending_sample():
    assert split_half_drift_pct([float(i) for i in range(100)]) > 50.0


def test_split_half_drift_is_scale_invariant_for_an_output_centred_on_zero():
    centred = [float(i) - 49.5 for i in range(100)]
    shifted = [v + 1000.0 for v in centred]
    assert split_half_drift_pct(centred) == pytest.approx(split_half_drift_pct(shifted))


def test_summarise_reports_ascending_percentiles_and_moments():
    data = [float(i) for i in range(1000)]
    summary = summarise(data)
    assert summary.count == 1000
    assert summary.p10 < summary.p50 < summary.p90
    assert summary.mean == pytest.approx(499.5)
    assert summary.minimum == 0.0
    assert summary.maximum == 999.0


def test_summarise_reports_the_probability_of_a_negative_outcome():
    summary = summarise([-1.0] * 30 + [1.0] * 70)
    assert summary.prob_negative_pct == pytest.approx(30.0)


def test_summarise_of_a_single_sample_has_zero_spread():
    summary = summarise([3.0])
    assert summary.std == 0.0
    assert summary.standard_error == 0.0
    assert summary.p50 == 3.0


def test_summarise_rejects_an_empty_sample():
    with pytest.raises(StatisticsError):
        summarise([])


def test_summary_dict_carries_the_report_block_keys():
    payload = summarise([float(i) for i in range(100)]).to_dict()
    for key in ("p10", "p50", "p90", "mean", "std", "prob_negative_pct", "n_simulations"):
        assert key in payload
