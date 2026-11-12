---
name: neqsim-open-incident-data
calculation_basis: "screening"
version: "0.1.0"
description: "Open, login-free offshore incident statistics from the US BSEE Data Center: accident investigations by type (fire, explosion, blowout, fatality, crane, pollution) divided by platform structure-years, with exact Poisson intervals and explicit caveats. USE WHEN: a safety, consequence or reliability task needs a sourced open order-of-magnitude frequency or trend to cross-check an assumed fire, explosion or blowout frequency, or needs to state what open incident data can and cannot support."
last_verified: "2026-11-12"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["www.data.bsee.gov"]
---

# Open Offshore Incident Data (BSEE Data Center, no login)

Most incident and failure-rate databases are paid or login-gated (OREDA) or block scripts (UK HSE release spreadsheets
and PHMSA pipeline files returned HTTP 405 and 403 to automated clients when checked on 2026-11-12). The US BSEE Data
Center serves its raw files anonymously, so it is the one dependable open source that an agent can read and cite.

Two files are used:

| Key | File | Content |
|-----|------|---------|
| `investigations` | `https://www.data.bsee.gov/Other/Files/IncInvRawData.zip` | about 2000 accident investigations, 1995 to date: date, lease, area/block, accident type label(s), status |
| `structures` | `https://www.data.bsee.gov/Platform/Files/PlatStrucRawData.zip` | 7091 platform structures: install and removal date (blank = installed), type, major flag, manned flag, water depth |

Together they give investigations **per structure-year**, which an incident list alone cannot.

## When to Use

- A HAZOP, LOPA, QRA or consequence task assumes a fire, explosion, blowout or fatality frequency and you want an
  independent open cross-check with a stated source and interval.
- You need a trend (for example fire investigations per year) or the ranking of incident types on an open data set.
- You need to say clearly what open data can support, and what it cannot (see Limitations).
- Do not use it for Norwegian-shelf design frequencies, SIL targets, or equipment-level failure rates.

## Inputs

Label(s) to count (`Fire`, `Explosion`, `Fatality`, `Blowout`, `Crane`, `Pollution`, `Required Evacuation`, ...),
period (start and end year), optional filters (`major_only`, `manned_only`, `areas` such as `["GC", "MC"]`),
and the confidence level (default 90 %).

## Outputs

- `RateEstimate`: count, structure-years, rate per structure-year, exact Poisson (Garwood) lower/upper bound,
  filters, and the `caveats` list that must travel with the number.
- `label_counts`, `annual_counts` for ranking and trend.
- `BseeClient.provenance()`: URL, SHA-256, size, retrieval time and the BSEE terms note for `results.json`.

## Engineering Method

1. Load both files: `client = BseeClient(cache_dir=...)`, then `parse_investigations(client.get_text("investigations"))`
   and `parse_structures(client.get_text("structures"))`.
2. Rank what exists: `label_counts(investigations, 2010, 2024)`. A record can carry several labels
   (`"- Fire - Required Muster"`), and counts by label are therefore not additive.
3. Pick the period and filters that match the asset (major structures, manned, area group) and
   `estimate_rate(...)`. Use 10 or more years: single-year counts are small and noisy.
4. Check the trend with `annual_counts`; compare the rate over two periods rather than quoting one value.
5. Report the rate **with its interval, the period, the filters and the caveats**; never as an asset frequency.
6. Compare with the assumed frequency: it is a plausibility test (same order of magnitude or not), and a mismatch
   is a question for the assumption, not proof it is wrong.

## Python Usage Pattern

```python
from open_incident_data import (BseeClient, estimate_rate, label_counts, annual_counts,
                                parse_investigations, parse_structures)

client = BseeClient(cache_dir=".bsee_cache")
investigations = parse_investigations(client.get_text("investigations"))
structures = parse_structures(client.get_text("structures"))

print(label_counts(investigations, 2010, 2024)[:8])
fire = estimate_rate(investigations, structures, ["Fire"], 2010, 2024, major_only=True)
print(fire.count, round(fire.structure_years), fire.rate_per_structure_year, fire.lower, fire.upper)
print(annual_counts(investigations, ["Fire"]))
block = {"estimate": fire.to_dict(), "sources": client.provenance()}   # into results.json
```

Verified example (snapshot retrieved 2026-11-12; the Data Center updates daily, so figures move): fire
investigations on major structures 2010-2024 were 135 over 16,401 structure-years, 8.2e-3 per structure-year
(90 % interval 7.1e-3 to 9.5e-3); explosion 18 (1.1e-3); fatality 17 (1.0e-3); blowout 2 (1.2e-4, interval
2e-5 to 3.8e-4). Fire investigations per year fell from 16 (2010) to 5 (2024).

## Validation Checklist

- [ ] Retrieval date and file SHA-256 recorded (the data change daily).
- [ ] Count, exposure, period, filters and interval all reported together.
- [ ] Labels are single labels; multi-label overlap acknowledged (an explosion that burns counts under both).
- [ ] The four `CAVEATS` are stated in the report next to the number.
- [ ] The result is used as a cross-check, not as the design basis.
- [ ] Jurisdiction mismatch (US Gulf of Mexico vs the asset's regime) is stated.

## Common Mistakes

- Treating investigations as all incidents or as hydrocarbon-release frequency.
- Adding counts of overlapping labels to get a "total".
- Dividing by installed structures at one date instead of structure-years over the period.
- Reading a one- or two-event rate (blowout 2 events) as meaningful; look at the interval.
- Quoting a rate from the 1990s peak and a rate from the 2020s as one number.
- Using the result for equipment-level failure rates (the data carry no equipment type).

## Limitations

- Numerator is investigations, not incidents; the rate is a lower-bound index. Thresholds and practice changed
  over time (the 1996 to 1998 peak may partly reflect reporting practice rather than risk).
- Investigations are linked only to lease/area/block; pipeline, vessel and drilling-unit events are in the
  numerator while the denominator counts platform structures.
- US Gulf of Mexico only; not transferable to the Norwegian continental shelf without review.
- No release size, ignition or consequence data in these files; no equipment taxonomy.
- Terms: US Department of the Interior data, provided as is; the BSEE page asks users to read its disclaimer
  before downloading. Cite "BSEE Data Center" and the retrieval date.
- Not covered because they are not scriptable anonymously: UK HSE hydrocarbon-release spreadsheets (405 from
  scripts), PHMSA pipeline incident files (403), and the Norwegian RNNP (reports are public PDFs without a data
  API). Read those by hand in a browser and cite the report; do not claim an automated retrieval.
- The CSB investigation catalogue (`https://www.csb.gov/investigations/`) and the EU eMARS search
  (`https://emars.jrc.ec.europa.eu/en/emars/accident/search`) are open to a browser without login and are good for case
  histories; this skill does not scrape them (HTML and a JavaScript application, brittle).

## References

- BSEE Data Center, raw data files: <https://www.data.bsee.gov/Main/RawData.aspx>.
- Garwood F. (1936), Fiducial limits for the Poisson distribution, Biometrika 28, 437-442 (exact interval used).
- Companion skills: `neqsim-reliability-data-screening`, `neqsim-gas-dispersion-distance-screening`,
  `neqsim-jet-fire-radiation-screening`, `neqsim-technology-fmirr`.
