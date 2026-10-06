# neqsim-reservoir-history-match-forecast

Compositional material-balance reservoir model for gas and gas-condensate fields with several
formations, compartments and wells: history match, produced-fluid composition versus time,
forecast under a wellhead-pressure limit, and wellstream hand-off to process models.

```text
pip install -e .[test]
pytest
```

The package imports without a JVM; fluid calculations need `jneqsim`. See `SKILL.md` for the
workflow and `examples/two_tank_field.py` for a runnable multi-tank example.
