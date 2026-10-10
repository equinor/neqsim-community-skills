---
name: neqsim-norwegian-continental-shelf-data
calculation_basis: "screening"
version: "0.4.0"
description: "Public Norwegian Continental Shelf reference facts, carbon-cost basis, Arps decline forecasting and screening analysis. USE WHEN: a task needs offline, source-attributed NCS production, resource, field, carbon-cost/abatement or decline-forecast facts (norskpetroleum.no / Sodir FactPages) to orient a production, resource-accounting, field-inventory, emission-reduction or forecast screening before a validated NeqSim study."
last_verified: "2026-07-13"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Norwegian Continental Shelf Reference Data

Use this skill to load a bundled, source-attributed snapshot of public
Norwegian Continental Shelf (NCS) facts and run screening-level analysis of
production, resources, and the field inventory. The data is sourced from
[norskpetroleum.no](https://www.norskpetroleum.no/en/) (Norwegian Petroleum,
run by the Norwegian Ministry of Energy and the Norwegian Offshore Directorate)
and the Norwegian Offshore Directorate (Sodir, formerly NPD) FactPages, which
publish open, reusable-with-attribution data about NCS activity.

The skill ships a curated **public seed** (headline national KPIs, a resource
accounting split, sea areas, and a qualitative inventory of major fields) plus a
tolerant ingestion path for the official Sodir yearly saleable-production CSV
exports, so a full production time series and per-field figures can be refreshed
without changing any code. All content is public; no proprietary or confidential
data is included. It is a data and screening-analysis skill, not a reservoir
simulator — quantitative production forecasting must use the validated NeqSim
`SimpleReservoir` / `runReservoir` workflows.

## When to Use

- When a task needs quick, offline, source-attributed NCS facts (production,
  resources, exports, field counts) to frame an analysis.
- When building a production, resource-accounting, or field-inventory study of
  the Norwegian shelf and you want a normalized schema plus an ingestion path
  for the official Sodir/norskpetroleum.no tables.
- When an agent needs an upstream "NCS context" feed before a validated NeqSim
  reservoir-depletion, production-routing, or asset-economics screening.
- When a task needs the public Norwegian carbon-cost basis (CO2 Tax Act rates,
  EU ETS allowance cost, NOx Fund contribution) or a first-pass economic
  screening of an emission-abatement measure (power-from-shore, waste-heat
  recovery, compressor upgrade, flaring reduction) before a validated NeqSim
  energy/combustion model and a qualified commercial review.
- When a task needs a screening production forecast: fit an Arps decline
  (exponential/hyperbolic/harmonic) to a produced-rate series and project a
  forward rate profile, remaining volume, and EUR to an economic-limit rate,
  before a validated NeqSim reservoir forecast.

## Inputs

- No inputs are required to load the bundled public seed.
- `NcsDataset.list_fields(...)`: optional filters `sea_area`, `main_product`
  (`oil`/`gas`), `status`, `operator`.
- `NcsDataset.ingest_annual_production(rows)`: iterable of dicts with `year` and
  either `oe_mill_sm3` or component volumes (`oil_mill_sm3`, `gas_bill_sm3`,
  `ngl_mill_sm3_oe`, `condensate_mill_sm3`).
- `NcsDataset.ingest_sodir_production_csv(path)`: local path to a Sodir yearly
  saleable-production CSV export (read locally, no network).
- `NcsDataset.ingest_field_reserves(rows)` / `ingest_sodir_field_reserves_csv(path)`:
  overlay per-field recoverable/remaining/produced oil-equivalent volumes from
  parsed rows or a local Sodir field-reserves CSV export.
- `NcsDataset.ngl_tonne_to_sm3_oe(tonnes)`: NGL mass to o.e. (1 tonne = 1.9 Sm3 o.e.).
- `carbon_cost_basis(year=None)`: public Norwegian carbon-cost rates for a year
  (default: latest known); falls back to the most recent earlier published year.
- `annual_carbon_cost(co2_tonnes_per_year=..., nox_tonnes_per_year=0.0, year=None,
  use_combined_co2_cost=True)`: screening annual carbon cost (NOK/year).
- `abatement_screening(measure=..., fuel_gas_avoided_sm3_per_year=... OR
  co2_avoided_tonnes_per_year=..., capex_nok=..., added_energy_cost_nok_per_year=0.0,
  gas_price_nok_per_sm3=0.0, horizon_years=15, discount_rate=0.08)`: NPV, simple
  payback, and breakeven CO2 price of an emission-reduction measure.
- `combustion_co2_tonnes(fuel_gas_sm3_per_year)` / `emission_source_split(2024)`.
- `fit_arps_decline(series, from_peak=True)`: fit an Arps decline model to a
  `(time, rate)` produced-rate series (best of exponential/hyperbolic/harmonic).
- `forecast_production(fit, economic_limit_rate=..., start_time=None,
  max_years=50.0, timestep_years=1.0, cumulative_to_date=None)`: forward rate
  profile, remaining volume, years-to-limit, and EUR.
- `sodir_download_plan()` / `refresh_instructions()`: offline refresh helper
  (returns official download URLs + ingestion routing; no network access).
