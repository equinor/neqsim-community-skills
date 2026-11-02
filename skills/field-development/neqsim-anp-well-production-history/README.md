# ANP Well Production History

Reads Brazilian ANP well-level production open data into unit-explicit series: parses the four public file families by header, merges onshore, offshore and pre-salt files without double counting, builds well, field and installation histories with gas-liquid ratio and water cut, checks the publication lag and data features, prepares input for a decline fit and a declared fluid basis (API, gas composition, GOR) for NeqSim.

## Install

```bash
python -m pip install -e skills/field-development/neqsim-anp-well-production-history
```

## Run Tests

```bash
python -m pytest skills/field-development/neqsim-anp-well-production-history/tests
python skills/field-development/neqsim-anp-well-production-history/examples/field_history.py
```

## Public Scope

Contains no ANP data beyond two excerpted public rows in the tests and example. Files are downloaded into the task folder with a provenance log. Headers are matched by name; a changed header raises an error.

See [SKILL.md](SKILL.md) for the verified file facts, usage pattern and limits.
