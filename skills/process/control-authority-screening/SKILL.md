---
name: neqsim-control-authority-screening
calculation_basis: "screening"
version: "0.1.0"
description: "Educational control-authority screening from a controller output history: saturation fraction at both stops, the trend in saturation across comparable periods, the variance and disturbance-gain ratio between saturated and modulating regimes, off-set-point time, and time-to-limit from the observed rate of change. USE WHEN: a controlled variable has got worse while the disturbance looks unchanged, a control valve is reported wide open or bottomed out, a loop is suspected of having stopped controlling, or a root-cause investigation must separate a growing disturbance from a loop that has run out of authority, before a validated loop performance review."
last_verified: "2026-09-17"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Control Authority Screening

Use this skill to test whether a regulatory loop still has authority. A final control element driven onto its stop can no longer reject a disturbance, so ordinary unchanged variability begins passing straight through to the controlled variable and into a trip. The presenting symptom — "the process got worse" — points outward at the disturbance, while the cause sits inside the loop.

The screening is cheap: it needs a controller output and its process value, two tags that are almost always historised. Run it as a default check before an investigation commits to an external cause.

## When to Use

- A controlled variable has degraded and the disturbance behind it looks unchanged.
- A control valve is reported wide open, bottomed out, or "already doing everything it can".
- An investigation into an external disturbance is being proposed, and the loop has not been ruled out.
- A root-cause analysis presents the symptom "the controlled variable got worse".
- A trip margin must be converted into the time an operator actually has to intervene.

## Inputs

- `controller_output`: controller output history, same units as `output_min` and `output_max`.
- `controlled_variable`: process value history, aligned sample for sample with the output.
- `output_min`, `output_max`: output stops, default 0 and 100.
- `saturation_band`: distance from a stop that still counts as saturated, default 1.
- `sample_interval_h`: sampling interval in hours, default 1.
- `set_point`, `set_point_tolerance`: optional, for the off-set-point fraction.
- `disturbance`: optional aligned disturbance history, for the regime gain fits.
- `limit_value`: optional trip or alarm limit, for time-to-limit.

`compare_periods` takes a sequence of `PeriodObservation(label, saturation_fraction, disturbance_std)` covering comparable periods, for example the same season in successive years.

## Outputs

- `saturation_fraction`, `upper_saturation_fraction`, `lower_saturation_fraction`, `modulating_fraction`.
- `saturated` and `modulating`: `RegimeStatistics` with sample count, mean, standard deviation, disturbance gain, and the gain fit r-squared.
- `variance_ratio`: controlled-variable variance while saturated over variance while modulating — the direct measure of rejection lost.
- `gain_ratio`: disturbance-to-process gain while saturated over the gain while modulating.
- `off_set_point_fraction`, `max_rate_per_hour`, `margin_to_limit`, `time_to_limit_h`.
- `authority_status`: `authority-retained`, `authority-marginal`, or `authority-lost`.
- `warnings`, `assumptions`.
- From `compare_periods`: `saturation_change`, `saturation_relative_change`, `disturbance_change`, `disturbance_relative_change`, `verdict` (`control-authority-loss`, `disturbance-growth`, `both`, `no-significant-trend`, `indeterminate`) and a one-paragraph `narrative`.

## Engineering Method

### 1. Saturation fraction, both stops

A sample counts as saturated when the output sits within `saturation_band` of either stop. Bottoming out removes authority as surely as topping out, so the lower stop is counted too and reported separately.

### 2. Trend in saturation across comparable periods

A single saturation figure says the loop is stressed now. The **trend** is what turns "the process got worse" into "the loop stopped controlling". Compare like with like — the same season, the same production mode — and put the disturbance measure beside it:

| period | disturbance sigma [K] | output saturated |
| --- | --- | --- |
| year 1 | 1.03 | 25 % |
| year 2 | 0.70 | 45 % |
| year 3 | 0.98 | 53 % |
| year 4 | 1.11 | 78 % |

The disturbance is flat; saturation tripled. `compare_periods` returns `control-authority-loss` for this pattern, because nothing is wrong with the disturbance — the plant lost the ability to absorb it.

### 3. Variance ratio between regimes

Split the controlled variable by regime and compare the spread. A variance ratio above one while saturated is the measurement of lost disturbance rejection, in the units the complaint was made in.

### 4. Disturbance gain, fitted separately per regime

Fit the controlled variable against the suspected disturbance in each regime. A gain that rises towards unity as saturation increases is the confirmation: with no authority left, the disturbance arrives undiluted. The gain is only reported as confirmation when the fit supports it — a large slope through scattered points says nothing, so the undamped-passthrough warning requires an r-squared of at least 0.5.

