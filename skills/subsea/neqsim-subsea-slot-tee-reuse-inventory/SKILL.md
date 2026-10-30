---
name: neqsim-subsea-slot-tee-reuse-inventory
calculation_basis: "screening"
version: "0.1.0"
description: "Inventory of tie-in capacity in existing subsea infrastructure (free template/manifold slots, spare tees and hubs, J-tube/riser slots, spare or reusable pipelines, flowlines, gas-lift, injection and MEG lines, umbilical cores) with status, size, remaining life, source and verification level, and a reuse-versus-new-build ranking. USE WHEN: a tie-in needs to know which existing slots, tees or lines can be used or re-purposed, or which line could raise production."
last_verified: "2026-10-30"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["Sodir DataService (only when live open data is read)"]
---

# Subsea slot, tee and reusable-line inventory

Answers "what can we plug into, and is it better than a new line?" before a tie-in study. It keeps four things apart
that are usually mixed: **what exists** (inventory), **whether it is free** (status + verification), **whether it works
for this fluid and rate** (capacity, hydraulics, compatibility) and **whether it lasts the horizon** (lifetime action).

## When to Use

- A discovery, satellite or infill target needs a tie-in point: which templates/manifolds have free slots, which tees or
  hubs are spare, which lines are spare, abandoned or could be re-purposed.
- A host wants more production from existing assets: gas lift through an existing line, converting an injection line,
  re-routing or looping, adding wells on free slots, using a spare umbilical core for chemical/MEG supply.
- Reuse must be compared with a new-build tie-back on distance, capacity, arrival pressure, flow-assurance
  compatibility, remaining life and cost class.
- The result must be handed to `export-tie-in-concept-agent`, `surf-design-study`, `tie-in-screening-agent` or an
  area-development study.

## Inputs

- Inventory JSON (`neqsim.subsea_infrastructure_inventory.v1`, schema in `data/subsea_infrastructure_inventory.schema.json`):
  per item `id`, `kind` (host, template, manifold, slot, tee, hub, plet, plem, well, pipeline, flowline, riser, j_tube,
  riser_slot, umbilical, umbilical_core, spool, gas_lift_line, injection_line, meg_line, chemical_line, cable), `status`
  (in_use, spare, abandoned, planned, unknown), `service`, `size_in`, `pressure_rating_bar`, `length_km`, `fluid`,
  `capacity`, `install_year`, `design_life_years` or `remaining_life_years`, `condition`, `total_slots`/`free_slots`,
  `hub_type`, `position {lat, lon}`, `connects`, `repurpose_option`, `source`, `verification`
  (measured, documented, estimated, unknown).
- Open data: Sodir facilities, pipelines, wells (`items_from_sodir`). Sodir does **not** publish free slots or spare
  lines: slots come out `estimated`, nothing is called spare.
- Target: position, host position, service, rate and unit, source pressure, minimum arrival pressure, design pressure,
  horizon end year, fluid flags (wax, hydrate_prone, h2s_ppm).

## Outputs

- Validation issues (errors, warnings such as "free slots are estimated: do not present as free").
- `summarize`: counts by kind/status, free slots by verification tier, spare line km by service.
- `free_slot_table`: total, free, in use, verification, `usable_as_free` (documented or measured only).
- `rank_reuse_options`: options (slot, hub, reuse_line, new_build) with score 0-100 and components, new/reused km,
  cost index (new-build = baseline), screening dp, arrival pressure, capacity check, lifetime action, flags, needs.
- `handoff(ranking, target, consumer)` for export-tie-in-concept, surf-design-study, tie-in-screening, area-development.

## Engineering Method

1. Build the inventory per host from the best available source and tag every item with `source` and `verification`.
   Prefer documents (slot registers, line lists, P&IDs, as-built) over map layers over open data. Mark unknowns as
   `unknown` - never as free.
2. Validate (`validate_inventory`). Estimated free slots and "believed spare" lines stay visible as warnings.
3. Rank against a new-build baseline (`rank_reuse_options`). Weights (fixed, stated): distance 25, capacity 20,
   hydraulics 20, compatibility 15, lifetime 10, cost 10; availability that is estimated/unknown costs 5 points and
   a flag. Distance uses great-circle x 1.15; hydraulics is single-phase Darcy with a density guess; line capacity is the
   API RP 14E erosional limit (C = 100); compatibility is a service-conversion table with rating/wax/hydrate/sour flags.
4. Lifetime (`lifetime_check`): remaining life vs the tie-in horizon gives **ok / monitor / life-extend / refurbish /
   replace / data-gap**. Report the action for every reused item and add it to the cost index. The owner's technical
   lifetime case decides; screening never replaces it.
5. Hand off with the flags: a slot is evidence of free slots only; host ullage, flow assurance and integrity studies
   follow before any commitment.

## Python Usage Pattern

```python
import json
from subsea_slot_tee_reuse import rank_reuse_options, free_slot_table, handoff, validate_inventory

inv = json.load(open("inventory.json"))
target = json.load(open("target.json"))
issues = validate_inventory(inv, 2026)
ranking = rank_reuse_options(inv, target, as_of_year=2026)
print(free_slot_table(inv, 2026))
print(handoff(ranking, target, "export-tie-in-concept"))
```

Command line: `python -m subsea_slot_tee_reuse inventory.json target.json --consumer area-development`.

## Validation Checklist

- [ ] Every item has `source` and `verification`; no slot or line is "free/spare" without documentation.
- [ ] Positions present for items that must be ranked by distance; otherwise the gap is stated.
- [ ] Rating, size and service of each reused line recorded; service conversions flagged.
- [ ] Remaining life or install year + design life recorded; lifetime action reported for every reused item.
- [ ] New-build baseline included and the advantage in points and cost index reported.
- [ ] `needs` (host ullage, spool/tie-in hardware, inspection) copied to the hand-off.

## Common Mistakes

- Treating a Sodir facility row as proof of a free slot (it is not).
- Ranking on distance only: a short but undersized or end-of-life line is worse than a longer new line.
- Reusing an injection line for production without checking materials, coating, rating and flow regime.
- Ignoring the lifetime horizon: a line that expires before plateau end is a replacement cost, not a reuse.
- Presenting the score as a decision: it orders options for study, it does not qualify them.

## Limitations

Screening only. Distance is great-circle x 1.15 (no seabed route); hydraulics is single-phase; no slugging, hydrate,
wax or corrosion modelling (hand-off to NeqSim flow-assurance skills); no host ullage; costs are relative to new-build
(AACE class 5). Cost factors and weights are defaults to be calibrated per study. Company slot registers, P&IDs and
lifetime cases are not in this public skill (see the enterprise skill `enterprise-infrastructure-slot-capacity`).

## References

- Sodir DataService / FactPages (facilities, pipelines, wells), NLOD 2.0.
- API RP 14E (erosional velocity), DNV-ST-F101 (submarine pipelines), DNV-RP-F116 / API 17N (integrity and life extension
  context), NORSOK U-001 (subsea production systems) for slot and tie-in terminology.
- Related skills: `neqsim-ncs-infrastructure-network`, `neqsim-tie-in-pipeline-concept`, `neqsim-tie-in-pid-sketch`,
  `neqsim-subsea-layout-geometry`, `neqsim-field-layout-import`, `neqsim-ageing-life-extension-screening`,
  `neqsim-pipe-route-profile`, `neqsim-production-network-routing`.
