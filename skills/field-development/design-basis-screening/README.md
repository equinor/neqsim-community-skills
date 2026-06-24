# Design Basis Screening

Educational, dependency-free assembly and margin sanity-check of a screening
design basis: flow, pressure, and temperature design margins versus operating
conditions, plus a standards-basis echo.

This is a transparent placeholder only. For a real design basis use validated
NeqSim mechanical-design classes (`neqsim.process.mechanicaldesign`) and the
applicable standards (ASME, API, DNV, NORSOK). See `SKILL.md` for the full
method and the validated NeqSim path.

## Quick Start

```bash
cd skills/field-development/design-basis-screening
python -m pytest          # run tests from inside the skill folder
python examples/basic_design_basis.py
```

## Layout

- `src/design_basis_screening/model.py` — screening model.
- `examples/basic_design_basis.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
