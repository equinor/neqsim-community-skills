---
name: neqsim-anp-open-data
calculation_basis: "screening"
version: "0.2.0"
description: "Reads Brazilian ANP open data: bid-round blocks, field and well production, well data bank, GeoANP layers (blocks, fields, wells, gas pipelines), installation positions from wellheads and tie-in host ranking, with CRS, unit and date checks. USE WHEN: a task needs Brazilian block, field or well facts, a host such as a pre-salt FPSO, nearby installations or export lines for a tie-in, or a Sodir-like open-data basis."
last_verified: "2026-10-26"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["ANP open-data portal (optional)", "ANP GeoServer geomaps.anp.gov.br WFS (optional; cached offline)"]
---

# ANP Open Data

Advisory skill. It is the Brazilian counterpart of `neqsim-norwegian-continental-shelf-data` and says what to read, how to trust it and how to hand it on.

## When to Use

- A task needs Brazilian block, field production or well facts for a Santos, Campos or other Brazilian block.
- A host field such as a pre-salt FPSO must be characterised from public data.
- A Sodir-like open-data basis is needed for a Brazilian evaluation.
- Nearby FPSOs, fields, wells or gas export lines must be located on a map, or tie-in hosts ranked for a Brazilian discovery.

## Inputs

- The downloaded ANP file and its documentation (header names, separator, decimal mark, encoding, units).
- A header mapping from the names you need to the names in the file.
- The block or field name and the year range of interest.

## Outputs

- Typed rows with explicit unit conversions (oil and gas volumes, daily rates).
- A CRS check for block coordinates and a distance to the host.
- Source, dataset name and download date for `references/SOURCES.md`.
- Approximate installation positions with spread and water depth, latest and peak daily rates per installation, distances to pipelines, and a ranked tie-in host table.

## What to look for

The ANP open-data page (checked 2026-10-09, `gov.br/anp`, "Dados abertos"; also mirrored on `dados.gov.br`) lists these datasets by name. Names are in Portuguese:

- Bid rounds and blocks: "Rodadas de Licitações de Petróleo e Gás Natural", "Fase de Exploração", "Fase de Desenvolvimento e Produção", "Blocos com Fase Exploratória Encerrada", "Dados Georreferenciados das Bacias Sedimentares Brasileiras".
- Production: "Produção de Petróleo e Gás Natural por Poço", "Produção de petróleo e gás natural por estado e localização".
- Wells and technical data: "Resultado de poço", "Dados de E&P", "Acervo de Dados Técnicos", "Amostras de Rochas e Fluidos".
- Planning and money: "Previsão de Atividades e Investimentos Exploratórios", "Participações Governamentais".

The page also links a data inventory spreadsheet and an annual open-data plan. Header names, separators and units are not listed there: read them from the file and its documentation, and do not rely on a remembered column name.

## Python Usage Pattern

The package `anp_open_data` has no data and no assumptions about headers:

```python
from anp_open_data import load_table, oil_volume, gas_volume, monthly_to_daily, check_crs, haversine_km

rows = load_table(path, {"field": "<header>", "month": "<header>", "oil": "<header>"},
                  sep=";", decimal=",", numeric=["month", "oil"])   # KeyError if a header is renamed
rate_bbl_d = oil_volume(monthly_to_daily(rows[0]["oil"], 2026, 3), "m3", "bbl")
```

Separator, decimal mark, encoding and source units are arguments because they differ between datasets; check them in the file before use.

## GeoANP WFS layers and installation location

ANP publishes map layers on a public GeoServer (`https://geomaps.anp.gov.br/geoserver/ows`, WFS 1.0.0, GeoJSON output, native CRS EPSG:4674 SIRGAS 2000, lon/lat order). `ANP_LAYERS` holds the aliases checked on 2026-10-26:

| Alias | Layer | Content |
| --- | --- | --- |
| `blocks` | `sisroc:block_shp_geoanp` | Contract blocks |
| `awarded_blocks_opc` | `geoanp:blocos_arrematados_opc_4deg_ciclo` | Permanent-offer awards |
| `fields` | `sisroc:campos_gishub_db` | Field outlines (`name`, `operador`, `etapa`, `dat_inicio`, `med_lamina`, `fluido_pri`) |
| `presalt_polygon` | `sisroc:presal_shp_geoanp` | Pre-salt polygon |
| `gas_outflow_pipelines` | `geoanp:gasodutos_de_escoamento` | Gas outflow (export) pipelines |
| `gas_processing_plants` | `geoanp:unidade_de_processamento_de_gas_natural` | Gas processing plants |
| `wells` | `sisroc:pocos_gishub_db` | Wells with coordinates and water depth |