- `resource_remaining(total_billion_sm3_oe, produced_fraction, latest_annual_oe_mill_sm3=None)`.
- `production_trend(series)`, `production_share(record)`.

## Outputs

- `national_summary()` / `national_kpi(key)`: headline KPIs, each with value,
  unit, reference year, note, and `source_url`.
- `resource_accounting()`: total resources and produced/remaining fractions.
- `list_fields()`, `find_field()`, `field_counts()`: field inventory queries and
  aggregations by sea area, product, and status.
- Per-field `recoverable_oe_mill_sm3`, `remaining_oe_mill_sm3`, and
  `cumulative_produced_oe_mill_sm3` on each `NcsField` (populated by ingestion),
  with `rank_fields_by_remaining()` and `remaining_reserves_by_area()`.
- `annual_production()` / `production_for_year(year)`: the annual o.e. series
  (seed plus anything ingested).
- `resource_remaining(...)`: produced/remaining volumes, remaining fraction, and
  a static reserves-to-production (R/P) horizon in years.
- `production_share(record)`: oil/gas/NGL/condensate share of total o.e.
- `production_trend(series)`: first-to-last change, CAGR, and rising/falling/flat.
- `fields_started_by_decade(fields)`: field starts grouped by decade.
- `carbon_cost_basis(year)`: a `CarbonCostBasis` with the CO2 tax (per Sm3 gas,
  per litre oil, per tonne CO2), gas-venting tax, EU ETS allowance cost, combined
  effective CO2 cost, NOx Fund rate, and the public gas combustion factor, each
  with `source_url` and attribution.
- `annual_carbon_cost(...)`: a `CarbonCost` with the CO2 tax, EU ETS, combined,
  and NOx components plus the total NOK/year.
- `abatement_screening(...)`: an `AbatementScreening` with avoided carbon cost,
  avoided fuel value, added energy cost, net annual saving, simple payback,
  discounted NPV, breakeven CO2 price, a verdict, and stated assumptions.
- `POWER_FROM_SHORE_FIELDS`, `CO2_SOURCE_SPLIT_2024`, `GAS_CO2_FACTOR_KG_PER_SM3`:
  bundled public context constants.
- `fit_arps_decline(...)`: an `ArpsFit` with the model name, b-exponent, initial
  rate, nominal decline rate (1/year), R-squared, and peak time.
- `forecast_production(...)`: a `ProductionForecast` with the forward `(time,
  rate)` profile, remaining volume, years-to-economic-limit, cumulative-to-date,
  and estimated ultimate recovery (EUR), with stated assumptions.

## Engineering Method

The bundled seed encodes published headline NCS figures (e.g. 129 fields since
1971 with 97 in production at year-end 2025, 239.2 mill Sm3 o.e. produced in
2025 with more than half gas, and total resources of 15.6 billion Sm3 o.e. of
which 56 % has been produced/sold/delivered), each carrying its own reference
year and source URL. Oil-equivalent aggregation uses the standard NCS convention
`1 Sm3 o.e. = 1000 Sm3 gas`, so gas in billion Sm3 equals million Sm3 o.e., with
NGL and condensate taken as already in million Sm3 o.e. Resource remaining is a
simple split of the published total by the produced fraction; the R/P horizon is
a static ratio of remaining volume to the latest annual rate, not a forecast.
Production trend and share are descriptive statistics over the (seeded or
ingested) annual series.

This skill performs no reservoir, PVT, or hydraulic physics. It is a transparent
public data layer and screening calculator that must be paired with validated
NeqSim workflows for any quantitative production or forecasting use.

## Python Usage Pattern

```python
from norwegian_continental_shelf_data import (
    load_dataset, resource_remaining, production_share,
)

ds = load_dataset()
print(ds.attribution)                       # required attribution string
prod = ds.national_kpi("annual_production_oe")
print(prod["value"], prod["unit"], prod["as_of_year"], prod["source_url"])

ra = ds.resource_accounting()
remaining = resource_remaining(
    total_billion_sm3_oe=ra["total_petroleum_resources"]["value"],
    produced_fraction=ra["produced_sold_delivered_fraction"]["value"],
    latest_annual_oe_mill_sm3=prod["value"],
)
print(remaining.remaining_billion_sm3_oe, remaining.reserve_to_production_years)

# Field inventory queries
barents = ds.list_fields(sea_area="barents_sea")
print(ds.field_counts())

# Refresh the full production series from an official Sodir CSV export
# ds.ingest_sodir_production_csv("table_production_saleable_yearly.csv")

# Populate per-field reserves from the official Sodir field-reserves export
# ds.ingest_sodir_field_reserves_csv("field_reserves.csv")
# from norwegian_continental_shelf_data import rank_fields_by_remaining
# top = rank_fields_by_remaining(ds.fields(), top=5)

# Offline refresh plan (URLs + which ingest method to use); no network access
from norwegian_continental_shelf_data import sodir_download_plan
for target in sodir_download_plan():
    print(target.dataset, target.factpages_page_url, target.ingest_with)

# Norwegian carbon-cost basis and an emission-abatement screening
from norwegian_continental_shelf_data import (
    carbon_cost_basis, abatement_screening,
)
basis = carbon_cost_basis(2025)
print(basis.co2_tax_nok_per_tonne_co2, basis.combined_co2_nok_per_tonne)  # 944, 1825

screen = abatement_screening(
    measure="Waste-heat recovery on GT exhaust",
    fuel_gas_avoided_sm3_per_year=20_000_000.0,   # fuel gas no longer burnt
    capex_nok=300_000_000.0,
    gas_price_nok_per_sm3=2.0,
    horizon_years=15,
    discount_rate=0.08,
    year=2025,
)
print(screen.co2_avoided_tonnes_per_year, screen.simple_payback_years,
      screen.npv_nok, screen.verdict)

# Screening production forecast: fit an Arps decline and project forward
from norwegian_continental_shelf_data import (
    fit_arps_decline, forecast_production,
)
series = [(0.0, 100.0), (1.0, 86.0), (2.0, 74.0), (3.0, 63.5), (4.0, 54.6)]
fit = fit_arps_decline(series)                    # exponential/hyperbolic/harmonic
fc = forecast_production(
    fit, economic_limit_rate=10.0, max_years=40.0, cumulative_to_date=500.0,
)
print(fit.model, fit.decline_rate_per_year, fit.r_squared)
print(fc.years_to_limit, fc.remaining_volume, fc.estimated_ultimate_recovery)
```

