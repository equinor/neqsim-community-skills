"""Open, keyless weather, marine and site-condition data for installations.

Worldwide via Open-Meteo (forecast, historical reanalysis, marine, geocoding),
with a Nordic-resolution MET Norway cross-check and a Sodir facility-name
resolver for the Norwegian Continental Shelf.
"""

from .metno import MetNorwayClient
from .ncs_facilities import FacilityLocation, SodirFacilityLocator
from .open_meteo import (
    DEFAULT_HOURLY_VARS,
    DEFAULT_MARINE_VARS,
    GeocodeResult,
    OpenMeteoClient,
    WeatherSeries,
)
from .service import Location, LocationNotResolvedError, WeatherDataService
from .site_conditions import (
    SiteConditionsSummary,
    estimate_pasquill_stability_class,
    summarize_site_conditions,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_HOURLY_VARS",
    "DEFAULT_MARINE_VARS",
    "FacilityLocation",
    "GeocodeResult",
    "Location",
    "LocationNotResolvedError",
    "MetNorwayClient",
    "OpenMeteoClient",
    "SiteConditionsSummary",
    "SodirFacilityLocator",
    "WeatherDataService",
    "WeatherSeries",
    "__version__",
    "estimate_pasquill_stability_class",
    "summarize_site_conditions",
]
