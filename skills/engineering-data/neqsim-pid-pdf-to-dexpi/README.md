# P&ID PDF to DEXPI

Reads a CAD-exported (vector) PDF P&ID into `neqsim_pid_drawing_records.v1` drawing records:
equipment, nozzle roles, off-page connectors, traced pipe runs, tees, inline valves, instruments
and the sheet data block. It then writes DEXPI with NeqSim's `PidDrawingRecordsDexpiWriter`,
builds and runs the flowsheet, regenerates the P&ID with stream results, and checks the round
trip. The extracted topology is a draft for engineering review; see `SKILL.md`.

## Install

```bash
pip install -e .[test]
```

## Run the tests

```bash
python -m pytest
```

## Example

```bash
python examples/pid_pdf_to_dexpi_example.py sheet.pdf out --jar path/to/neqsim.jar
```
