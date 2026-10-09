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

- Bid-round and block data: block polygons, round, contract type, area and operator after award.
- Field and well production: monthly oil, gas and water by field and well, with API gravity where reported.
- Well data and the national data bank for wells, seismic and geology, which is where analogue depth, temperature and pressure facts live.

Find the current portal, dataset names and file formats from the ANP open-data site at the time of use. Do not rely on a remembered URL or column name; check the file header before parsing.

## Rules

- Record the source, dataset name and download date for every number in `references/SOURCES.md`.
- Units: ANP reports oil in m3 and gas in thousand m3 in many tables; convert explicitly and state the conversion to barrels or Sm3. Check month versus calendar-year aggregation.
- Coordinates: confirm the CRS and datum of block polygons before computing distance to a host; reproject to a metric CRS first.
- Production history of a host field is public only at the level the portal exposes; ullage and plateau need operator data and belong in a governed layer, not here.
- Keep a small offline anchor table (field, block, year, rate) so a task still runs without network.

## Hand-offs

- Production series to `neqsim-reservoir-depletion-screening` and decline fitting.
- Block and host positions to `neqsim-pipe-route-profile` and `neqsim-subsea-layout-geometry` for tie-back distance.
- Block facts to `neqsim-psc-bid-economics-screening` and the `frontier-block-bid-agent`.
