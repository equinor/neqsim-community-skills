---
name: neqsim-reliability-data-screening
version: "0.1.0"
description: "Educational reliability and availability screening from an ISO 14224 / OREDA style failure rate and repair time, with simple parallel-redundancy and planned-downtime handling. USE WHEN: a task needs a public, screening-level estimate of MTBF, steady-state availability, mission reliability, and expected failures for an equipment item or a simple redundant system before detailed RAM analysis."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reliability Data Screening

Use this skill for public, educational reliability screening. From an ISO 14224 / OREDA style failure rate and a mean time to repair, it estimates mean time between failures (MTBF), steady-state availability with simple parallel redundancy, mission reliability, and expected failures, so an agent can scope a reliability/availability/maintainability (RAM) study before detailed analysis.

## When to Use

- When a user asks for an MTBF, availability, or reliability figure from a failure rate and repair time.
- When an agent needs a quick parallel-redundancy availability estimate.
- When planned downtime must be folded into a screening availability number.
- When examples must run without proprietary OREDA datasets or vendor reliability data.

## Inputs

- `failure_rate_per_year`: failure rate (lambda) in failures per year.
- `mean_time_to_repair_h`: mean time to repair in hours, default 24.
- `redundancy`: number of parallel units (k = 1 of n), integer, default 1.
- `mission_time_years`: mission duration in years for reliability, default 1.
- `planned_downtime_h_per_year`: planned downtime in hours per year, default 0.

## Outputs

- `mtbf_years`: mean time between failures in years.
- `mtbf_h`: mean time between failures in hours.
- `unit_availability`: steady-state availability of a single unit.
- `system_availability`: availability of the redundant system including planned downtime.
- `system_unavailability`: one minus the system availability.
- `reliability_over_mission`: probability of no system failure over the mission time.
- `expected_failures`: expected single-unit failures over the mission time.
- `availability_warning`: `ok`, `watch`, or `low-availability`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `ReliabilityDataModel` uses open reliability relations only:

- MTBF uses `MTBF = 1 / lambda` (years) and `MTBF_h = 8760 / lambda` (hours).
- single-unit availability uses `A = MTBF_h / (MTBF_h + MTTR)`.
- redundant unavailability from failures uses `(1 - A) ** n` for `n` parallel units.
- planned downtime adds `planned_downtime / 8760` to the unavailability, capped at 1.
- mission reliability uses `R = exp(-lambda * t)` for a unit and `1 - (1 - R) ** n` for the parallel system.
- expected failures use `lambda * mission_time` for a single unit.

This is educational and screening-only logic. It assumes a constant failure rate (exponential lifetime), independent identical parallel units, and additive planned downtime. It is not a replacement for validated RAM analysis or a qualified reliability dataset.

## Python Usage Pattern

```python
from reliability_data_screening import ReliabilityDataModel

model = ReliabilityDataModel()
result = model.evaluate(
    failure_rate_per_year=0.5,
    mean_time_to_repair_h=48.0,
    redundancy=2,
    mission_time_years=1.0,
    planned_downtime_h_per_year=24.0,
)

print(result.mtbf_years)
print(result.system_availability)
print(result.availability_warning)
```

## Related NeqSim Functionality

For validated reliability and risk modelling, redirect to NeqSim resources:

- proposed `neqsim.process.reliability.ReliabilityDataset` — ISO 14224 / OREDA dataset ingestion and availability roll-up; candidate NeqSim gap.
- `neqsim.process.diagnostics` — multi-source reliability priors for root cause analysis.
- the `neqsim-process-safety` skill — SIL and risk-matrix methods that consume availability figures.

This skill is a public triage layer that decides when to invoke a validated RAM analysis.

## Validation Checklist

- [ ] Failure rate and mean time to repair are positive.
- [ ] Redundancy is an integer of at least 1.
- [ ] Planned downtime is in [0, 8760) hours per year.
- [ ] Tests cover MTBF, single-unit availability, redundancy improvement, planned downtime, and invalid input.
- [ ] Real RAM work is redirected to validated NeqSim resources and qualified datasets.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Availability unchanged by redundancy | `redundancy` left at 1 | Provide the number of parallel units |
| Availability above 1 | Planned downtime not capped | Model caps unavailability at 1 automatically |
| `low-availability` always shown | Very high failure rate or repair time | Check the OREDA basis for the inputs |

## Limitations

- No proprietary OREDA datasets or vendor reliability data are included.
- A constant failure rate (exponential model) is assumed; no wear-out is modelled.
- Parallel units are assumed identical and independent (no common-cause factor).

## References

- ISO 14224, Petroleum, petrochemical and natural gas industries — Collection and exchange of reliability and maintenance data for equipment.
- OREDA, Offshore and Onshore Reliability Data Handbook.
- IEC 61508, Functional safety of electrical/electronic/programmable electronic safety-related systems.
- NeqSim repository: https://github.com/equinor/neqsim
