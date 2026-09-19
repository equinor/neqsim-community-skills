---
name: neqsim-ageing-life-extension-screening
calculation_basis: "screening"
version: "0.1.0"
description: "Educational ageing-trend and remaining-life screening for a repairable equipment population from its corrective-failure history: Laplace centroid trend test, Crow-AMSAA / NHPP power-law intensity fit, projection of the failure load to a required end-of-life year, and a maintain-versus-replace economic crossover. USE WHEN: a task asks whether equipment is degrading with age, whether a failure history shows a worsening trend, how many failures to expect between now and a life-extension target year, or whether to keep repairing versus replace, before a qualified life-extension or technical-condition assessment."
last_verified: "2026-09-10"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Ageing and Life-Extension Screening

Use this skill when a maintenance history has to answer a life-extension question: *is this equipment getting worse, and will it still do its job in year N?* It turns a list of corrective-failure dates into a trend verdict, a fitted failure-intensity model, a projection to a target year, and a maintain-versus-replace crossover.

## When to Use

- A life-extension or lifetime-programme decision must be justified from failure history.
- A user asks whether failures are becoming more frequent (ageing) or less frequent (reliability growth).
- A projection is needed of how many failures to expect between today and a required end-of-life year.
- A maintain-versus-replace comparison is needed at screening level.
- A recurring failure has to be characterised across many years of records.

## Do NOT Use For

- A single non-repairable item's time-to-failure distribution — that is a lifetime (Weibull) problem, not a point-process problem.
- Structural fatigue or corrosion remaining-life — those need a damage model, not a failure-count trend.
- A qualified life-extension assessment or regulatory submission. This is screening input to one.

## The Modelling Trap This Skill Exists to Prevent

A population that is **repaired and returned to service** is a stochastic point process, not a lifetime distribution. Fitting a two-parameter Weibull to the *inter-arrival times* of a repairable system and reporting the shape parameter as "the ageing parameter" is a standard and consequential error: it assumes every repair restores the item to as-good-as-new, which is exactly the assumption a life-extension study must not make.

The correct screening statistic is the trend in the **rate of occurrence of failures (ROCOF)**. This skill uses two independent, complementary tests of that trend so a single statistic cannot carry the conclusion alone.

## Inputs

- `failure_times_years`: corrective-failure times in years measured from the start of the observation window, each in `(0, observation_years]`.
- `observation_years`: length of the observation window in years (time-truncated).
- `target_year_offset`: years from the **end** of the window to the required end-of-life. Observed to 2026, required to 2037 ⇒ `11.0`.
- `population_size`: number of items, used to normalise reported rates (default 1).
- `replacement_cost`, `corrective_cost_per_failure`, `annual_cost_of_ownership`, `discount_rate`: optional economics in one consistent currency unit.

## Outputs

- `laplace_u`, `laplace_verdict`: `deteriorating` / `improving` / `no-significant-trend` / `insufficient-data`.
- `crow_amsaa_beta`, `crow_amsaa_lambda`, `beta_confidence_low`, `beta_confidence_high`.
- `rate_now_per_year`, `rate_at_target_per_year`, `rate_ratio_target_over_now`.
- `expected_failures_to_target`, `expected_failures_if_no_ageing`, `excess_failures_from_ageing`.
- `ageing_verdict`: `significant-ageing` / `ageing-suspected` / `no-ageing-detected` / `improving` / `insufficient-data`.
- `life_extension_verdict`: `replace` / `extend-with-measures` / `extend` / `insufficient-data-for-decision`.
- `replacement_crossover_year`: first year in which cumulative discounted keep-cost exceeds replacement cost, or `None`.
- `assumptions`: the public assumptions actually applied.

## Engineering Method

**Laplace centroid trend test.** For a time-truncated process observed over $T$ with failures at $t_i$,

$$
U = \frac{\bar t - T/2}{T \big/ \sqrt{12 n}}, \qquad \bar t = \frac{1}{n}\sum_{i=1}^{n} t_i
$$

$U$ is approximately standard normal under the no-trend (homogeneous Poisson) null. $U > 1.96$ means failures cluster late in the window — deterioration. $U < -1.96$ means they cluster early — improvement. The statistic is scale-invariant, so the choice of time unit cannot change the verdict.

**Crow-AMSAA / NHPP power-law intensity.** The mean cumulative function is modelled as

$$
N(t) = \lambda t^{\beta}, \qquad \rho(t) = \frac{\mathrm{d}N}{\mathrm{d}t} = \lambda \beta t^{\beta - 1}
$$

with the time-truncated maximum-likelihood estimates

$$
\hat\beta = \frac{n}{\sum_{i=1}^{n} \ln\!\left(T / t_i\right)}, \qquad
\hat\lambda = \frac{n}{T^{\hat\beta}}
$$

$\beta > 1$ is an increasing ROCOF (system-level wear-out), $\beta = 1$ is a homogeneous Poisson process, $\beta < 1$ is reliability growth. The asymptotic standard error of $\hat\beta$ is $\hat\beta/\sqrt{n}$, which gives the reported confidence band. **Ageing is only called `significant-ageing` when the lower confidence bound on $\beta$ exceeds 1** — a point estimate above 1 on a short record is not evidence.

**Projection to the target year.** Expected failures between the end of the window $T$ and the target $T + \Delta$ are $\lambda\big[(T+\Delta)^{\beta} - T^{\beta}\big]$, compared against the no-ageing baseline $\bar\rho \Delta$. The difference is reported as `excess_failures_from_ageing` so the ageing penalty is separated from the base load.

