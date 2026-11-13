---
name: neqsim-brazil-presalt-well-reach-and-layout
calculation_basis: "screening"
version: "0.1.0"
description: "Drilling-reach constraints for Brazilian deepwater pre-salt SURF layouts: wells are near vertical (max about 30 deg) with about 500 m step-out, so templates and drill centres are replaced by loops or daisy chains of single vertical wells. USE WHEN: a Santos or Campos pre-salt layout, well count, drill-centre or template question, or well step-out check is requested. Not for the NCS or other regions."
last_verified: "2026-11-13"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Brazil Pre-Salt Well Reach and Layout

Advisory skill. In Brazilian deepwater pre-salt fields the well-construction (D&W) limits decide the subsea layout, not the other way round. A generic layout tool places multi-slot templates and drill centres; that is wrong for these fields unless D&W confirms otherwise.

## When to Use

- A layout, tie-back, well count or concept study for a Santos or Campos Basin pre-salt field or block (deep water with a salt overburden above the reservoir).
- Someone proposes templates, drill centres or manifolds for such a field, or asks how many drill centres are needed.
- A well position, step-out or deviation has to be checked against the reservoir target.
- A SURF cost take-off must count trees, manifolds and flowline loops for a pre-salt concept.

Do not apply this outside Brazilian deepwater pre-salt. Other regions (NCS, West Africa, Gulf of Mexico) keep the generic template and drill-centre logic unless the project states its own limits.

## Inputs

Ask D&W for these; the defaults apply only to Brazilian pre-salt and must be shown as assumptions when used.

| Input | Default (pre-salt) | Source to cite |
|-------|--------------------|----------------|
| Maximum inclination | 30 deg | D&W premise |
| Maximum horizontal step-out, surface location to reservoir target | about 500 m | D&W assessments of pre-salt fields |
| Salt thickness (TVD) along the well | none - must be supplied | seismic or offset well |
| Build rate (dogleg severity) through salt | none - ask D&W; 3 deg/30 m only as a placeholder | D&W |
| Reservoir target positions (surface projection) | from reservoir or well-count basis | reservoir model |
| Host position, water depth, bathymetry | from the study | |

Salt thickness is the controlling input: angle is preferably built through the salt, so a thin salt cuts the achievable step-out below 500 m.

## Outputs

- Surface (wellhead) position for every well, its target, step-out distance and a PASS / FAIL against the step-out and inclination limit.
- Layout built from single vertical wells connected by production loops or daisy chains, with no multi-slot templates.
- Flowline, umbilical and riser lengths and counts of trees, PLEMs and in-line structures for the SURF take-off.
- Assumptions and data gaps naming every D&W limit that was assumed rather than given.

## Engineering Method

1. **Fix the premise first.** State the inclination and step-out limits and where they came from. If D&W has not given them, use the defaults above and list them in `assumptions` and `data_gaps`.
2. **Do not default to templates.** Set one well per structure (`slots_per_template=1`). Each well has its own tree and PLEM or flowline connection. Multi-slot templates or drill centres are used only when D&W explicitly allows deviation for that field, and then with the stated step-out.
3. **Put wells where the targets are.** The surface location is the reservoir target projected up, displaced by at most the allowed step-out. Well spacing follows drainage and target spacing, not a template slot pitch. Do not move wells to a regular grid of drill centres.
4. **Connect with loops or daisy chains.** Connect the single wells with production loops (round-trip piggable) or daisy-chain flowlines, and treat the chain or loop as the architecture decision, with `production_architecture="dual_loop"` or `"daisy_chain"`. Check pigging, shutdown and hydrate-remediation consequences of each (`neqsim-surf-field-layout-design`, `neqsim-flow-assurance`).
5. **Check reach per well.** Step-out = horizontal distance from the surface location to the target. It must not exceed the step-out limit or the salt-limited reach below.
6. **Estimate the salt-limited reach.** A constant-dogleg build to the maximum inclination, then a tangent at that inclination, through a salt of true vertical thickness `T`:
   - Build radius `R = 1718.9 / DLS` metres (DLS in deg per 30 m).
   - Build to inclination `theta` uses `R * sin(theta)` of TVD and gives `R * (1 - cos(theta))` of displacement.
   - Tangent through the rest of the salt gives `(T - R * sin(theta)) * tan(theta)` of displacement.
   - The indicative maximum step-out is the sum, capped by the D&W step-out limit. If the salt is too thin to complete the build, the inclination reached is `asin(T / R)`: report the smaller reach and flag it.
   This is a geometry check for ranking, not a well plan. D&W numbers govern.
