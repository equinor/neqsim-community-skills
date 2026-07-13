"""Tests for the Arps decline-curve fitting and production forecasting."""

from __future__ import annotations

import math

import pytest

from norwegian_continental_shelf_data import (
    ArpsFit,
    fit_arps_decline,
    forecast_production,
)


def _exponential_series(qi, decline, years):
    return [(float(t), qi * math.exp(-decline * t)) for t in range(years)]


def _hyperbolic_series(qi, di, b, years):
    return [
        (float(t), qi / ((1.0 + b * di * t) ** (1.0 / b))) for t in range(years)
    ]


def test_fit_exponential_recovers_parameters():
    series = _exponential_series(qi=100.0, decline=0.15, years=12)
    fit = fit_arps_decline(series)
    assert fit.model in {"exponential", "hyperbolic", "harmonic"}
    # Exponential data should be recovered with a near-perfect fit.
    assert fit.r_squared > 0.999
    assert fit.decline_rate_per_year == pytest.approx(0.15, abs=0.02)
    assert fit.initial_rate == pytest.approx(100.0, rel=0.02)


def test_fit_hyperbolic_series_prefers_hyperbolic():
    series = _hyperbolic_series(qi=200.0, di=0.25, b=0.5, years=15)
    fit = fit_arps_decline(series)
    assert fit.r_squared > 0.99
    assert 0.0 < fit.b_exponent <= 1.0


def test_fit_uses_decline_from_peak():
    # Rising then declining; fit should start at the peak.
    series = [(0.0, 50.0), (1.0, 80.0), (2.0, 100.0)] + _exponential_series(
        qi=100.0, decline=0.12, years=8
    )[1:]
    # Reindex times for the declining tail after the peak at t=2.
    series = [(0.0, 50.0), (1.0, 80.0), (2.0, 100.0), (3.0, 88.7), (4.0, 78.7), (5.0, 69.8), (6.0, 61.9)]
    fit = fit_arps_decline(series, from_peak=True)
    assert fit.peak_time == pytest.approx(2.0)
    assert fit.decline_rate_per_year > 0.0


def test_fit_rejects_rising_series():
    rising = [(0.0, 10.0), (1.0, 20.0), (2.0, 30.0)]
    with pytest.raises(ValueError):
        fit_arps_decline(rising, from_peak=False)


def test_fit_requires_three_points():
    with pytest.raises(ValueError):
        fit_arps_decline([(0.0, 100.0), (1.0, 80.0)])


def test_forecast_reaches_economic_limit_and_volumes():
    series = _exponential_series(qi=100.0, decline=0.20, years=10)
    fit = fit_arps_decline(series)
    forecast = forecast_production(
        fit,
        economic_limit_rate=10.0,
        max_years=40.0,
        timestep_years=1.0,
        cumulative_to_date=500.0,
    )
    assert forecast.years_to_limit is not None
    # q = 100 exp(-0.2 t) = 10 at t = ln(10)/0.2 ~ 11.5 years.
    assert forecast.years_to_limit == pytest.approx(12.0, abs=1.0)
    assert forecast.remaining_volume > 0.0
    assert forecast.estimated_ultimate_recovery == pytest.approx(
        500.0 + forecast.remaining_volume, rel=1e-6
    )
    assert len(forecast.profile) >= 2


def test_forecast_respects_max_years_when_limit_not_reached():
    # Very shallow decline that will not hit the limit within max_years.
    series = _exponential_series(qi=100.0, decline=0.01, years=10)
    fit = fit_arps_decline(series)
    forecast = forecast_production(
        fit, economic_limit_rate=1.0, max_years=5.0, timestep_years=1.0
    )
    assert forecast.years_to_limit is None
    assert forecast.remaining_volume > 0.0


def test_forecast_requires_positive_limit():
    fit = ArpsFit(
        model="exponential",
        b_exponent=0.0,
        initial_rate=100.0,
        decline_rate_per_year=0.1,
        r_squared=1.0,
        n_points=5,
        peak_time=0.0,
    )
    with pytest.raises(ValueError):
        forecast_production(fit, economic_limit_rate=0.0)
