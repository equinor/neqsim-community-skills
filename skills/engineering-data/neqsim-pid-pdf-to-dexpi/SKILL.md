---
name: neqsim-pid-pdf-to-dexpi
calculation_basis: "hybrid"
version: "1.0.0"
description: "Vector-PDF P&ID to NeqSim: extracts equipment, nozzle roles, off-page connectors, traced pipe runs, tees, inline valves, instruments and the sheet data block into drawing records; writes DEXPI with PidDrawingRecordsDexpiWriter; builds and runs the flowsheet; regenerates the P&ID with results and checks the round trip. USE WHEN: a P&ID exists only as a CAD-exported PDF and must become DEXPI, a simulation or a redrawn sheet."
last_verified: "2026-11-23"
requires:
  python_packages: [pymupdf, jpype1]
  java_packages: [neqsim]
  env: []
  network: []
---

# P&ID PDF to DEXPI, simulation and regenerated P&ID

Most P&IDs in document systems are PDF exports from a CAD tool, not DEXPI. This skill turns
one such sheet into a reviewable, machine-readable topology and runs it through NeqSim:

```text
vector PDF sheet
  -> drawing records (neqsim_pid_drawing_records.v1) + review overlay     [Python, this skill]
  -> Proteus DEXPI with the drawing geometry (PidDrawingRecordsDexpiWriter) [NeqSim Java]
  -> runnable ProcessSystem (DexpiSimulationBuilder) -> results             [NeqSim Java]
  -> regenerated P&ID (DexpiXmlSvgRenderer), with stream results on the runs
  -> DEXPI 2.0.1 of the simulated flowsheet + conformance assessment
```

The extracted topology is a **draft**. The source drawing stays the controlled reference. Every
run produces an overlay of the traced topology on the original sheet for review.

## When to Use

- "Read this P&ID PDF and make a DEXPI / a NeqSim model of it."
- "Regenerate this P&ID from DEXPI" or "show simulated conditions on the P&ID".
- Building a topology (which nozzle goes where, through which valves and tees) for routing,
  isolation or model-build work when no smart P&ID export exists.

Not for scanned (raster) sheets: they have no vector lines. Use OCR for tags only and build the
topology by hand, or ask the drawing owner for a DEXPI/Proteus export first. A native DEXPI
export is always better than extraction.

## Inputs

- A vector PDF page (CAD export). Check: `page.get_drawings()` returns thousands of paths and
  `page.get_text("words")` returns the tags.
- For simulation: fluid composition and feed rate (never on a P&ID). Feed pressure and
  temperature default to the operating values in the equipment data block on the sheet
  (for example `DES./OPER. PRESSURE barg -1 & 30 / 16`), else pass them.
- A NeqSim jar that contains `PidDrawingRecordsDexpiWriter` (`jar=` or `NEQSIM_JAR`).

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
4. **Off-page connectors.** The thin pentagon around each drawing reference; its label (text
   above, else below). Direction comes from FROM/TO in the label, otherwise from the arrow: a
   line attached at the tip flows in. A disagreement is reported. Utility labels (drain, flare,
   vent, sampling, chemicals, jet water, purge...) mark the run `normal_flow=false`. A connector
   with no process line attached is an instrument-signal connector.
5. **Line graph.** Process strokes are joined end to end, end to line interior (tees), and
   across a short collinear gap between facing ends (default up to 30 pt). That gap is where CAD
   breaks a line for a valve, flange, reducer or blind. A line end that points at an equipment
   outline within `nozzle_reach` (default 20 pt) reaches it across a thin flange or nozzle stub.
6. **Routes and junctions.** Shortest routes are traced from every connector and every nozzle
   to every reachable terminal. They are merged into one point graph. Points with three or more
   pipe pieces become **tee** nodes. Degree-2 chains are contracted into pipe runs. Pairwise
   routes alone would wrongly make a side stream that tees into a gas header look like a vessel
   inlet.
7. **Direction and roles.** Runs at connectors take the connector direction. A tee whose known
   branches all leave (or all enter) gets the remaining branches in the opposite sense.
   Remaining runs at equipment default to outward, with a warning. A nozzle role comes from the
   first process connector downstream: gas, oil/condensate/stabilisation, water/hydrocyclone. The
   fallback is the fluid code, then the highest outlet for gas. A separator with a water outlet
   becomes `ThreePhaseSeparator`.
8. **Inline valves.** A gap with a small filled body or several thin strokes is a valve. A
   nearby actuated-valve bubble (XV, ESV, SDV, PV, LV, FV...) gives its tag and class.
