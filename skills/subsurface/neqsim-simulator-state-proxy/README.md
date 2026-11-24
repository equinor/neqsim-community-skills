# neqsim-simulator-state-proxy

Reservoir-state proxy tables from Eclipse / OPM Flow summary results, for the NeqSim hybrid
reservoir-well-network production model.

```text
pip install -e .[test]
pytest                      # offline, synthetic summary vectors
pip install -e .[resdata]   # to read SMSPEC / UNSMRY files
```

See [SKILL.md](SKILL.md).
