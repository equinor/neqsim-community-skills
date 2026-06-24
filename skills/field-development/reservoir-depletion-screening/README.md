# Reservoir Depletion Screening

Educational, dependency-free screening of how a reservoir develops with time:
year-by-year reservoir pressure, cumulative production, recovery factor, water
cut, and hydrocarbon/water rates from a recoverable volume and offtake rate.

This is a transparent placeholder only. For real depletion behaviour use the
validated NeqSim `SimpleReservoir` tank model (`runTransient`) or the NeqSim MCP
`runReservoir` workflow. See `SKILL.md` for the full method and the validated
NeqSim path.

## Quick Start

```bash
cd skills/field-development/reservoir-depletion-screening
python -m pytest          # run tests from inside the skill folder
python examples/basic_reservoir_depletion.py
```

## Layout

- `src/reservoir_depletion_screening/model.py` — screening model.
- `examples/basic_reservoir_depletion.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