7. **Do not use the horizontal-well trajectory tool.** `surf_field_layout_design.wells.build_well_paths` draws horizontal drains landing from a drill centre. It does not represent near-vertical pre-salt wells; do not use its build-rate result as a drillability check for these fields.
8. **Cost the structures that exist.** Count single-well trees and the loop or daisy-chain flowlines. Do not carry template or manifold cost for slots that are not used.

## Python Usage Pattern

```python
from math import asin, cos, hypot, radians, sin, tan

MAX_INCLINATION_DEG = 30.0   # D&W premise for pre-salt, replace with the project value
MAX_STEP_OUT_M = 500.0       # D&W assessments of pre-salt fields, replace with the project value


def salt_limited_reach_m(salt_tvd_m, dls_deg_per_30m=3.0, max_inclination_deg=MAX_INCLINATION_DEG,
                         max_step_out_m=MAX_STEP_OUT_M):
    """Indicative step-out from building angle through the salt. Returns (reach_m, build_complete)."""
    radius = 1718.9 / dls_deg_per_30m
    theta = radians(max_inclination_deg)
    build_tvd = radius * sin(theta)
    if salt_tvd_m <= build_tvd:
        phi = asin(min(max(salt_tvd_m, 0.0) / radius, 1.0))
        return radius * (1.0 - cos(phi)), False
    reach = radius * (1.0 - cos(theta)) + (salt_tvd_m - build_tvd) * tan(theta)
    return min(reach, max_step_out_m), True


def check_well(surface_xy_m, target_xy_m, salt_tvd_m, dls=3.0):
    step_out = hypot(surface_xy_m[0] - target_xy_m[0], surface_xy_m[1] - target_xy_m[1])
    reach, complete = salt_limited_reach_m(salt_tvd_m, dls)
    return {"step_out_m": round(step_out, 1), "reach_m": round(reach, 1),
            "build_complete": complete, "pass": step_out <= min(reach, MAX_STEP_OUT_M)}


# layout: one well per structure, loops or a daisy chain
from surf_field_layout_design import design_surf_layout

layout = design_surf_layout(
    field_name="Example pre-salt field", centre_latitude_deg=-25.0, centre_longitude_deg=-42.5,
    water_depth_m=2000.0, producers=8, water_injectors=6,
    slots_per_template=1, production_architecture="dual_loop",
)
```

The numbers above are placeholders that show the call shape. `layout.summary["max_step_out_km"]` is the distance from the host to the farthest node, not a well step-out: do not read it as a drilling reach.

## Validation Checklist

- [ ] The inclination and step-out limits are stated with their source; defaults appear in `assumptions` and `data_gaps`.
- [ ] No template or drill centre with more than one slot is used without a D&W statement allowing it.
- [ ] Every well has a surface position, a target and a step-out that passes the limit.
- [ ] Salt thickness is a supplied input; if it is missing, the reach check is reported as not assessed.
- [ ] The architecture is a loop or daisy chain, with pigging and shutdown consequences noted.
- [ ] Take-off counts single trees and flowline loops, not unused template slots.
- [ ] Horizontal-well build rates were not used as a drillability result.
- [ ] D&W review is listed as a required next step.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Layout shows 4-slot templates in deep water | Generic default `slots_per_template=4` | Set `slots_per_template=1` and use loops or a daisy chain |
| Wells drilled 1 500 m from the target | Drill-centre grid used instead of target positions | Place wells over the targets within the step-out limit |
| Step-out read from `max_step_out_km` | That field is host to farthest node | Compute surface-to-target distance per well |
| Reach claimed without salt data | Salt thickness not asked for | Ask for salt TVD; otherwise mark not assessed |
| Pre-salt rule applied to an NCS field | Region not checked | Apply only to Brazilian deepwater pre-salt |

## Limitations

- The limits (about 30 deg and about 500 m) are D&W premises reported for pre-salt fields, not a standard. They can differ by field, rig and salt section; the project value governs.
- The reach formula assumes a constant dogleg, a straight tangent, a vertical salt column and no drop-back below the salt. It is a ranking check, not a well plan; anti-collision, torque and drag and casing design are out of scope.
- The layout tool still labels single-well structures as drill centres and templates in its node and file names; read them as single-well hubs.
- Screening only. D&W and subsea engineering review is required before any decision.

## Related

- `neqsim-surf-field-layout-design`, `neqsim-step-out-screening`, `neqsim-subsea-layout-geometry`, `neqsim-brazil-presalt-analogue-basis`, `neqsim-brazil-offshore-infrastructure-market`, `neqsim-capex-opex-screening`.

## References

- D&W premises and well-construction assessments for the field, supplied by the operator's drilling and wells discipline.
