# ANP Open Data

Helpers for reading Brazilian ANP open data safely: oil and gas unit conversion, monthly-to-daily rates, CRS classification, great-circle distance, and a delimited-file reader that maps columns explicitly and fails loudly when a header changes.

## Install

```bash
python -m pip install -e skills/field-development/neqsim-anp-open-data
```

## Run Tests

```bash
python -m pytest skills/field-development/neqsim-anp-open-data/tests
```

## Public Scope

Contains no ANP data. Dataset names, headers, separators and units must be read from the file and its documentation at the time of use.
