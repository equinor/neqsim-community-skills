---
name: neqsim-jv-cost-control-screening
version: "0.1.0"
description: "Educational JV cost-control toolkit for a non-operating partner: parse JIB-style statements with subtotal checks, rank budget/forecast variances with fact-only commentary, split unit cost into volume and rate effects, check partner-share PI, and reconcile reports by roll-forward and arithmetic identities. USE WHEN: a partner receives JIB, budget, operations and cost-recovery reports from an operator and wants extraction and cross-report controls before human review."
last_verified: "2026-10-21"
calculation_basis: "screening"
requires:
  python_packages: ["pandas", "openpyxl"]
  java_packages: []
  env: []
  network: []
---

# JV Cost Control Screening

Public, screening-level controls for the finance-and-control work of a non-operating
partner. The operator sends four kinds of material: monthly Joint Interest Billing
(JIB, PDF and Excel), an annual budget issued twice a year, a monthly operations
report and a quarterly cost-recovery report. This skill turns the repetitive checks on
that material into tested functions so the controller spends time on explanations
instead of on retyping and re-adding numbers.

It does not account, approve or dispute costs. Every output is a question for the
operator or a number to review; a qualified controller decides.

## When to Use

- A JIB or cost-recovery statement must be loaded into a table and proven to be complete.
- Actual cost must be compared with budget or forecast, with material variances ranked.
- Two reports that should agree (JIB vs operations report vs cost-recovery report) must be reconciled.
- A participating-interest share must be tested against gross amounts.
- A cost overrun must be split into a volume effect and a unit-rate effect.

## Inputs

- Rows of a statement that uses label columns plus numeric columns (for example from `openpyxl`).
- Actual and reference (budget/forecast/plan) tables with matching keys, in one currency and unit.
- Participating interest(s) as fractions, for example `[0.12, 0.12 / 0.9]`.
- Line codes and values of a statement that carries arithmetic identities.

## Outputs

- `ParsedStatement`: tidy `detail` lines and `totals` with the sum of the lines they close.
- `check_subtotals`: totals that do not equal their detail lines, largest first.
- `variance_table` and `variance_commentary`: material variances and fact-only sentences with a
  `TO BE CONFIRMED WITH OPERATOR` cause placeholder.
- `price_volume_split`, `run_rate_outlook`, `outlier_months`.
- `reconcile_tables`, `rollforward_check`, `check_identities`, `interest_share_check`.

## Engineering Method

1. **Parse and prove.** Statements write a hierarchy label only when it changes and close each
   group with `TOTAL <label>`. `parse_hierarchical_rows` forward-fills the labels, keeps TOTAL rows
   separately and records for each TOTAL the sum of the detail lines it closes. A TOTAL with no
   detail since the previous total at its level is a grand total and is checked against the sibling
   totals. Net-zero detail groups are not mistaken for grand totals.
2. **Compare with a reference.** `variance_table` flags a line when the absolute variance and the
   relative variance both exceed thresholds; spend against a zero reference is always material.
3. **Explain with numbers only.** `variance_commentary` states actual, reference, variance and
   percentage. The cause is left as a placeholder so that nothing is invented.
4. **Split the variance.** `price_volume_split` uses
   `volume effect = (V_act - V_ref) x unit_ref` and `rate effect = (unit_act - unit_ref) x V_act`; the
   two add to the total exactly.
5. **Roll forward.** `YTD(t) = YTD(t-1) + month(t)`. When the cost-recovery report ends before the
   previous JIB month, the implied cost of the months in between is compared with the report's
   monthly run-rate.
6. **Identities.** `check_identities` evaluates only `+ - * /`, numbers and line codes (no
   `eval`), with a rounding tolerance.
7. **Share check.** `interest_share_check` tests `share = gross x PI` for any of several PIs. Use
   it on current-month and year-to-date; inception-to-date mixes periods with different PIs.

All methods are educational screening logic.

## Python Usage Pattern

```python
import pandas as pd
from jv_cost_control import (parse_hierarchical_rows, check_subtotals,
                             variance_table, price_volume_split)

rows = [
    ["Area A", "EXPENDITURES", "Drilling", 10.0, 100.0],
    [None, None, None, 20.0, 200.0],
    [None, None, "TOTAL Drilling", 30.0, 300.0],
]
parsed = parse_hierarchical_rows(rows, label_cols=range(3), value_cols={"cm": 3, "ytd": 4})
assert check_subtotals(parsed).empty

df = pd.DataFrame({"acct": ["a", "b"], "actual": [120.0, 52.0], "budget": [100.0, 50.0]})
print(variance_table(df, "actual", "budget", ["acct"], abs_threshold=10.0))
print(price_volume_split(415.6, 38.4, 360.9, 40.3))
```

A complete run on synthetic data is in `examples/basic_jv_control.py`.

## Validation Checklist

- [ ] Every TOTAL in the parsed statement equals its detail lines (or the exception is explained).
- [ ] Currency, unit (USD or MUSD) and basis (100 % or partner share) are identical on both sides of a comparison.
- [ ] A budget version filter is case- and whitespace-insensitive; check the count of rows per version.
- [ ] Reference phasing is stated (linear phasing is a screening assumption).
- [ ] Reports of different dates are rolled forward, not compared directly.
- [ ] Differences are phrased as questions to the operator, not as conclusions.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| A budget version is missing 100+ MUSD | Inconsistent spelling such as `Final forecast` | Normalise the version text before filtering |
| ITD share is 12.9 % instead of 12 % | ITD blends periods with different PIs | Test PI on current month and YTD only |
| Grand total looks wrong | Group nets to zero and was treated as empty | Use detail-line count, not the sum, to detect grand totals |
| JIB area cost does not match the budget area | Common-cost JV is allocated to areas in the cost-recovery report | Compare at phase level, area level only as indication |
| Ops-report and JIB cost differ | Different scope (for example wellwork, allocations) | Reconcile with a scope map, do not force-match |

## Limitations

- No operator-specific layout is included; adapters for a given operator live outside this public skill.
- Variance thresholds and linear phasing are screening choices, not accounting policy.
- The skill never approves, rejects or disputes a cost; it prepares questions.
- Do not store operator data in this repository; examples use synthetic numbers only.

## Related NeqSim Functionality

- This skill supplies finance-control logic around a NeqSim engineering study; it calls no Java class.
- Production volumes used for unit cost can come from a NeqSim process or production model.
- Downstream: `neqsim-capex-opex-screening`, `neqsim-asset-value-npv-screening` and `neqsim-resource-classification-screening` for value and reserves context.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- Common-practice JV accounting terms (JIB, AFE, cost recovery, PSA uplift) are generic industry vocabulary; consult the applicable joint operating agreement and production sharing agreement for definitions.
