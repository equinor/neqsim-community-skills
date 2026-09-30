"""Read-only client for the MET Norway Locationforecast API.

Locationforecast needs no API key or account, but MET Norway enforces a
descriptive ``User-Agent`` header identifying the application (and ideally a
contact point); requests with a missing or generically-named header (e.g.
``okhttp``, ``Java``, ``Dalvik``) get an HTTP 403
(see https://api.met.no/doc/FAQ). It serves the MET Nordic model (~1 km
resolution) for Norway, Sweden and Denmark, which is why this skill uses it as
the Norwegian Continental Shelf cross-check alongside the worldwide
``OpenMeteoClient`` forecast.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional

from .open_meteo import WeatherSeries

Fetch = Callable[[str, float], bytes]

DEFAULT_USER_AGENT = "neqsim-weather-data/0.1 github.com/equinor/neqsim-community-skills"

BASE_URL = "https://api.met.no/weatherapi/locationforecast/2.0"

_HOURLY_COLUMNS = (
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "precipitation",
)

_HOURLY_UNITS = {
    "temperature_2m": "degC",
    "relative_humidity_2m": "%",
    "surface_pressure": "hPa",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "degrees",
    "wind_gusts_10m": "m/s",
    "cloud_cover": "%",
    "precipitation": "mm",
}


def make_fetch(user_agent: str = DEFAULT_USER_AGENT) -> Fetch:
    """Build a ``fetch`` function that carries the mandatory MET Norway User-Agent."""

    def _fetch(url: str, timeout: float = 30.0) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
            return response.read()

    return _fetch


class MetNorwayClient:
    """Read-only client for MET Norway Locationforecast (``/compact`` or ``/complete``)."""

    def __init__(self, fetch: Optional[Fetch] = None, *, user_agent: str = DEFAULT_USER_AGENT,
                 timeout: float = 30.0) -> None:
        self.fetch = fetch or make_fetch(user_agent)
        self.timeout = timeout

    def forecast(self, latitude: float, longitude: float, *, altitude: Optional[int] = None,
                 method: str = "complete") -> WeatherSeries:
        """Up to ~9-day forecast at MET Nordic resolution (Norway/Sweden/Denmark)."""
        params: Dict[str, object] = {"lat": round(latitude, 4), "lon": round(longitude, 4)}
        if altitude is not None:
            params["altitude"] = int(altitude)
        url = f"{BASE_URL}/{method}?" + urllib.parse.urlencode(params)
        payload = json.loads(self.fetch(url, self.timeout).decode("utf-8"))
        return _parse_locationforecast(payload, url)


def _parse_locationforecast(payload: dict, url: str) -> WeatherSeries:
    geometry = payload.get("geometry", {})
    coords = geometry.get("coordinates", [None, None, None])
    longitude = coords[0] if len(coords) > 0 else None
    latitude = coords[1] if len(coords) > 1 else None
    elevation_m = coords[2] if len(coords) > 2 else None
    timeseries = payload.get("properties", {}).get("timeseries", [])

    hourly_time: List[str] = []
    columns: Dict[str, List[Optional[float]]] = {name: [] for name in _HOURLY_COLUMNS}
    for entry in timeseries:
        data = entry.get("data", {})
        instant = data.get("instant", {}).get("details", {})
        next_hour = data.get("next_1_hours", {}).get("details", {})
        hourly_time.append(entry.get("time"))
        columns["temperature_2m"].append(instant.get("air_temperature"))
        columns["relative_humidity_2m"].append(instant.get("relative_humidity"))
        columns["surface_pressure"].append(instant.get("air_pressure_at_sea_level"))
        columns["wind_speed_10m"].append(instant.get("wind_speed"))
        columns["wind_direction_10m"].append(instant.get("wind_from_direction"))
        columns["wind_gusts_10m"].append(instant.get("wind_speed_of_gust"))
        columns["cloud_cover"].append(instant.get("cloud_area_fraction"))
        columns["precipitation"].append(next_hour.get("precipitation_amount"))

    current = {key: (values[0] if values else None) for key, values in columns.items()}
    return WeatherSeries(
        source="met-norway-locationforecast",
        latitude=float(latitude) if latitude is not None else float("nan"),
        longitude=float(longitude) if longitude is not None else float("nan"),
        elevation_m=elevation_m,
        timezone="UTC",
        hourly_time=hourly_time,
        hourly=columns,
        hourly_units=dict(_HOURLY_UNITS),
        current=current,
        url=url,
    )
