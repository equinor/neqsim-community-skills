# neqsim-open-incident-data

Keyless client and screening statistics for the US BSEE Data Center incident investigations and platform inventory.

```text
pip install -e .[test]
pytest                                  # offline
NEQSIM_SKILLS_LIVE=1 pytest             # adds one anonymous live download
```

See [SKILL.md](SKILL.md) for the method, caveats and limitations. No dependencies.