The mirror image is equally informative and is raised as its own finding. In the motivating case the controlled variable moved 0.34 units per unit of the suspected disturbance at r-squared 0.04, so that disturbance explained about 4 % of the variance being complained about — it was not the problem, and the numbers said so before the inspection campaign did.

### 5. Time to limit

The margin to a trip divided by the largest observed rate of change is what decides whether an operator can intervene. A 3 K margin against excursions running at 21 K/h is roughly eight minutes, which is an operability finding regardless of what caused the excursion.

## Python Usage Pattern

```python
from control_authority_screening import ControlAuthorityModel, PeriodObservation

model = ControlAuthorityModel()

result = model.evaluate(
    controller_output=[62.0, 78.0, 95.0, 100.0, 100.0, 100.0, 88.0, 71.0],
    controlled_variable=[18.2, 18.9, 20.4, 22.1, 23.6, 24.9, 21.0, 19.1],
    output_max=100.0,
    saturation_band=1.0,
    sample_interval_h=0.5,
    set_point=19.0,
    set_point_tolerance=0.5,
    disturbance=[11.0, 11.4, 12.2, 12.9, 13.5, 14.1, 12.6, 11.5],
    limit_value=26.0,
)

print(result.authority_status, result.saturation_fraction)
print(result.variance_ratio, result.time_to_limit_h)

trend = model.compare_periods(
    [
        PeriodObservation("year 1", 0.25, 1.03),
        PeriodObservation("year 2", 0.45, 0.70),
        PeriodObservation("year 3", 0.53, 0.98),
        PeriodObservation("year 4", 0.78, 1.11),
    ]
)

print(trend.verdict)
print(trend.narrative)
```

## Related NeqSim Functionality

- `neqsim-controllability-operability` — the design-side question: rangeability, turndown, valve sizing, and whether the element was ever large enough. This skill is the operational counterpart.
- `neqsim-root-cause-analysis` — run this screening before accepting an external cause for "the controlled variable got worse"; see its section on correlation when a controller closes the loop, which is the same loop seen from the other side.
- `neqsim-heat-exchanger-fouling-assessment` — a common reason the authority was consumed: a degraded exchanger pushes the cooling valve open until nothing is left.
- `neqsim-plant-data` — supplies the controller output and process value tags.
- `neqsim.process.equipment.valve.ThrottlingValve` and `neqsim.process.controllerdevice` — validated valve and controller models for a rigorous follow-up.

## Validation Checklist

- [ ] The output stops are the real ones from the controller configuration, not assumed 0 to 100.
- [ ] Output and process value are aligned sample for sample over the same window.
- [ ] Periods compared for trend are genuinely comparable in season, rate, and operating mode.
- [ ] A disturbance measure accompanies every period before a `control-authority-loss` verdict is quoted.
- [ ] The modulating regime has enough samples to act as a baseline.
- [ ] The finding names what consumed the authority, not only that it was consumed.
- [ ] Qualified human review is completed before an inspection or investment decision.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| "The disturbance is getting worse" | Only the controlled variable was trended | Trend the saturation fraction beside the disturbance measure |
| Saturation looks low | Only the upper stop was counted | Count both stops; bottoming out costs the same authority |
| Verdict flips between years | Periods are not comparable | Match season, rate, and operating mode before comparing |
| Gain fit meaningless | Disturbance barely moves in that regime | Check the r-squared; a flat regressor gives no gain |
| Loop blamed, nothing fixed | Saturation reported without its cause | A saturated valve is a symptom; find what consumed the margin |
| Trip arrives without warning | Margin quoted without a rate | Divide the margin by the observed rate to get intervention time |

## Limitations

- Screening on two historian tags; no loop model, no tuning assessment, no valve characteristic.
- Evenly spaced samples are assumed; resampling artefacts are not detected.
- Saturation is detected, not explained — the cause of the lost margin needs a separate analysis.
- The disturbance gain is a single-input linear fit; multiple simultaneous disturbances are not separated.
- No proprietary controller configuration, vendor tuning rules, or company specifications are included.

## References

- IEC 60534-2-1, Industrial-process control valves — flow capacity sizing equations.
- ISA-75.01.01, Flow equations for sizing control valves.
- EEMUA 191, Alarm systems — a guide to design, management and procurement (operator intervention time).
- Shinskey, F. G. — Process Control Systems (valve saturation and loss of regulation).
- NeqSim repository: https://github.com/equinor/neqsim
