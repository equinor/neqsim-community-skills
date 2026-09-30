---
name: neqsim-weather-data
calculation_basis: "data-retrieval"
version: "0.1.0"
description: "Live, forecast and historical weather, wind and sea-state data for installations from open, keyless APIs - Open-Meteo worldwide and MET Norway/Sodir for the Norwegian Continental Shelf. USE WHEN: a task needs current, forecast or historical temperature, wind, humidity, pressure or wave data for an installation - by name on the NCS or by coordinates anywhere - for gas-turbine derating, fire-water/flare wind screening, dispersion stability class, or subsea cooldown screening."
last_verified: "2026-09-30"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Weather Data for Installations

This skill gives an agent live and historical weather, wind and sea-state data
for any installation, onshore or offshore, from open APIs that need no account,
subscription or API key:

| Source | What it provides | Coverage | Access |
|--------|------------------|----------|--------|
| Open-Meteo Forecast API | hourly temperature, humidity, pressure, wind, cloud cover, precipitation | worldwide, up to 16 days ahead | open, keyless |
| Open-Meteo Historical Weather API | the same variables from ERA5/ERA5-Land/IFS reanalysis | worldwide, 1940 to present | open, keyless |
| Open-Meteo Marine Weather API | wave height/period/direction, swell, sea-surface temperature | worldwide coastal/offshore | open, keyless |
| Open-Meteo Geocoding API | place/installation name to coordinates | worldwide | open, keyless |
| MET Norway Locationforecast | hourly forecast from the MET Nordic model (~1 km) | Norway/Sweden/Denmark, ~9 days ahead | open, requires a descriptive `User-Agent` header only |
| Sodir DataService `facility` layer | installation name to WGS84 position (best-effort) | Norwegian Continental Shelf | open API, NLOD 2.0 |

It is built especially to work well on the **Norwegian Continental Shelf**
(MET Norway's 1 km Nordic model plus the Sodir facility register let an agent
resolve "Troll A" or "Åsgard B" by name and cross-check two independent
forecast sources), while every function also works anywhere in the world given
a name (Open-Meteo geocoding) or a latitude/longitude.

It is a **data-retrieval** skill: it returns measured/modelled weather series
and simple empirical summaries, not a certified met-ocean design study. Design
wind, wave and temperature return periods, extreme-value (Gumbel/Weibull)
statistics and site-specific met-ocean criteria require a qualified met-ocean
study; this skill only gives a screening-level, order-of-magnitude picture to
scope one.

## When to Use

- A task needs the current or forecast ambient temperature, wind speed/
  direction/gust, humidity or pressure at an installation, by name or by
  coordinates.
- A task needs historical weather ("what has the weather been like here") for
  a past incident window, a fouling/corrosion season, or a design-basis
  screening statistic (min/mean/max temperature, wind speed percentile).
- A task needs a forward-looking forecast (hours to ~16 days) to plan a lift,
  a flaring event, a marine operation, or a fire-water/dispersion screening.
- A task needs wave height, wave period or sea-surface temperature for an
  offshore installation or subsea cooldown screening.
- An agent needs a Pasquill-Gifford stability class for
  `neqsim-gas-dispersion-distance-screening` from live wind speed, time of day
  and cloud cover, instead of an assumed class.
- An agent needs ambient temperature and elevation for
  `neqsim-gas-turbine-performance-screening`, or a wind speed for
  `neqsim-firewater-deluge-design`'s monitor/wind-drift screening, without the
  user supplying them by hand.
