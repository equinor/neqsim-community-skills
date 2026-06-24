# Economy Basis Screening

Educational, dependency-free assembly and sanity-check of the economic
assumptions that feed an asset-value (NPV) screening: gas and oil prices,
discount rate, currency, inflation, and tax regime.

This is a transparent placeholder only. For real economic evaluation use the
validated NeqSim field-economics workflow (`neqsim.process.util.fielddevelopment`)
or the NeqSim MCP `runFieldEconomics` tool. See `SKILL.md` for the full method
and the validated NeqSim path.

## Quick Start

```bash
cd skills/field-development/economy-basis-screening
python -m pytest          # run tests from inside the skill folder
python examples/basic_economy_basis.py
```

## Layout

- `src/economy_basis_screening/model.py` — screening model.
- `examples/basic_economy_basis.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
