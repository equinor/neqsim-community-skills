# Asset Value (NPV) Screening

Educational, dependency-free discounted-cash-flow screening: build a year-by-year
net cash flow from revenue, OPEX, and a CAPEX schedule, then return NPV, IRR, and
payback with a simple flat tax.

This is a transparent placeholder only. For real asset economics use the
validated NeqSim field-development DCF utilities and the NeqSim MCP
`runFieldEconomics` workflow. See `SKILL.md` for the full method and the
validated NeqSim path.

## Quick Start

```bash
cd skills/field-development/asset-value-npv-screening
python -m pytest          # run tests from inside the skill folder
python examples/basic_asset_value.py
```

## Layout

- `src/asset_value_npv_screening/model.py` — screening model.
- `examples/basic_asset_value.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
