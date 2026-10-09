---
name: neqsim-anp-open-data
calculation_basis: "screening"
version: "0.1.0"
description: "Guide to reading Brazilian ANP open data for evaluation work: bid-round blocks, field and well production, well and seismic data bank, with CRS, unit and date checks and offline anchor handling. USE WHEN: a task needs Brazilian block, field production or well facts for a Santos, Campos or other Brazilian block, a host field such as a pre-salt FPSO, or a Sodir-like open-data basis."
last_verified: "2026-10-09"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["ANP open-data portal (optional)"]
---

# ANP Open Data

Advisory skill. It is the Brazilian counterpart of `neqsim-norwegian-continental-shelf-data` and says what to read, how to trust it and how to hand it on.

## What to look for

The ANP open-data page (checked 2026-10-09, `gov.br/anp`, "Dados abertos"; also mirrored on `dados.gov.br`) lists these datasets by name. Names are in Portuguese:

- Bid rounds and blocks: "Rodadas de Licitações de Petróleo e Gás Natural", "Fase de Exploração", "Fase de Desenvolvimento e Produção", "Blocos com Fase Exploratória Encerrada", "Dados Georreferenciados das Bacias Sedimentares Brasileiras".
- Production: "Produção de Petróleo e Gás Natural por Poço", "Produção de petróleo e gás natural por estado e localização".
- Wells and technical data: "Resultado de poço", "Dados de E&P", "Acervo de Dados Técnicos", "Amostras de Rochas e Fluidos".
- Planning and money: "Previsão de Atividades e Investimentos Exploratórios", "Participações Governamentais".

The page also links a data inventory spreadsheet and an annual open-data plan. Header names, separators and units are not listed there: read them from the file and its documentation, and do not rely on a remembered column name.

## Python helpers

The package `anp_open_data` has no data and no assumptions about headers:

```python
from anp_open_data import load_table, oil_volume, gas_volume, monthly_to_daily, check_crs, haversine_km

rows = load_table(path, {"field": "<header>", "month": "<header>", "oil": "<header>"},
                  sep=";", decimal=",", numeric=["month", "oil"])   # KeyError if a header is renamed
rate_bbl_d = oil_volume(monthly_to_daily(rows[0]["oil"], 2026, 3), "m3", "bbl")
```

Separator, decimal mark, encoding and source units are arguments because they differ between datasets; check them in the file before use.

## Rules

- Record the source, dataset name and download date for every number in `references/SOURCES.md`.
- Units: read the unit of every volume column from the file documentation (oil is often in m3 and gas in a thousand-m3 or m3 basis, but confirm); convert explicitly with `oil_volume` and `gas_volume` and state the conversion. Check month versus calendar-year aggregation.
- Coordinates: confirm the CRS and datum of block polygons before computing distance to a host; reproject to a metric CRS first.
- Production history of a host field is public only at the level the portal exposes; ullage and plateau need operator data and belong in a governed layer, not here.
- Keep a small offline anchor table (field, block, year, rate) so a task still runs without network.

## Hand-offs

- Production series to `neqsim-reservoir-depletion-screening` and decline fitting.
- Block and host positions to `neqsim-pipe-route-profile` and `neqsim-subsea-layout-geometry` for tie-back distance.
- Block facts to `neqsim-psc-bid-economics-screening` and the `frontier-block-bid-agent`.