```python
from anp_open_data import fetch_layer, locate_installations, installation_production, name_key

wells, log = fetch_layer("wells", task / "references/anp", bbox=(-44.6, -26.2, -41.8, -24.0),
                         max_features=20000)          # cache + .log.json sidecar; offline=True reuses cache
if log["truncated"]:
    raise RuntimeError("raise max_features or narrow the bbox")
hosts = locate_installations(wells, well_installation_pairs)   # pairs from the production file
rates = installation_production(rows, "installation", "month", ["oil", "condensate"], ["gas"])
```

- **ANP does not publish FPSO hull coordinates.** `locate_installations` takes the median of the wellheads that produce to each installation; the result is labelled `approximate-derived-from-ANP-wells` with `well_spread_max_km`. Report it as approximate and replace it with the operator position where one exists.
- Well-to-installation pairs come from "Produção de Petróleo e Gás Natural por Poço". Its headers are often damaged (U+FFFD); select columns by position after checking a known row, and parse Brazilian numbers (`.` thousands, `,` decimal).
- Names mix accents, mojibake and U+FFFD. Join on `name_key`, which folds them to one key, and use `repair_name` for display.
- Every download writes its URL, time, feature count and `truncated` flag; copy that record into `SOURCES.md`.

## Tie-in host screening

```python
from anp_open_data import nearest_pipeline, rank_tie_in_hosts

lines = nearest_pipeline((lon, lat), pipelines_geojson, top=5)        # km, nearest point, along-line km
ranked = rank_tie_in_hosts((lon, lat), hosts, target_water_depth_m=2200,
                           required_oil_m3d=16000, preferred_operators=["..."])
```

- Score = weighted sum of distance (`1 - d/max_step_out`), oil/gas ullage against the required rate, water-depth similarity, operator preference and remaining host life (`DEFAULT_WEIGHTS`). Unknown ullage or life scores 0.5 and is flagged in `notes`.
- `kind: "standalone"` is the reference case; `kind: "pipeline"` with a `distance_km` from `nearest_pipeline` ranks an export line beside the FPSOs.
- Ullage is not public. Feed operator capacity where known, or `host_capacity_check` from `neqsim-brazil-offshore-infrastructure-market`, and say which basis was used. The ranking is a screening order, not a host decision: hand the top hosts to flow assurance and cost.

## National pipeline and connection-point overview

```python
from anp_open_data import overview
layers = overview.load_cached_layers(cache_dir)     # cached ANP GeoJSON layers (fetch_layer first)
pipes = overview.pipeline_register(layers)          # every pipeline, category, length, offshore flag
nodes = overview.node_register(layers)              # platforms, UPGN, terminals, refineries, LNG
conns = overview.connect_pipelines(pipes, nodes, snap_km=5.0, junction_km=1.0)
summary = overview.summarise(pipes, conns)
overview.write_csv(out_csv, pipes)
overview.plot_overview(ax, layers, pipes, conns, bbox=None, label_nodes=True)
```

- Categories: gas outflow (escoamento), gas transport, oil outflow, oil transfer, oil transport; `offshore` is set when an endpoint is a platform or the line runs seaward of the coast.
- Endpoints within `snap_km` of a node are connected to it; ends of different lines within `junction_km` become junctions; the rest are unnamed endpoints and are listed as gaps, not guessed.
- Typical national read (2026): 656 lines, about 22,200 km, 152 offshore lines (3,790 km), 183 platforms, 36 UPGN.
- ANP publishes trunk and export lines only; no flowlines, risers or umbilicals.

## Bathymetry for SURF and pipeline routing

```python
from anp_open_data import bathymetry as bt
grid = bt.fetch_etopo_grid((-45, -41.5, -28, -24.5), cache_dir, stride=1)  # (min_lon, max_lon, min_lat, max_lat); NOAA ETOPO 1', ERDDAP
depth = bt.depth_at(grid, lat, lon)                                       # note lat, lon; positive metres
prof = bt.profile_along_route(grid, [(lon0, lat0), (lon1, lat1)], step_km=1.0)
flags = bt.flag_slopes(prof)        # length, depth range, max slope, length above 5 and 10 deg
```

- ETOPO is about 1.85 km resolution: route-screening and depth-class data only. Validate against ANP well and platform water depths (Santos pre-salt: mean deviation 1.4 %, max 6 % over 43 points) and report the deviation.
- Slopes are smoothed by the grid; local escarpments, pockmarks and debris flows are invisible. A detailed design needs an MBES route survey.
- Hand profiles to `neqsim-pipe-route-profile` / `flow-assurance` as KP-depth tables, and the field-area relief to `neqsim-subsea-layout-geometry`.

