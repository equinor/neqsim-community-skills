---
name: neqsim-stage-gate-project-timeline
calculation_basis: "screening"
version: "1.0.0"
description: "Educational stage-gate project timelines for field-development screening: prospect maturation (exploration, appraisal, DG1-DG3, execution, first oil at a turnaround), host modification projects scheduled ASAP or just in time with cost in the phases that incur it, and host life-extension decision deadlines, combined into a portfolio plan, capex calendar and Gantt. USE WHEN: a tie-in, area-development or debottlenecking screening must respect that projects take time."
last_verified: "2026-10-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Stage-Gate Project Timeline

Use this skill whenever a screening study would otherwise let a prospect
produce, a host modification add capacity, or a host run past its technical
life "whenever the optimiser wants". Real projects pass stage gates and are
tied in at turnarounds; a decision taken today earns nothing for years. The
skill turns that into explicit timelines so the value model, the ullage
allocation and the report all use the same calendar.

## When to Use

- Tie-in portfolio and timing (which prospects, when): the earliest first-oil
  year per prospect comes from its maturity, not from the first year with ullage.
- Host modification / debottleneck options with capex: the capacity is only
  available after study + DG1-DG3 + execution, at a shutdown; capex falls in
  the execution years, study cost earlier, opex after availability. Compare
  "ASAP" with "just in time for the first prospect that needs it".
- Host technical life (e.g. a technical-lifetime programme ending in year N
  with a pool of not-yet-sanctioned life-extension actions): when must the
  extension be decided, and what does it cost by year.
- Any report that needs a Gantt of the recommended portfolio and a capex calendar.

## Inputs

- Prospect: `name`, `status` (`undrilled` | `discovered` | `appraised` |
  `sanctioned`), optional `phase_years` overrides, `decision_year`,
  `earliest_start_year` (hard floor such as a licence milestone).
- Host project: `id`, `name`, `capex_musd`, `study_cost_musd` (default 5 % of
  capex), `opex_musd_per_year`, `study_years` (DG0), `concept_years` (DG1-DG3),
  `execution_years`, `requires_shutdown` (default true), `earliest_decision_year`.
- Life extension: `programme_end_year`, `pool_by_year` {year: MUSD} of
  unsanctioned actions, `lead_years` (default 5).
- Optional turnaround calendar (default biennial from 2027).

## Outputs

- `prospect_timeline`: phases, `first_production_year`, `exploration_year`, `sanction_year`.
- `project_timeline`: phases, `available_year`, `sanction_year`, `timing`
  (`asap` | `just_in_time`), `cost_by_year_musd`.
- `life_extension_timeline`: phases, `decision_deadline`, `cost_by_year_musd`.
- `portfolio_plan`: Gantt rows for the chosen prospects (development phases
  slide to the chosen first oil, the exploration well stays at its earliest
  year - information first), the selected host projects scheduled just in time,
  the life-extension window, a `capex_calendar_musd` and DG3 / deadline milestones.
- `plot_gantt`: PNG (matplotlib, optional dependency).
- `discounted`: present value of a cost calendar.

## Engineering Method

Phase templates per maturity (years): undrilled = exploration 1, appraisal 1,
DG1-DG2 1, DG3 FEED 1, execution 2 -> first oil 6 years after the decision,
moved to the next turnaround; discovered skips exploration; appraised starts at
concept; sanctioned only executes. A host project is DG0 study -> DG1-DG3 ->
execution and, with a shutdown, becomes available at the next turnaround; just
in time slides the chain so the capacity arrives at the turnaround at or before
the year it is first needed (never earlier than ASAP). Life extension must be
sanctioned `lead_years` before the programme end or before the first action is
due, whichever is earlier.

The screening value of this is in the coupling: in a portfolio evaluation,
`first_production_year` bounds each prospect's start-year search; a project's
capacity multiplier applies to ullage only from `available_year`; its
discounted `cost_by_year_musd` is subtracted from the portfolio EMV; the life
extension pool is compared with the host's own value beyond the programme end
to decide what residual the tie-ins must carry. See the Snorre A tie-in
living task pattern (ullage per option set x {host life as programmed,
extended} x {ASAP, just in time}; net EMV ranks).

## Python Usage Pattern

```python
from stage_gate_project_timeline import (life_extension_timeline, plot_gantt, portfolio_plan,
                                         project_timeline, prospect_timeline)

p = prospect_timeline({"name": "34/9 Ski", "status": "undrilled"}, decision_year=2026)
p["first_production_year"]          # 2033

proj = {"id": "oil_train", "name": "HP separator debottleneck", "capex_musd": 60, "opex_musd_per_year": 1,
        "study_years": 1, "concept_years": 1, "execution_years": 2}
project_timeline(proj, 2026)["available_year"]                    # 2031 (ASAP)
project_timeline(proj, 2026, needed_by=2036)["available_year"]    # 2035 (just in time)

le = life_extension_timeline(2050, {2040: 207.0, 2044: 279.0})
le["decision_deadline"]             # 2039

plan = portfolio_plan(chosen=[{"prospect": "34/9 Ski", "start_year": 2036, "last_year": 2050}],
                      prospects=[{"name": "34/9 Ski", "status": "undrilled"}],
                      project_ids=["oil_train"], projects=[proj], life_extension=le)
plot_gantt(plan, "figures/project_plan_gantt.png")
```

## Validation Checklist

- No chosen start year is earlier than the prospect's `first_production_year`.
- Every host project's capacity multiplier is applied to ullage only from `available_year`.
- `sum(cost_by_year_musd)` of a project equals capex + opex x (horizon - available_year + 1).
- Just-in-time `available_year` is never earlier than the ASAP one, and never later than the first year the capacity is needed (turnaround-rounded).
- The life-extension `decision_deadline` is earlier than the first pooled action year and at least `lead_years` before the programme end.
- The Gantt shows an exploration bar only for `undrilled` prospects.

## Common Mistakes

- Letting the optimiser pick a start year earlier than `first_production_year`: the EMV is then fiction.
- Reading a just-in-time plan without reporting the margin it gives up: show the ASAP-vs-JIT discounted cost difference as the price of a capacity-slip buffer (risk register).
- Deferring the exploration well together with the development: the plan keeps it at the earliest year when the value of information says "drill now".
- Treating life-extension records from a lifetime-management system as funded decisions; they are recommendations.
- Using the default biennial turnaround calendar once the asset's calendar is available.

## Limitations

- Phase durations are generic screening defaults with no resource, rig or vessel constraints and no inter-project interference.
- Costs are placed uniformly within a phase; no S-curve, escalation or currency handling.
- One decision year for everything; staged decisions (drill-or-drop after appraisal) are expressed only through the prospect `status`.
- Detailed scheduling and cost phasing belong to the asset's project planning tool and economics model; NeqSim field-development (`neqsim-field-development`, `neqsim-field-economics`) takes the resulting profiles and capex calendar.

## References

- Stage-gate decision gates DG0-DG4 (public descriptions by operators and regulators) and the FEL 0-3 framework (CII / IPA).
- Typical tie-in portfolio study: ullage per host-option set x {host life as programmed, extended} x {ASAP, just in time}, ranked by net EMV.
- Related skills: `neqsim-field-development`, `neqsim-field-economics`, `neqsim-capex-opex-screening`. Companies add their own governed data (host plans, technical life, committed tie-ins) in a private enterprise skill.
