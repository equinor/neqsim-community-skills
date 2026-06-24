---
name: neqsim-capex-opex-screening
version: "0.1.0"
description: "Educational factored CAPEX/OPEX screening that turns a bare equipment cost into a total installed CAPEX (Lang/Hand-style installation factor + contingency), an annual OPEX, and a lifecycle total cost of ownership. USE WHEN: a task needs a public, screening-level CAPEX and OPEX magnitude before detailed NeqSim CostEstimationCalculator estimating or qualified cost-engineering review."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# CAPEX/OPEX Screening

Use this skill for a quick, public screening of project cost. Given a bare
equipment cost, it applies a public installation (Lang/Hand-style) factor and a
contingency allowance to estimate a total installed CAPEX, then adds a simple
OPEX (a fraction of CAPEX per year plus an annual energy cost) to produce a
lifecycle total cost of ownership. It is intentionally simple and should guide
users toward the validated NeqSim `CostEstimationCalculator` (Turton / Peters /
Ulrich / Seider correlations with CEPCI escalation) and the NeqSim MCP
`runFieldEconomics` workflow for real estimates.

## When to Use

- When a user wants a first-pass CAPEX and OPEX magnitude for a concept.
- When an agent needs a cost feed for an asset-value / NPV screening chain.
- When examples must run without confidential cost data or licensed estimating tools.

## Inputs

- `bare_equipment_cost_musd`: total bare (uninstalled) equipment cost in million USD.
- `installation_factor`: Lang/Hand-style multiplier from bare to installed cost (default 3.5).
- `contingency_fraction`: contingency added on top of installed cost (default 0.2).
- `opex_fraction_of_capex_per_year`: annual OPEX as a fraction of total CAPEX (default 0.04).
- `annual_energy_use_mwh`: optional annual energy use for the energy-cost term (default 0).
- `energy_price_usd_per_mwh`: optional energy price (default 0).
- `project_life_years`: number of years used for the lifecycle OPEX roll-up (default 20).

## Outputs

- `installed_capex_musd`: bare cost * installation factor.
- `total_capex_musd`: installed CAPEX including contingency.
- `annual_opex_musd`: OPEX-fraction term per year.
- `annual_energy_cost_musd`: energy-cost term per year.
- `total_annual_opex_musd`: sum of the two OPEX terms.
- `lifecycle_opex_musd`: total annual OPEX times project life.
- `total_cost_of_ownership_musd`: total CAPEX plus lifecycle OPEX.
- `capex_warning`: `ok`, `watch`, or `high` (magnitude flag vs a configurable threshold).
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

The factored estimate uses the classic installation-factor approach:
`CAPEX_installed = C_equipment * f_install`, then
`CAPEX_total = CAPEX_installed * (1 + contingency)`. Annual OPEX is
`opex_fraction * CAPEX_total + (energy_use_MWh * energy_price_USD/MWh)`. The
lifecycle roll-up multiplies the total annual OPEX by the project life, and the
total cost of ownership adds CAPEX and lifecycle OPEX. The verdict is a simple
magnitude flag against a configurable CAPEX threshold.

This skill applies no CEPCI escalation, material or pressure factors, location
factor, currency conversion, phasing, financing, depreciation, or abandonment
cost. It is a transparent placeholder that must be replaced by a validated
NeqSim cost estimate for any quantitative use.

## Python Usage Pattern

```python
from capex_opex_screening import CapexOpexModel

model = CapexOpexModel()
result = model.evaluate(
    bare_equipment_cost_musd=120.0,
    installation_factor=3.5,
    contingency_fraction=0.25,
    opex_fraction_of_capex_per_year=0.04,
    annual_energy_use_mwh=180000.0,
    energy_price_usd_per_mwh=60.0,
    project_life_years=20,
)

print(result.total_capex_musd)
print(result.total_annual_opex_musd)
print(result.total_cost_of_ownership_musd)
print(result.capex_warning)
```

## Validated NeqSim Path

This screening is a placeholder. For real cost estimates use:

- NeqSim `CostEstimationCalculator` — equipment-level CAPEX with Turton / Peters /
  Ulrich / Seider correlations, CEPCI escalation, material/pressure factors, and
  AACE class 1–5 (see the `neqsim-equipment-cost-estimation` skill).
- The field-development DCF utilities in `neqsim.process.util.fielddevelopment`
  for CAPEX/OPEX phasing and cash-flow modelling (see `neqsim-field-economics`).
- The NeqSim MCP `runFieldEconomics` tool for an orchestrated economics evaluation.

## Escalation

Escalate any `watch` or `high` verdict, and any quantitative use, to a validated
NeqSim cost estimate and qualified cost-engineering review.

## Validation Checklist

- [ ] Inputs are validated and within stated ranges.
- [ ] Examples use public data only.
- [ ] Screening assumptions are stated explicitly.
- [ ] Limitations are respected.
- [ ] Quantitative use is escalated to validated NeqSim models.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Unrealistic result | Inputs outside the screening range | Keep inputs within the stated bounds |
| Misused for design | Screening output taken as final | Escalate to validated NeqSim models |

## Limitations

- Educational screening only; not a validated design method.
- No confidential data or proprietary methods are included.
- Escalate any quantitative or design use to validated NeqSim workflows.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
