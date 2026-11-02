---
name: neqsim-anp-well-production-history
calculation_basis: "screening"
version: "0.1.0"
description: "Reads Brazilian ANP well-level production open data into unit-explicit series: merges onshore, offshore and pre-salt files without double counting, builds well/field histories with GOR and water cut, checks data features, prepares decline-fit input and a declared fluid basis. USE WHEN: a task needs production history of Brazilian wells or fields, decline or GOR analysis, a fluid basis from public data, or what public data can support for an MBAL or well-flow model."
last_verified: "2026-11-02"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["ANP open-data pages gov.br/anp (optional; cached offline)"]
---

# ANP Well Production History

Turns the public ANP well-level production files into clean, unit-explicit series that NeqSim workflows can use for decline analysis, GOR and water-cut trends, field aggregation and a declared fluid basis. It reads files and says what they can support; it does not forecast and it does not claim a calibrated model. The map layers, installation positions and tie-in ranking are in `neqsim-anp-open-data`; this skill is the production-history counterpart.

## When to Use

- Real production history of a Brazilian well, field, installation or basin is needed as a worked example, a benchmark or a model input.
- A decline, GOR or water-cut trend is needed from public data.
- A fluid basis (API gravity, separator gas composition, GOR) is needed for a Brazilian field without a PVT report.
- Someone asks whether the public data are enough for a material balance or a well-flow (VFP) model.

## Inputs

- The ANP file(s), downloaded into the task folder (`download` writes the URL, time and SHA-256 next to each file). Never build a URL from a pattern: take links from the ANP page with `extract_links`.
- The family: it is detected from the header (`detect_schema`).
- A well, field, installation or basin to select; a reference date for the publication-lag check.

## Outputs

- Records with rates in m3/d (liquid, water) and thousand m3/d (gas), `period` (`YYYY-MM`), days in month and hours on stream where the file has them.
- Well, field, installation or national series with GOR (sm3/sm3 and scf/bbl), water cut and well count.
- Completeness, publication-lag, per-well data flags and file reconciliation results.
- `(year, rate)` input for `fit_arps_decline` and a `fluid_basis` hand-off with warnings.

## The four file families (checked 2026-11-02)

| Family | Content | Units and format |
| --- | --- | --- |
| `well_monthly_rates` ("Produção por Poço", zips with `Mar`, `PreSal`, `Terra` CSV) | Per well and month: oil, condensate, water, gas, hours on stream, installation, **API gravity, gas composition C1-C11/N2/CO2/O2, gross calorific value** | `;` CSV, cp1252, decimal comma; oil and water in **bbl/dia**, gas in **Mm3/dia = thousand m3/d** |
| `well_monthly_volumes` ("Produção de petróleo e gás natural nacional") | Per well and month volumes and **injection** (gas, water, CO2, N2, steam); offshore back to 1941 | `,` CSV, bracketed headers, quoted, dot thousands; **m3 and Mm3 per month** |
| `zone_daily_rates` ("Produção por zona", from Oct 2014) | Per well, **reservoir zone** and month; injection per zone | `,` CSV; m3/d and Mil m3/d |
| `well_status` ("Situação de poços", 1939 onward) | Status, **lift method**, drilling/completion/first-production dates, last intervention, base coordinates | `,` CSV with underscores; dates dd/mm/yyyy; coordinates DMS |

Verified facts that decide how the data are used:

