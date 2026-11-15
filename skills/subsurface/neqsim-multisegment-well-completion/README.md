# neqsim-multisegment-well-completion

Package `msw_completion`. It adds inflow-control devices (AICD, spiral ICD, nozzle valve, density-switched / DAR) to Eclipse and OPM Flow decks with [equinor/completor](https://github.com/equinor/completor), and screens them with OPM's device equations and NeqSim phase properties.

```text
<python> -m msw_completion run config.json     # deck -> plain MSW -> completor -> device check -> zonal screening
<python> -m msw_completion devices deck.DATA   # summarise the device layer of a completor deck
```

The evidence record is `completion_evidence.json` (`well_completion_evidence.v1`). See [SKILL.md](SKILL.md) for inputs, equations and limits.

Dependencies are declared in `pyproject.toml`: completor and matplotlib, with neqsim as an optional extra. They are installed with the skill, never at run time.
