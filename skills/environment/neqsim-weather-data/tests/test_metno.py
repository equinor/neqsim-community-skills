"""Offline tests for MetNorwayClient using an injected fake fetch (no network)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from weather_data.metno import MetNorwayClient, make_fetch


def _locationforecast_payload() -> bytes:
    return json.dumps(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [3.724, 60.643, 12.0]},
            "properties": {
                "timeseries": [
                    {
                        "time": "2026-09-30T00:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 8.2,
                                    "relative_humidity": 88.0,
                                    "air_pressure_at_sea_level": 1008.1,
                                    "wind_speed": 9.4,
                                    "wind_from_direction": 210.0,
                                    "wind_speed_of_gust": 14.2,
                                    "cloud_area_fraction": 82.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "cloudy"},
                                "details": {"precipitation_amount": 0.1},
                            },
                        },
                    },
                    {
                        "time": "2026-09-30T01:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 7.9,
                                    "relative_humidity": 89.0,
                                    "air_pressure_at_sea_level": 1007.6,
                                    "wind_speed": 10.1,
                                    "wind_from_direction": 215.0,
                                    "wind_speed_of_gust": 15.0,
                                    "cloud_area_fraction": 90.0,
                                }
                            },
                            "next_1_hours": {"details": {"precipitation_amount": 0.2}},
                        },
                    },
                ]
            },
        }
    ).encode("utf-8")


def test_forecast_parses_timeseries_into_weather_series():
    calls = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        return _locationforecast_payload()

    client = MetNorwayClient(fetch=fetch)
    series = client.forecast(60.643, 3.724, altitude=12)

    assert series.source == "met-norway-locationforecast"
    assert series.latitude == pytest.approx(60.643)
    assert series.longitude == pytest.approx(3.724)
    assert series.hourly["temperature_2m"] == [8.2, 7.9]
    assert series.hourly["wind_speed_10m"] == [9.4, 10.1]
    assert series.hourly_units["wind_speed_10m"] == "m/s"
    assert series.current["temperature_2m"] == 8.2

    query = parse_qs(urlparse(calls[0]).query)
    assert query["lat"] == ["60.643"]
    assert query["altitude"] == ["12"]


def test_make_fetch_sets_descriptive_user_agent():
    fetch = make_fetch("my-app/1.0 contact@example.com")
    request_headers = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return _locationforecast_payload()

    import urllib.request

    original_urlopen = urllib.request.urlopen

    def fake_urlopen(request, timeout=None):
        request_headers.update(request.headers)
        return _FakeResponse()

    urllib.request.urlopen = fake_urlopen
    try:
        fetch("https://api.met.no/weatherapi/locationforecast/2.0/complete?lat=1&lon=2", 10.0)
    finally:
        urllib.request.urlopen = original_urlopen

    assert request_headers.get("User-agent") == "my-app/1.0 contact@example.com"
