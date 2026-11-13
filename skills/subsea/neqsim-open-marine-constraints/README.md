# neqsim-open-marine-constraints

Keyless client and route screening for open marine constraint layers: fishing and trawl exposure, protected and
sensitive areas, offshore wind areas, onshore grid, shipwrecks, munitions and earthquakes.

```text
pip install -e .[test]
pytest                                  # offline
NEQSIM_SKILLS_LIVE=1 pytest             # adds anonymous live reads of each service
```

See [SKILL.md](SKILL.md) for the method, caveats and limitations. No dependencies.