9. **DEXPI and simulation.** `PidDrawingRecordsDexpiWriter` writes Proteus DEXPI with nozzle
   `PortRole`, `NormalFlow`, operating and design data and the drawing geometry (pt -> mm,
   y flipped). `DexpiSimulationBuilder` excludes `NormalFlow=false` runs and builds the units.
10. **Checks.** These are recorded in `pipeline_summary.json`:
    - an independent re-read of the DEXPI matches every run and nozzle role in the records;
    - equipment classes are as extracted;
    - the unit mass balance closes;
    - excluded no-flow runs equal the records;
    - the DEXPI 2.0.1 export is conformant.

## Python Usage Pattern

```python
from pid_pdf_to_dexpi import extract_pid_records
from pid_pdf_to_dexpi.overlay import render_overlay
from pid_pdf_to_dexpi.pipeline import run_pipeline

records = extract_pid_records("sheet.pdf")          # draft topology
render_overlay("sheet.pdf", records, "overlay.png")  # review it

fluid = {"eos": "srk", "components": [{"name": "methane", "moles": 0.6},
         {"name": "C10", "moles": 0.3, "molarMass": 0.15, "density": 0.79},
         {"name": "water", "moles": 0.1}]}
summary = run_pipeline("sheet.pdf", "out", fluid, feed_flow=200000.0,
                       feed_flow_unit="kg/hr", jar="neqsim.jar")
assert summary["passed"]
```

## Outputs

All outputs go to `out/`:

- `drawing_records.json` and `extraction_overlay.png`;
- `extracted.dexpi.xml` and `regenerated_pid.svg/png`;
- `simulated.dexpi.xml` and `regenerated_pid_with_results.svg/png`, with P, T and mass flow on
  every normal-flow run;
- `simulated_flowsheet.dexpi201.xml`;
- `pipeline_summary.json`.

## Validation Checklist

- Open `extraction_overlay.png`. Every main nozzle has its role. Every traced run follows a drawn pipe. Untraced (grey) connectors are expected only for signal, sampling or chemical tie-ins.
- Read `warnings` in the records. Check each assumed flow direction and each connector without FROM/TO.
- `pipeline_summary.json` `passed` is true. `dexpiRoundTrip` has no missing or extra runs. The mass balance closes. `noFlowRunsExcluded` counts are equal.
- Compare the regenerated P&ID with the source sheet side by side.

### Verified on

A production three-phase inlet-separator sheet (A1, 18k vector paths, about 2,000 words)
was extracted in about 7 s. The result has 1 separator, 17 connectors (4 identified as signal),
21 tees and 46 runs (15 normal flow), 20 inline valves and 104 instruments. All main nozzles were
resolved:

- N01 inlet, with the wellstream and the contactor condensate teeing together;
- N02A/B gas, joined by the test-separator gas, to first-stage compression;
- N03A/B oil to stabilisation;
- N04A/B water to the hydrocyclones;
- the N11/N12 sand-jetting and N07/N27 PSV/flare nozzles as no-flow.

Round trip: 46/46 runs and all nozzle roles match. The mass balance closes to 1e-13, and 31/31
no-flow runs were excluded. The DEXPI 2.0.1 export is conformant.

## Common Mistakes

- Treating the extracted topology as the controlled P&ID. It is a draft; check the overlay.
- Running a scanned sheet. There are no vector lines; use a DEXPI export or OCR plus manual topology.
- Reading flows on side streams that enter from other sheets. The builder has one feed, so they stay unlabelled.
- Keeping default stroke widths for a drawing style with different weights. Profile `get_drawings()` widths first.

## Limitations

- Vector PDFs only. Stroke-width classes are drawing-style dependent; tune `ExtractionConfig`
  and check the overlay.
- Connectors drawn without a pentagon (some drain boxes) are not detected. Their lines end as
  open runs.
- A line crossing drawn as touching strokes reads as a tee. A crossing with a gap or hop reads
  correctly.
- Inline items other than valves (flanges, reducers, spectacle blinds) are bridged but not
  written as DEXPI components. Valve position (NO/NC) is not read.
- Side streams entering on other sheets get no flow (one builder feed). Twin nozzles are
  labelled with the role total.
- Instrument bubbles are placed but not tied to signal lines or loops.
- Multi-sheet stitching by continuation reference is not done; run sheet by sheet.

## References

- NeqSim Java: `PidDrawingRecordsDexpiWriter`, `DexpiSimulationBuilder`,
  `DexpiXmlSvgRenderer`, `Dexpi201XmlWriter` (docs: `docs/integration/dexpi-reader.md`).
- Skills: `neqsim-pid-process-operations` (P&ID-to-simulation),
  `neqsim-dexpi-conformance-validation`, `neqsim-document-intelligence-extraction` (raster/OCR).
- Company document-system connectors fetch the sheet; this skill reads it.
