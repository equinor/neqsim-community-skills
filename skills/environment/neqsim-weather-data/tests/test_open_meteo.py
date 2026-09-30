"""Offline tests for OpenMeteoClient using an injected fake fetch (no network)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from weather_data.open_meteo import OpenMeteoClient


def _forecast_payload() -> bytes:
    return json.dumps(
        {
            "latitude": 60.64,
            "longitude": 3.72,
            "elevation": 12.0,
            "timezone": "UTC",
            "hourly": {
                "time": ["2026-09-30T00:00", "2026-09-30T01:00", "2026-09-30T02:00"],
                "temperature_2m": [8.1, 7.9, 7.8],
                "wind_speed_10m": [9.5, 10.2, 11.0],
                "wind_gusts_10m": [14.0, 15.5, 16.1],
                "surface_pressure": [1008.0, 1007.5, 1007.0],
                "relative_humidity_2m": [88, 89, 90],
                "cloud_cover": [80, 85, 90],
                "precipitation": [0.0, 0.1, 0.2],
            },
            "hourly_units": {"temperature_2m": "\u00b0C", "wind_speed_10m": "m/s"},
        }
    ).encode("utf-8")


def _archive_payload() -> bytes:
    return json.dumps(
        {
            "latitude": 60.64,
            "longitude": 3.72,
            "elevation": 12.0,
            "timezone": "UTC",
            "hourly": {
                "time": ["2021-09-30T00:00", "2021-09-30T01:00"],
                "temperature_2m": [6.0, 5.8],
                "wind_speed_10m": [12.0, 20.0],
                "wind_gusts_10m": [18.0, 30.0],
                "surface_pressure": [1005.0, 1004.0],
                "relative_humidity_2m": [95, 96],
            },
            "hourly_units": {"temperature_2m": "\u00b0C"},
        }
    ).encode("utf-8")


def _marine_payload() -> bytes:
    return json.dumps(
        {
            "latitude": 60.64,
            "longitude": 3.72,
            "timezone": "UTC",
            "hourly": {
                "time": ["2026-09-30T00:00", "2026-09-30T01:00"],
                "wave_height": [2.1, 2.4],
                "sea_surface_temperature": [9.5, 9.4],
            },
            "hourly_units": {"wave_height": "m"},
        }
    ).encode("utf-8")


def _geocoding_payload() -> bytes:
    return json.dumps(
        {
            "results": [
                {
                    "name": "Ekofisk",
                    "latitude": 56.55,
                    "longitude": 3.21,
                    "country": "Norway",
                    "admin1": "Rogaland",
                    "elevation": 0.0,
                    "timezone": "Europe/Oslo",
                }
            ]
        }
    ).encode("utf-8")


def _error_payload() -> bytes:
    return json.dumps({"error": True, "reason": "bad parameter"}).encode("utf-8")


class FakeFetch:
    """Routes a URL to canned payloads by path and asserts on query parameters."""

    def __init__(self, payload_by_host):
        self.payload_by_host = payload_by_host
        self.calls = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.calls.append(url)
        parsed = urlparse(url)
        return self.payload_by_host[parsed.netloc]()


def test_forecast_requests_ms_and_celsius_and_parses_series():
    fetch = FakeFetch({"api.open-meteo.com": _forecast_payload})
    client = OpenMeteoClient(fetch=fetch)

    series = client.forecast(60.64, 3.72, forecast_days=2)

    call_url = fetch.calls[0]
    query = parse_qs(urlparse(call_url).query)
    assert query["wind_speed_unit"] == ["ms"]
    assert query["temperature_unit"] == ["celsius"]
    assert query["latitude"] == ["60.64"]

    assert series.source == "open-meteo-forecast"
    assert series.latitude == pytest.approx(60.64)
    assert series.hourly["wind_speed_10m"] == [9.5, 10.2, 11.0]
    assert series.hourly_time[0] == "2026-09-30T00:00"
    assert series.url == call_url


def test_historical_builds_archive_url_with_date_range():
    fetch = FakeFetch({"archive-api.open-meteo.com": _archive_payload})
    client = OpenMeteoClient(fetch=fetch)

    series = client.historical(60.64, 3.72, "2021-09-01", "2021-09-30")

    query = parse_qs(urlparse(fetch.calls[0]).query)
    assert query["start_date"] == ["2021-09-01"]
    assert query["end_date"] == ["2021-09-30"]
    assert series.source == "open-meteo-archive"
    assert series.hourly["wind_speed_10m"] == [12.0, 20.0]


def test_marine_requests_sea_cell_selection_by_default():
    fetch = FakeFetch({"marine-api.open-meteo.com": _marine_payload})
    client = OpenMeteoClient(fetch=fetch)

    series = client.marine(60.64, 3.72)

    query = parse_qs(urlparse(fetch.calls[0]).query)
    assert query["cell_selection"] == ["sea"]
    assert series.hourly["wave_height"] == [2.1, 2.4]


def test_geocode_parses_results():
    fetch = FakeFetch({"geocoding-api.open-meteo.com": _geocoding_payload})
    client = OpenMeteoClient(fetch=fetch)

    results = client.geocode("Ekofisk")

    assert len(results) == 1
    assert results[0].name == "Ekofisk"
    assert results[0].latitude == pytest.approx(56.55)
    assert results[0].country == "Norway"


def test_error_payload_raises_runtime_error():
    fetch = FakeFetch({"api.open-meteo.com": _error_payload})
    client = OpenMeteoClient(fetch=fetch)

    with pytest.raises(RuntimeError, match="bad parameter"):
        client.forecast(60.64, 3.72)
