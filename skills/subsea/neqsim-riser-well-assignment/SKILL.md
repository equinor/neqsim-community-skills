---
name: neqsim-riser-well-assignment
calculation_basis: "screening"
version: "1.0.0"
description: "Mixed-integer optimisation of which well connects to which riser and manifold: splitter risers (several wells per riser), LP-only and HP-only risers, temperature-limited injection risers, riser reach versus well slot, shared manifold and facility limits, and ROV swap cost, shut-in loss and swap budget over multi-year periods. USE WHEN: planning or reviewing a riser plan, a riser swap campaign or well-riser pairing on a floating host."
last_verified: "2026-11-23"
requires:
  python_packages: [numpy, scipy]
  java_packages: []
  env: []
  network: []
---

# Riser-Well Assignment Optimizer

On a floating host with a limited number of risers, production is often limited
by *which well hangs on which riser* rather than by the wells themselves. A riser
can serve one well, or three through a splitter. It reaches only some well slots.
It may be lined up to only the LP or only the HP manifold. An injection riser may
have a temperature limit most producing wells exceed. Moving a riser takes an ROV
campaign: days of work, cost and lost production.

This skill turns that into a mixed-integer linear program (HiGHS through
`scipy.optimize.milp`) that returns the best pairing, the swaps that are worth
doing, and the value-versus-number-of-swaps curve for choosing a campaign size.
It carries no field data: wells, risers, reach and rates are inputs.

## When to Use

- Which wells should be on which risers, and on HP or LP, to maximise production or value?
- Which swaps pay back the ROV cost and the shut-in loss? How many are worth doing?
- Which constraint binds (manifold gas, water, riser rate, reach, temperature, capacity)?
- What does a new riser limit, a changed well temperature or a manifold debottleneck do to the plan?

## Engineering Method

Per planning period `t` (a year, a quarter, or one period for a static case):

| Variable | Meaning |
|----------|---------|
| `z[w,r,t]` binary | well `w` is physically connected to riser `r` (persists while the well is shut in) |
| `x[w,r,m,t]` binary | the connected well flows through riser `r` to manifold `m` |
| `u[w,r,m,t]` in `[0,x]` | fraction of the well rate allowed (choking), optional |
| `L[r,m,t]` binary | riser `r` is lined up to manifold `m` (one manifold; persists while idle) |
| `mv`, `dm`, `sib`, `ms` | new connection (ROV swap), disconnection, sibling shut-in on a disturbed splitter riser, new line-up |

Constraints: at most one riser per well; riser capacity (1, or 3 with a splitter) on
connections; all flowing wells on a riser share its manifold; allowed manifolds per riser
(LP-only, HP-only); reach set (explicit, or distance against a required `max_reach_m`);
temperature limit of a riser against the well flowing temperature in each period (unknown
temperature excludes the pairing unless `unknown_temp_policy` is `allow`); capacity limits
per manifold, per riser, per riser and manifold (`limits_by_manifold`, for example a gas
velocity limit that is lower on the low-pressure header) and total for any stream (every limited stream must exist in every
well rate table, or be a `derived_streams` sum such as liquid = oil + water); swap budget in
total and per period; `available: false` reserves a riser (for example for injection duty);
`lock_manifolds` keeps every riser lined up as today.

Objective: `sum(days * value * rate * u) - swap costs - disconnect costs - sibling losses - line-up costs`.
A swap costs `rov_cost_per_swap + swap_days * best-case revenue rate of the moved well` (never
negative); a well-specific `swap_cost` overrides it. When a splitter riser is disturbed, each
sibling well that stays connected is charged `swap_days * revenue rate` (`sibling_shutin`).
A well that is only shut in keeps its connection and is not a swap. A first connection of an
unconnected well counts as a swap, so a zero swap budget leaves unconnected wells off.
`evaluate()` recomputes value and every violation from a plan with separate code; `check_solution`
fails when the plan is missing, a constraint is broken, or the MILP and the accounting disagree.

## Inputs

```json
{
  "wells":  [{"id": "W01", "slot": "S01", "current_riser": "R05",
              "temp_c": [95, 93, 90],
              "rates": {"HP": {"oil": [800, 700, 600], "gas": [200, 180, 160], "water": [100, 150, 200]},
                        "LP": {"oil": [1100, 950, 800], "gas": [270, 240, 210], "water": [140, 200, 260]}}}],
  "risers": [{"id": "R05", "capacity": 3, "manifolds": ["HP", "LP"], "current_manifold": "HP",
              "max_temp_c": null, "limits": {"liquid": 6000}}],
  "distance_m": {"W01": {"R05": 1450}},
  "manifold_limits": {"HP": {"gas": 2400, "water": 6000}, "LP": {"gas": 1500}},
  "total_limits": {"oil": 30000},
  "config": {"period_days": [365, 365, 365], "stream_value": {"oil": 60},
             "swap_days": 4, "rov_cost_per_swap": 250000, "max_swaps_per_period": 4}
}
```

`reach` (`{"R05": ["W01", ...]}`) can replace `distance_m` + riser `max_reach_m`.

