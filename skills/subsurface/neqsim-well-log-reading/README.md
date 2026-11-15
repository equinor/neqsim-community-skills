# neqsim-well-log-reading

Reads DLIS and LIS well logs with [equinor/dlisio](https://github.com/equinor/dlisio) and LAS 1.2/2.0 with a built-in parser. All three formats load into one model with frames, curves, units, canonical mnemonics and depth in metres. The skill also writes `well_log_evidence.v1` provenance records and does zone and event-window screening.

```bash
pip install -e .[test]
pytest
python -m well_log_reading path/to/log.dlis --out evidence.json
```

See [SKILL.md](SKILL.md) for usage, validation and limitations.
