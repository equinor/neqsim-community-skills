---
name: neqsim-seismic-segy-reading
calculation_basis: "data-retrieval"
version: "1.0.0"
description: "Read SEG-Y seismic with equinor/segyio: geometry (inline/crossline ranges, header-byte fallback, unstructured 2-D), scaled trace coordinates, bin spacing, CRS hints, amplitude QA, inline/crossline/slice sections, nearest trace at a well, fences along map polylines, PNG sections and seismic_dataset_evidence.v1. USE WHEN: a task has SEG-Y files and needs structural context, a well tie or a fence."
last_verified: "2026-11-15"
requires:
  python_packages: [segyio, numpy, matplotlib]
  java_packages: []
  env: []
  network: []
---

# Seismic SEG-Y Reading

Use this skill to open SEG-Y post-stack volumes and 2-D lines with [equinor/segyio](https://github.com/equinor/segyio), to describe what is in them, and to cut the sections an engineering study needs. It does not interpret seismic. It hands over amplitude sections, geometry and provenance so that horizons, faults and well ties can be checked against wells and reports.

## When to Use

- A SEG-Y file is supplied (or exported from a seismic store) and the agent must know its survey extent, sampling, coordinates and CRS before using it.
- A section is needed through a well, a fault or loss-event pick, a pipeline route or a tie-back corridor (fence along a polyline).
- The trace nearest a well location is needed for a simple well tie, or to check an amplitude anomaly at a reservoir zone.
- Several SEG-Y files in a folder must be catalogued with SHA-256 and geometry before a study starts.

## Inputs

- SEG-Y file path or folder (read only).
- Optional inline/crossline header bytes (default tries 189/193, then 9/21, 9/13, 5/21, then unstructured).
- Coordinate source: `cdp` (default), `source` or `group` trace-header pairs.
- For fences: polyline vertices in the survey CRS and coordinate units, and a spacing close to the bin size.

## Outputs

- `SegyGeometry`: trace count, sampling (`samples`, `sample_interval`, `domain` as a guess from the text header), `structured`, `sorting`, `inlines` and `crosslines` arrays (None when unstructured), `offsets` (more than one means pre-stack), bin spacing, coordinate scalar and unit, bounding box, CRS hints from the text header, amplitude statistics (min, max, RMS, P1/P50/P99, zero fraction) and warnings.
- `Section` from `read_inline`, `read_crossline` (traces selected from the headers, ordered along the line, first offset unless `offset=` is given) or `extract_fence`: data (traces x samples), samples, x, y, trace index and, for fences, distance along the line and snap distance (NaN columns outside the survey).
- `read_slice`: horizontal slice nearest a time or depth. `trace_at_xy`: nearest trace with inline/crossline and snap distance.
- `save_section_png`, `write_cube` (synthetic or model volumes) and `seismic_dataset_evidence.v1` via `to_evidence` / `scan_folder`.

## Engineering Method

1. Open with segyio, trying standard and legacy inline/crossline byte pairs. If no regular grid exists, reopen with `ignore_geometry=True` and treat the file as unstructured.
2. Coordinates come from the trace headers with the SEG-Y scalar (bytes 71-72) applied: positive multiplies, negative divides, zero means 1. Units come from binary-header byte 3255 (1 = m, 2 = ft).
3. The text header is searched for EPSG codes, UTM zones and datums (ED50, WGS84, ETRS89, NAD). These are reported as hints, never applied.
4. Fences: densify the polyline at the requested spacing, snap each point to the nearest trace (KD-tree when SciPy is present), and blank points further than 1.5 bins from any trace.
5. Amplitude QA samples up to 2000 traces evenly, so very large volumes are summarised without a full read.

## Python Usage Pattern

```python
from segy_seismic_reading import inspect_segy, extract_fence, trace_at_xy, save_section_png, to_evidence, write_evidence

geo = inspect_segy("references/seismic/survey_pstm.sgy")
print(geo.inlines.min(), geo.inlines.max(), geo.bin_spacing, geo.crs_hints, geo.warnings)
fence = extract_fence(geo.path, [(456200.0, 7201300.0), (459800.0, 7203900.0)], spacing=12.5)
save_section_png(fence, "figures/fence_loss_zone.png", title="Fence through loss events")
trace, samples, info = trace_at_xy(geo.path, 457100.0, 7202050.0)   # well location, same CRS
write_evidence(to_evidence(geo), "step2_analysis/seismic_evidence.json")
```

Command line: `<python> -m segy_seismic_reading <file-or-folder> --out evidence.json [--coordinates cdp|source|group]`. With `--out` it prints one summary line and writes the JSON; without it the JSON goes to stdout. Use `--coordinates source` (or `group`) when the evidence warns that CDP coordinates are all zero.

## Validation Checklist

- [ ] CRS and datum are confirmed with the data owner. Well and route coordinates are in the same CRS before snapping (use a geodetic transform if not).
- [ ] Domain (time or depth), sample unit and reference datum are confirmed. Picks in depth are not overlaid on a time volume without a velocity model.
- [ ] Snap distances in fences are no more than one bin inside the survey. Blank columns are explained as outside coverage.
- [ ] Amplitude QA shows no all-zero or clipped volume (`zero_fraction`, `max` versus format limits).
- [ ] Every volume used is listed in `references/SOURCES.md` with its SHA-256, and the evidence status stays `unverified`.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Coordinates 100x too large | Coordinate scalar ignored | Read coordinates through `trace_coordinates`, never raw headers |
| Fence entirely NaN | Polyline in another CRS or in lat/long | Transform points to the survey CRS first |
| "no inline geometry" | Non-standard header bytes or 2-D line | Pass `header_bytes=((byte_il, byte_xl),)` or use `extract_fence` |
| Depth pick lands in the wrong reflector | Time volume treated as depth | Check `geometry.domain` and convert with a velocity model |
| Wrong fault offset | Section drawn along inline although the fault strikes obliquely | Use `extract_fence` perpendicular to strike |
| `ImportError` for segyio | Package not installed in the environment | Plugin installs it; in a checkout run `<python> -m pip install segyio` once |

## Limitations

- Post-stack volumes and 2-D lines are the target. Pre-stack files are detected and flagged; sections then use one offset, but slices and amplitude statistics mix offsets, and no gather processing, velocity conversion, interpretation, attribute or inversion work is done.
- Nearest-trace snapping, no interpolation between traces. VDS/OpenVDS, ZGY and compressed formats need conversion to SEG-Y first.
- CRS detection is limited to text-header hints; the user or data owner must confirm it.
- segyio is LGPL-3.0; this skill only imports it.

## Related NeqSim Functionality

- Skill `neqsim-well-log-reading` for log character at the same well and depths (loss events, fault picks).
- Skills `neqsim-reservoir-model-builder` and `neqsim-reservoir-3d-visualisation` for structure handed on as surfaces or grids; `neqsim-pipeline-survey-processing` and `neqsim-subsea-equipment-placement` for route and seabed context.
- `neqsim-well-trajectory-anticollision` provides well paths whose map positions can be snapped to traces.
- Skill `neqsim-seismic-structure-to-reservoir` turns a cube (or interpreted surfaces) into structure: horizon tracking from a well seed, depth conversion, closure, area and gross rock volume, builder inputs and an OPM grid.

## References

- SEG-Y revision 1 (2002) and revision 2.0 (2017) data exchange formats, Society of Exploration Geophysicists.
- equinor/segyio documentation, <https://segyio.readthedocs.io>.