## Engineering Method

- Record the source, dataset name and download date for every number in `references/SOURCES.md`.
- Units: read the unit of every volume column from the file documentation (oil is often in m3 and gas in a thousand-m3 or m3 basis, but confirm); convert explicitly with `oil_volume` and `gas_volume` and state the conversion. Check month versus calendar-year aggregation.
- Coordinates: confirm the CRS and datum of block polygons before computing distance to a host; reproject to a metric CRS first.
- Production history of a host field is public only at the level the portal exposes; ullage and plateau need operator data and belong in a governed layer, not here.
- Keep a small offline anchor table (field, block, year, rate) so a task still runs without network.

## Discoveries and near-field plans

ANP publishes no discovery list, names or volumes, but the layers below let a discovery inventory be
reconstructed (implemented in `neqsim-near-field-discoveries`; use it instead of re-deriving the logic):

| Layer | Use |
| --- | --- |
| `evaluation_plans` (`geoanp:pad`) | Discovery-evaluation plan polygons with start and end dates: a candidate inside a running plan is "in evaluation". The status code `IN_PL_ATIV` is not documented; keep the raw code. |
| `wells` (`sisroc:pocos_gishub_db`) | Exploratory wells with `reclassificacao` (`DESCOBRIDOR`, `PORTADOR`, `PRODUTOR SUBCOMERCIAL`, `SECO ...`); hydrocarbon-bearing wells outside field outlines are discovery candidates. Compare folded text, because accents and encodings are damaged. |
| `fields` (`sisroc:campos_gishub_db`) | `etapa` Produção / Desenvolvimento / Em Devolução gives producing, in-development and relinquished neighbours. |
| `blocks` (`sisroc:block_shp_geoanp`) | `NUM_DESCOB` is the number of notified discoveries in the block. |
| `relinquished_blocks`, `relinquished_fields` | Returned areas: the discovery was not pursued by that licensee. |
| `production_units` (`geoanp:unidade_de_producao`) | Platform and FPSO points with owner, `DESC_ATENDIMENTOS` (fields served) and water depth. |

Volumes of discoveries are not public: take them from the operator, a concession-contract summary or a
press release and record the source. A discovery name (for example one used by an operator) maps to its
discovery well through an alias with that source.

## Validation Checklist

- [ ] Header, separator, decimal mark and encoding were read from the file, not remembered.
- [ ] Every volume column has a stated source unit and an explicit conversion.
- [ ] Block polygons were reprojected to a metric CRS before any distance was computed.
- [ ] Each number has its source, dataset name and download date in `references/SOURCES.md`.
- [ ] An offline anchor table exists so the task runs without network.
- [ ] WFS reads are cached with their log record and none is `truncated`.
- [ ] Derived installation positions are labelled approximate and the ullage basis of every ranked host is stated.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Rates off by a factor of 1000 | Gas or oil unit assumed | Read the unit from the dataset documentation |
| Wrong decimals | Comma decimal parsed as a thousands separator | Pass `decimal=","` and check a known row |
| Distances look wrong | Geographic CRS used for distance | Reproject, or use `haversine_km` on lat/lon |
| Monthly total used as a rate | No days-in-month conversion | Use `monthly_to_daily` |
| FPSO missing from the host list | Name spelled with mojibake or U+FFFD | Join on `name_key` |
| Too few wells or fields on the map | WFS `maxFeatures` reached | Check `truncated`; narrow the bbox |
| Lon and lat swapped | WFS 1.1/2.0 axis order | Use WFS 1.0.0 as built by `build_getfeature_url` |

## Limitations

- Public production history only; ullage, plateau and operator data belong in a governed layer.
- Dataset names and headers change; the skill holds no column map.
- Screening basis, not a reserves or fiscal statement.

## Hand-offs

- Production series to `neqsim-reservoir-depletion-screening` and decline fitting.
- Block and host positions to `neqsim-pipe-route-profile` and `neqsim-subsea-layout-geometry` for tie-back distance.
- Block facts to `neqsim-psc-bid-economics-screening` and the `frontier-block-bid-agent`.
- Installation positions, pipelines and ranked hosts to the `brazil-offshore-infrastructure-agent` and on to `tie-in-screening-agent` / `flow-assurance` for the top hosts.

## References

- ANP open-data portal (`gov.br/anp`, "Dados abertos") and its mirror on `dados.gov.br`; cite dataset name and download date per number.
- ANP GeoServer (`geomaps.anp.gov.br/geoserver`, the WebMaps / GeoANP backend); cite layer name and retrieval time.
