---
name: neqsim-pid-pdf-to-dexpi
calculation_basis: "hybrid"
version: "1.1.0"
description: "P&ID PDF to NeqSim: extracts equipment, nozzle roles, connectors, pipe runs, tees, valves with normal position, flanges, reducers and instruments into drawing records; stitches sheets; reads scanned sheets best-effort; writes DEXPI, builds and runs the flowsheet with side-stream feeds, redraws the P&ID and checks the round trip. Reviewer corrections gate approval. USE WHEN: a P&ID exists only as PDF and must become DEXPI, a simulation or a redrawn sheet."
last_verified: "2026-11-23"
requires:
  python_packages: [pymupdf, jpype1]
  java_packages: [neqsim]
  env: []
  network: []
---

# P&ID PDF to DEXPI, simulation and regenerated P&ID

Most P&IDs in document systems are PDF exports from a CAD tool, not DEXPI. This skill turns
one or more such sheets into a reviewable, machine-readable topology and runs it through NeqSim:

```text
PDF sheet(s)  (vector; scanned best-effort)
  -> drawing records (neqsim_pid_drawing_records.v1) + overlay + review checklist [Python]
  -> sheets stitched through matching off-page connectors                         [Python]
  -> reviewer corrections applied (named reviewer; approval recorded)             [Python]
  -> Proteus DEXPI with drawing geometry (PidDrawingRecordsDexpiWriter)           [NeqSim Java]
  -> runnable ProcessSystem with side-stream feeds (DexpiSimulationBuilder)       [NeqSim Java]
  -> regenerated P&ID (DexpiXmlSvgRenderer) with stream results on the runs
  -> DEXPI 2.0.1 of the simulated flowsheet + conformance assessment
```

The extracted topology is a **draft** until a named reviewer approves it. The source drawing stays
the controlled reference. Every run writes an overlay of the traced topology on the original sheet
and a review checklist of the items most likely to be wrong.

## When to Use

- "Read this P&ID PDF and make a DEXPI / a NeqSim model of it."
- "Regenerate this P&ID from DEXPI" or "show simulated conditions on the P&ID".
- "Join these two P&ID sheets and simulate across them."
- Building a topology (which nozzle goes where, through which valves and tees, which valves are
  normally closed) for routing, isolation or model-build work when no smart P&ID export exists.

A native DEXPI/Proteus export is always better than extraction; ask the drawing owner first.

## Inputs

- PDF page(s). A CAD export (`page.get_drawings()` returns thousands of paths) gives the best
  result. A scanned sheet is detected automatically (`is_raster_pdf`) and read from the image.
- For simulation: fluid composition and feed rate (never on a P&ID). Feed pressure and
  temperature default to the operating values in the equipment data block on the sheet
  (for example `DES./OPER. PRESSURE barg -1 & 30 / 16`), else pass them.
- Optional `boundary_feeds`: the fluid, rate and state of side streams that enter through other
  off-page connectors.
- Optional `corrections`: a reviewer corrections file (see Review workflow).
- A NeqSim jar that contains `PidDrawingRecordsDexpiWriter` (`jar=` or `NEQSIM_JAR`).
- Scanned sheets: `pip install .[raster]` (numpy, scipy, pillow, pytesseract) and the Tesseract
  OCR engine on `PATH` (or set `pytesseract.pytesseract.tesseract_cmd`).

## Engineering Method

1. **Primitives.** Strokes are classified by width and dash. Process piping is the heavy,
   solid class (`process_min_width`, default 0.9 pt). Symbols, connector outlines and signal
   lines are thinner or dashed.
2. **Text.** Equipment tags (`20VA001`, `20-PA-001`; type letters mapped in
   `ExtractionConfig.equipment_codes`), drawing references, line numbers
   (`<size><fluid>-<class>`, fluid code kept), nozzle labels (`N01`), instrument bubbles
   (function letters over a loop number).
3. **Equipment outline.** The thin outline directly above the tag is grown into its connected
   component. Outlines with curves (vessel heads, pump casings) score higher than table grids.
4. **Off-page connectors.** The thin pentagon, or a rectangular box (drain, flare and vent
   boxes), around each drawing reference, with its label above or below. Box direction comes
   from the arrowhead on the attached line. Direction comes from FROM/TO in the label, else
   from the arrow: a line at the tip flows in. A disagreement is reported. Utility labels
   (drain, flare, vent, sampling, chemicals, jet water, purge...) and chemical fluid codes mark
   the run `normal_flow=false`. A connector with no process line is a signal connector.
