"""Screening-level site-condition summaries and a Pasquill-Gifford stability
class estimator built on top of ``WeatherSeries`` data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .open_meteo import WeatherSeries


def _clean(values: List[Optional[float]]) -> List[float]:
    return [float(v) for v in values if v is not None]


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


@dataclass
class SiteConditionsSummary:
    """Plain empirical ambient statistics over a retrieved historical window."""

    location_name: str
    latitude: float
    longitude: float
    period_start: Optional[str]
    period_end: Optional[str]
    n_hours: int
    min_temperature_c: Optional[float]
    mean_temperature_c: Optional[float]
    max_temperature_c: Optional[float]
    mean_wind_speed_ms: Optional[float]
    p99_wind_speed_ms: Optional[float]
    max_wind_speed_ms: Optional[float]
    max_wind_gust_ms: Optional[float]
    mean_relative_humidity_pct: Optional[float]
    mean_surface_pressure_hpa: Optional[float]
    source: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def summarize_site_conditions(series: WeatherSeries, *, location: Any = None) -> SiteConditionsSummary:
    """Reduce an hourly ``WeatherSeries`` to screening design statistics.

    This is a plain empirical summary of the retrieved window (min/mean/max,
    and a 99th-percentile wind speed as a crude design-gust proxy). It is not
    a Gumbel/Weibull return-period extreme-value analysis; treat any
    percentile as indicative and escalate to a proper met-ocean study for
    design loads.
    """
    warnings: List[str] = []
    temperature = _clean(series.hourly.get("temperature_2m", []))
    wind_speed = _clean(series.hourly.get("wind_speed_10m", []))
    wind_gust = _clean(series.hourly.get("wind_gusts_10m", []))
    humidity = _clean(series.hourly.get("relative_humidity_2m", []))
    pressure = _clean(series.hourly.get("surface_pressure", []))

    n_hours = len(series.hourly_time)
    if n_hours < 24 * 30:
        warnings.append(
            f"Only {n_hours} hours of data ({n_hours / 24.0:.1f} days); statistics are indicative, "
            "not a design-basis extreme-value estimate."
        )
    if not wind_speed:
        warnings.append("No wind speed data returned; wind statistics are unavailable.")
    if not temperature:
        warnings.append("No temperature data returned; temperature statistics are unavailable.")

    return SiteConditionsSummary(
        location_name=getattr(location, "name", "") if location is not None else "",
        latitude=series.latitude,
        longitude=series.longitude,
        period_start=series.hourly_time[0] if series.hourly_time else None,
        period_end=series.hourly_time[-1] if series.hourly_time else None,
        n_hours=n_hours,
        min_temperature_c=min(temperature) if temperature else None,
        mean_temperature_c=(sum(temperature) / len(temperature)) if temperature else None,
        max_temperature_c=max(temperature) if temperature else None,
        mean_wind_speed_ms=(sum(wind_speed) / len(wind_speed)) if wind_speed else None,
        p99_wind_speed_ms=_percentile(wind_speed, 99.0),
        max_wind_speed_ms=max(wind_speed) if wind_speed else None,
        max_wind_gust_ms=max(wind_gust) if wind_gust else None,
        mean_relative_humidity_pct=(sum(humidity) / len(humidity)) if humidity else None,
        mean_surface_pressure_hpa=(sum(pressure) / len(pressure)) if pressure else None,
        source=series.source,
        warnings=warnings,
    )


# Simplified Turner (1964) day table: upper bound of wind-speed bucket (m/s) ->
# stability class by insolation (cloud-cover-derived). Values at/above the
# highest bucket resolve to the neutral class D (see the loop fallback below).
_INSOLATION_DAY_TABLE: Dict[float, Dict[str, str]] = {
    2.0: {"strong": "A", "moderate": "A", "slight": "B"},
    3.0: {"strong": "A", "moderate": "B", "slight": "C"},
    5.0: {"strong": "B", "moderate": "B", "slight": "C"},
    6.0: {"strong": "C", "moderate": "C", "slight": "D"},
}

# Simplified night table: upper bound of wind-speed bucket (m/s) -> stability
# class by cloud cover ("clear" <50%, "cloudy" >=50%).
_NIGHT_TABLE: Dict[float, Dict[str, str]] = {
    2.0: {"cloudy": "F", "clear": "F"},
    3.0: {"cloudy": "E", "clear": "F"},
    5.0: {"cloudy": "D", "clear": "E"},
}


def estimate_pasquill_stability_class(
    wind_speed_ms: float,
    *,
    is_daytime: bool,
    cloud_cover_fraction: Optional[float] = None,
) -> str:
    """Screening Pasquill-Gifford stability class (A-F) from wind speed, time
    of day and cloud cover, following a simplified Turner (1964) lookup.

    Use as a stand-in for ``neqsim-gas-dispersion-distance-screening``'s
    ``stability_class`` input when no site meteorologist classification
    exists. It ignores solar elevation, season and terrain, so treat the
    class as indicative, not a certified meteorological classification.
    """
    cloud = 0.5 if cloud_cover_fraction is None else max(0.0, min(1.0, cloud_cover_fraction))
    if is_daytime:
        insolation = "strong" if cloud < 0.3 else ("moderate" if cloud < 0.7 else "slight")
        table = _INSOLATION_DAY_TABLE
        key = insolation
    else:
        insolation = "clear" if cloud < 0.5 else "cloudy"
        table = _NIGHT_TABLE
        key = insolation

    for upper_bound in sorted(table.keys()):
        if wind_speed_ms < upper_bound:
            return table[upper_bound][key]
    return "D"
