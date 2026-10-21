# neqsim-jv-cost-control-screening

Educational joint-venture cost-control toolkit for non-operating partners. See
[SKILL.md](SKILL.md) for the method, inputs, outputs and limitations.

```bash
python -m pip install -e ".[test]"
python examples/basic_jv_control.py
python -m pytest
```

The package `jv_cost_control` has four modules:

| Module | Purpose |
| --- | --- |
| `hierarchy` | Parse label-hierarchy statements and prove subtotals |
| `variance` | Variance table, fact-only commentary, volume/rate split, run-rate, outliers |
| `reconcile` | Table reconciliation, roll-forward, arithmetic identities |
| `share` | Participating-interest share checks |

Only synthetic data is used in the examples and tests.
