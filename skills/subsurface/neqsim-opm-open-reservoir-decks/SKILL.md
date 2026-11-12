---
name: neqsim-opm-open-reservoir-decks
calculation_basis: "screening"
version: "0.1.0"
description: "Open, login-free reservoir benchmark decks from the OPM opm-data repository (Norne full field, SPE1/3/5/9/10 comparative solution projects, Sleipner CO2) with per-case licence, size guard, deck summary and PVTO/PVTG/PVDG/SWOF table extraction. USE WHEN: a NeqSim reservoir, PVT, material-balance or reservoir-to-facility task needs a real published reference case, a black-oil table to compare against a NeqSim fluid, or a realistic well/schedule example that is not company data."
last_verified: "2026-11-12"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["raw.githubusercontent.com", "api.github.com"]
---

# OPM Open Reservoir Decks (Norne, SPE comparative solutions, Sleipner)

The `OPM/opm-data` repository on GitHub holds complete ECLIPSE-format simulation decks that anyone can read
without an account. They are the standard open benchmarks of reservoir simulation: use them as realistic inputs and as
reference tables for NeqSim PVT and reservoir-facing work, instead of inventing a reservoir.

Access verified without login on 2026-11-12: anonymous `GET` on `raw.githubusercontent.com/OPM/opm-data/<ref>/...`
returns the files (HTTP 200); head commit at verification `eaa2261683a97027e057c2bc49612ad1c86390b3`. The Equinor
Volve data set is **not** covered: it is distributed through a Databricks Marketplace listing that needs an account.

## When to Use

- A reservoir, material-balance, depletion or reservoir-to-facility task needs a published, citable reference case.
- You need black-oil tables (Rs, Bo, viscosity, Rv, Bg) or relative permeability to compare with a NeqSim-derived table.
- You want a realistic field deck (wells, VFP tables, history schedule) for a demo, workshop or student exercise.
- Do not use it as a substitute for the licensed field model, a PVT report, or a validation of a specific asset.

## Inputs

A case name (`spe1`, `spe3`, `spe5`, `spe9`, `spe10model1`, `spe10model2`, `norne`, `sleipner`), optionally a deck
file, a pinned git ref (use `resolve_ref()`), and a byte limit for includes.

## Outputs

- `summary(case)`: units, phases, grid dimensions and cell count, start date, wells (including those in schedule
  includes), include list, PVT keywords present, number of schedule records, licence and title.
- `keyword_records(text, "PVTO")` and friends: numeric tokens per `/`-terminated record for table work.
- `provenance()`: URL, ref, SHA-256, size, licence and cache flag per file for `results.json` / `SOURCES.md`.

## Engineering Method

1. Choose the case from the catalog (`case_names()`, `get_case(name)["use_for"]`) and read its **licence** first.
2. Pin the repository head: `client = OpmDataClient(cache_dir=...); sha = client.resolve_ref()`; record `sha`.
3. `client.summary(case)` for grid, wells and keywords; fetch only the includes you need (`get_include`).
4. Extract tables: `keyword_records(text, "PVTO")` (each record starts with Rs, then pressure/Bo/viscosity triples),
   `PVDG`, `PVTG`, `PVTW`, `SWOF`, `SGOF`, `DENSITY`, `ROCK`. Use `to_floats` to expand `n*value` repeats.
5. Convert units from the deck unit system (`FIELD`: psia, STB, ft; `METRIC`: barsa, sm3, m) before comparing.
6. Build the equivalent NeqSim fluid and compare Rs/Bo/Bg/viscosity at the table pressures; report the deviation and
   state that the deck PVT is a simulator input, not a laboratory measurement.

## Case Guide

