# neqsim-reservoir-h2s-estimation

Screening estimate of H2S in the gas of a reservoir, prospect or discovery, with an explicit uncertainty and a report.

- `reservoir_h2s.buffer` calls the NeqSim class `ReservoirH2SEstimator` (pyrite and Fe-carbonate buffer) and flashes
  the reservoir fluid to test-separator gas.
- `reservoir_h2s.model` calibrates the buffer against wells with measured H2S: offset and scatter per depositional
  setting, with each well left out in turn.
- `reservoir_h2s.estimate` combines the buffer, the calibration, the uncertainty of the prospect inputs and any
  readings from the discovery into P10, P50 and P90, with a sour-service and gas-specification screening.
- `reservoir_h2s.report` writes Markdown, Word and two figures.

The package holds no measured data. Give it your own well table. See `SKILL.md` for the method and its limits.

```bash
pip install -e ".[report,test]"
pytest
```
