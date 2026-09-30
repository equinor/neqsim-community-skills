"""Facade tying location resolution, forecast/historical/marine weather and
screening-level site-condition summaries into one call for consuming agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as _timezone
from typing import Any, Dict, List, Optional, Sequence

from .metno import MetNorwayClient
from .ncs_facilities import SodirFacilityLocator
from .open_meteo import OpenMeteoClient, WeatherSeries
from .site_conditions import SiteConditionsSummary, summarize_site_conditions


@dataclass
class Location:
    """A resolved installation position with its resolution provenance."""

    name: str
    latitude: float
    longitude: float
    elevation_m: Optional[float] = None
    source: str = "explicit-coordinates"
    country: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class LocationNotResolvedError(RuntimeError):
    """Raised when a name could not be resolved to coordinates by any source."""


class WeatherDataService:
    """Resolve installations and read open weather, marine and site-condition data for them."""

    def __init__(
        self,
        open_meteo: Optional[OpenMeteoClient] = None,
        metno: Optional[MetNorwayClient] = None,
        ncs_locator: Optional[SodirFacilityLocator] = None,
    ) -> None:
        self.open_meteo = open_meteo or OpenMeteoClient()
        self.metno = metno or MetNorwayClient()
        self.ncs_locator = ncs_locator or SodirFacilityLocator()

    def resolve_location(
        self,
        name: Optional[str] = None,
        *,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        elevation_m: Optional[float] = None,
        try_ncs: bool = True,
        try_geocoding: bool = True,
    ) -> Location:
        """Resolve a location.

        Resolution order: (1) explicit ``latitude``/``longitude`` - always
        correct, works anywhere; (2) ``name`` against the open Sodir
        ``facility`` register - Norwegian Continental Shelf, best-effort;
        (3) ``name`` against Open-Meteo's worldwide geocoding API.
        """
        if latitude is not None and longitude is not None:
            return Location(
                name=name or "supplied-coordinates",
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation_m,
                source="explicit-coordinates",
            )
        if not name:
            raise ValueError("Provide either (latitude, longitude) or a name to resolve.")

        if try_ncs:
            try:
                matches = self.ncs_locator.find(name)
            except Exception:
                matches = []
            if matches:
                best = matches[0]
                return Location(
                    name=best.name, latitude=best.latitude, longitude=best.longitude,
                    source="sodir-facility-register", country="NO",
                )

        if try_geocoding:
            try:
                results = self.open_meteo.geocode(name)
            except Exception:
                results = []
            if results:
                best = results[0]
                return Location(
                    name=best.name, latitude=best.latitude, longitude=best.longitude,
                    elevation_m=best.elevation_m, source="open-meteo-geocoding", country=best.country,
                )

        raise LocationNotResolvedError(
            f"Could not resolve '{name}' to coordinates via the Sodir facility register or Open-Meteo "
            "geocoding. Supply latitude/longitude directly from an authoritative source (STID, P&ID, "
            "operator records)."
        )

    def get_forecast(
        self, location: Location, *, hourly: Optional[Sequence[str]] = None,
        days: int = 7, past_days: int = 0,
    ) -> WeatherSeries:
        """Worldwide forecast (Open-Meteo), up to 16 days ahead."""
        return self.open_meteo.forecast(
            location.latitude, location.longitude, hourly=hourly, forecast_days=days, past_days=past_days,
        )

    def get_metno_forecast(self, location: Location) -> WeatherSeries:
        """Nordic-resolution forecast cross-check (MET Norway), ~9 days ahead."""
        altitude = int(location.elevation_m) if location.elevation_m is not None else None
        return self.metno.forecast(location.latitude, location.longitude, altitude=altitude)

    def get_historical(
        self, location: Location, start_date: str, end_date: str,
        *, hourly: Optional[Sequence[str]] = None,
    ) -> WeatherSeries:
        """Worldwide reanalysis history (Open-Meteo archive), back to 1940."""
        return self.open_meteo.historical(location.latitude, location.longitude, start_date, end_date, hourly=hourly)

    def get_marine(
        self, location: Location, *, days: int = 7, hourly: Optional[Sequence[str]] = None,
    ) -> WeatherSeries:
        """Wave height/period and sea-surface temperature, current plus forecast."""
        return self.open_meteo.marine(location.latitude, location.longitude, hourly=hourly, forecast_days=days)

    def design_site_conditions(
        self, location: Location, *, years_back: int = 10,
        end_date: Optional[str] = None, hourly: Optional[Sequence[str]] = None,
    ) -> SiteConditionsSummary:
        """Screening-level ambient design statistics from ``years_back`` years
        of historical reanalysis (min/mean/max temperature, max wind/gust, a
        percentile wind speed). Not a return-period extreme-value analysis.
        """
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            # Open-Meteo's archive lags live data by a few days; stay clear of the edge.
            end = datetime.now(_timezone.utc).date() - timedelta(days=6)
        start = end.replace(year=end.year - years_back)
        series = self.get_historical(location, start.isoformat(), end.isoformat(), hourly=hourly)
        return summarize_site_conditions(series, location=location)

    def compare_forecast_sources(self, location: Location, *, days: int = 3) -> Dict[str, Any]:
        """Cross-check Open-Meteo against MET Norway for the same point and
        window (temperature and wind), most useful on the Norwegian
        Continental Shelf where MET Norway runs the higher-resolution Nordic
        model.
        """
        open_meteo_series = self.get_forecast(location, days=days)
        try:
            metno_series = self.get_metno_forecast(location)
        except Exception as exc:  # pragma: no cover - network/User-Agent failures
            return {"open_meteo": open_meteo_series.to_dict(), "met_norway": None, "error": str(exc)}

        temp_deltas = _paired_deltas(open_meteo_series, metno_series, "temperature_2m", limit_hours=days * 24)
        wind_deltas = _paired_deltas(open_meteo_series, metno_series, "wind_speed_10m", limit_hours=days * 24)

        return {
            "n_hours_compared_temperature": len(temp_deltas),
            "n_hours_compared_wind": len(wind_deltas),
            "mean_abs_temperature_delta_c": (sum(abs(d) for d in temp_deltas) / len(temp_deltas)) if temp_deltas else None,
            "mean_abs_wind_speed_delta_ms": (sum(abs(d) for d in wind_deltas) / len(wind_deltas)) if wind_deltas else None,
            "open_meteo_url": open_meteo_series.url,
            "met_norway_url": metno_series.url,
        }


def _paired_deltas(a: WeatherSeries, b: WeatherSeries, variable: str, *, limit_hours: int) -> List[float]:
    """Pair up two hourly series by matching ISO timestamps and return a - b for shared, non-null hours."""
    a_by_time = dict(zip(a.hourly_time, a.hourly.get(variable, [])))
    b_by_time = dict(zip(b.hourly_time, b.hourly.get(variable, [])))
    deltas = []
    for timestamp in a.hourly_time[:limit_hours]:
        value_a = a_by_time.get(timestamp)
        value_b = b_by_time.get(timestamp)
        if value_a is not None and value_b is not None:
            deltas.append(float(value_a) - float(value_b))
    return deltas
