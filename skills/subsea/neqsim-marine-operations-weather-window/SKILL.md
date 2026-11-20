---
name: neqsim-marine-operations-weather-window
calculation_basis: "screening"
version: "1.0.0"
description: "Educational weather-window planning for offshore marine campaigns: a sequence of Hs and wind restricted operations simulated over every start date of a hindcast gives P10/P50/P90 duration including waiting on weather, a monthly view, probability of finishing inside a budget, and a cost ranking of vessel options. USE WHEN: a tie-back, survey, lay, installation or intervention concept needs campaign duration, season choice or vessel option screening before a marine contractor study."
last_verified: "2026-11-20"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Marine Operations Weather-Window Planning

A subsea tie-back is only cheap if the marine spread is not idle. Duration and cost
of survey, lay, installation and intervention campaigns are set less by the work
itself than by waiting for a window in which significant wave height and wind stay
below the limit of each step for long enough to finish it.

This skill makes that explicit and repeatable. A campaign of weather-restricted
operations is replayed from every start date in a hindcast, so the result is a
distribution of total duration (not a single number), a seasonal view, and a cost
comparison of vessel options with different sea-keeping and day rates. It is the
natural input for the marine-operations lever of a strategic tie-back study.

It does not model vessel motions, crane or lift dynamics, or the contractor's
criteria. Limits come from the caller.

## When to Use

- Compare campaign duration and P90 cost for two or more vessels or spreads.
- Choose the start season for a lay or installation campaign.
- Test how much a better-sea-keeping vessel or a lower forecast factor changes
  waiting on weather.
- Give a tie-back screening study a defensible marine duration and cost range
  instead of a fixed number of days.
- Check whether a planned budget in hours or days is likely (probability) to hold.

## When *Not* to Use

- As an installation analysis. Motion, lift, tension and tow analyses belong to
  the marine contractor and the governing standard (for example DNV-ST-N001).
- To set alpha factors or operational limits; supply them from the standard and
  the contractor's operating manual.
- To plan a live operation from a forecast. This is climatological screening.
- With confidential metocean data in a public workspace.

## Inputs

| Input | Meaning |
|---|---|
| `WeatherSeries.hs_m` | Uniformly sampled significant wave height, metres |
| `WeatherSeries.wind_ms` | Optional wind speed, m/s; required if any operation has a wind limit |
| `WeatherSeries.step_h` | Hindcast time step, hours |
| `WeatherSeries.months` | Optional month 1-12 of each sample for the seasonal view |
| `MarineOperation` | `name`, `duration_h`, `hs_limit_m`, optional `wind_limit_ms`, `contingency_fraction`, `forecast_factor` |
| `VesselOption` | `day_rate`, `mobilisation_days`, `hs_limit_scale`, `wind_limit_scale` |
| `start_step_h` | Spacing of simulated start dates (default 24 h) |

## Outputs

| Output | Contents |
|---|---|
| `CampaignStatistics.p10_h/p50_h/p90_h/mean_h` | Total duration distribution, hours |
| `mean_waiting_h`, `working_h` | Average weather waiting and planned working time |
| `by_month_p50_h`, `by_month_p90_h` | Seasonal duration by start month |
| `probability_within(budget_h)` | Share of start dates finishing inside a budget |
| `incomplete_count` | Start dates whose campaign runs past the end of the hindcast |
| `warnings` | Short hindcast, high truncation, no start date completes |
| `VesselRanking` | Vessel, statistics and P50/P90/mean cost, sorted by P50 cost |

## Engineering Method

**Window rule.** An operation can start at sample *i* only if Hs (and wind, when
limited) stay at or below the limit for every sample across its planned duration
(duration plus contingency). Otherwise the spread waits to the next sample that
satisfies this. Operations run in sequence, each from the end of the previous one.

**Forecast factor.** The limit is multiplied by `forecast_factor` (alpha-style), so
a campaign planned on forecasts uses a tighter limit than the contractor's
operating limit. The factor is an input; it is not tabulated here.

**Every start date.** The campaign is replayed from every `start_step_h` sample
across the hindcast. Percentiles over those starts are the climatological
duration distribution; grouping by start month gives the seasonal view.

**Truncation is explicit.** A start whose campaign cannot finish before the
hindcast ends is counted as incomplete and excluded; if more than 20 % are
incomplete the result warns that durations are biased low.

**Vessel ranking.** Limits are scaled by the vessel's sea-keeping factors, the
campaign is re-run, and cost is `(mobilisation_days + duration_h / 24) x day_rate`
at P50, P90 and mean. Ranking is by P50; read P90 for risk.

## Python Usage Pattern

```python
from marine_operations_planning import (
    MarineOperation, VesselOption, WeatherSeries, WeatherWindowPlanner, rank_vessels,
)

weather = WeatherSeries(step_h=3.0, hs_m=hs_series, wind_ms=wind_series, months=month_series)
campaign = [
    MarineOperation("lay flowline", 36.0, 3.0, wind_limit_ms=15.0, contingency_fraction=0.2),
    MarineOperation("lower structure", 8.0, 2.0, forecast_factor=0.8),
    MarineOperation("connect jumper", 12.0, 2.5),
]

stats = WeatherWindowPlanner(weather, campaign).statistics(start_step_h=24)
print(stats.p50_h, stats.p90_h, stats.mean_waiting_h, stats.by_month_p90_h)
print(stats.probability_within(14 * 24), stats.warnings)

ranking = rank_vessels(
    weather,
    campaign,
    [VesselOption("CSV-A", 1.0, mobilisation_days=3),
     VesselOption("CSV-B", 1.3, mobilisation_days=5, hs_limit_scale=1.25)],
)
for entry in ranking:
    print(entry.vessel.name, entry.p50_cost, entry.p90_cost)
```

## Validation Checklist

- The hindcast covers at least 10 years at the site, and `warnings` is empty.
- `step_h` is not coarser than the shortest operation, or the window is rounded up.
- Operation limits and forecast factors are traced to the standard and contractor.
- Contingency is stated per operation, not hidden in the limit.
- `incomplete_count` is small; otherwise the hindcast is extended.
- P90 and seasonal results are read alongside P50, not only the median.
- Vessel scaling factors come from the contractor's capability data.

## Common Mistakes

- Using mean Hs or the percentage of calm hours instead of requiring a continuous
  window over the full operation duration.
- Dropping contingency so the window is exactly as long as the nominal duration.
- Reading only P50 when the cost risk is in the P90 weather tail.
- Comparing vessels on day rate alone while ignoring waiting on weather.
- Using a hindcast too short to give a stable P90.
- Applying a forecast factor and also the contractor's already-reduced limit.

## Limitations

- Screening only; no vessel motion, lift or tow analysis, and no operational
  decision support.
- Hs and wind are the only criteria; period, direction, current and visibility are
  not modelled.
- Operations are strictly sequential; no parallel operations or standby crew rules.
- Window length is rounded up to the hindcast step.
- Weather limits are treated as fixed per operation, with no limit that depends on
  heading or load case.
- Climatology only; no forecast uncertainty beyond the supplied factor.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Companion skills: `neqsim-open-marine-constraints`, `neqsim-pipeline-survey-processing`,
  `neqsim-subsea-layout-geometry`, `neqsim-umbilical-design`
- Public standard for the downstream assessment: DNV-ST-N001 (marine operations
  and marine warranty), for alpha factors and operational criteria.
