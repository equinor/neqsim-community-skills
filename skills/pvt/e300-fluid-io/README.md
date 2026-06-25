# neqsim-e300-fluid-io

Read, write, and add water to Eclipse 300 (E300) compositional EOS fluid files
for NeqSim.

This community skill provides:

- A pure-Python E300 reader/writer (no NeqSim required) for inspecting and
  editing the E300 keyword format.
- Water addition using the public PVTsim water parameters (volume shift
  0.084004, parachor 10.0, binary interaction parameter 0.5 against all
  components), reproducing a PVTsim `*_water.e300` file.
- A NeqSim bridge that wraps `EclipseFluidReadWrite` to load E300 files into
  rigorous NeqSim fluids, add water, and export fluids back to E300.

## Capabilities

- Read an E300 file into a NeqSim fluid.
- Read an E300 file and add water in one call.
- Add water to an existing NeqSim fluid or E300 file.
- Write a NeqSim fluid to an E300 file.
- Render a NeqSim fluid as E300 text.
- Parse and document the E300 keyword layout.

## Directory Contents

- [SKILL.md](SKILL.md) — skill standard, format documentation, and usage.
- `src/e300_fluid_io/` — Python package (`format.py`, `neqsim_bridge.py`).
- `examples/` — public example (`build_water_e300.py`, `sample_gas.e300`).
- `tests/` — pure-Python format tests.
- `pyproject.toml` — packaging and test configuration.

## Quick Start

```bash
pip install -e ".[test]"
pytest
python examples/build_water_e300.py
```

The pure-Python path runs without NeqSim. For the NeqSim bridge, install the
optional dependency:

```bash
pip install neqsim
```

## Human Review

Generated fluids, water additions, and E300 files are screening-level outputs.
Qualified review of fluid data, EOS parameters, and water modeling is required
before use in design, assurance, reporting, or operations.

## License

Apache-2.0.
