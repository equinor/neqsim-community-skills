# P&ID PDF to DEXPI

Reads P&ID PDFs into `neqsim_pid_drawing_records.v1` drawing records:

- equipment and nozzle roles;
- off-page connectors (pentagons and drain/flare boxes);
- traced pipe runs and tees;
- valves with their normal position, plus flanges, reducers and blinds;
- instruments and the sheet data block.

Several sheets are stitched through matching connectors. Scanned sheets are read best-effort
with OCR. The records are written as DEXPI with NeqSim's `PidDrawingRecordsDexpiWriter`, and the
flowsheet is built and run, with side streams as boundary feeds. The P&ID is then regenerated
with stream results and the round trip is checked.

`safety.py` builds a safeguard register from the drawing (trip initiators, shutdown and relief valves, controllers) and runs trip tests, blowdown/flare loads and a HAZOP preparation worksheet with NeqSim. Reviewer corrections are drawn on the regenerated P&ID as revision clouds.

The extracted topology is a draft. A named reviewer approves it through a corrections file; see
`SKILL.md`.

## Install

```bash
pip install -e .[test]          # vector PDFs
pip install -e .[test,raster]   # also scanned sheets (needs the Tesseract OCR engine on PATH)
```

## Run the tests

```bash
python -m pytest
```

## Example

```bash
python examples/pid_pdf_to_dexpi_example.py sheet.pdf out --jar path/to/neqsim.jar
```