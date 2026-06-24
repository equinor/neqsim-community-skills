---
name: neqsim-economy-basis-screening
version: "0.1.0"
description: "Educational economy-basis assembly and range-check screening for prices, discount rate, currency, inflation, and tax regime. USE WHEN: a task needs a public, screening-level economic assumptions basis with sanity flags before an asset-value (NPV) screening or detailed NeqSim field-economics modelling."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Economy Basis Screening

Use this skill to assemble and sanity-check the economic assumptions that feed a
downstream asset-value (NPV) screening: gas and oil prices, discount rate,
currency, inflation, and tax regime. It echoes a normalized basis, range-checks
the discount rate against an indicative public band, checks the tax regime
against a small public name set, and raises consistency flags. It is
intentionally simple and should guide users toward the validated NeqSim
field-economics workflow and the NeqSim MCP `runFieldEconomics` tool.

## When to Use

- When a user needs a clean, documented economic-assumptions basis before NPV work.
- When an early concept needs a discount-rate and tax-regime sanity check.
- When an agent needs an upstream "economy basis" feed for an asset-value screening chain.

## Inputs

- `gas_price_per_sm3`: gas price in the chosen currency per Sm3.
- `oil_price_per_bbl`: oil price in the chosen currency per barrel.
- `discount_rate`: real or nominal discount rate (fraction, 0-1).
- `currency`: currency code (default `USD`).
- `inflation_rate`: inflation rate (fraction, default 0).
- `real_terms`: whether the basis is in real terms (default `True`).
- `tax_regime`: tax-regime label (`generic`, `norwegian-ncs`, `uk`, `us`, `none`).

## Outputs

- `currency`, `gas_price_per_sm3`, `oil_price_per_bbl`, `discount_rate`,
  `real_terms`, `inflation_rate`, `tax_regime`.
- `discount_rate_flag`: `ok`, `low`, or `high` vs the indicative band.
- `tax_regime_recognized`: whether the regime is in the public name set.
- `basis_warning`: `ok` or `watch`.
- `flags`: human-readable consistency warnings.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

The skill normalizes the supplied assumptions and applies transparent checks:
the discount rate is compared against an indicative public band (default
6%-12%); the tax regime is checked against a small public name set; and
consistency flags are raised for zero-revenue, or nominal terms with zero
inflation. The verdict is `watch` when any flag is raised, otherwise `ok`.

This skill performs no fiscal, financing, currency-forward, or escalation
modelling. It is a transparent placeholder that must be replaced by a validated
NeqSim field-economics workflow for any quantitative use.

## Python Usage Pattern

```python
from economy_basis_screening import EconomyBasisModel

model = EconomyBasisModel()
result = model.evaluate(
    gas_price_per_sm3=0.30,
    oil_price_per_bbl=70.0,
    discount_rate=0.08,
    currency="USD",
    tax_regime="norwegian-ncs",
)

print(result.discount_rate_flag, result.tax_regime_recognized)
print(result.basis_warning)
for flag in result.flags:
    print(flag)
```

## Validated NeqSim Path

This screening is a placeholder. For real economic evaluation use:

- `neqsim.process.util.fielddevelopment` discounted cash-flow and field-economics
  calculators (NPV, IRR, payback) with tax-regime support.
- The NeqSim MCP `runFieldEconomics` tool for an orchestrated economic evaluation.
- The community `asset-value-npv-screening` skill for a screening NPV from a
  net cash-flow profile that uses this economy basis.

## Escalation

Escalate any `watch` verdict, and any quantitative use, to a validated NeqSim
field-economics workflow and qualified commercial review.