- **Rate = monthly volume / calendar days.** For the whole offshore file of December 2023 the by-well rate file and the by-well volume file agree on every well (`reconcile` returns nothing). A well on stream for half the month therefore shows half the rate; use `producing_rate` (needs `hours_on`) for the on-stream rate.
- **Pre-salt is a subset of offshore.** In December 2023 all 364 pre-salt rows are in the offshore file. Never add the files: `merge_environments` drops the duplicates and flags `presalt`; `aggregate` raises on a repeated row.
- **A well can be split over several fields** (one row per field with its allocated share, for example onshore Potiguar wells). A well name is not a unique row key; `well_history` sums the rows of a month, `aggregate` keys on well, month, field, zone and installation.
- **The by-well zips with fluid data stop at 2023-12.** The page heading "2024 em diante" links the 2023 folder. From 2024 use the CDP query portal or the volume family, which has no API, composition or hours.
- **Publication lag of two months** (January data appear in March; `expected_latest_period`). The newest month can be absent without being an error; `completeness` reports `behind_expected_months`.
- **Mixed encodings.** Headers can be cp1252 above UTF-8 rows, and a row can be cut inside a character. `read_table_bytes` decodes line by line. Well names are ASCII and the safe join key; field and installation names can lose accents (join with `anp_open_data.name_key`).
- **Composition is per installation or field, repeated for every well and month of that stream**, not a wellstream and not time-resolved. The oxygen, nitrogen and carbon dioxide columns look mislabelled for Mero in 2023-12 (oxygen 2.6 %, nitrogen 40 %); `fluid_basis` warns when oxygen exceeds 0.5 %.
- December 2023 anchor for a sanity check: oil plus condensate 3.59 million bbl/d, gas 157 million m3/d, 6,546 producing wells, pre-salt 2.74 million bbl/d.

## Python Usage Pattern

```python
from anp_well_production import (
    FAMILIES, extract_links, download, read_zip, read_table_bytes, normalize, merge_environments,
    aggregate, well_history, well_flags, completeness, decline_series, latest_fluid_basis, readiness,
)

page_url = FAMILIES["well_monthly_rates"]["page"]
page = download(page_url, task / "references/anp")[0].read_text(encoding="utf-8")        # the ANP page
link = extract_links(page, "well_monthly_rates")[0]["url"]                              # choose by name, do not guess
path, log = download(link, task / "references/anp")        # log -> SOURCES.md (url, time, sha256)

by_env = {}
for name, raw in read_zip(path).items():                   # Mar, PreSal, Terra
    headers, rows, meta = read_table_bytes(raw)
    by_env[name.rsplit("_", 1)[-1][:-4]] = normalize(headers, rows, source=name)
records, report = merge_environments(by_env)               # pre-salt is a subset of Mar
assert report["presalt_is_subset"], report

field = aggregate(records, by=("field",))                  # per field and month: rates, GOR, water cut
hist = well_history(records, "7-MRO-10B-RJS")              # one well, rows of split wells summed
flags = well_flags(hist)                                   # shut-in, partial, gaps, GOR outliers
series = decline_series(hist)                              # [(year, m3/d)] without shut-in months
basis = latest_fluid_basis(hist)                           # API, density, GOR, gas mole fractions, warnings
```

Decline: pass `series` to `fit_arps_decline` of `neqsim-norwegian-continental-shelf-data`; label the result screening. Cumulative volume: `cumulative(hist)` (calendar days).

## Engineering Method

1. Fetch the page, take the link, download into the task folder, record URL, time and SHA-256.
2. Read with `read_table_bytes` and `normalize`; a missing or renamed header raises `KeyError` naming the field. Do not map columns by position.
3. Merge environments, then aggregate. Check `completeness` against the lag and `reconcile` when two families cover the same wells.
4. Before any decline fit, inspect `well_flags`: shut-in months, partial months, gaps and GOR jumps are operating events and must be excluded or modelled, not fitted as reservoir decline.
5. For a model input state which family, which months and what the file does not contain. `readiness("material_balance")` and the other keys give the public items, the missing items and the next step.

## What the open data can and cannot support

