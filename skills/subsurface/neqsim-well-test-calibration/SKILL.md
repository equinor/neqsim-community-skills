---
name: neqsim-well-test-calibration
calculation_basis: "hybrid"
version: "0.1.0"
description: "Calibrate a well's lift and inflow model on raw test-separator data with NeqSim: recombine the well stream from actual separator gas/oil volumes, convert to stock tank through the real separation train, tune heat transfer U and head factor kH with priors, update inflow only from gauge tests, gate on a held-out test, virtual flow meter from a gauge. USE WHEN: well tests should tune a well model automatically."
last_verified: "2026-11-17"
requires:
  python_packages: [numpy, pandas, neqsim]
  java_packages: []
  env: []
  network: []
---

# Well-Test Calibration from Raw Test-Separator Data

Use this skill to turn each well test into a better well model. Allocated or reported test rates are already converted to standard conditions with a fluid model and a shrinkage factor, so calibrating against them tunes your model to someone else's conversion. This skill starts one step earlier, from what the test separator actually measured: pressure, oil and gas temperature, and the actual oil and gas volume rates at separator conditions. NeqSim recombines the well stream, takes it through the separation train to stock tank, and the recombined fluid then drives the tubing (VLP) model that is tuned to the measured wellhead temperature and the gauge-to-wellhead pressure drop.

The package `well_test_calibration` holds the generic parts. Site data access (historian tags, test databases, fluid sources) stays with the caller.

## When to Use

- A production-optimisation, surveillance or digital-twin task needs per-well lift curves and inflow that track the latest well tests automatically.
- Allocated test rates and a well model disagree and you need to know whether the fluid conversion, the tubing model or the inflow is wrong.
- A well has a downhole gauge and you want its rate between tests (virtual flow meter).
- Thermal behaviour matters (wax, hydrate margin, wellhead temperature as an observation): the heat-transfer coefficient is tuned from the tests.

## Inputs

| Input | Unit | Note |
|---|---|---|
| Test window (start, end) | time | first 10 % dropped (separator still settling) |
| Separator pressure, oil temperature, gas temperature | barg, C, C | window means from the historian |
| Actual gas and oil volume rate at separator conditions | m3/h | raw meters, not flow-computer standard volumes |
| Water rate | m3/h | used for the water-mismatch check against the reported test |
| Separation train after the test separator | [(barg, C), ...] | last stage = stock tank |
| NeqSim fluid of the well's formation | - | tuned to PVT data; water component present |
| Wellhead pressure/temperature, gauge pressure (if any) | barg, C | gauge depth and well geometry for the tubing model |
| Priors on U and kH | - | from design or a previous calibration |

## Outputs

- Recombined composition, mass rate, stock-tank oil and gas, separator gas (compare with the flow computer), shrinkage.
- Per well: fitted U and kH, singular values (identifiability), held-out errors tuned vs prior, `accept` and reason; parameters actually used (prior when not accepted).
- Inflow points (rate, flowing bottomhole pressure) from gauge tests only.
- Virtual-flow-meter rate scale from a gauge pressure.

## Engineering Method

1. **Screen the test.** Drop deduction tests, tests shorter than 0.5 h, unstable tests (oil CV > 30 %) and tests whose raw water differs from the reported water by more than 15 % - the raw window then is not a single-well test (`quality_flags`).
2. **Recombine** (`recombine_separator_volumes`). Flash the formation fluid at separator P/T; convert the measured actual gas and oil volumes to moles with each phase's molar volume (gas meter corrected to its own temperature); add the water; the mole-weighted phase compositions give the well stream.
3. **Stock tank** (`stock_tank_rates`). Re-flash the separator oil stage by stage through the real train. A single flash to standard conditions over-states live-oil volume by several per cent. All liquid volumes are mass/density so that they are on the same basis as the separator molar volumes.
4. **Check before tuning.** Stock-tank oil and gas against the reported test (expect 0.9-1.1), separator gas against the flow computer (expect 1.00 +- 0.02). Large ratios mean the fluid or the meters are wrong - do not tune the tubing to hide them.
5. **Tune the lift model** (`calibrate_well` + `fit_with_priors`). Parameters ln U (heat transfer) and kH (head/holdup factor); observations wellhead temperature (sigma about 1 C) and gauge-to-wellhead pressure drop (sigma about 2 bar); Gaussian priors; damped Gauss-Newton with forward differences (each evaluation is a NeqSim tubing run, so keep iterations few).
6. **Gate** (`accept_calibration`). Refit without the latest test and predict it; accept only if the tuned model beats the prior on it. A single test is accepted only if identifiable. A rejected calibration keeps the prior, so a bad test never degrades the model.
7. **Inflow only from gauges.** Update productivity J only from tests with a measured bottomhole pressure. Inferring Pwf from the tuned tubing and then fitting J to it double-counts the tubing error; in an operating case this degraded choke-move predictions while gauge-only updates did not.
8. **Virtual flow meter** (`rate_from_gauge`). With tuned U and kH and the measured wellhead pressure, find the rate whose bottomhole pressure matches the gauge.
9. **Automate per test.** Keep a seen-set keyed on (test number, wellbore) - deduction groups share a test number - and recalibrate only wells with new tests; merge accepted results into the curve file the network reads.

