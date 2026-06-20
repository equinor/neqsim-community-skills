# CO2 Emissions Screening

Educational combustion-CO2 emission screening that estimates the CO2 mass rate from a fuel-gas flow and composition using public stoichiometry (per-component carbon counts) and the IPCC basis. It routes real work to validated NeqSim combustion and ISO 6976 tools.

## Install

```bash
python -m pip install -e skills/environment/co2-emissions-screening
```

## Run Example

```bash
python skills/environment/co2-emissions-screening/examples/basic_co2_emissions_screening.py
```

## Run Tests

```bash
python -m pytest skills/environment/co2-emissions-screening/tests
```

## Public Scope

This skill uses only public combustion stoichiometry and standard molar masses. It is an educational screening placeholder and does not replace validated NeqSim combustion modelling, ISO 6976 calculations, certified emission factors, or qualified reporting.