5. **Line graph.** Process strokes are joined end to end, end to line interior (tees), and
   across a short collinear gap between facing ends (default up to 30 pt). That gap is where CAD
   breaks a line for a valve, flange, reducer or blind. A line end that points at an equipment
   outline within `nozzle_reach` (default 20 pt) reaches it across a thin flange or nozzle stub.
6. **Routes and junctions.** Shortest routes are traced from every connector and every nozzle
   to every reachable terminal. They are merged into one point graph. Points with three or more
   pipe pieces become **tee** nodes. Degree-2 chains are contracted into pipe runs.
7. **Direction.** In order:
   - paths from process inlet to outlet connectors through tees;
   - utility connectors;
   - the tee balance rule (if all known branches enter, the rest leave, and vice versa);
   - remaining equipment runs outward, all at once, with a warning.

   Each run records `direction_source`.
8. **Nozzle roles.** A nozzle role comes from the first process connector downstream: gas,
   oil/condensate/stabilisation, or water/hydrocyclone. The fallback is the fluid code, then the
   highest outlet for gas. A separator with a water outlet becomes `ThreePhaseSeparator`.
9. **Inline items.** Each line gap is classified:
   - **gate/globe valve**: two diagonals crossing on the axis (open) or two filled triangles
     (closed);
   - **ball valve**: a ring (open) or a filled disc (closed);
   - **reducer**: tapered sides off the axis, supported by size text (`1600 x 1400`);
   - **flange**: two short perpendicular bars in a narrow gap;
   - **spectacle blind**: half-filled discs beside the line.

   Lock text nearby (`NC`, `LC`, `CSC`, `NO`, `LO`, `CSO`) is read as locking and normal
   position. A nearby actuated-valve bubble (XV, ESV, SDV, PV, LV, FV...) gives the tag. A
   normally closed valve sets its run to `normal_flow=false`. Each valve records
   `position_source`: filled = closed is a drawing convention to confirm.
10. **Several sheets.** `stitch_records` pairs an outbound connector that names sheet B with the
    inbound connector on sheet B that names sheet A. Ties are broken by line number, fluid code
    and service words. Pairs are joined by `sheet_link` edges; IDs are prefixed `S1-`, `S2-`.
11. **Scanned sheets** (`raster.py`, best effort):
    - strokes are recovered by morphological opening, and solid symbols by erosion;
    - equipment outlines by region flood fill;
    - text by Tesseract with long lines removed;
    - drawing references whose first character OCR garbled are repaired from the prefix most
      often read on the sheet.

    Diagonal strokes are not recovered, so hollow valves are missed; compare with
    `compare_records` when a vector copy exists.
12. **DEXPI and simulation.** `PidDrawingRecordsDexpiWriter` writes Proteus DEXPI with nozzle
    `PortRole`, `NormalFlow`, valves, flanges, reducers and blinds with `NormalPosition` and
    `LockingStatus`, box-shaped connectors, review and sheet metadata, operating and design data,
    and the drawing geometry (pt -> mm, y flipped). `DexpiSimulationBuilder`:
    - excludes `NormalFlow=false` runs and normally closed valves, and passes open blinds;
    - passes flow through off-page connectors linked on both sides;
    - feeds each `addBoundaryFeed` connector with its own fluid and rate. The other inbound
      connectors carry the builder feed.
13. **Checks.** These are recorded in `pipeline_summary.json`:
    - an independent re-read of the DEXPI matches every run and nozzle role in the records;
    - equipment classes are as extracted;
    - the unit mass balance closes;
    - excluded no-flow runs equal the records;
    - the DEXPI 2.0.1 export is conformant.

## Review workflow

Records start as `REVIEW_REQUIRED`. `review_checklist.md` lists the items to check, highest
severity first: assumed flow directions, low-confidence valves and positions, unresolved
connectors and sheet links. A reviewer answers with a corrections file:

```json
{"reviewer": "Name", "date": "2026-11-23", "approved": true, "corrections": [
  {"op": "set_valve", "edge": "E-12", "index": 0, "normal_position": "open", "reason": "LO on sheet"},
  {"op": "reverse", "edge": "E-7"},
  {"op": "set_normal_flow", "edge": "E-30", "value": false},
  {"op": "set_role", "node": "EQ-1", "port": "EQ-1-P3", "role": "OilOutlet"},
  {"op": "add_edge", "from_node": "OPC-4", "to_node": "TEE-2"}]}
```

Other operations are `set_connector`, `set_tag` and `remove_edge`.
`apply_corrections` refuses a file without a reviewer. It records the reviewer, the date, each
correction and the SHA-256 of the file. Only `"approved": true` sets `APPROVED`; the writer carries
`ReviewedBy`/`ReviewDate` into the DEXPI.

## Python Usage Pattern

