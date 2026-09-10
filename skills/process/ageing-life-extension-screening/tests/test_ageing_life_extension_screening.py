from __future__ import annotations

import math

import pytest

from ageing_life_extension_screening import AgeingLifeExtensionModel, days_to_years


def _model() -> AgeingLifeExtensionModel:
    return AgeingLifeExtensionModel()


def test_homogeneous_process_shows_no_trend():
    # Evenly spaced failures -> homogeneous Poisson process, beta ~ 1, U ~ 0.
    times = [float(i) for i in range(1, 19)]
    res = _model().evaluate(
        failure_times_years=times, observation_years=18.0, target_year_offset=11.0
    )
    assert abs(res.laplace_u) < 1.96
    assert res.laplace_verdict == "no-significant-trend"
    assert 0.85 < res.crow_amsaa_beta < 1.25
    assert res.ageing_verdict in ("no-ageing-detected", "ageing-suspected")


def test_late_clustered_failures_flag_ageing():
    # All failures in the last third of the window -> strongly deteriorating.
    times = [12.0 + 0.3 * i for i in range(1, 20)]
    res = _model().evaluate(
        failure_times_years=times, observation_years=18.0, target_year_offset=11.0
    )
    assert res.laplace_u > 1.96
    assert res.laplace_verdict == "deteriorating"
    assert res.crow_amsaa_beta > 1.5
    assert res.ageing_verdict == "significant-ageing"
    assert res.rate_at_target_per_year > res.rate_now_per_year


def test_early_clustered_failures_flag_improvement():
    times = [0.2 * i for i in range(1, 20)]
    res = _model().evaluate(
        failure_times_years=times, observation_years=18.0, target_year_offset=11.0
    )
    assert res.laplace_u < -1.96
    assert res.laplace_verdict == "improving"
    assert res.crow_amsaa_beta < 1.0
    assert res.ageing_verdict == "improving"
    assert res.life_extension_verdict == "extend"


def test_crow_amsaa_reproduces_mean_cumulative_function():
    times = [1.0, 4.0, 9.0, 16.0]  # N(t) = t**0.5 exactly
    beta, lam = AgeingLifeExtensionModel.crow_amsaa_fit(times, 16.0)
    assert lam * (16.0**beta) == pytest.approx(len(times))
    assert beta < 1.0


def test_projection_matches_power_law_integral():
    times = [float(i) for i in range(1, 13)]
    res = _model().evaluate(
        failure_times_years=times, observation_years=12.0, target_year_offset=8.0
    )
    lam, beta = res.crow_amsaa_lambda, res.crow_amsaa_beta
    expected = lam * (20.0**beta) - lam * (12.0**beta)
    assert res.expected_failures_to_target == pytest.approx(expected, rel=1e-9)


def test_replacement_crossover_triggers_when_repair_cost_dominates():
    times = [12.0 + 0.3 * i for i in range(1, 20)]
    res = _model().evaluate(
        failure_times_years=times,
        observation_years=18.0,
        target_year_offset=11.0,
        replacement_cost=1.0e6,
        corrective_cost_per_failure=5.0e4,
        annual_cost_of_ownership=2.0e4,
    )
    assert res.replacement_crossover_year is not None
    assert res.replacement_crossover_year <= 11.0
    assert res.life_extension_verdict == "replace"


def test_no_crossover_when_replacement_is_expensive():
    times = [float(i) for i in range(1, 19)]
    res = _model().evaluate(
        failure_times_years=times,
        observation_years=18.0,
        target_year_offset=11.0,
        replacement_cost=1.0e9,
        corrective_cost_per_failure=1.0e3,
    )
    assert res.replacement_crossover_year is None
    assert res.life_extension_verdict in ("extend", "extend-with-measures")


def test_population_normalises_the_rate():
    times = [float(i) for i in range(1, 19)]
    single = _model().evaluate(
        failure_times_years=times, observation_years=18.0, target_year_offset=5.0
    )
    fleet = _model().evaluate(
        failure_times_years=times,
        observation_years=18.0,
        target_year_offset=5.0,
        population_size=9,
    )
    assert fleet.mean_rate_per_year == pytest.approx(single.mean_rate_per_year / 9.0)


def test_insufficient_data_is_reported_not_guessed():
    res = _model().evaluate(
        failure_times_years=[2.0, 5.0], observation_years=18.0, target_year_offset=11.0
    )
    assert res.laplace_verdict == "insufficient-data"
    assert res.ageing_verdict == "insufficient-data"
    assert res.life_extension_verdict == "insufficient-data-for-decision"


def test_rejects_failure_time_outside_window():
    with pytest.raises(ValueError):
        _model().evaluate(
            failure_times_years=[1.0, 25.0], observation_years=18.0, target_year_offset=11.0
        )
    with pytest.raises(ValueError):
        _model().evaluate(
            failure_times_years=[0.0], observation_years=18.0, target_year_offset=11.0
        )


def test_rejects_bad_configuration():
    with pytest.raises(ValueError):
        AgeingLifeExtensionModel(beta_watch=1.6, beta_significant=1.2)
    with pytest.raises(ValueError):
        _model().evaluate(
            failure_times_years=[1.0], observation_years=-1.0, target_year_offset=1.0
        )


def test_days_to_years_helper():
    assert days_to_years(365.25) == pytest.approx(1.0)
    assert days_to_years(0.0) == pytest.approx(0.0)


def test_assumptions_warn_about_reporting_artefacts():
    res = _model().evaluate(
        failure_times_years=[float(i) for i in range(1, 19)],
        observation_years=18.0,
        target_year_offset=11.0,
    )
    joined = " ".join(res.assumptions).lower()
    assert "reporting" in joined
    assert "screening only" in joined


def test_laplace_statistic_is_scale_invariant():
    times = [float(i) for i in range(1, 19)]
    u1 = AgeingLifeExtensionModel.laplace_statistic(times, 18.0)
    u2 = AgeingLifeExtensionModel.laplace_statistic([2.0 * t for t in times], 36.0)
    assert u1 == pytest.approx(u2)
    assert math.isfinite(u1)