## Python Usage Pattern

```python
import math

from neqsim import jneqsim
from well_test_calibration import recombine_separator_volumes, calibrate_well, rate_from_gauge

fluid = my_formation_fluid()            # NeqSim fluid with water, tuned to PVT data
r = recombine_separator_volumes(fluid, p_sep_barg=8.8, t_oil_c=58.0, t_gas_c=45.0,
                                gas_act_m3h=1150.0, oil_act_m3h=42.0, water_m3h=60.0,
                                train=((8.8, 60.0), (0.8, 50.0), (0.0, 15.0)))
print(r["oil_Sm3d"], r["gas_Sm3d"], r["shrinkage"])

def predict(case, theta):               # your NeqSim tubing run (e.g. TwoFluidPipe) for one test
    ln_u, kh = theta
    out = run_tubing(case, U=math.exp(ln_u), kH=kh)
    return {"wht": out["wht"], "dp": out["p_in"] - case["whp"]}

res = calibrate_well(cases, predict, prior=(math.log(8.0), 1.0), prior_std=(1.0, 0.2),
                     bounds=((math.log(0.5), math.log(200.0)), (0.6, 1.5)),
                     sigma={"wht": 1.0, "dp": 2.0}, steps=(0.15, 0.05))
if res["accept"]:
    use_parameters(res["theta"])
```

## Validation Checklist

- [ ] Separator gas vs flow computer within +- 2 %; stock-tank oil and gas vs reported test within +- 10 %.
- [ ] Shrinkage between about 0.6 and 1.0 for an oil; above 1 means a water or volume-basis error.
- [ ] Every accepted well beats its prior on the held-out test; the share accepted is reported, not hidden.
- [ ] Identifiability reported; unidentifiable fits lean on the prior and say so.
- [ ] J changed only for wells with gauge tests.
- [ ] Downstream skill (choke-move or production prediction) checked before and after the new curves: no degradation.

## Common Mistakes

- Calibrating to allocated standard rates instead of the raw separator volumes.
- One flash to stock tank instead of the stage path (oil over-stated by several per cent).
- Mixing volume bases: `getVolume()` can omit the volume translation that `getDensity()` includes (10-20 % for an SRK liquid, 1-4 % for a PR78 E300 fluid). Use mass/density everywhere.
- Running without a multiphase check: free water then sits in the "oil" phase and inflates the oil volume.
- Keying tests on the test number alone; deduction tests share a number across wells.
- Updating J from VLP-inferred bottomhole pressure.
- Letting a fit run free without priors on two weakly identifiable parameters.

## Limitations

- Steady state over the test window; slugging and start-up tests are screened out, not modelled.
- U and kH are effective parameters lumping heat transfer, holdup and friction; extrapolation far outside the test rates is uncertain.
- The recombination is only as good as the formation fluid; a wrong fluid shows up as poor checks in step 4.
- Water measured on a separator without a water meter (or with a deduction) cannot be used.

## References

- `neqsim-vfp-lift-curves` (lift tables from the tuned model), `neqsim-model-calibration-and-data-reconciliation` (parameter estimation patterns), `neqsim-dynamic-model-identification` (event dynamics used alongside the tests), `neqsim-continuous-task-improvement` (running this per test in a living task).
- NeqSim TwoFluidPipe and TPflash: <https://github.com/equinor/neqsim>.