| Use | Public | Missing (operator or BDEP) |
| --- | --- | --- |
| Decline and EUR (screening) | rate history, hours, status, lift method | reservoir pressure, workovers beyond status dates |
| GOR and water-cut trends | gas, oil, water per well | separator conditions, allocation basis |
| Field aggregation | field, basin, installation, operator | fiscal and allocated volumes (differ from ANP statistics) |
| Material balance | history, zone rates from Oct 2014 | static pressure, PVT (Bo, Rs, Bg, Pb), aquifer |
| Well flow and VFP | lift method, base coordinates | tubing and casing geometry, wellhead P and T, chokes |
| Process feed fluid | API, gas composition, GCV, GOR | separator P and T, C7+ properties, wellstream composition |

ANP's technical database BDEP holds well records, logs and reports subject to confidentiality periods; some items are free, others need a request or a fee, and there is an academic access route.

## Validation Checklist

- [ ] Family detected from the header; no column mapped by position.
- [ ] URL, retrieval time and SHA-256 of every file are in `references/SOURCES.md`.
- [ ] Onshore, offshore and pre-salt merged with `merge_environments`; `presalt_is_subset` is true or the difference is explained.
- [ ] Latest month compared with `expected_latest_period`; gaps listed.
- [ ] Units stated: m3/d, thousand m3/d, bbl/d converted with 0.158987294928 m3/bbl.
- [ ] Shut-in and partial months handled before decline fitting.
- [ ] Fluid basis carries its warnings and is called a declared best guess.
- [ ] Sum of a field or the nation compared with an independent figure (for example the ANP monthly bulletin) before it is used as a benchmark.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Offshore total far too high (pre-salt is about three quarters of Brazilian oil) | Pre-salt file added to the offshore file | `merge_environments`; `aggregate` raises on repeats |
| Well appears twice in a month | Well is split over fields | Sum rows with `well_history`; key on field too |
| Rate 1000 times off | Gas `Mm3` read as million m3 | ANP `Mm3` is thousand m3; use the record fields |
| Weak month looks like decline | Shut-in or partial month | `well_flags`, `producing_rate`, `decline_series` drops zeros |
| No data after 2023 in the zips | Fluid-data zips end at 2023-12 | Use the volume family or the CDP portal; state the loss of API and composition |
| Latest month missing | Two-month publication lag | `expected_latest_period` |
| Mojibake in field names | Mixed encodings | Join on well name or `name_key` |
| Methane-rich composition with 2.6 % O2 | Mislabelled columns in the operator report | Check against the gross calorific value; do not use blindly |

## Limitations

- Statistics as published by ANP, not fiscal, allocated or reserves figures.
- Composition and API are stream-level, sparse in time and unverified; no PVT.
- No reservoir pressure, well geometry or wellhead conditions: a calibrated MBAL or well-flow model is not possible from these files alone.
- Screening basis only; human review required.

## Related NeqSim Functionality

- Feeds `neqsim-norwegian-continental-shelf-data` (`fit_arps_decline`, `forecast_production`), `neqsim-reservoir-depletion-screening` and `neqsim-reservoir-history-match-forecast` with rate history.
- Feeds `neqsim-pseudocomponent-split-characterization` and `neqsim-e300-fluid-io` (through the fluid-characterization agent) with API, GOR and gas mole fractions; component names in `NEQSIM_COMPONENTS` exist in the NeqSim database (`methane` ... `nC11`, `CO2`). The gas mole fractions and GOR are the surface-gas and ratio inputs of `neqsim.process.fielddevelopment.reservoir.RecombinationFluidFactory`; the stock-tank liquid must still be characterised from the API gravity.
- Companion of `neqsim-anp-open-data` (layers, installations, tie-in hosts). No NeqSim calculation runs inside this skill.

## References

- ANP, "Produção de Petróleo e Gás Natural por Poço", https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/producao-de-petroleo-e-gas-natural-por-poco (metadata PDF linked there).
- ANP, "Fase de Desenvolvimento e Produção", https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/fase-de-desenvolvimento-e-producao
- ANP technical database BDEP, https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/dados-tecnicos/acervo-de-dados
- ANP CDP query portal, https://cdp.anp.gov.br
