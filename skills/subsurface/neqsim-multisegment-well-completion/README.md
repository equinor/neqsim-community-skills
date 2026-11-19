# neqsim-multisegment-well-completion

Package `msw_completion`. It adds inflow-control devices (AICD, spiral ICD, nozzle valve, density-switched / DAR) to Eclipse and OPM Flow decks with [equinor/completor](https://github.com/equinor/completor), and screens them with OPM's device equations and NeqSim phase properties.

```text
<python> -m msw_completion run config.json     # deck -> plain MSW -> completor -> device check -> zonal screening
<python> -m msw_completion devices deck.DATA   # summarise the device layer of a completor deck
```

The evidence record is `completion_evidence.json` (`well_completion_evidence.v1`). See [SKILL.md](SKILL.md) for inputs, equations and limits.

Dependencies are declared in `pyproject.toml`: completor and matplotlib, with neqsim as an optional extra. They are installed with the skill, never at run time.
Completor is available on Python 3.11-3.13 only. Its dependency marker also keeps
the aggregate plugin installable on Python 3.10; this standalone skill still
requires Python 3.11+, and running Completor needs a supported interpreter.
