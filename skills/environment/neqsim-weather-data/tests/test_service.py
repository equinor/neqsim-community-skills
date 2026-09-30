"""Tests for WeatherDataService using fake client objects (no network)."""

from __future__ import annotations

import pytest
from weather_data.open_meteo import GeocodeResult, WeatherSeries
from weather_data.service import LocationNotResolvedError, WeatherDataService
from weather_data.ncs_facilities import FacilityLocation


class FakeOpenMeteo:
    def __init__(self, geocode_results=None, forecast_series=None, historical_series=None, marine_series=None):
        self.geocode_results = geocode_results or []
        self.forecast_series = forecast_series
        self.historical_series = historical_series
        self.marine_series = marine_series
        self.forecast_calls = []
        self.historical_calls = []

    def geocode(self, name, **kwargs):
        return self.geocode_results

    def forecast(self, latitude, longitude, **kwargs):
        self.forecast_calls.append((latitude, longitude, kwargs))
        return self.forecast_series

    def historical(self, latitude, longitude, start_date, end_date, **kwargs):
        self.historical_calls.append((latitude, longitude, start_date, end_date))
        return self.historical_series

    def marine(self, latitude, longitude, **kwargs):
        return self.marine_series


class FakeNcsLocator:
    def __init__(self, matches=None):
        self.matches = matches or []

    def find(self, name):
        return self.matches


class FakeMetNo:
    def __init__(self, series=None, raise_error=False):
        self.series = series
        self.raise_error = raise_error

    def forecast(self, latitude, longitude, altitude=None):
        if self.raise_error:
            raise RuntimeError("403 Forbidden")
        return self.series


def _series(source, hourly_time, temperature, wind):
    return WeatherSeries(
        source=source, latitude=60.64, longitude=3.72, elevation_m=12.0, timezone="UTC",
        hourly_time=hourly_time,
        hourly={"temperature_2m": temperature, "wind_speed_10m": wind},
    )


def test_resolve_location_prefers_explicit_coordinates():
    service = WeatherDataService(open_meteo=FakeOpenMeteo(), ncs_locator=FakeNcsLocator())

    location = service.resolve_location(name="Anything", latitude=60.0, longitude=3.0)

    assert location.source == "explicit-coordinates"
    assert location.latitude == 60.0


def test_resolve_location_uses_ncs_facility_register_before_geocoding():
    facility = FacilityLocation(name="TROLL A", latitude=60.64, longitude=3.72, attributes={})
    service = WeatherDataService(
        open_meteo=FakeOpenMeteo(geocode_results=[GeocodeResult("Troll", 1.0, 1.0, "NO", None, None, None)]),
        ncs_locator=FakeNcsLocator(matches=[facility]),
    )

    location = service.resolve_location(name="Troll A")

    assert location.source == "sodir-facility-register"
    assert location.latitude == 60.64


def test_resolve_location_falls_back_to_geocoding_when_no_ncs_match():
    service = WeatherDataService(
        open_meteo=FakeOpenMeteo(geocode_results=[GeocodeResult("Prudhoe Bay", 70.25, -148.32, "US", "Alaska", 10.0, "US/Alaska")]),
        ncs_locator=FakeNcsLocator(matches=[]),
    )

    location = service.resolve_location(name="Prudhoe Bay")

    assert location.source == "open-meteo-geocoding"
    assert location.country == "US"


def test_resolve_location_raises_when_nothing_matches():
    service = WeatherDataService(open_meteo=FakeOpenMeteo(geocode_results=[]), ncs_locator=FakeNcsLocator(matches=[]))

    with pytest.raises(LocationNotResolvedError):
        service.resolve_location(name="Nowhere At All")


def test_resolve_location_requires_name_or_coordinates():
    service = WeatherDataService(open_meteo=FakeOpenMeteo(), ncs_locator=FakeNcsLocator())
    with pytest.raises(ValueError):
        service.resolve_location()


def test_design_site_conditions_requests_years_back_window():
    historical_series = _series("open-meteo-archive", ["2016-09-30T00:00"] * 24 * 400, [5.0] * (24 * 400),
                                 [8.0] * (24 * 400))
    open_meteo = FakeOpenMeteo(historical_series=historical_series)
    service = WeatherDataService(open_meteo=open_meteo, ncs_locator=FakeNcsLocator())
    location = service.resolve_location(latitude=60.64, longitude=3.72)

    summary = service.design_site_conditions(location, years_back=5, end_date="2021-09-24")

    assert open_meteo.historical_calls[0][2] == "2016-09-24"
    assert open_meteo.historical_calls[0][3] == "2021-09-24"
    assert summary.mean_temperature_c == 5.0


def test_compare_forecast_sources_pairs_by_timestamp_and_reports_mean_abs_delta():
    open_meteo_series = _series(
        "open-meteo-forecast",
        ["2026-09-30T00:00", "2026-09-30T01:00"],
        [8.0, 7.0],
        [10.0, 11.0],
    )
    metno_series = _series(
        "met-norway-locationforecast",
        ["2026-09-30T00:00", "2026-09-30T01:00"],
        [7.5, 7.5],
        [9.0, 12.0],
    )
    service = WeatherDataService(
        open_meteo=FakeOpenMeteo(forecast_series=open_meteo_series),
        metno=FakeMetNo(series=metno_series),
        ncs_locator=FakeNcsLocator(),
    )
    location = service.resolve_location(latitude=60.64, longitude=3.72)

    result = service.compare_forecast_sources(location, days=1)

    assert result["n_hours_compared_temperature"] == 2
    assert result["mean_abs_temperature_delta_c"] == pytest.approx(0.5)
    assert result["mean_abs_wind_speed_delta_ms"] == pytest.approx(1.0)


def test_compare_forecast_sources_reports_error_when_metno_fails():
    open_meteo_series = _series("open-meteo-forecast", ["2026-09-30T00:00"], [8.0], [10.0])
    service = WeatherDataService(
        open_meteo=FakeOpenMeteo(forecast_series=open_meteo_series),
        metno=FakeMetNo(raise_error=True),
        ncs_locator=FakeNcsLocator(),
    )
    location = service.resolve_location(latitude=60.64, longitude=3.72)

    result = service.compare_forecast_sources(location, days=1)

    assert result["met_norway"] is None
    assert "error" in result
