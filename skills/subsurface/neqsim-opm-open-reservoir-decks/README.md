# neqsim-opm-open-reservoir-decks

Catalog, bounded fetcher and keyword parser for the open `OPM/opm-data` reservoir decks.

```text
pip install -e .[test]
pytest                                  # offline
NEQSIM_SKILLS_LIVE=1 pytest             # adds live checks of grid sizes and tables (anonymous GitHub)
```

See [SKILL.md](SKILL.md). No dependencies.