**Maintain-versus-replace crossover.** Year-by-year the projected failure count is costed, an annual ownership cost is added, the stream is discounted, and the first year where the cumulative keep-cost exceeds the replacement cost is reported.

## The Data-Quality Gate (read before trusting any verdict)

The trend statistics assume a **stationary reporting regime**. Every real CMMS record set violates that somewhere, and each violation biases the trend in a predictable direction:

| Artefact | Effect on the trend | Required action |
|---|---|---|
| System migration stamping thousands of legacy records on one date | Huge fake early cluster ⇒ false `improving` | Truncate the series to start after the migration date |
| Tags created mid-window (modification, life-extension project) | Fake late cluster ⇒ false `deteriorating` | Normalise by the exposed population per year, or start the window at the tag creation date |
| A yard stay / shutdown period with no operation | Silent gap ⇒ both tests biased | Subtract the non-operating period from the exposure time |
| Campaign inspections raising a burst of notifications | Fake late cluster | Screen campaign-driven notifications out or treat the campaign as one event |
| Change in notification practice (new work-order regime) | Step change in rate misread as ageing | Compare the item's rate against the *plant-wide* rate as a control |

The last row is the strongest defence: **always compute the same trend on a control population** from the same plant and report both. A rising rate that matches the plant-wide rise is a reporting change, not ageing.

## Python Usage Pattern

```python
from ageing_life_extension_screening import AgeingLifeExtensionModel

model = AgeingLifeExtensionModel()
result = model.evaluate(
    failure_times_years=[2.1, 5.4, 8.8, 11.2, 12.9, 14.1, 15.6, 16.4, 17.2, 17.9],
    observation_years=18.0,      # 2008 -> 2026
    target_year_offset=11.0,     # required to 2037
    population_size=168,
    replacement_cost=1.0e7,
    corrective_cost_per_failure=1.2e5,
    discount_rate=0.07,
)

print(result.laplace_verdict, result.crow_amsaa_beta)
print(result.expected_failures_to_target, result.excess_failures_from_ageing)
print(result.ageing_verdict, result.life_extension_verdict)
```

## Interpreting the Verdicts

| `life_extension_verdict` | Meaning | Typical follow-up |
|---|---|---|
| `extend` | No trend evidence and economics do not favour replacement | Keep the current maintenance concept; re-screen at the next review |
| `extend-with-measures` | Trend or economics give one warning but not both | Strengthen the maintenance concept, add condition monitoring, target the dominant failure mode |
| `replace` | Significant ageing AND the keep-cost crosses replacement cost inside the target horizon | Build a replacement business case |
| `insufficient-data-for-decision` | Fewer than four usable failure records | Report the data gap; do not report a rate |

A `replace` verdict is a *screening* signal. It has to be combined with the consequence side — for a safety-critical element, a barrier-performance and regulatory assessment governs, not the economics.

## Validation Checklist

- [ ] At least four usable corrective failure records, otherwise the verdict is
      `insufficient-data-for-decision` and no rate is reported.
- [ ] The data-quality gate above has been walked: migration date, mid-window tag
      creation, yard stays, and campaign inspections all screened out.
- [ ] The same trend has been computed on a plant-wide control population and both
      are reported.
- [ ] `observation_years` covers operating time only, with non-operating periods
      subtracted.
- [ ] Costs are on one basis (same currency, same year) and the discount rate is stated.
- [ ] The verdict is presented as screening, with the consequence side handled
      separately for safety-critical elements.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Strong `improving` trend with no engineering reason | Legacy records stamped on the migration date | Truncate the series to start after the migration |
| Strong `deteriorating` trend across a whole plant | Notification practice changed, not the equipment | Compare against the plant-wide control rate |
| Rate jumps in one year | A campaign inspection raised a burst of notifications | Treat the campaign as one event or screen it out |
| Availability looks worse than field experience | Non-operating periods counted as exposure | Subtract yard stays from `observation_years` |
| `replace` on a protective function | Economics used alone | Add the barrier-performance and regulatory assessment |

## Related Skills and Agents

- `neqsim-reliability-data-screening` — MTBF / availability once a failure rate is agreed. Use this skill first to establish whether that rate is *constant*; use that skill second to turn it into availability.
- `neqsim-safety-function-coverage-screening` — when the item is a protective function.
- `enterprise-life-extension-assessment` — the governed enterprise wrapper: regulatory framing, SAP/STID evidence requirements, safety-critical-element gating, and review handoff.
- `enterprise-maintenance-api` — pulls the corrective-failure history that feeds `failure_times_years`.
- `enterprise-ram-availability` — company acceptance policy on the resulting availability.

## Limitations

- Screening only. Not a qualified life-extension assessment, technical-condition survey, or regulatory submission.
- The NHPP assumes minimal repair; a genuinely as-good-as-new renewal is not represented.
- Verdicts are driven by open thresholds, not by any operator's acceptance criteria.
- No failure-mode resolution: the projection covers all corrective failures together. Split the series by failure mode when one mode dominates.

## References

- ISO 14224, Collection and Exchange of Reliability and Maintenance Data for Equipment.
- NORSOK Z-008, Risk Based Maintenance and Consequence Classification.
- Crow, L. H., Reliability Analysis for Complex, Repairable Systems, in Reliability and
  Biometry, SIAM, 1974 — the Crow-AMSAA / NHPP power-law model.
- Ascher, H., and Feingold, H., Repairable Systems Reliability, Marcel Dekker, 1984 —
  the Laplace trend test and the minimal-repair assumption.
- NeqSim repository: https://github.com/equinor/neqsim
