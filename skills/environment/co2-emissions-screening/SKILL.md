---
name: neqsim-co2-emissions-screening
version: "0.1.0"
description: "Educational combustion-CO2 emission screening that estimates the CO2 mass rate from a fuel-gas flow and composition using public per-component carbon-count stoichiometry and the IPCC basis. USE WHEN: a task needs a public, screening-level CO2 emission rate (kg/s or tonnes/day) from burning a fuel-gas stream before detailed combustion or emission-factor reporting."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# CO2 Emissions Screening

Use this skill for public, educational combustion-CO2 emission screening. It estimates the CO2 mass rate from full combustion of a fuel-gas stream using public per-component carbon counts, so an agent can scope an emission rate before detailed combustion modelling or certified emission-factor reporting.

## When to Use

- When a user asks roughly how much CO2 a fuel-gas stream produces when burned.
- When an agent needs a quick emission rate for turbine, heater, or flare fuel.
- When examples must run without confidential metering or certified emission factors.

## Inputs

- `composition`: dict of component name to mole fraction (normalized internally).
- `molar_flow`: fuel-gas molar flow in mol/s (provide this or `mass_flow`).
- `mass_flow`: fuel-gas mass flow in kg/s (provide this or `molar_flow`).
- `co2_limit_t_per_day`: optional CO2 limit in tonnes/day for the flag.

Supported components: methane, ethane, propane, n/i-butane, n/i-pentane, hexane, CO2, CO, nitrogen, hydrogen, water, oxygen, H2S, helium.

## Outputs

- `mixture_molecular_weight_g_mol`: composition-weighted molecular weight.
- `carbon_per_mole_fuel`: carbon atoms per mole of fuel mixture.
- `co2_mass_rate_kg_s`: CO2 mass rate.
- `co2_mass_rate_t_per_day`: CO2 rate in tonnes/day.
- `specific_co2_kg_per_kg_fuel`: CO2 mass per unit fuel mass.
- `emission_warning`: `ok`, `over-limit`, or `no-limit`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `CombustionCO2Model` uses public combustion stoichiometry:

- the carbon per mole of fuel uses `C = sum(y_i * carbon_number_i)`.
- the CO2 mass rate uses `m_CO2 = n_fuel * C * M_CO2` with `M_CO2 = 44.01 g/mol`.
- complete combustion is assumed, so every fuel carbon atom becomes one CO2; feed CO2 is carried through and counted.
- mass-flow input is converted to molar flow with the composition-weighted molecular weight.

This is educational and screening-only logic. It assumes complete combustion with no combustion efficiency, unburned-carbon slip, flaring loss, or capture credit. It is not a replacement for validated combustion modelling, ISO 6976 calculations, certified emission factors, and qualified reporting.

## Python Usage Pattern

```python
from co2_emissions_screening import CombustionCO2Model

model = CombustionCO2Model()
result = model.evaluate(
    composition={"methane": 0.9, "ethane": 0.07, "co2": 0.03},
    mass_flow=2.0,
    co2_limit_t_per_day=400.0,
)

print(result.co2_mass_rate_t_per_day)
print(result.specific_co2_kg_per_kg_fuel)
print(result.emission_warning)
```

## Related NeqSim Functionality

For validated combustion and gas-quality behaviour, redirect to existing NeqSim classes:

- `neqsim.standards.gasquality.Standard_ISO6976` — calorific value, density, and Wobbe index per ISO 6976.
- `neqsim.process.equipment.reactor.GibbsReactor` — equilibrium combustion product modelling.
- `neqsim.process.equipment.powergeneration.GasTurbine` — fuel-gas consumption and turbine duty.

This skill is a public emission-rate triage layer that decides when to invoke those validated combustion and gas-quality classes.

## Validation Checklist

- [ ] Composition fractions are non-negative and sum to a positive value.
- [ ] Exactly one of `molar_flow` or `mass_flow` is supplied.
- [ ] All components are in the supported list.
- [ ] Tests cover methane stoichiometry, mass-flow basis, inerts/CO2, limit flag, and invalid input.
- [ ] Real emission accounting is redirected to validated NeqSim tools and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Emission too low | Feed CO2 ignored | The model carries feed CO2 through |
| Component rejected | Heavy or uncommon species | Limit to the supported fuel-gas list |
| Wrong basis | Both flows passed | Provide exactly one flow basis |

## Limitations

- Complete combustion only; no efficiency, slip, or capture.
- Limited fuel-gas component set; no heavy hydrocarbons or oxygenates.
- Not a certified greenhouse-gas inventory method.
