# Energy & Emissions Screening

Educational, dependency-free roll-up of field-life energy use into emissions:
annual and total CO2-equivalent emissions from a public emission factor, a carbon
intensity (kg CO2e/boe), and an optional CO2-tax cost.

This is a transparent placeholder only. For real emission accounting use the
validated NeqSim combustion path (`Standard_ISO6976`, `GasTurbine`,
`GibbsReactor`) and certified emission factors. See `SKILL.md` for the full
method and the validated NeqSim path.

## Quick Start

```bash
cd skills/environment/energy-emissions-screening
python -m pytest          # run tests from inside the skill folder
python examples/basic_energy_emissions.py
```

## Layout

- `src/energy_emissions_screening/model.py` — screening model.
- `examples/basic_energy_emissions.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
