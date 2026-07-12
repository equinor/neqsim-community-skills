# Norwegian Continental Shelf Reference Data

Educational, dependency-free, offline database of public Norwegian Continental
Shelf (NCS) facts — headline national KPIs, a resource-accounting split, sea
areas, and a qualitative inventory of major fields — plus screening-analysis
helpers for production and resource studies.

Data is sourced from [norskpetroleum.no](https://www.norskpetroleum.no/en/)
(Norwegian Petroleum, run by the Norwegian Ministry of Energy and the Norwegian
Offshore Directorate) and the Sodir FactPages, which publish open,
reusable-with-attribution data. The bundled data is a public *seed*; the full
production time series and per-field figures are refreshed by ingesting the
official Sodir/norskpetroleum.no CSV exports. See `SKILL.md` for the method,
the ingestion path, and the validated NeqSim workflows this data feeds.

## Quick Start

```bash
cd skills/field-development/norwegian-continental-shelf-data
python -m pytest          # run tests from inside the skill folder
python examples/basic_ncs_data.py
```

## Layout

- `src/norwegian_continental_shelf_data/dataset.py` — loader, queries, ingestion.
- `src/norwegian_continental_shelf_data/analysis.py` — screening analysis helpers.
- `src/norwegian_continental_shelf_data/data/ncs_reference.json` — public seed.
- `examples/basic_ncs_data.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## Attribution

Source: Norwegian Petroleum (www.norskpetroleum.no), Norwegian Ministry of
Energy and Norwegian Offshore Directorate. Reused figures must keep this
attribution and a link to www.norskpetroleum.no.

## License

Apache-2.0 (skill code). NCS facts are open data reusable with attribution.
