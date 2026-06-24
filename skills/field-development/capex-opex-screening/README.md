# CAPEX/OPEX Screening

Educational, dependency-free screening of project cost: a bare equipment cost is
turned into a total installed CAPEX (Lang/Hand-style installation factor plus
contingency), an annual OPEX (fraction of CAPEX plus energy cost), and a
lifecycle total cost of ownership.

This is a transparent placeholder only. For real cost estimates use the
validated NeqSim `CostEstimationCalculator` and the NeqSim MCP
`runFieldEconomics` workflow. See `SKILL.md` for the full method and the
validated NeqSim path.

## Quick Start

```bash
cd skills/field-development/capex-opex-screening
python -m pytest          # run tests from inside the skill folder
python examples/basic_capex_opex.py
```

## Layout

- `src/capex_opex_screening/model.py` — screening model.
- `examples/basic_capex_opex.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
