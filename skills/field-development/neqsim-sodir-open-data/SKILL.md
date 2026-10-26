---
name: neqsim-sodir-open-data
calculation_basis: "screening"
version: "0.1.0"
description: "Map and read-only client for ALL Sodir (Sokkeldirektoratet) open data: DataService REST with 112 FactPages tables/layers (wellbores, DST, tops, fields, reserves, production, owners, facilities, pipelines, licences, surveys, CO2), FactPages CSV, FactMaps, bulk files. USE WHEN: a task needs an official NCS fact or must pick the right Sodir layer. Keyless, NLOD 2.0."
last_verified: "2026-10-26"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["factmaps.sodir.no", "factpages.sodir.no"]
---

# Sodir Open Data (Sokkeldirektoratet)

Sodir publishes its petroleum, CO2, seabed-mineral and survey data openly under
NLOD 2.0 (reuse with attribution). This skill is the single place agents learn
**what exists, which layer answers which question, how to read it, and the traps**.
Page of record: <https://www.sodir.no/fakta/data-og-analyser/apne-data/>
(it answers HTTP 403 to scripts - use the service hosts below, never scrape it).

## When to Use

- A task needs an official NCS fact: well, DST, formation top, field reserves, production history,
  owner or operator, licence, facility, pipeline, survey or CO2 storage record.
- You must pick the right Sodir layer or table, or need a prior for a fluid or reservoir model when no PVT study exists.
- A company data source (GeoX, PDM, SMDA) is unavailable and Sodir is the open cross-check.

## Inputs

Field, discovery, well or licence name (or NPDID), an optional bounding box (WGS84), the question to answer,
and the data tier required (`screening` only: open data never replaces PVT or governed data).

## Outputs

Rows (dict per record) with the layer id, join keys and retrieval date; `provenance()` source list for
`results.json` / `SOURCES.md`; `assumptions` and `data_gaps` for anything not open.

## Engineering Method

1. Identify the question with `search()` / `use_case()` and the layer table below.
2. Query server-side (`where`, `bbox`, `out_fields`) and join on `*Npdid*` keys, not names.
3. Convert dates (Europe/Oslo) and geometry (`out_sr=4326`), take the latest version/valid-to-null rows.
4. Label every derived number `screening`, cite Sodir (NLOD 2.0) and record the gaps.

## Routes (all keyless GET)

| Route | URL | Use |
|-------|-----|-----|
| DataService REST (preferred) | `https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer/{id}/query` | **Every** FactPages table and layer, SQL `where`, paging, bbox, JSON |
| DataService metadata | `.../DataService/Metadata/MapServer/10` (tables), `/11` (attributes) | Table and column descriptions |
| FactPages CSV views | `https://factpages.sodir.no/public?/Factpages/external/tableview/{view}&rs:Format=CSV...` | Whole table as CSV (`field_production_monthly`, `field_reserves`, `wellbore_exploration_all`, `wellbore_development_all`, `wellbore_formation_top`, `licence_licensee_hst`, ...) |
| FactMaps map services | `.../Factmaps/FactMapsWGS84/MapServer` and `FactMapsED50UTM32` | Styled map layers, WMS/WFS/OGC, GetCapabilities |
| Bulk files | `https://factpages.sodir.no/downloads/{shape\|csv}/{name}.zip`, FGDB `SODIR_FactMaps_data_v3_0.zip` | GIS/offline (CSV has WKT geometry; only FGDB is complete) |
| Themes | `.../Themes/CO2_storage_{depths,options,thickness}_1_0/MapServer` | CO2 storage atlas |
| Human viewers | factmaps.sodir.no/map, survey map, Deep Sea Surveys, CO2 atlas | Look, do not script |
| geonorge.no | national catalogue copy | Alternative discovery |

DataService layer id scheme `XYZZ`: X = 1 admin, 2 geology, 3 licences, 4 surveys,
5 wellbore, 6 facilities, 7 hydrocarbons, 8 seabed minerals, 9 carbon storage;
`ZZ=00` is the mother table.

## Python Usage Pattern
```python
# pip install -e skills/field-development/neqsim-sodir-open-data   (pure stdlib, no keys)
from sodir_open_data import SodirOpenData, search, describe, use_case, field_names

search("drill stem test")            # find the layer/table (bundled catalog of all 112)
print(describe("wellbore_dst"))      # columns with Sodir's own descriptions
print(use_case("pvt"))               # recipe: layers, join keys, traps

sd = SodirOpenData()
wells = sd.query("wellbore", "wlbPurpose='WILDCAT'", bbox=(2.0, 60.4, 2.6, 60.8),
                 geometry=True, out_sr=4326, max_rows=200)        # WGS84 box
npdid = sd.by_name("wellbore", "wlbWellboreName", "31/2-1")[0]["wlbNpdidWellbore"]
tops = sd.children("wellbore_formation_top", npdid)
dst = sd.children("wellbore_dst", npdid)                           # BHP, BHT, GOR, densities
reserves = sd.factpages_table("field_reserves")                    # CSV view as dict rows
sources = sd.provenance()                                          # put in results.json / SOURCES.md
```

CLI: `<python> -m sodir_open_data search|describe|query|usecase` (selected interpreter, e.g. `C:\appl\neqsim-venv\Scripts\python.exe`).
Refresh the catalog when Sodir adds fields: `<python> -m sodir_open_data.refresh`.

## Which layer answers what

