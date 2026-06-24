---
name: neqsim-energy-emissions-screening
version: "0.1.0"
description: "Educational field-life energy and CO2-equivalent emissions roll-up that turns a year-by-year energy use into annual and total CO2e, a carbon intensity (kg CO2e/boe), and an optional CO2-tax cost. USE WHEN: a task needs a public, screening-level field-life emissions and carbon-intensity picture before detailed NeqSim combustion modelling or certified emission reporting."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Energy & Emissions Screening

Use this skill for a quick, public roll-up of field-life energy use into
emissions. Given a year-by-year energy use (MWh), a public emission factor, and an
optional production profile, it returns annual and total CO2-equivalent
emissions, a carbon intensity in kg CO2e per barrel of oil equivalent, and an
optional CO2-tax cost. It complements the instantaneous combustion skill
`neqsim-co2-emissions-screening` by aggregating over the field life and adding
carbon intensity and cost.

## When to Use

- When a user wants total and per-year CO2e and a carbon intensity for a concept.
- When an agent needs an emissions/cost feed for an asset-value chain.
- When examples must run without certified emission factors or confidential data.

## Inputs

- `annual_energy_use_mwh`: sequence of annual energy use in MWh (one per year).
- `emission_factor_kg_co2e_per_mwh`: public emission factor (default 450).
- `annual_production_boe`: a flat value or a per-year sequence in boe (default 0).
- `co2_tax_usd_per_tonne`: optional CO2 tax (default 0).

## Outputs

- `annual_co2e_tonnes`: per-year CO2-equivalent emissions in tonnes.
- `total_co2e_tonnes`: total field-life CO2e in tonnes.
- `total_energy_use_mwh`: total field-life energy use.
- `carbon_intensity_kg_per_boe`: total CO2e (kg) divided by total production (boe), or `None`.
- `annual_emission_cost_musd` / `total_emission_cost_musd`: CO2-tax cost in million USD.
- `intensity_warning`: `ok`, `watch`, `high`, or `no-production`.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

Annual CO2e is `energy_use_MWh * emission_factor_kg/MWh / 1000` (kg to tonnes).
Total CO2e and total energy are the year sums. Carbon intensity is
`total_CO2e_kg / total_production_boe` (undefined when production is zero). The
CO2-tax cost is `annual_CO2e_tonnes * tax_USD/tonne / 1e6` (million USD). The
verdict compares carbon intensity to a configurable threshold (default 17 kg
CO2e/boe, a public global-average order of magnitude).

This skill uses a single public emission factor and models no combustion
efficiency, methane slip, flaring, venting, allowances, or capture credit. It is
a placeholder that must be replaced by validated NeqSim combustion modelling and
certified emission factors for any quantitative or reporting use.

## Python Usage Pattern

```python
from energy_emissions_screening import EnergyEmissionsModel

model = EnergyEmissionsModel()
result = model.evaluate(
    annual_energy_use_mwh=[120000.0, 180000.0, 175000.0, 150000.0, 120000.0],
    emission_factor_kg_co2e_per_mwh=450.0,
    annual_production_boe=[3.0e6, 7.0e6, 6.5e6, 5.0e6, 3.5e6],
    co2_tax_usd_per_tonne=85.0,
)

print(result.total_co2e_tonnes)
print(result.carbon_intensity_kg_per_boe)
print(result.total_emission_cost_musd)
print(result.intensity_warning)
```

## Validated NeqSim Path

This screening is a placeholder. For real emission accounting use:

- NeqSim `neqsim.standards.gasquality.Standard_ISO6976` for calorific value.
- NeqSim `neqsim.process.equipment.powergeneration.GasTurbine` for fuel-gas
  consumption and turbine duty.
- NeqSim `neqsim.process.equipment.reactor.GibbsReactor` for equilibrium
  combustion products, and the `neqsim-co2-emissions-screening` skill for a
  per-stream combustion-CO2 rate.

## Escalation

Escalate any `high` verdict, any reporting use, and any carbon-tax exposure to
validated NeqSim combustion modelling, certified emission factors, and qualified
environmental reporting.
