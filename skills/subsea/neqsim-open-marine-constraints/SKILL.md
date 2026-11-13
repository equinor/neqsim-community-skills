---
name: neqsim-open-marine-constraints
calculation_basis: "screening"
version: "0.1.0"
description: "Keyless route and site screening against open marine constraint layers: fishing and trawl exposure, protected and vulnerable seabed areas (MAREANO corals and sponges), offshore wind areas, Norwegian grid, existing pipelines, wrecks, munitions and earthquakes, from EMODnet, Fiskeridirektoratet, Miljodirektoratet, NVE, NOAA and USGS. USE WHEN: a tie-back, pipeline, cable or drill-centre concept needs sourced seabed-use, environmental or grid constraints that Omnia Maps and Sodir do not hold."
last_verified: "2026-11-13"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["gis.fiskeridir.no", "kart.miljodirektoratet.no", "gis3.nve.no", "gis.ngdc.noaa.gov", "ows.emodnet-humanactivities.eu", "earthquake.usgs.gov"]
---

# Open Marine Constraint Layers (fishing, environment, wind, grid, hazards)

Field-development maps usually carry infrastructure and licences, and miss what drives protection scope, routing
and permitting: how heavily a route is fished, which seabed is protected or vulnerable, where wind areas and the
onshore grid are. This skill reads those layers from six open services (no login) and screens a route against them.
`SOURCES` holds the layer catalogue; every host is allow-listed and every read is recorded with a SHA-256.

| Theme | Layers (keys in `sources.SOURCES`) | Source |
|-------|------------------------------------|--------|
| `fishing` | `fishing_bottom_otter_trawls`, `_beam_trawls`, `_bottom_seines`, `_dredges`, `_static_gears` (MW fishing hours per 0.05 deg C-square, European seas); `no_bottom_trawl_intensity`, `no_fishing_norwegian_vessels_2022_k1`, `no_fishing_foreign_vessels_2022` (rasters); `no_fixed_gear`, `no_lost_gear_2022` | EMODnet Human Activities, Fiskeridirektoratet |
| `environment` | `no_coral_reef_ban`, `no_marine_protected`, `no_svo_*` (spawning, seabirds, bottom communities), `no_mareano_*` (modelled and observed coral, sponge, sea-pen), `no_nature_reserves`, `no_marine_habitats_hb19`, `eu_marine_protected_areas`, `eu_natura2000` | Fiskeridirektoratet, HI, MAREANO, Miljodirektoratet, EMODnet |
| `infrastructure`, `hazard`, `restriction` | `eu_pipelines`, `eu_platforms`, `eu_shipwrecks`, `eu_munitions_poly`, `eu_military_areas`, `eu_msp_zoning`, `world_*` NOAA catalogues | EMODnet, NOAA NCEI |
| `wind`, `grid` | `no_wind_areas_2023`, `no_wind_areas_current`, `eu_windfarms*`; `no_grid_central`, `_regional`, `_subsea_cables`, `_substations`, `_planned_lines` | NVE, Fiskeridirektoratet, EMODnet |
| earthquakes | `screen_earthquakes` (USGS FDSN catalogue) | USGS |

## When to Use

- A tie-back, export line, cable or drill-centre screening needs trawl exposure to size burial or rock dump
  (companion: `neqsim-seabed-protection-screening`), and Omnia only gives trawling KP events on Equinor lines.
- A concept must list environmental constraints (coral, sponge, spawning, protected areas) before routing.
- A power-from-shore or electrification screen needs the nearest grid lines, subsea cables and substations.
- The asset is outside Norway and Omnia/Sodir have no seabed-use layers (EU seas via EMODnet).
- Not for: structural or flow design inputs, survey-grade positions, permits, or Norwegian pipeline/installation
  design data (use Omnia/STID and `neqsim-sodir-open-data`).

## Inputs

Route as lon/lat vertices in WGS84 degrees (a single point is allowed), the list of layer keys
(`keys_for_theme("fishing", "environment")`), buffer in km (default 5), sampling step (default 250 m), and an
optional disk cache directory. Pass a route that follows the planned centreline, not a straight line between ends.

## Outputs

`screen_route` returns per layer: features in the box, features intersecting the route, km of route inside
polygons, line crossings, nearest distance and the five nearest feature names, a `truncated` flag, the theme
implication, and for EMODnet effort layers the MW fishing hours inside cells (newest averaging period only).
Raster layers give samples with data, class values and the maximum pixel value. Failures are listed under
`errors` per layer. `provenance` carries URL, SHA-256, size and retrieval time for `SOURCES.md` and `results.json`.

## Engineering Method

1. Build the route centreline (see `neqsim-pipe-route-profile`) and choose themes. Start with `fishing` and
   `environment`; add `grid` and `wind` for electrification, `infrastructure` outside Norway.
2. `screen_route(client, route, keys, buffer_km=...)`. Read `errors` first: a refused layer is not an empty one.
3. Read `truncated` and `features_in_box`. A truncated layer (the registry caps at 5000 features) must be
   re-run with a smaller box or a shorter route section; `no_fixed_gear` truncates for long coastal routes.
4. Interpret per theme: fishing km inside effort cells and MW fishing hours rank route sections for protection;
   environment intersections are routing constraints to confirm with the regulator; grid nearest distance
   screens the cable length for power from shore (capacity is not in the layer).