- A root-cause or operational investigation needs the weather at an
  equipment's location for a past trip/anomaly window, to test whether an
  ambient-temperature, wind, or sea-state condition was a candidate driver
  (feeds `neqsim-root-cause-analysis`'s "Weather as Evidence" method and
  `neqsim-autonomous-investigation`'s lead-lag relationship discovery).

## Inputs

- Location, resolved in this order (first available wins):
  1. `latitude` / `longitude` (and optional `elevation_m`) supplied directly -
     always correct, works anywhere.
  2. `name` matched against the open Sodir `facility` register (Norwegian
     Continental Shelf only) - best-effort, live, open data.
  3. `name` matched against Open-Meteo's worldwide geocoding API.
- `hourly`: list of Open-Meteo variable names to request (defaults cover
  temperature, humidity, pressure, wind speed/direction/gust, cloud cover,
  precipitation).
- `start_date` / `end_date` (`YYYY-MM-DD`) for historical queries.
- `days` / `past_days` for forecast queries (up to 16 / 92 respectively).
- Every HTTP client takes an injectable `fetch(url, timeout) -> bytes`, which
  makes it testable offline, mirroring `neqsim-ncs-infrastructure-network`.

## Outputs

- `WeatherSeries`: normalised hourly data (`hourly_time`, `hourly` dict of
  variable -> list of floats, `hourly_units`, optional `current`), the
  resolved `latitude`/`longitude`/`elevation_m`, the source URL and a
  retrieval timestamp - the same shape from every source, so callers do not
  need source-specific parsing.
- `SiteConditionsSummary`: min/mean/max temperature, mean/max/p99 wind speed,
  max wind gust, mean relative humidity, mean surface pressure, the period
  covered, and `warnings` when the sample is short or a variable is missing.
- `estimate_pasquill_stability_class(...)`: a screening `A`-`F` stability
  class from wind speed, day/night and cloud cover.
- `compare_forecast_sources(...)`: mean absolute temperature/wind deltas
  between Open-Meteo and MET Norway for the same point and window, useful on
  the NCS to sanity-check either source.

## Engineering Method

1. **Location resolution.** Explicit coordinates are used as-is. A name is
   first tried against the Sodir `facility` layer (ArcGIS REST,
   `outSR=4326`, `returnGeometry=true`); every string attribute is scanned for
   the search term because Sodir field names are not guaranteed stable across
   releases. If nothing matches (or the installation is outside Norway),
   Open-Meteo's geocoding API resolves the name worldwide.
2. **Forecast.** `GET api.open-meteo.com/v1/forecast` with `wind_speed_unit=ms`
   and `temperature_unit=celsius` so results already match NeqSim/screening
   conventions; up to 16 forecast days and 92 past days in one call.
3. **Historical.** `GET archive-api.open-meteo.com/v1/archive` reads the ERA5 /
   ERA5-Land / IFS reanalysis for any `start_date`/`end_date` back to 1940,
   worldwide, at ~9-25 km resolution.
4. **Marine.** `GET marine-api.open-meteo.com/v1/marine` (`cell_selection=sea`)
   returns wave height/period/direction and sea-surface temperature from
   MeteoFrance/ECMWF/NOAA wave models.
5. **MET Norway cross-check.** `GET api.met.no/weatherapi/locationforecast/2.0/
   complete` returns the MET Nordic model (~1 km) forecast for Norway, Sweden
   and Denmark. MET Norway requires a descriptive `User-Agent` header (no key);
   a missing or generic one (e.g. `okhttp`, `Java`) gets HTTP 403.
6. **Site-condition summary.** `summarize_site_conditions` reduces an hourly
   series to plain empirical statistics (min/mean/max, a 99th-percentile wind
   speed as a crude gust proxy) with pure-stdlib arithmetic; it is not a
   Gumbel/Weibull extreme-value fit and says so in its `warnings`.
7. **Stability class.** `estimate_pasquill_stability_class` follows a
   simplified Turner (1964) day/night, wind-speed/cloud-cover lookup. It
   ignores solar elevation, season and terrain and is meant as a stand-in only
   when no certified meteorological classification exists.

## Python Usage Pattern

```python
from weather_data import WeatherDataService

service = WeatherDataService()

# By coordinates - works anywhere in the world
troll_a = service.resolve_location(latitude=60.643, longitude=3.724, name="Troll A")

# By name - tries the Norwegian Sodir facility register first, then
# Open-Meteo's worldwide geocoding
ekofisk = service.resolve_location(name="Ekofisk")

forecast = service.get_forecast(troll_a, days=5)
print(forecast.hourly["wind_speed_10m"][:6], forecast.hourly_units["wind_speed_10m"])

history = service.design_site_conditions(troll_a, years_back=5)
print(history.max_wind_speed_ms, history.min_temperature_c, history.warnings)

waves = service.get_marine(troll_a, days=5)
print(waves.hourly.get("wave_height", [])[:6])

cross_check = service.compare_forecast_sources(troll_a, days=2)
print(cross_check["mean_abs_wind_speed_delta_ms"])
```

```python
from weather_data import estimate_pasquill_stability_class

stability_class = estimate_pasquill_stability_class(
    wind_speed_ms=4.5, is_daytime=True, cloud_cover_fraction=0.2,
)
# feed directly into neqsim-gas-dispersion-distance-screening's stability_class input
```

## Related NeqSim Functionality

- `neqsim-gas-dispersion-distance-screening`: `wind_speed` and `stability_class`
  can come from `get_forecast`/`get_historical` and
  `estimate_pasquill_stability_class` instead of an assumed value.
- `neqsim-gas-turbine-performance-screening`: `ambient_temperature_k` and
  `site_elevation_m` can be read from `get_forecast`/`design_site_conditions`.
- `neqsim-firewater-deluge-design`: `wind_speed_m_s` for the fire-monitor
  wind-drift screening.
- `neqsim-surf-cooldown-screening`: `seabed_temperature`/ambient temperature
  can be informed by `get_marine`'s `sea_surface_temperature` or
  `design_site_conditions`.
- `neqsim-root-cause-analysis` / `neqsim-autonomous-investigation` (core
  `equinor/neqsim` repo): historical weather for an equipment's location and
  event window, used as circumstantial evidence or as an extra time series in
  `RelationshipGraph` lead-lag discovery, never as a confirmed cause on its own.
- `neqsim-ncs-infrastructure-network`: the open Sodir DataService pattern this
  skill's facility resolver follows; use that skill for the wider NCS
  connectivity graph.
- The `installation-weather-agent` community agent wraps this skill for
  conversational use and points to the consuming agents above.

## Validation Checklist

- [ ] The resolved `Location.source` is recorded (`explicit-coordinates`,
      `sodir-facility-register`, or `open-meteo-geocoding`) so provenance is
      traceable.
- [ ] Any coordinate resolved by name (Sodir or geocoding) is verified against
      an authoritative source (STID, P&ID, operator records) before any
      safety-critical use.
- [ ] `SiteConditionsSummary.warnings` is checked before quoting min/mean/max
      or percentile values as a design basis.
- [ ] MET Norway calls carry a descriptive `User-Agent`; a 403 means the
      header was rejected, not that the location has no data.
- [ ] Marine results are only used for genuinely offshore/coastal locations;
      an inland point returns the nearest sea grid cell, which can be far away.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `LocationNotResolvedError` | Name not on the Sodir facility register and not found by Open-Meteo geocoding | Supply `latitude`/`longitude` directly |
| HTTP 403 from MET Norway | Missing or banned `User-Agent` header | Use the client's default header or set a descriptive one via `MetNorwayClient(user_agent=...)` |
| Wind speed looks like km/h | `wind_speed_unit` not set | This skill always requests `wind_speed_unit=ms`; check custom calls pass the same parameter |
| Marine data far from the platform | `cell_selection` defaulted to `land`/`nearest` | Use `cell_selection="sea"` (this skill's default) for offshore points |
| Sodir facility match is wrong | Field-name-agnostic substring search matched an unrelated record | Inspect `FacilityLocation.attributes` and disambiguate with a more specific name, or supply coordinates |

## Limitations

- Open-Meteo's non-commercial terms cap usage at under 10,000 API calls/day;
  self-hosting or a commercial key is available for heavier use
  (see https://open-meteo.com/en/terms).
- The Sodir facility resolver is best-effort name matching, not an
  authoritative asset register; never use it to place equipment.
- Historical reanalysis (ERA5/ERA5-Land) has ~9-25 km spatial resolution and
  is not a substitute for a site-specific met-ocean measurement campaign.
- `SiteConditionsSummary` statistics are plain empirical min/mean/max/
  percentiles over the retrieved window, not a return-period extreme-value
  analysis.
- `estimate_pasquill_stability_class` is a simplified screening lookup; use a
  certified meteorological classification for real consequence studies.
- MET Norway Locationforecast covers the Nordic region at high resolution;
  outside Norway/Sweden/Denmark, rely on the Open-Meteo forecast only.

## References

- Open-Meteo API documentation: https://open-meteo.com/en/docs,
  https://open-meteo.com/en/docs/historical-weather-api,
  https://open-meteo.com/en/docs/marine-weather-api,
  https://open-meteo.com/en/docs/geocoding-api
- Open-Meteo terms and attribution: https://open-meteo.com/en/terms
- MET Norway Locationforecast documentation:
  https://api.met.no/weatherapi/locationforecast/2.0/documentation
- Sodir (Norwegian Offshore Directorate) open data:
  https://factpages.sodir.no, NLOD 2.0 licence
- Turner, D.B. (1964). "A Diffusion Model for an Urban Area." *Journal of
  Applied Meteorology*, for the simplified Pasquill-Gifford stability lookup.
- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
