"""Offline walkthrough of neqsim-weather-data using fake fetch functions.

Run with:
    C:\\appl\\neqsim-venv\\Scripts\\python.exe examples\\weather_data_walkthrough.py

This walkthrough never touches the network; it demonstrates the API shape
with canned responses shaped like the real Open-Meteo/MET Norway payloads. To
call the live APIs, construct ``OpenMeteoClient()`` / ``MetNorwayClient()``
with no arguments (they default to a real ``urllib``-based fetch).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from weather_data import Location, WeatherDataService  # noqa: E402
from weather_data.open_meteo import OpenMeteoClient, WeatherSeries  # noqa: E402
from weather_data.site_conditions import estimate_pasquill_stability_class  # noqa: E402


def _fake_forecast_fetch(url: str, timeout: float) -> bytes:
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
                "cloud_cover": [80, 85, 90],
            },
            "hourly_units": {"temperature_2m": "degC", "wind_speed_10m": "m/s"},
        }
    ).encode("utf-8")


def main() -> None:
    service = WeatherDataService(open_meteo=OpenMeteoClient(fetch=_fake_forecast_fetch))

    # Works anywhere in the world given coordinates.
    troll_a = Location(name="Troll A", latitude=60.643, longitude=3.724)

    forecast: WeatherSeries = service.get_forecast(troll_a, days=1)
    print("Forecast wind speed (m/s):", forecast.hourly["wind_speed_10m"])
    print("Forecast temperature (C):", forecast.hourly["temperature_2m"])

    stability = estimate_pasquill_stability_class(
        wind_speed_ms=forecast.hourly["wind_speed_10m"][0],
        is_daytime=True,
        cloud_cover_fraction=forecast.hourly["cloud_cover"][0] / 100.0,
    )
    print("Screening Pasquill stability class for dispersion screening:", stability)


if __name__ == "__main__":
    main()