| Question | Layers (id) | Key |
|----------|-------------|-----|
| Wells near a target; type, status, depth, water depth, HC, BHT | `wellbore` 5000 | `wlbNpdidWellbore` |
| Fluid and reservoir priors when no PVT study exists | `wellbore_dst` 5008, `wellbore_oil_sample` 5013, `wellbore_core` 5003, `wellbore_formation_top` 5009, `wellbore_co2` 5002, `wellbore_mud` 5012 | `wlbNpdidWellbore` |
| Production history (oil, gas, NGL, condensate, water; yearly/monthly) | `profiles` 7300, FactPages `field_production_*` | `prfNpdidInformationCarrier` |
| Reserves, in-place, resource class | `field_reserves` 7113, `field_reserves_company` 7114, `discovery_reserves` 7008 | `fldNpdidField`, `dscNpdidDiscovery` |
| Owners and operators, history | `field_licensee_hst` 7108, `field_operator_hst` 7110, `discovery_owner_hst` 7007, `licence_licensee_hst` 3007, `company` 1200 | `cmpNpdidCompany` |
| Hosts, subsea facilities, pipelines (from/to, medium, size) | `facility` 6000, `pipeline` 6100, `tuf` 6200 | `fclNpdidFacility`, `pplNpdidPipeline` |
| Licences, work obligations, rounds, APA/AFEX, blocks | `licence` 3000, `licence_task` 3010, `licensing_activity` 3100, `afex_area` 3200, `bsns_arr_area` 3300, `block` 1001 | `prlNpdidLicence` |
| Seismic/EM/shallow surveys (metadata only) | `seis_acquisition` 4000 (+ children 4001-4015) | `seaNpdidSurvey` |
| CO2 injection and storage | `csd_injection` 9001, `wellbore_co2` 5002, Themes MapServers, atlas FGDB | `cslNpdidLicence` |
| Stratigraphy, structural elements, plays | `strat_litho` 2100, `str_structuralelements` 2000, `play_current_public` 7800 | `lsuNpdidLithoStrat` |
| Seabed minerals | `sbm_*` 4501-4504, 8001-8002 | |

`use_case(topic)` returns the same recipes with join keys and tips
(`wellbores`, `pvt_and_reservoir_data`, `production_history`, `reserves_and_resources`,
`ownership_and_operators`, `facilities_and_pipelines`, `licences_and_blocks`,
`seismic_and_surveys`, `co2_storage`, `geology`, `seabed_minerals`, `bulk_and_gis`).

## Common Mistakes (read before trusting a number)

1. Scripts get HTTP 403 on `www.sodir.no`; the machine routes are `factmaps.` and `factpages.`.
2. Geometry defaults to ED50 (EPSG:4230): pass `out_sr=4326` for WGS84 distances and maps.
3. Page limit is 2000 rows; the client pages. Filter server-side (`where`, `bbox`, `out_fields`).
4. Dates are epoch ms of local midnight (previous day in UTC): convert with `Europe/Oslo`.
5. Join on `*Npdid*` integers, not names (wells are renamed, fields merge, names differ in case).
6. `*_hst` tables are history: filter valid-to null for the current state.
7. `wlbBottomHoleTemperature = 0` and empty depths mean *not reported*, not zero.
8. Reserves are Sodir's official estimates, versioned (`fldVersion`): take the latest; not company volumes.
9. Pipelines in `pipLine`/layer 6100 are main (TUF) lines, not infield lines.
10. Not open: prospect volumes and equity, seismic and log data (Diskos), well reports, fluid
    compositions. Open data gives priors and screening bounds, never a fluid model: label results
    `screening` and list the missing PVT/data in `data_gaps`.
11. Cite as: `Norwegian Offshore Directorate (Sodir), factpages.sodir.no, NLOD 2.0`, with retrieval date.

## How other skills and agents use this

- Ownership/equity: `neqsim-ncs-ownership-equity`. Hosts, pipelines, plants: `neqsim-ncs-infrastructure-network`.
- Production, reserves and decline: `neqsim-norwegian-continental-shelf-data`, `reservoir-forecasting-agent`.
- Fluid basis when only open data exist: `fluid-characterization-agent` (DST GOR/densities, BHT, depth as priors).
- SURF layout and map data: `neqsim-surf-field-layout-design` (wellbore, field, pipeline layers).
- CO2/CCS: `ccs-hydrogen` (injection history, storage themes).
- When a company workflow exists with governed data (GeoX, PDM, SMDA), use it first; Sodir is the open cross-check.

## Validation Checklist

- [ ] Every number carries its layer id, `*Npdid*` key and retrieval date.
- [ ] Geometry requested with `out_sr=4326`; dates converted from epoch ms (Europe/Oslo).
- [ ] History tables filtered to the current state; latest `fldVersion` used for reserves.
- [ ] Zero-valued temperatures/depths treated as not reported.
- [ ] Results labelled `screening`; missing PVT and non-open data listed in `data_gaps`.
- [ ] Sodir cited as `Norwegian Offshore Directorate (Sodir), factpages.sodir.no, NLOD 2.0`.

`pytest` in this folder runs offline with a fake fetch and verifies that every layer id and join key cited in
the recipes exists in the bundled catalog. A live smoke test is `<python> -m sodir_open_data query field --max-rows 2`.

## Limitations

Metadata only for seismic and logs (data are in Diskos); no prospect volumes or equity; no fluid compositions;
reserves are Sodir's official estimates, not company volumes; the services can change layer ids (refresh the catalog).

## References

- Sodir open data: <https://www.sodir.no/fakta/data-og-analyser/apne-data/>
- DataService REST: <https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer>
- FactPages: <https://factpages.sodir.no>; licence: NLOD 2.0