## Data Refresh

The seed is a snapshot. To load the full, current dataset:

1. Download the official yearly production and field tables from the
   [norskpetroleum.no quick-downloads page](https://www.norskpetroleum.no/en/interactive-map-quick-downloads/quick-downloads/)
   or the [Sodir FactPages](https://factpages.sodir.no/) CSV exports. Use
   `sodir_download_plan()` / `refresh_instructions()` for the entry points and
   the matching ingestion method (offline; it only builds URLs).
2. Ingest with `NcsDataset.ingest_sodir_production_csv(path)` (yearly
   production), `NcsDataset.ingest_sodir_field_reserves_csv(path)` (per-field
   recoverable/remaining reserves), or `NcsDataset.ingest_annual_production(rows)`
   / `ingest_field_reserves(rows)` (parsed rows).
3. Always keep the source attribution and reference year with any reused figure.

## Validated NeqSim Path

This skill supplies public data; it does not forecast production. For
quantitative NCS production analysis use:

- NeqSim `SimpleReservoir` (`neqsim.process.processTools.simplereservoir`) with
  gas/oil/water producers and a `runTransient(deltat)` time loop, and the NeqSim
  MCP `runReservoir` tool for reservoir-versus-time behaviour.
- The community `reservoir-depletion-screening` and `production-network-routing`
  skills for a screening reservoir/production chain seeded with these facts.
- The community `asset-value-npv-screening` and `energy-emissions-screening`
  skills to turn a production profile into value and emissions screening.

## Validation Checklist

- [ ] Reused figures carry the source attribution and reference year.
- [ ] Only public data is used (no proprietary or confidential sources).
- [ ] Field operator/status are treated as a snapshot and re-verified against
      Sodir FactPages before quantitative use.
- [ ] Full production series is ingested from official exports for any analysis
      beyond the headline seed.
- [ ] Quantitative production/forecasting is escalated to validated NeqSim models.
- [ ] Carbon-cost rates (CO2 tax, EU ETS, NOx Fund) are re-verified against the
      norskpetroleum.no "Emissions to air" page for the current year before use.
- [ ] Abatement screening is treated as indicative only and escalated to a
      validated NeqSim energy/combustion model and a commercial review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Stale numbers | Using only the bundled seed | Ingest current Sodir/norskpetroleum.no tables |
| Wrong o.e. total | Mixing gas units | Gas in billion Sm3 equals million Sm3 o.e.; keep units consistent |
| Over-reading a field record | Treating operator/status as current truth | Re-verify per-field data against FactPages |
| Forecasting from R/P | Reading the static R/P ratio as a forecast | Use NeqSim `SimpleReservoir` / `runReservoir` |
| Undrilled licence or prospect has no data | Looking in the field tables | Read the neighbourhood from the Sodir FactMaps FeatureServer (below) |

### Fresh discovery pair and its host profile (verified 2026-10-10, PL1140 Lofn / Langemann)

- Discoveries named `15/5-8 S (Lofn)` and `15/5-8 A (Langemann)` are in `discovery_reserves` (layer 7008, join on `dscNpdidDiscovery`, status `Production not evaluated`, RC `7F`); `wellbore_coordinates` (FactPages CSV table) gives their position (decimal degrees `wlbNsDecDeg`, `wlbEwDecDeg`), TD and age at TD. `licence_licensee_hst`, `licence_phase_hst` and `discovery` CSV tables return HTML (not served) - use the licence layer 3000 for dates and take partners from the brief.
- Centuries Forecast 2027 holds them as project `Lofn & Langemann` (RC5) under field names `15/5-8 S (Lofn)` / `15/5-8 A (Langemann)` and facility `GINA KROG`; the Centuries gas and liquid are a fraction of the Sodir recoverable (43 % and 23 % at Lofn / Langemann), so quote both.
- Host capacity for a screening ullage = Sodir peak annual gas throughput (`field_production_yearly`, max of `prfPrdGasNetBillSm3` x 1000 / 365), host end = last Centuries year with gas above 0.02 MSm3/d; a host's Centuries profile can end before a neighbouring project that is planned to use it (Gina Krog 2036 vs Lofn & Langemann 2038): flag that as a life-extension question.

### Neighbourhood of an undrilled licence (verified 2026-10-09, PL1252)

Base `https://factmaps.sodir.no/api/rest/services/Factmaps/FactMapsWGS84/FeatureServer/<layer>/query`
with `f=json&outSR=4326&returnGeometry=true` and an envelope (`geometry`, `geometryType=esriGeometryEnvelope`,
`spatialRel=esriSpatialRelIntersects`). Layers: 616 licence (filter `prlName='1252'`, TFO licences use the bare number),
304 facilities in place, 311 pipelines, 503 discoveries, 502 fields, 204 exploration wellbores, 201 all wellbores;
tables: 532 discovery reserves (join on `dscNpdidDiscovery`), 515 field reserves, 651 licence phases, 652 licence tasks.
Facility geometry is a point (`x`,`y`), discoveries and fields are polygons: take the minimum vertex distance, not a centroid.
Useful reads: distance to candidate hosts, analogue discoveries with recoverable volumes, wildcat hit rate (biased by
infrastructure-led exploration), the status mix of nearby discoveries (platform-drilled sub-discoveries "included in other discovery"
versus stand-alone "production unlikely"), and ERD precedent as `sqrt(wlbTotalDepth^2 - wlbFinalVerticalDepth^2)` for wells
drilled from a candidate host (layer 201 filtered on the platform well-name prefix).

### Undrilled prospect in a named reservoir formation (verified 2026-10-10, Linnorm Lange)

Analogues and temperature for a prospect with no prospect data come from layer 201/204 wellbores and layer 503/502 discoveries and fields:

- **Formation filter:** use equality, never LIKE: `wlbFormationWithHc1='LANGE FM' OR wlbFormationWithHc2='LANGE FM' OR wlbFormationWithHc3='LANGE FM'`. A `LIKE '%LANGE%'` query returns an empty response from this service.
- **Analogue volumes:** join the hosting discoveries/fields to table 532/515 recoverable volumes (gas in GSm3 = MSm3 o.e. equivalent, oil/condensate in MSm3); fit a lognormal to the nonzero values (8 Lange analogues: P90/P50/P10 2.1 / 6.3 / 18.9 MSm3 o.e.). State the survivor bias: analogues are discoveries.
- **Geotherm:** regress `wlbBottomHoleTemperature` on `wlbFinalVerticalDepth` (Norwegian Sea n=279: 34.2 K/km); leave out the neighbour wells, test the fit against them, and add a declared anomaly where they are warmer (Linnorm/Onyx +3 to +12 K). BHT is a drilling temperature, so it is a lower bound of formation temperature.
- **Pore pressure:** Sodir has no formation pressure for an undrilled prospect; declare an EMW range (1.30-1.85 sg) and show the HPHT probability (P > 690 bara and T > 150 C) explicitly.
- **Other tables:** formation tops, DST and well history are separate tables (layers for `wlbFormationTops`, `wlbDST`, `wlbHistory`), not columns of the wellbore layer.

### Producing licence with unnamed opportunities (verified 2026-10-09, PL190 Tune)

When the brief names opportunities that are not in Sodir (no wellbore, discovery or facility with the name), say so
and value them from the neighbourhood instead of searching further:

- Licence layer 616 uses the bare number (`prlName='190'`); its polygon can be a long strip, so draw a prior
  location uniformly over the polygon and report the distance distribution to each candidate node, not one number.
- Ownership: `OwnershipReader().licence("190")` and `.field("TUNE")` (name without `PL`).
- A field with `fldRemainingOE` near zero in layer 515 (Tune: 0.05 of 23.0 MSm3 OE) has an idle template and export
  route: the first tie-in candidate. Cross-check with the Centuries base profile of the field.
- The Sodir pipeline layer (311) holds trunklines only; infield lines are not there, so existing-route lengths are
  straight-line estimates to be confirmed by subsea integrity.
- Step-out precedent by drilling facility: layer 205 (development wellbores) in an envelope, group on
  `wlbDrillingFacility`, take the upper bound `sqrt(MD^2 - TVD^2)`; rig names and platform names are mixed in that column,
  so quote the best well name (template wells reached 5.4-6.4 km, Oseberg platforms 8.0-9.6 km).
- A wildcat just completed in the licence (`wlbCompletionYear` = current year, `wlbContent` empty, P&A) has no public result
  yet: record it as an evidence gap and as an update to Pg, never infer the outcome.
- Centuries may hold an RC5 project of the same field (Tune: "Tune Statfjord", TLI 0.35 to 0.5, first production 2034). Use
  it as a volume and profile-shape anchor, and do not map it to a named opportunity without confirmation.

### Producing licence with a platform host (verified 2026-10-09, PL193 Kvitebjorn)

When the unnamed opportunity sits in a licence whose own field has a fixed platform:

- The licence layer gives the strip geometry and the platform jacket is in layer 304; draw the prior location over the part of the
  licence on the side named in the brief (e.g. north of the platform for 'Nord') and report the share within extended-reach distance
  (here 60 % within 6 km), because a platform well is then the base concept and subsea only the fallback.
- The field and its licence have the same partners and no host tariff: charge only downstream transport and variable cost.
  Partners come from OwnershipReader().field("<NAME>") (names with special characters work, e.g. `KVITEBJØRN`).
- Host capacity proxy: the 30-day peak of the field's PDM export streams (<FIELD>-PROD_<FIELD>-G and -C in NET_VOL);
  the Centuries base profile of an old field ends well before its cut-off year, so read both and show the tail.
- Pressure state of the target (connected to the depleted main tank or an isolated compartment) changes well rate by a factor of
  four and the subsea break-even volume by a factor of two; make it a discrete uncertainty, not a fluid case.
- Check the Centuries projects of the field (IOR infill, pressure-reduction, other tie-ins with the field as host) for overlap
  with the opportunity before valuing it.

### Producing field with a subsea template and a stand-alone tie-back candidate (verified 2026-10-09, Sleipner Ost / Loke Ty)

- The DataService MapServer (`https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer/<id>/query`) is the easier
  entry for lists: facilities 6000, pipelines 6100, discoveries 7000, fields 7100 (tables 7113 and 7008). Facility attributes give
  start-up year, design life, water depth and slot count, so the age of a reused template at first gas is computed, not assumed.
  The subsea template itself is often not named in the facility layer: match it by distance to the host and the slot count, and say
  that it is an assumption.
- Yearly production: the factpages table view `field_production_yearly` as CSV works (all fields; filter the host fields),
  while the norskpetroleum.no `csv.php` export answered HTTP 500. Field names arrive with an encoding artefact for Oe/Ae/Aa
  (for example `SLEIPNER ╪ST`); decode as UTF-8 and compare diacritic-folded.
- Host throughput history is the cheapest way to show that gas volume is not the constraint for a small tie-back: Sleipner-hosted
  fields went from 15.2 GSm3/yr (2005) to 4.5 (2025). Show the load of every concept in the same year with success-case area volumes.
- Never turn an unnamed brief item (here 'Hod') into a Sodir field of the same name; the Sodir field 'Hod' is an oil field in another
  area. Record it as a data gap.

### Exploration prospect in a named licence (verified 2026-10-09, Abel PL1204 / Utsira North)

- A prospect has no public volume or coordinates. Position proxy = centroid of the licence polygon (`licence` layer 3000 with
  `returnGeometry=true`, `where=prlName like '%1204%'`; keep `prlStatus='ACTIVE'`); the licence rows also give grant date and
  `prlDateValidTo`/initial-period expiry, i.e. the drill-or-drop date. Sodir lists one row per licensee, so partners are not complete.
- The Sodir WAF answers `Request Rejected` (HTTP 200, HTML) to POST queries and to long `OR` chains of `like` clauses: use GET, one
  `where` per block or licence, and retry. Wellbore layer 5000 gives total depth, bottom-hole temperature and discovery per wellbore
  (HPHT context without pressure data); filter with `wlbWell like '25/7-%'`.
- Neighbour resources: join discovery reserves (layer 7008) to discoveries (layer 7000) on `dscNpdidDiscovery` and field reserves
  (7113) to fields (7100) on `fldNpdidField`; the reserves table repeats a field per reporting date, so take the latest row. The oil/gas
  ratio of the recoverable volumes gives an analogue GOR bracket (Busta 864, Norma 3610 Sm3/Sm3) for a fluid when no PVT exists.
- Run a nearest-infrastructure screen (haversine from the prospect to all in-service facilities, plus pipeline chord distance) before
  accepting the hosts named in a brief: here Alvheim (14 km), Heimdal gas pipelines (3 km) and Grane (39 km) were closer than every
  host named, which were 60-125 km away. Name the extra hosts and flag third-party ownership.
- Prospect with no public data next to an ageing satellite (Aurelius, south of Sigyn, 2026-10-10): wellbore label and brief can
  disagree (16/10-4 is `DRY` in layer 5000 while the brief reports residual oil and a gas cloud) - quote both and use the brief for
  the fluid, Sodir for depth, temperature and position; query wellbores by GET with one `wlbWellboreName like '16/10-%'` per block;
  the APA licence layer returns no rows for awards that are not yet published, so record the licence number and drill-or-drop
  date as a data gap instead of guessing. When the host is a depleting satellite whose Centuries plan ends before first production
  plus plateau (Sigyn ends 2039, tie-back production 2033-2044), add an explicit life-extension cost and an NPV "no extension"
  comparison, and size the existing lines from the host's own flow (Sigyn 0.3 MSm3/d in Centuries, 0.06 in Sodir 2025) - the lines
  are then almost empty and the value of a "released" line is small compared with the extension cost.

### Discovery maturing to a project basis with an area host (verified 2026-10-09, Fogelberg / Asgard)

- Discovery layer 7000 gives name, wellbore (here 6506/9-2 S) and operator; discovery reserves (7008, latest reporting date) give recoverable
  gas, oil and NGL and the resource class (RC7F). Positions come from the wellbore layer 5000, host and template positions from the facility
  layer 6000: a haversine screen gives 9.5 km to the nearest template and 17.3 km to the host semi-submersible, times about 1.15 for a route.
- Licence layer 3000: query with an equality filter (`prlName='1227'`); `like` returned `Request Rejected`. The licensee table (partners, equity %,
  operator) is the factpages CSV table view, not a layer. The licence rows give the initial-period end and `prlDateValidTo`, i.e. the decision window
  that sets the VPbo schedule.
- Centuries holds the same discovery under two forecast cycles with different resource classes and first-gas years (FC2026 RC7 first gas 2030,
  FC2027 RC5 first gas 2031) and a changed NGL split (here -21 % NGL, +7 % dry gas): compare against Sodir before using either as base.
  Host profiles (the declining host fields at the receiving platform) are the cheap test of whether gas volume constrains the tie-in.

### Prospect licence with partners, hosts of another operator (verified 2026-10-10, Trollebotsnova PL1247)

- Licensee shares and operator of a licence: FactPages CSV tables `licence_licensee_hst` (columns `prlName`, `cmpLongName`, `prlLicenseeInterest`,
  `prlLicenseeDateValidTo`; current = empty valid-to) and `licence_oper_hst`; layer 3010 returns licence TASKS per company (decision to drill,
  BoK, BoV, PDO dates), not shares. Host-field ownership: `field_licensee_hst` (`fldName`, `fldCompanyShare`, current = empty valid-to).
  PL1247 = Aker BP 60 % operator, Equinor 40 %: the licence operator is also the operator of Edvard Grieg and Ivar Aasen.
- Centuries holds only Equinor-operated or Equinor-partnered fields: Edvard Grieg and Solveig return no records and the `find_fields` call ignores
  its filter and returns all 349 fields (filter locally). For such hosts build a Sodir proxy: fit the decline of `field_production_yearly` for the
  last three full years (2026 is a partial year) and bracket it with a reserve-tail decline that exhausts `fldRemaining*`; capacity = 1.1 x the
  historic peak, flagged as a proxy.
- The discovery layer 7000 returns geometry only with `outFields=*`; use it to list the analogue discoveries within 30 km of a licence centroid
  (here Brokk-Mju, Sigrun, Apollo, Gudrun, Ivar Aasen) before choosing the fluid cases.
- A brief label such as "Sleipner area" can be a region, not a distance: the licence centroid was 59 km from Sleipner A but 11-17 km from three other
  hosts. Run the haversine screen to all in-service facilities before accepting the hosts named in the brief.

### Several partner-operated licences at once (verified 2026-10-10, five Greater Horda licences)

- Licence names in a brief (Hesje/Staur, Lindstrom, Viva, Robin) are Equinor internal labels: Sodir publishes the PL number only, and a name
  search over wellbores, discoveries and fields returns nothing (only Litjklakken matches a discovery, 25/1-9). Say so explicitly. A name with
  a letter suffix is stored with a space (`1183 S`); use an equality filter on `prlName`.
- Survey layer 420 `surveyTypeMain` is in Norwegian ("Ordinaer seismisk undersokelse", "Havbunnseismisk ..."): a filter on `SEISMIC` finds
  nothing. Use `"seismisk" in type.lower()` with `surveyTypePart == "3D"`; names are also stored without the o-slash in ASCII folds (Gjoa, Byrding).
- Tasks of the licence (layer 652) give the decision-to-drill (DOD) dates; the five licences here fall within 31 days (2027-02-17 to 2027-03-20),
  which is a scheduling finding in itself. The initial-extended phase (PL1151, PL1144) means the earlier work programme is complete.
- The hit rate of all Sodir wildcats near a licence (0.5-0.7 here) counts sub-commercial finds; use it as an upper bound for Pg of a
  commercial-size discovery, not as Pg.

- Neighbourhood gotchas (verified 2026-10-10, four Greater Tampen licences): an internal label such as "Valemon Sor" can match only the neighbouring
  field and its discoveries (Valemon, Valemon Nord, Valemon Vest), whose polygons touch the licence edge (0.0-0.2 km); report that as "name not found
  as such". A wildcat with status DRILLING in the wells layer (here 34/10-56 S, 2.2 km from the edge, operator Equinor) has no content, year or
  discovery: list it as a pending data point, not as a hit or a dry hole. When no wildcat lies within 30 km the hit rate is undefined (`None`), widen to
  45 or 60 km and say which radius was used. The block list of a multi-polygon licence can include blocks far from the main area (PL1263 lists 6201/9 to
  34/1); use the polygon area, not the block list, for distances. Ownership `stakes` carry `is_operator`; Equinor's share of the licence and of the host
  field are different numbers and both are needed for the net value.

### Undrilled satellite next to a producing subsea cluster (verified 2026-10-10, Drage / Hanz / Symra / Ivar Aasen)

- A prospect is not in `discoveries` (7000) or `fields` (7100) and not in Centuries; take position and volume from the brief and state the position as
  assumed. The facility layer 6000 returns `geometry.x` as the string `NaN` for some rows: coerce with `float()` in a `try`, and look up templates by the
  name prefix (`25/10-C-1 H`), the field name is appended in the label. Small subsea tie-backs (Hanz, Symra) are absent from the pipeline layer 6100.
- The analogue named in a brief may sit in another reservoir: Hanz is Intra-Draupne / Hugin sand in the wellbore `wlbFormationWithHc*` fields, while the
  Heimdal analogues are Symra, Verdandi, Apollo and Lillefix. Check this before using the analogue for relative permeability or recovery.
- `field_production_monthly` (factpages table view, same URL pattern as `field_production_yearly`) gives a monthly series from start-up: Hanz went from
  11 % to 65 % water cut and GOR 130 to 950 in 16 months; this is the cheapest back-test for coning parameters. Negative monthly oil values occur
  (allocation corrections): filter `> 0.003 MSm3`.
- `field_reserves` (7113) holds one row per annual estimate: sort by `fldDateOffResEstDisplay` and take the last (Hanz recoverable oil 2.5 to 0.4 MSm3
  in the 2025 revision); a dictionary keyed by field name silently keeps an arbitrary row.
- Centuries host plan: `discover_forecast_dimensions(forecast_name, field_name, facility_name)` for `IVAR AASEN` with facility `IVAR AASEN` also returns the
  `Backout from Hanz` and `Deferral IA` projects; use the Reserves classes as planned throughput and the sum of IA, Hanz and Symra as the host load. The
  plan water (13.2 kSm3/d) exceeded the Sodir demonstrated water (10 kSm3/d), so a host capacity proxy must be at least the plan peak.

### Gas-condensate prospect next to an ageing host (verified 2026-10-10, Lambda Hugin PL1200S / Sleipner A)

- Licence gates are public: the licence-task table (factpages layer 652; FactMaps `MapServer/3010` with `prlName like '%1200%'` also returned it) lists
  `prlTaskTypeEn` / `prlTaskExpiryDate` for `Drill exploration well`, `(BoK) Decision to concretize`, `(BoV) Decision to continue`, `(PDO) Submit plan for
  development` and `Decision to enter extension period` (epoch ms): PL1200S had BoK 2028-03-15, BoV 2030-03-15 and PDO 2031-03-15 = licence end. Use them as
  the hard decision-gate dates of a success plan instead of generic DG1-DG3 timings. The licence layer (3000) matched `like '%1200%'` but not `like 'PL1200%'`.
- A cheap fluid benchmark exists next door: recoverable (NGL + condensate) / gas from `field_reserves` of the neighbouring Hugin field (Sleipner Vest
  292.6 Sm3/MSm3) matched the brief CGR 295 within 1 %; use it before assuming a PVT. Wellbore layer 5000 rejects a long `or` list of `like` terms
  ("Request Rejected"): one query per block prefix.
- Host life is a Centuries question, not a Sodir one: `SLEIPNER VEST` Forecast 2027 has Base profile 2026-2034 (6.7 GSm3), contingent `Low pressure SLT` (RC4,
  2028-2039) and `Low pressure phase 2` (RC4, 2030-2039), while the Sleipner A complex plan runs to 2045; a late first gas (2032-33) is exposed to which
  of these windows is real. The A-complex Centuries throughput (2.9 MSm3/d in 2027) is much lower than the Sodir 2025 throughput of the same fields (9.6 MSm3/d).
- NeqSim `ConstantVolumeDepletion` returns relative volume, Z and liquid dropout but not produced-stream standard volumes: for recoverable condensate vs
  abandonment pressure loop `TPflash`, remove the excess gas (`addComponent(i, -n x_i)`), flash the removed composition at 15 C / 1.01325 bara and sum
  gas and condensate. A brief that gives gas RF 65 % and condensate RF 57 % for a lean condensate (CGR 338) is not reproduced: depletion gives 47 % at
  gas RF 67 %.

### Prospect with a neighbouring discovery and a sibling tie-back (verified 2026-10-10, Pedalo North / Loke Ty / Sleipner A)

- Sodir has no prospect objects: a prospect name (Pedalo) returns nothing in the discovery, field or wellbore layers, while the similarly named `Loke` is
  discovery 15/9-17, "included in other discovery", 9 km north of Sleipner A. State this in the data gaps; equity, Pg and licence dates of a prospect are
  not public. FactMaps accepts GET only; POST is rejected by the WAF.
- A synergy with a sibling tie-back must be tested after tax (a pre-tax saving is worth about 22 % after the 78 % shield) and as a scenario matrix against
  two own lines (S0 own lines, joint start, accelerated start), reporting the delta with P(positive) from common random numbers. The sign follows the
  geometry: report the break-even direct-line length (14.7 km for a 12 in spur) instead of a yes/no.
- A shared trunk is limited by API RP 14E erosion, not by pressure: add both producers at peak and check v/ve before sizing the spur.
- Brief EMV vs success NPV: back-calculate the implied Pg of a stated EMV under three NPV bases (brief, model mean case, Monte Carlo mean); the Monte Carlo
  mean is well below the mean case when host-life and connectivity risk are included.
- NeqSim `hydrateFormationTemperature` can throw `IsNaNException` for a rich gas condensate with MEG: retry with a different start temperature.

### Stranded infill targets on an old host (verified 2026-10-10, Sleipner A, My 2 / Gungne infill)

- A brief that quotes a target as "0,7 MSm3/d o.e" can mean a VOLUME in MSm3 o.e.: Centuries Forecast 2027 holds the same targets as RC7 projects
  `My2 well` (field `SLEIPNER ØST`: 0.424 GSm3 rich gas, 2032-35, oilEquivalents 0.76 MSm3) and `Gungne infill` (field `GUNGNE`: 0.481 GSm3, 0.81 MSm3 o.e.);
  as rates the brief would be 2.4-3.6 times the Centuries gas. Read `oilEquivalents` (Sm3 o.e.) and `richGasProductionRate` before asserting a unit, and
  list the sibling RC7 projects of the same host (`Hod` 1.3 GSm3, `Ty reopen with coil tubing drilling`, `Loke Ty additional`) - they share the same stranded rig
  and are the portfolio upside of any rig decision.
- Centuries project rows are per field and facility: `discover_forecast_dimensions(forecast_name="Forecast 2027", field_name="GUNGNE")` lists every project with
  `metadata.resourceClass` / `resourceSubClassCode` and `equity` (Equinor 59.6 % Sleipner Øst, 62.0 % Gungne); filter `corporateEquity == "Field100Percent"` and `unitSet == "Metric"`.
- Calibrate a tank/IPR model to the Centuries yearly gas of the project (fit the productivity multiplier and the in-place gas together) and show the model-versus-Centuries
  table; deliverability-limited abandonment pressure makes the in-place gas 50 % larger than recoverable / (p/z recovery to 45 bara).
- Sleipner A platform wells to Gungne are extended-reach (15/9-A-2 8561 m, A-3 7743 m, A-19 A 7209 m, A-14 A 9661 m MD; Gungne wells 7-9 km from the platform); a
  Lambda-type subsea template 6 km away from the target is not closer than the platform, so test the synergy by distance before assuming one.
- Rig dependency: a platform rig that is needed for PP&A anyway turns the rig cost into a timing penalty (PV of the rig now versus at the PP&A date plus care and
  maintenance); report the break-even share of the rig cost that PP&A would otherwise carry (here 89 % versus coiled-tubing drilling, after depreciating the avoided PP&A rig cost with the same tax treatment as the rig capex; without that symmetry the break-even is wrongly low) instead of one NPV.
- The methane hydrate literature check is 6.5 / 12.4 / 15.6 C at 50 / 100 / 150 bara (NeqSim CPA 6.4 / 12.8 / 16.1 C); do not use 17 C at 100 bara (that is a rich-gas value).

## Limitations

- Educational public data layer and screening calculator only; not a validated
  design or forecasting method.
- The bundled seed is a curated headline snapshot; per-field production/reserves
  and the full annual series require ingesting official exports.
- No reservoir, PVT, hydraulic, or economic physics is performed.
- No confidential or proprietary data is included; attribution to
  norskpetroleum.no / the Norwegian Offshore Directorate is required for reuse.
- The carbon-cost basis carries a small set of published annual rates; the
  abatement screening is a transparent single-measure cash-flow calculation, not
  a certified emission inventory, a marginal-abatement-cost curve, or a validated
  energy model. It does not replace, and human review is required before, any
  investment or emission-reduction decision.
- The Arps decline forecast is a transparent empirical curve fit to a produced
  -rate series; it is not a reservoir simulator or a material-balance model and
  does not capture drive mechanism, aquifer, or infill effects. Use validated
  NeqSim `SimpleReservoir` / `runReservoir` for quantitative forecasting.

## Related NeqSim Functionality

This skill supplies and renders public data; it feeds downstream NeqSim
workflows rather than running calculations itself:

- NeqSim Java: `neqsim.process.processTools.simplereservoir.SimpleReservoir`
  (`runTransient`) for reservoir-versus-time production, and
  `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` for flowline/riser
  hydraulics downstream of the reservoir.
- NeqSim MCP tools: `runReservoir`, `runPipeline`, `runProcess`,
  `runFieldEconomics`.
- Reached from Python via `from neqsim import jneqsim` (or the devtools setup).
- Community companions: `reservoir-depletion-screening`,
  `production-network-routing`, `asset-value-npv-screening`,
  `energy-emissions-screening`.
- Whole-shelf system questions (which fields share which pipelines, plants and
  terminals; bottlenecks; outages; shelf-wide optimisation) go to
  `neqsim-ncs-infrastructure-network` and `neqsim-ncs-value-chain-optimization`.
  The optimiser reuses this skill's `fit_arps_decline` for its field forecasts.

## References

- Norwegian Petroleum (facts about Norwegian petroleum activities): https://www.norskpetroleum.no/en/
- Norwegian Petroleum — Fields: https://www.norskpetroleum.no/en/facts/field/
- Norwegian Petroleum — Historical production: https://www.norskpetroleum.no/en/facts/historical-production/
- Norwegian Petroleum — Petroleum resources: https://www.norskpetroleum.no/en/petroleum-resources/
- Norwegian Petroleum — Quick downloads: https://www.norskpetroleum.no/en/interactive-map-quick-downloads/quick-downloads/
- Norwegian Petroleum — Emissions to air (CO2 tax, EU ETS, NOx Fund, power from shore): https://www.norskpetroleum.no/en/environment-and-technology/emissions-to-air/
- Norwegian Offshore Directorate — Resource accounts: https://www.sodir.no/en/facts/resource-accounts/
- Norwegian Offshore Directorate FactPages: https://factpages.sodir.no/
- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