| Case | Size | Kind | Typical use |
|------|------|------|-------------|
| spe1 | 10x10x3 | black-oil gas injection | smallest end-to-end black-oil check |
| spe3 | see deck | gas condensate (PVTG/PVTO) | condensate yield versus a NeqSim CVD |
| spe5 | see deck | miscible flood | solvent-oil PVT |
| spe9 | 24x25x15 | black-oil waterflood | heterogeneous benchmark, many wells |
| spe10model1 | 100x1x20 | upscaling | small heterogeneity study |
| spe10model2 | 60x220x85 | upscaling | large; includes 58 MB and 19 MB files |
| norne | 46x112x22 | real North Sea field | wells in `INCLUDE/BC0407_HIST01122006.SCH`, VFP, `PVT-WET-GAS.INC` |
| sleipner | see deck | CO2 storage | **different licence**, 34 MB porosity file |

The dimensions of spe1, spe9, spe10model1 and norne are asserted against the live decks in the tests.

## Python Usage Pattern

```python
from opm_open_decks import OpmDataClient, keyword_records, to_floats

client = OpmDataClient(cache_dir=".opm_cache")
sha = client.resolve_ref()                      # pin for reproducibility, record in results.json
info = client.summary("spe1")                   # grid, wells, units, PVT keywords, licence
text = client.get_text("spe3", "SPE3CASE1.DATA")
pvto = keyword_records(text, "PVTO")            # records: [Rs, p, Bo, mu, p, Bo, mu, ...]
rs = float(pvto[0][0])                          # 0.189473 (FIELD units: Mscf/STB)
rows = to_floats(pvto[0])
sources = client.provenance()                   # file URL, sha256, licence for SOURCES.md
```

## Validation Checklist

- [ ] Licence recorded per case; Sleipner terms (no resale, credit the Sleipner Group) honoured if used.
- [ ] Repository ref (commit SHA) and file SHA-256 recorded.
- [ ] Unit system read from the deck (`FIELD` or `METRIC`) and converted before any comparison.
- [ ] `schedule_includes_skipped` empty, or the missing schedule stated as a limitation.
- [ ] Large files fetched only deliberately (`allow_large=True`, raised `max_bytes`).
- [ ] The result is labelled as a benchmark case, not as asset data.

## Common Mistakes

- Reading wells from the main deck only: Norne keeps them in the schedule include.
- Treating `PVTO` records as one row per pressure; each record is one Rs with several pressure points and a lone `/`
  ends the table for a PVT region.
- Mixing `FIELD` and `METRIC` tables, or forgetting that Rs in `FIELD` is Mscf/STB.
- Using the data under the wrong licence: decks are ODbL (share-alike, attribution), Sleipner is not.
- Fetching `master` without pinning, so a later repository change alters the benchmark.
- Calling a simulator deck PVT table a measured PVT result.

## Limitations

- Parser is a keyword/record reader, not a simulator: it ignores `-- comments`, handles repeats and `/`
  terminators, and assumes a keyword stands alone on its line. A data line made of one unquoted upper-case word of
  2-8 characters would be read as a keyword.
- Binary results and restart files are not part of the open repository (reference results were removed).
- GitHub's anonymous API allows about 60 requests per hour per IP; raw file downloads are not subject to that limit.
- The git history contains proprietary decks that were removed; only the current tree is covered here.
- The SPE10 original archive (`https://www.spe.org/web/csp/datasets/set02.htm`, about 19 MB, anonymous) is listed
  in `EXTERNAL` as a pointer only; the page states no licence, so cite SPE CSP and do not redistribute.

## References

- `OPM/opm-data` (README states ODbL 1.0 for decks, DbCL 1.0 for contents, "unless stated otherwise"):
  <https://github.com/OPM/opm-data>
- Odeh (1981) SPE1; Kenyon and Behie (1987) SPE3; Killough and Kossack (1987) SPE5; Killough (1995) SPE9;
  Christie and Blunt (2001) SPE10; Norne benchmark case (NTNU/IPT).
- Sleipner 2019 Benchmark Model: <https://co2datashare.org/dataset/sleipner-2019-benchmark-model>.
- Companion skills: `neqsim-reservoir-model-builder`, `neqsim-reservoir-material-balance`,
  `neqsim-reservoir-depletion-screening`, `neqsim-benchmark-reference-data`.