5. Fetch the owner's metadata for every raster class value and attribute you quote (year, units, classes).
6. Record `provenance` and the caveats in the report next to every number.

## Python Usage Pattern

```python
from open_marine_constraints import MarineClient, keys_for_theme, screen_earthquakes, screen_route, summary_rows

client = MarineClient(cache_dir=".marine_cache")
route = [(3.0, 60.55), (4.4, 60.6), (5.1, 60.6)]          # lon, lat; follow the planned centreline
keys = keys_for_theme("fishing", "environment", "wind", "grid") + ["eu_pipelines"]
result = screen_route(client, route, keys, buffer_km=15.0, raster_step_km=15.0)
for row in summary_rows(result):
    print(row["layer"], row["exposure"])
quakes = screen_earthquakes(client, route, radius_km=200, min_magnitude=4.0, start_year=1950)
block = {"screening": result, "earthquakes": quakes}        # into results.json; keep result["provenance"]
```

Verified example (retrieved 2026-11-13, 114.9 km route west of Bergen, 15 km buffer): bottom otter trawl cells
(2021-2024) cover 66 km of the route with a mean 12.3 and a maximum 45.5 MW fishing hours per cell; static gears
touch 2.8 km; 9 EMODnet pipeline features cross or touch the route (Troll and Asgard export lines); a 2023
identified wind area (Vestavind) covers 20.5 km; one NVE subsea power cable crosses it; two nature reserves are
intersected (0.75 km); 21 earthquakes of M4 or more since 1950 lie within 200 km (largest M5.2, 116 km away).

## Validation Checklist

- [ ] `errors` is empty or each failed layer is stated in the report as not screened.
- [ ] `truncated` is False for every layer used, or the route was split and re-run.
- [ ] Layer year, units and legend were read from the owner for each value quoted; the raster class value is not
      quoted as a frequency.
- [ ] Route sampled at 250 m or finer, and the route is a centreline, not a chord.
- [ ] CRS: all results are WGS84 lon/lat; distances use a local projection (error below 1 % for routes under
      a few hundred km).
- [ ] The four `CAVEATS` accompany the numbers; open data is not presented as survey or permit evidence.

## Common Mistakes

- Treating an empty layer as clear: ArcGIS answers HTTP 200 with an error object, and some layers return nothing
  outside their country (Norwegian layers say nothing about the UK sector). Check coverage in the metadata.
- EMODnet effort layers hold five overlapping 4-year periods per cell; summing all of them multiplies km and mixes
  epochs. The skill keeps the newest period only; quote `averaging_periods_used`.
- WFS 2.0 with a bare `EPSG:4326` bbox is latitude-first and silently returns nothing; the client sends the URN form.
- Querying the Fiskeridirektoratet intensity rasters as features (they are raster layers; use `identify` sampling).
- Quoting `mw_fshn` as fishing hours: it is engine power times hours (MW fishing hours).
- Group layers (MAREANO layer 9, 0) reject queries; use their sub-layers.
- Reading a mapped protected area as a ban: the legal basis and the activity covered differ by area.

## Limitations

- Screening only: published positions and generalised geometry (about 20 m for ArcGIS layers), vessel-tracking
  based fishing data that misses small vessels, and different years per layer.
- Not covered because no keyless service could be read from the build network on 2026-11-13: EMODnet Geology and
  NGU/MAREANO geology (substrate, geohazards, slope stability; EMODnet Geology viewer and WFS time out, NGU answers
  503 or 404), UK NSTA, US BSEE GIS, CO2 storage atlases (Sodir CO2 atlas, CO2StoP), Global Energy Monitor
  trackers, MET Norway sea-ice and ocean API, EEZ boundaries (MarineRegions). Get these by hand from the owner and
  cite them; do not claim an automated read. For the US Gulf, BOEM publishes lease, block and pipeline shapefiles at
  `https://www.data.boem.gov/Main/Mapping.aspx` (NAD27 coordinates; convert to WGS84 before use).
- Grid layers show lines, cables and substations, not capacity, voltage margin or connection queue.
- Earthquake output is a historic catalogue, not a probabilistic seismic hazard for design.
- Terms: Fiskeridirektoratet, Miljodirektoratet and NVE data are under NLOD 2.0; EMODnet needs attribution; NOAA and
  USGS are public domain. Cite owner and retrieval date.

## References

- EMODnet Human Activities WFS: <https://ows.emodnet-humanactivities.eu/wfs> (vessel density and fishing effort, MSP).
- Fiskeridirektoratet map services: <https://gis.fiskeridir.no/server/rest/services/Yggdrasil>.
- Miljodirektoratet map services: <https://kart.miljodirektoratet.no/arcgis/rest/services>.
- NVE map services: <https://gis3.nve.no/map/rest/services/Mapservices>.
- NOAA NCEI hazards: <https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer>;
  USGS FDSN event service: <https://earthquake.usgs.gov/fdsnws/event/1/>.
- Companion skills: `neqsim-seabed-protection-screening`, `neqsim-subsea-equipment-placement`,
  `neqsim-surf-field-layout-design`, `neqsim-tie-in-pipeline-concept`, `neqsim-sodir-open-data`,
  `neqsim-jurisdiction-regulatory-basis`.
