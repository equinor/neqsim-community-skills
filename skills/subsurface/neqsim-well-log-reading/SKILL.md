---
name: neqsim-well-log-reading
calculation_basis: "data-retrieval"
version: "1.0.0"
description: "Read DLIS and LIS well logs with equinor/dlisio and LAS 1.2/2.0 with a built-in parser into one model: frames, curves, units, canonical mnemonics, nulls as NaN, depth in metres, curve inventory and SHA-256 provenance. Zone statistics, event-window contrast and resampling. USE WHEN: a task has well-log files (petrophysics, formation tops, loss or fault picks, H2S vs formation, offset-well evidence)."
last_verified: "2026-11-15"
requires:
  python_packages: [dlisio, numpy, pandas]
  java_packages: []
  env: []
  network: []
---

# Well-Log Reading (DLIS, LIS, LAS)

Use this skill whenever a task receives well-log files. It turns DLIS (RP66 v1), LIS (LIS79) and LAS 1.2/2.0 files into a single, format-neutral `WellLog` model and a provenance-stamped `well_log_evidence.v1` record. DLIS and LIS are decoded by [equinor/dlisio](https://github.com/equinor/dlisio); LAS needs no extra package.

## When to Use

- A task folder, a document root or a well database holds `.dlis`, `.lis` or `.las` files, and the agent must know which curves exist, over which depths and in which units.
- Log character is needed in a depth window: loss events, fault or fracture picks, influx depths, casing shoes.
- Curves are averaged per formation or zone, for example H2S against formation mineralogy, net-to-gross screening or zone properties for a reservoir model.
- Offset-well evidence for well design (caliper, density, sonic) or reservoir inputs (porosity, saturation) must come from the logs, not from a report table.

## Inputs

- A file path (`read_well_log`) or a folder (`scan_folder`, read only).
- Optional `fmt` (`"dlis"`, `"lis"`, `"las"`) when the suffix is non-standard, and `null_values` (default `-999.25, -999, -9999, -99999`).
- For analyses: zones as `{"name", "top_m", "base_m"}` and event depths in metres on the same reference as the log index.

## Outputs

- `WellLog`: well, field and company from the header (DLIS origin, LIS wellsite table, LAS `~W`), metadata, warnings (time-indexed frames, empty frames, placeholder headers such as `WELL`/`FIELD`), SHA-256 and one `LogFrame` per DLIS frame, LIS data-format spec and sample rate, or LAS file.
- `LogFrame`: index name, unit and type; `depth_m()` (from the index, or from the `TDEP`/`DEPT` channel of a time-indexed station or tension log, see `depth_curve()` and `has_depth`); `curve(name)` by file mnemonic or canonical mnemonic (GR, RHOB, NPHI, DT, DTS, RDEP, RMED, RSHAL, CALI, BS, SP, PEF, DRHO, TEMP, ROP, WOB, TVD); `to_dataframe()`; `inventory()`.
- `LogCurve` (returned by `frame.curve(...)`): `name`, `unit`, `long_name`, `canonical` and `values` (a NumPy array; use `curve.values`, not the curve object, in calculations). A canonical name shared by several curves (for example two gamma-ray runs) raises `KeyError` that lists them; ask for the file mnemonic instead.
- `zone_statistics`: n, valid fraction, mean and P10/P50/P90 per zone and curve. A zone is `top <= depth < base`, so adjacent zones never share a sample; a base at or below the deepest sample keeps that sample.
- `depth_window_contrast`: window, above and below means, and the contrast in curve units and shoulder standard deviations.
- `to_evidence` / `scan_folder`: `well_log_evidence.v1` JSON with curve inventory, `depth_range_m`, `depth_from_channel` and `depth_reference_hints` (header PDAT, DREF, LMF, DMF, EKB, EDF, EGL, APD, EPD), no curve values; `write_frame_csv` writes the values.

## Engineering Method

1. Detect the format from the suffix, then from the file signature (LAS `~V`, DLIS storage-unit label).
2. DLIS: read origins (well, field, company) and depth-reference parameters, then every frame with `frame.curves()`. The index channel and its units come from the frame. Time-indexed frames (station and tension logs) take depth from their `TDEP`/`DEPT` channel; such depths repeat at stations. With `tolerant=True`, dlisio logs recoverable errors instead of failing. Multiple logical files are kept as separate frames (`MAIN@LF1`).
3. LIS: read the wellsite (CONS) table for well, field and company, then each data-format spec once per sample rate, because LIS79 fast channels cannot share one array (dlisio rule). Mnemonics are trimmed and the DFSR absent value is added to the null list.
4. LAS: parse `~V/~W/~C/~P/~A`, honour `WRAP`, `NULL` and duplicate mnemonics (`GR`, `GR:1`). LAS 3.0 is rejected explicitly.
5. Replace absent values with NaN, convert depth to metres (including scaled units such as `0.1 in`), and map mnemonics to canonical names by alias or run suffix. Unit and description must agree before an unknown mnemonic is classified (`g/cm3` plus "bulk density"); a unit alone never classifies a curve, because mud density shares `g/cm3` with bulk density and spectral gamma components share `gAPI` with total gamma ray.
6. Analyses work on depth in metres along the log index (normally MD from the log's depth reference).

## Python Usage Pattern

```python
from well_log_reading import read_well_log, zone_statistics, depth_window_contrast, to_evidence, write_evidence

log = read_well_log("references/well-logs/WELL-1_MAIN.dlis")
frame = log.frame()                      # depth frame with most samples
print(log.well_name, frame.index_unit, [c["name"] for c in frame.inventory()])
rhob = frame.curve("RHOB")               # finds RHOZ, DEN, ... by canonical name
zones = [{"name": "Reservoir A", "top_m": 2410.0, "base_m": 2475.0}]
print(zone_statistics(frame, zones, curves=["GR", "RHOB"]))
print(depth_window_contrast(frame, depth_m=2512.0, half_width_m=3.0, curves=["CALI", "RHOB", "RDEP"]))
write_evidence(to_evidence(log), "step2_analysis/well_log_evidence.json")
```

Command line: `<python> -m well_log_reading <file-or-folder> --out evidence.json [--csv DIR]`. With `--out` it prints one summary line and writes the JSON; without it the JSON goes to stdout.

## Validation Checklist

- [ ] Well identity is taken from the header (origin, wellsite table or `~W`), and it matches the intended wellbore and sidetrack. Placeholder-header warnings are resolved.
- [ ] Depth unit and reference (RKB, DF, MSL) are confirmed from `depth_reference_hints` or the data owner. Tops and events use the same reference and MD versus TVD.
- [ ] The inventory shows the expected curves with plausible ranges in their own units (GR 0-200 gAPI; RHOB 1.9-3.0 g/cm3, which is 1900-3000 kg/m3; NPHI -0.05 to 0.6 v/v). Convert units before comparing files.
- [ ] Null fraction and gaps are reported per curve; no NaN is silently filled.
- [ ] `to_evidence` status stays `unverified` until a petrophysicist or the data owner confirms environmental corrections and depth matching.
- [ ] Every file used is listed in `references/SOURCES.md` with its SHA-256.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Depths 10x or 120x too large | DLIS index in `0.1 in` or feet read as metres | Use `frame.depth_m()`, never the raw index |
| Spikes at -999.25 in plots | Absent values kept | Read through this skill; add custom null codes in `null_values` |
| Curve "missing" | Vendor mnemonic (RHOZ, TNPH, AT90) | Look it up with `frame.curve("RHOB")` or by canonical name |
| Mud density reported as formation density | Curve classified by unit alone | Canonical names need an alias or unit plus description; check `long_name` |
| `depth_m()` refuses a DLIS frame | Time-indexed frame without a depth channel | Pick another frame or set the depth from the survey; never use time as depth |
| Wrong well | File name trusted over header | Check `log.well_name` and the origin metadata |
| Loss event shows no contrast | Event depth in TVD, log in MD | Convert picks with the well survey first |
| `ImportError` for dlisio | Package not installed in the environment | Plugin installs it; in a checkout run `<python> -m pip install dlisio` once |

## Limitations

- Reads and summarises logs. It does not do petrophysical interpretation (Vshale, porosity, Sw), environmental corrections, depth matching or splicing.
- LAS 3.0 and LIS fast channels at different rates in one frame are not merged. Image and waveform array channels are kept but excluded from DataFrames and zone statistics.
- Canonical mnemonics are a screening convenience, not a vendor-complete catalogue. Check the long name for quantitative work.
- dlisio and segyio are LGPL-3.0; this skill only imports them.

## Related NeqSim Functionality

- Skill `neqsim-seismic-segy-reading` for the seismic around the well (trace at the well, fences through loss or fault picks).
- Skills `neqsim-reservoir-model-builder` and `neqsim-near-well-and-injectivity` consume zone porosity and permeability; `neqsim-reservoir-h2s-mineral-buffer` uses formation mineralogy; `neqsim-integrated-well-planning` and `neqsim-well-design-study` use offset caliper, density and sonic data.
- `neqsim-document-intelligence-extraction` for log headers and composite logs that exist only as PDF or scan.
- Skill `neqsim-seismic-structure-to-reservoir` uses well tops as tracking seeds and depth ties, and zone properties as grid inputs.

## References

- API RP 66 / RP66 v1 Digital Log Interchange Standard (DLIS); Schlumberger LIS79 specification.
- Canadian Well Logging Society, LAS 2.0 specification.
- equinor/dlisio documentation, <https://dlisio.readthedocs.io>.
