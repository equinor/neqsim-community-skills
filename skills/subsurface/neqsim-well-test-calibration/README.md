# neqsim-well-test-calibration

Package `well_test_calibration`. It calibrates a well's lift and inflow model on raw test-separator data with NeqSim:
recombination from actual separator volumes, stage-wise stock-tank conversion, tuning of heat transfer U and head factor
kH with priors, a held-out acceptance gate and a virtual flow meter from a downhole gauge.

```text
<python> -m pytest skills/subsurface/neqsim-well-test-calibration
```

See [SKILL.md](SKILL.md).
