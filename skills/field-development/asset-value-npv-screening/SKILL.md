---
name: neqsim-asset-value-npv-screening
version: "0.1.0"
description: "Educational discounted-cash-flow (DCF) asset-value screening that builds a year-by-year net cash flow from revenue, OPEX, and a CAPEX schedule and returns NPV, IRR, and payback with a simple flat tax. USE WHEN: a task needs a public, screening-level NPV/IRR/payback before detailed NeqSim field-development economics or qualified commercial review."
last_verified: "2026-06-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Asset Value (NPV) Screening

Use this skill for a quick, public discounted-cash-flow (DCF) screening of an
asset. Given a year-by-year revenue series, an OPEX series (or a flat value), and
a CAPEX schedule (or a single year-0 spend), it computes net cash flow, discounts
it to a net present value (NPV), and estimates IRR and payback. It is a
transparent placeholder that should guide users toward the validated NeqSim
field-development DCF utilities and the NeqSim MCP `runFieldEconomics` workflow.

## When to Use

- When a user wants a first-pass NPV / IRR / payback for a concept.
- When an agent has a production-and-price revenue profile plus a cost screen.
- When examples must run without confidential fiscal terms or licensed tools.

## Inputs

- `annual_revenue_musd`: sequence of annual revenues in million USD (one per year).
- `annual_opex_musd`: a flat OPEX or a per-year sequence in million USD.
- `capex_schedule_musd`: a single year-0 spend or a per-year sequence in million USD.
- `discount_rate_fraction`: annual discount rate (default 0.08).
- `tax_rate_fraction`: flat tax on positive operating profit (default 0.0).

## Outputs

- `net_cash_flow_musd`: per-year revenue - OPEX - tax - CAPEX.
- `discounted_cash_flow_musd`: per-year discounted cash flow.
- `cumulative_cash_flow_musd`: running (undiscounted) cumulative cash flow.
- `npv_musd`: net present value.
- `irr_fraction`: internal rate of return (or `None` if not identifiable).
- `payback_year` / `discounted_payback_year`: first year cumulative turns non-negative.
- `total_capex_musd` / `total_revenue_musd`: roll-up totals.
- `value_warning`: `ok` (NPV>0), `watch` (NPV=0), or `high` (NPV<0).
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

For each year, operating profit is `revenue - OPEX`; tax is
`tax_rate * max(0, operating profit)`; net cash flow is
`operating profit - tax - CAPEX`. NPV discounts each net cash flow at year-end:
`NPV = sum(CF_t / (1 + r)^t)` for `t = 1..N`. IRR is the rate that zeroes NPV,
found by bisection over a wide bracket (returns `None` when there is no sign
change). Payback is the first year cumulative cash flow becomes non-negative.

This skill models no inflation, depreciation, uplift, ring-fencing, financing,
or working capital. It is a placeholder that must be replaced by validated NeqSim
economics for any quantitative or commercial use.

## Python Usage Pattern

```python
from asset_value_npv_screening import AssetValueModel

model = AssetValueModel()
result = model.evaluate(
    annual_revenue_musd=[0.0, 300.0, 320.0, 280.0, 230.0, 180.0],
    annual_opex_musd=40.0,
    capex_schedule_musd=[600.0, 200.0, 0.0, 0.0, 0.0, 0.0],
    discount_rate_fraction=0.08,
    tax_rate_fraction=0.78,
)

print(result.npv_musd)
print(result.irr_fraction)
print(result.payback_year)
print(result.value_warning)
```

## Validated NeqSim Path

This screening is a placeholder. For real asset economics use:

- The field-development DCF utilities in `neqsim.process.util.fielddevelopment`
  for cash-flow modelling, fiscal regimes, and uncertainty (see the
  `neqsim-field-economics` skill).
- The NeqSim MCP `runFieldEconomics` tool for an orchestrated NPV/IRR evaluation
  with tax regimes (Norwegian NCS, UK, generic) and Monte Carlo sensitivity.

## Escalation

Escalate any `high` verdict, any negative NPV, and any commercial decision to a
validated NeqSim economics evaluation and qualified commercial review.
