"""Read-only client for the Open-Meteo family of open weather APIs.

Open-Meteo requires no API key or account for non-commercial use under
10,000 calls/day (https://open-meteo.com/en/terms). Every endpoint takes an
injectable ``fetch(url, timeout) -> bytes`` so tests and offline runs never
touch the network, mirroring the pattern used by
``neqsim-ncs-infrastructure-network``.

Covered endpoints:

* Forecast API (worldwide, up to 16 days ahead) -
  ``api.open-meteo.com/v1/forecast``
* Historical Weather API (worldwide, ERA5/ERA5-Land/IFS reanalysis back to
  1940) - ``archive-api.open-meteo.com/v1/archive``
* Marine Weather API (wave height/period/direction, sea surface temperature)
  - ``marine-api.open-meteo.com/v1/marine``
* Geocoding API (place name -> coordinates, worldwide) -
  ``geocoding-api.open-meteo.com/v1/search``
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

Fetch = Callable[[str, float], bytes]

USER_AGENT = "neqsim-weather-data/0.1 (+https://github.com/equinor/neqsim-community-skills)"

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

DEFAULT_HOURLY_VARS: List[str] = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "precipitation",
]

DEFAULT_MARINE_VARS: List[str] = [
    "wave_height",
    "wave_direction",
    "wave_period",
    "wind_wave_height",
    "swell_wave_height",
    "sea_surface_temperature",
]


def default_fetch(url: str, timeout: float = 30.0) -> bytes:
    """Perform a bounded, read-only GET and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        return response.read()


@dataclass
class WeatherSeries:
    """Normalised hourly (and optional current) weather data from one source."""

    source: str
    latitude: float
    longitude: float
    elevation_m: Optional[float]
    timezone: str
    hourly_time: List[str] = field(default_factory=list)
    hourly: Dict[str, List[Optional[float]]] = field(default_factory=dict)
    hourly_units: Dict[str, str] = field(default_factory=dict)
    current: Dict[str, Any] = field(default_factory=dict)
    current_units: Dict[str, str] = field(default_factory=dict)
    url: str = ""
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class GeocodeResult:
    """One worldwide name -> coordinate match from Open-Meteo geocoding."""

    name: str
    latitude: float
    longitude: float
    country: Optional[str]
    admin1: Optional[str]
    elevation_m: Optional[float]
    timezone: Optional[str]


class OpenMeteoClient:
    """Read-only client for Open-Meteo forecast, archive, marine and geocoding endpoints."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 30.0) -> None:
        self.fetch = fetch
        self.timeout = timeout

    def _get(self, base_url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        url = base_url + "?" + urllib.parse.urlencode(query, doseq=True)
        payload = json.loads(self.fetch(url, self.timeout).decode("utf-8"))
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Open-Meteo error for {url}: {payload.get('reason')}")
        payload["_url"] = url
        return payload

    @staticmethod
    def _to_series(source: str, payload: Dict[str, Any]) -> WeatherSeries:
        hourly = payload.get("hourly", {}) or {}
        hourly_time = list(hourly.get("time", []))
        hourly_values = {k: v for k, v in hourly.items() if k != "time"}
        current = dict(payload.get("current", {}) or {})
        current.pop("time", None)
        current.pop("interval", None)
        return WeatherSeries(
            source=source,
            latitude=float(payload.get("latitude")),
            longitude=float(payload.get("longitude")),
            elevation_m=payload.get("elevation"),
            timezone=payload.get("timezone", "GMT"),
            hourly_time=hourly_time,
            hourly=hourly_values,
            hourly_units=dict(payload.get("hourly_units", {}) or {}),
            current=current,
            current_units=dict(payload.get("current_units", {}) or {}),
            url=payload.get("_url", ""),
        )

    def forecast(
        self,
        latitude: float,
        longitude: float,
        *,
        hourly: Optional[Sequence[str]] = None,
        current: Optional[Sequence[str]] = None,
        forecast_days: int = 7,
        past_days: int = 0,
        wind_speed_unit: str = "ms",
        temperature_unit: str = "celsius",
        timezone_name: str = "UTC",
    ) -> WeatherSeries:
        """Forward-looking forecast up to 16 days ahead, worldwide."""
        hourly_vars = list(hourly) if hourly is not None else DEFAULT_HOURLY_VARS
        params: Dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(hourly_vars),
            "forecast_days": forecast_days,
            "past_days": past_days,
            "wind_speed_unit": wind_speed_unit,
            "temperature_unit": temperature_unit,
            "timezone": timezone_name,
        }
        if current:
            params["current"] = ",".join(current)
        payload = self._get(FORECAST_URL, params)
        return self._to_series("open-meteo-forecast", payload)

    def historical(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        *,
        hourly: Optional[Sequence[str]] = None,
        wind_speed_unit: str = "ms",
        temperature_unit: str = "celsius",
        timezone_name: str = "UTC",
    ) -> WeatherSeries:
        """Backward-looking reanalysis (ERA5/ERA5-Land/IFS), worldwide, back to 1940."""
        hourly_vars = list(hourly) if hourly is not None else DEFAULT_HOURLY_VARS
        params: Dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(hourly_vars),
            "wind_speed_unit": wind_speed_unit,
            "temperature_unit": temperature_unit,
            "timezone": timezone_name,
        }
        payload = self._get(ARCHIVE_URL, params)
        return self._to_series("open-meteo-archive", payload)

    def marine(
        self,
        latitude: float,
        longitude: float,
        *,
        hourly: Optional[Sequence[str]] = None,
        forecast_days: int = 7,
        cell_selection: str = "sea",
    ) -> WeatherSeries:
        """Wave and sea-surface conditions (current plus up to 8-day forecast)."""
        hourly_vars = list(hourly) if hourly is not None else DEFAULT_MARINE_VARS
        params: Dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(hourly_vars),
            "forecast_days": forecast_days,
            "cell_selection": cell_selection,
        }
        payload = self._get(MARINE_URL, params)
        return self._to_series("open-meteo-marine", payload)

    def geocode(self, name: str, *, count: int = 5, language: str = "en") -> List[GeocodeResult]:
        """Resolve a place/installation name to coordinates, worldwide."""
        params = {"name": name, "count": count, "language": language, "format": "json"}
        payload = self._get(GEOCODING_URL, params)
        results: List[GeocodeResult] = []
        for row in payload.get("results", []) or []:
            results.append(
                GeocodeResult(
                    name=row.get("name", name),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    country=row.get("country"),
                    admin1=row.get("admin1"),
                    elevation_m=row.get("elevation"),
                    timezone=row.get("timezone"),
                )
            )
        return results