```python
from pid_pdf_to_dexpi import extract_pid_records
from pid_pdf_to_dexpi.overlay import render_overlay
from pid_pdf_to_dexpi.pipeline import run_pipeline

records = extract_pid_records("sheet.pdf")          # draft topology (vector or scanned)
render_overlay("sheet.pdf", records, "overlay.png")  # review it

fluid = {"eos": "srk", "components": [{"name": "methane", "moles": 0.6},
         {"name": "C10", "moles": 0.3, "molarMass": 0.15, "density": 0.79},
         {"name": "water", "moles": 0.1}]}
summary = run_pipeline(["sheet1.pdf", "sheet2.pdf"], "out", fluid, feed_flow=200000.0,
                       feed_flow_unit="kg/hr", jar="neqsim.jar",
                       boundary_feeds={"CONDENSATE FROM": {"flow": 5000.0, "flow_unit": "kg/hr"}},
                       corrections="corrections.json")
assert summary["passed"]
```

## Outputs

All outputs go to `out/`:

- `drawing_records.json`, `extraction_overlay*.png` and `review_checklist.md`;
- `extracted.dexpi.xml` and `regenerated_pid.svg/png`;
- `simulated.dexpi.xml` and `regenerated_pid_with_results.svg/png`, with P, T and mass flow on
  every normal-flow run;
- `simulated_flowsheet.dexpi201.xml`;
- `pipeline_summary.json`.

## Validation Checklist

- Open `extraction_overlay.png`. Every main nozzle has its role. Every traced run follows a drawn pipe.
- Work through `review_checklist.md`. Confirm each closed valve, assumed direction and sheet link against the sheet.
- `pipeline_summary.json` `passed` is true. `dexpiRoundTrip` has no missing or extra runs. The mass balance closes. `noFlowRunsExcluded` counts are equal.
- Compare the regenerated P&ID with the source sheet(s) side by side.

### Verified on

**Single sheet.** A production three-phase inlet-separator sheet (A1, 18k vector paths) took
about 7 s. The result has 32 connectors (13 box-shaped drain/flare boxes), 30 tees and 64 runs
(14 normal flow), and 74 inline items:

- 28 flanges and 20 reducers;
- 20 closed and 6 open valves, with the test-separator gas line correctly read as normally closed.

All main nozzles were resolved (inlet, gas, oil and water). Round trip: 64/64 runs match. The
mass balance closes to 1e-13, 50/50 no-flow runs were excluded, and DEXPI 2.0.1 is conformant.

**Two sheets.** The separator sheet plus its downstream sheet were stitched with 2 process links
(oil, water) and 1 signal link. A 5 t/h condensate side stream was a boundary feed. The separator
inlet was 205 t/h, all 84 runs round-tripped and all checks pass.

**Scanned copy.** A 300 dpi raster of the separator sheet found the separator and 30 connectors.
Against the vector result: process connections recall 0.8, precision 1.0. All pipeline checks pass.

## Common Mistakes

- Treating the extracted topology as the controlled P&ID before a reviewer approves it.
- Accepting filled = closed without checking: some drawing styles fill all valve bodies.
- Simulating a sheet with side streams without `boundary_feeds`. Each side stream then carries a
  copy of the builder feed and a `DEXPI_BUILD_ADDITIONAL_FEED` warning.
- Keeping default stroke widths for a drawing style with different weights. Profile `get_drawings()` widths first.
- Trusting a scanned-sheet result without comparing it to the source.

## Limitations

- Stroke-width classes are drawing-style dependent; tune `ExtractionConfig` and check the overlay.
- Scanned sheets: diagonals are not recovered, so hollow valves are missed, and OCR misreads
  tags. Expect a recall below the vector route.
- Drain boxes are detected, but their lines are often thin or dashed. Many remain untraced to
  the network; the review checklist lists them.
- Blind and spectacle symbols vary by drawing style. Detection is low-confidence and reports an
  assumed open position.
- A line crossing drawn as touching strokes reads as a tee. A crossing with a gap or hop reads
  correctly.
- Instrument bubbles are placed but not tied to signal lines or loops. Twin nozzles are labelled
  with the role total.

## References

- NeqSim Java: `PidDrawingRecordsDexpiWriter`, `DexpiSimulationBuilder` (`addBoundaryFeed`),
  `DexpiXmlSvgRenderer`, `Dexpi201XmlWriter` (docs: `docs/integration/dexpi-reader.md`).
- Skills: `neqsim-pid-process-operations` (P&ID-to-simulation),
  `neqsim-dexpi-conformance-validation`, `neqsim-document-intelligence-extraction`.
- Company document-system connectors fetch the sheets; this skill reads them.
