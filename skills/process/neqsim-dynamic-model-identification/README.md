# neqsim-dynamic-model-identification

Package `dynamic_identification`. It identifies process models, PID tuning and closed-loop dynamics from historian data with [equinor/TimeSeriesAnalysis](https://github.com/equinor/TimeSeriesAnalysis), called through pythonnet.

```text
<python> -m dynamic_identification setup          # once: publish the .NET assemblies from NuGet (needs dotnet)
<python> -m dynamic_identification run config.json
```

The evidence record is `identification_evidence.json` (`dynamic_identification_evidence.v1`); each result has a `usable` verdict. See [SKILL.md](SKILL.md).
