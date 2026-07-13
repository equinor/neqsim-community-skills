---
name: neqsim-norwegian-continental-shelf-data
version: "0.4.0"
description: "Public Norwegian Continental Shelf (NCS) reference-facts database, carbon-cost basis, decline-curve forecasting, and screening analysis. USE WHEN: a task needs offline, source-attributed NCS production, resource, field, carbon-cost/emission-abatement, or Arps decline-forecast facts (from norskpetroleum.no / Norwegian Offshore Directorate FactPages) to orient a production, resource-accounting, field-inventory, emission-reduction, or production-forecast screening before a validated NeqSim reservoir/process study."
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
