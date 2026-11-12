# neqsim-thermoml-experimental-data

Keyless client, parser and comparison helper for the NIST/TRC ThermoML Archive.

```text
pip install -e .[test]
pytest                                  # offline
NEQSIM_SKILLS_LIVE=1 pytest             # adds one anonymous live fetch
```

See [SKILL.md](SKILL.md) for the method, validation checklist and limitations. No dependencies; NeqSim is only
needed for `examples/compare_with_neqsim.py`.