**Production profiles.** Every rate and temperature accepts one value per planning period, so a forecast is
supplied as lists: `rates.HP.oil = [y1, y2, y3]`, `temp_c = [..]`, `period_days = [365, 365, 365]`. The rate of a
well on each header and period is the profile at the current header times a header factor from the well's
deliverability. A well that arrives later (restart, new well) has zero rates until its start period; it needs no
swap if it is already connected (`current_riser`). The optimizer then plans swaps over time, because a limit that
does not bind today (riser gas velocity, header gas, temperature) can bind or release as rates fall. Field-level
forecasts (for example a Centuries profile) are allocated to wells by the caller; the optimizer does not allocate.
When the allocation is uncertain, run the optimizer on a lower and an upper profile and report both.
Header and riser limits (`manifold_limits`, `total_limits`, riser `limits` and `limits_by_manifold`) also accept
one value per period, so capacity taken by new wells, tie-backs or a compressor derate is modelled as a lower
limit in the periods it applies (for example `"LP": {"gas": [2150, 2040, 1960]}`); a scalar applies to all
periods and a list must have one value per period. New wells that are not part of the pairing are entered this
way, not as wells; their own revenue is then outside the reported gain.
Rates per manifold come from well deliverability against the manifold pressure,
for example NeqSim well and flowline models (skill `neqsim-integrated-production-and-lifecycle`,
`WellDeliverabilityCurve`) or a well-test matched IPR/VLP. Use the *same* manifold
pressure basis for HP and LP as the topside model.

## Python Usage Pattern

```python
from riser_well_assignment import load_problem, solve, check_solution, pareto_swaps

problem = load_problem(data)
best = solve(problem)                 # optimal plan with swap budget from config
as_is = solve(problem, 0, lock_manifolds=True)  # nothing moved, line-ups as today
assert check_solution(problem, best) == []      # independent constraint check
curve = pareto_swaps(problem, [1, 2, 4, 6, 8, 10])   # baseline is always an explicit zero-swap solve
```

Command line: `python -m riser_well_assignment problem.json --pareto --lock-manifolds --out result.json`
(`--synthetic` runs the built-in demonstration instance, which is invented data).

## Outputs

- `plan.connections`, `plan.flows`, `plan.lineups` per period; `assignment` lists the flowing wells.
- `moves` lists each new well-riser connection with its period and cost.
- `binding_limits` names the capacity rows at their limit: where a debottleneck pays.
- `unproducible_wells` never flow (reach, temperature, capacity or economics).
- `pareto_swaps` gives net value per swap budget; stop where the marginal gain is
  below the uncertainty in the rates.
- Solver `status` is `optimal` or `time_limit`; report `mip_gap` when not optimal.

## Validation Checklist

- `check_solution` returns no violations (reach, temperature, capacity, line-up, limits, budget, MILP versus accounting).
- The as-is reference (`solve(problem, 0, lock_manifolds=True)`) reproduces today's production within the rate-table accuracy.
- On small cases the result equals `brute_force` for one and two periods with every transition cost (covered by the tests).
- Each reported swap has a payback: gain over the as-is case exceeds its cost and shut-in loss.
- Manifold pressures behind the HP and LP rate tables match the topside model.
- Re-simulate the chosen plan in the network or topside model before it goes to the subsea team.

## Common Mistakes

- Using one rate table for HP and LP: the benefit of moving a well to LP is the rate difference.
- Treating reach or temperature as soft: both are hard exclusions in the model.
- Forgetting that wells on a splitter riser all go to the same manifold.
- Reading `optimal` for a `time_limit` run without checking `mip_gap`.
- Counting only ROV cost and ignoring the shut-in loss of the moved wells and their splitter siblings.
- Comparing against a baseline that is allowed to change manifold line-ups; use `lock_manifolds`.
- Using wellhead temperature as riser temperature: the riser inlet is cooler by the flowline heat loss.

## Limitations

- Rates are fixed per manifold and period; choking scales them linearly. Shared
  back-pressure between wells, riser hydraulics, gas-lift allocation and slugging are not
  modelled; they enter through the rate table or a stream limit, and the result must be
  re-simulated.
- Reach is binary. Slot-to-riser clearance, jumper length and ROV access need
  the subsea team; encode them as `reach` or `pinned_riser`.
- A swap is one new well-riser connection and no ROV schedule is modelled: durations do not
  overlap or queue. Disconnection is free unless `disconnect_cost` is set.
- Injection duty is not modelled; reserve injection risers with `available: false`.
- Time-expanded cases (four or more periods) can stop on the time limit with a gap of
  about 0.5 %; check `mip_gap` and shorten the horizon or raise the limit if it matters.
- Screening: the plan needs review against the subsea integrity, marine and operations teams.

## Handoffs

- Rate tables: `neqsim-integrated-production-and-lifecycle`, `neqsim-production-system-modeling`.
- Binding topside limits: `neqsim-capacity-and-utilization-analysis`.
- Value of extra capacity: `neqsim-field-economics`.

## References

- Mixed-integer linear programming with HiGHS: Huangfu and Hall, Mathematical Programming Computation 10 (2018) 119-142.
- Assignment and generalised-assignment formulations: Martello and Toth, Knapsack Problems (1990).
