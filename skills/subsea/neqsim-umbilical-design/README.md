# Umbilical Design and Visualisation

Sizes, checks and draws a subsea umbilical with the NeqSim umbilical physics and writes a study
hand-off (figures, captions, key numbers, evidence status, open items). See `SKILL.md` for the
method, inputs and limitations.

## Install

```bash
python -m pip install -e skills/subsea/neqsim-umbilical-design
```

## Run

```bash
# size from a spec or a study COMMON_BASIS.json with an "umbilical" block (needs NeqSim with the umbilical physics)
python -m umbilical_design run --spec basis.json --out umbilical_workstream

# render figures and HANDOFF.md from a saved result (no JVM needed)
python -m umbilical_design render --result tests/fixtures/sample_design.json --out out --title "Synthetic umbilical"
```

`examples/generate_sample_design.py` regenerates the test fixture from NeqSim.

## Test

```bash
python -m pytest skills/subsea/neqsim-umbilical-design/tests
```
