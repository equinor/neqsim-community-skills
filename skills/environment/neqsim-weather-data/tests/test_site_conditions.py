"""Tests for site-condition summaries and the Pasquill stability-class helper."""

from __future__ import annotations

from weather_data.open_meteo import WeatherSeries
from weather_data.site_conditions import estimate_pasquill_stability_class, summarize_site_conditions


def _series(n_hours=48, wind=None, temperature=None, gust=None):
    wind = wind if wind is not None else [5.0 + (i % 5) for i in range(n_hours)]
    temperature = temperature if temperature is not None else [10.0 - (i % 3) for i in range(n_hours)]
    gust = gust if gust is not None else [w * 1.5 for w in wind]
    return WeatherSeries(
        source="open-meteo-archive",
        latitude=60.64,
        longitude=3.72,
        elevation_m=12.0,
        timezone="UTC",
        hourly_time=[f"2026-01-{(i // 24) + 1:02d}T{i % 24:02d}:00" for i in range(n_hours)],
        hourly={
            "temperature_2m": temperature,
            "wind_speed_10m": wind,
            "wind_gusts_10m": gust,
            "relative_humidity_2m": [90.0] * n_hours,
            "surface_pressure": [1008.0] * n_hours,
        },
    )


def test_summarize_site_conditions_computes_min_mean_max():
    series = _series(wind=[1.0, 2.0, 3.0, 4.0, 5.0], temperature=[0.0, 5.0, 10.0, 15.0, 20.0],
                      gust=[2.0, 3.0, 4.0, 5.0, 6.0])

    summary = summarize_site_conditions(series)

    assert summary.min_temperature_c == 0.0
    assert summary.max_temperature_c == 20.0
    assert summary.mean_temperature_c == 10.0
    assert summary.max_wind_speed_ms == 5.0
    assert summary.max_wind_gust_ms == 6.0
    assert summary.source == "open-meteo-archive"


def test_summarize_site_conditions_warns_on_short_window():
    series = _series(n_hours=24)  # one day only

    summary = summarize_site_conditions(series)

    assert any("statistics are indicative" in warning for warning in summary.warnings)


def test_summarize_site_conditions_warns_on_missing_wind():
    series = _series(n_hours=24 * 40)
    series.hourly["wind_speed_10m"] = []

    summary = summarize_site_conditions(series)

    assert summary.max_wind_speed_ms is None
    assert any("wind speed" in warning for warning in summary.warnings)


def test_pasquill_stability_class_daytime_strong_insolation_low_wind():
    assert estimate_pasquill_stability_class(1.5, is_daytime=True, cloud_cover_fraction=0.1) == "A"


def test_pasquill_stability_class_night_clear_low_wind_is_most_stable():
    assert estimate_pasquill_stability_class(1.5, is_daytime=False, cloud_cover_fraction=0.1) == "F"


def test_pasquill_stability_class_high_wind_is_neutral_d():
    assert estimate_pasquill_stability_class(12.0, is_daytime=True, cloud_cover_fraction=0.5) == "D"
    assert estimate_pasquill_stability_class(12.0, is_daytime=False, cloud_cover_fraction=0.5) == "D"


def test_pasquill_stability_class_defaults_cloud_cover_when_not_supplied():
    # cloud_cover_fraction=None should not raise and should return a valid class letter.
    result = estimate_pasquill_stability_class(4.0, is_daytime=True)
    assert result in "ABCDEF"
