---
name: neqsim-subsea-layout-geometry
version: "0.1.0"
description: "Educational subsea field-layout geometry screening from supplied coordinates. USE WHEN: a task needs public, screening-level step-out distances, tie-back lengths, and a node-to-node distance matrix for wells, manifolds, and a host from a subsea map before detailed routing and hydraulic design."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Subsea Layout Geometry

Use this skill for a quick, public geometry screening of a subsea field layout. Given the coordinates and water depths of wells, manifolds, and a host, it computes horizontal step-out distances, straight-line tie-back lengths (including water-depth difference), and a node-to-node distance matrix. It is intentionally simple and should guide users toward validated NeqSim routing and hydraulic workflows.

## When to Use

- When a user supplies a subsea map or layout (well, manifold, and host coordinates) and wants early tie-back distances.
- When an engineer needs a node-to-node distance matrix for initial routing or step-out screening.
- When an agent should explain that validated NeqSim hydraulic and routing methods are required for design-grade work.

## Inputs

- `nodes`: a list of layout nodes, each with `name`, `x`, `y`, optional `water_depth_m`, and optional `kind` (`well`, `manifold`, `host`, `riser_base`).
- `host_name`: the node treated as the reference host for step-out distances.
- `coordinate_system`: `cartesian` (x, y in metres) or `geographic` (x = longitude, y = latitude in degrees).
- `max_step_out_km`: configurable public step-out guideline (constructor, default 50 km).

## Outputs

- `step_out_km`: horizontal distance from the host to each other node in km.
- `straight_line_km`: straight-line distance from the host including the water-depth difference, in km.
- `pairwise_distances`: node-to-node horizontal and straight-line distances and depth differences.
- `max_step_out_km`: the largest host step-out distance.
- `step_out_warning`: `ok`, `watch`, or `high` against the public guideline.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

Horizontal distance between two nodes is the planar Euclidean distance for `cartesian` coordinates, or the great-circle (haversine) distance on a spherical Earth (radius 6 371 km) for `geographic` coordinates. The straight-line tie-back length is `sqrt(horizontal^2 + depth_difference^2)` using the water-depth difference between the two nodes.

The step-out warning compares the largest host step-out distance to the configurable `max_step_out_km` guideline: at or above the guideline is flagged `high`, above 80 % of the guideline is `watch`, and below that is `ok`.

This is not a route-optimisation or hydraulic model. Real flowline lengths follow a routed corridor (not a straight line), and step-out feasibility depends on arrival pressure, temperature, and flow assurance, which must come from validated NeqSim workflows.

## Python Usage Pattern

```python
from subsea_layout_geometry import SubseaLayoutModel

model = SubseaLayoutModel(max_step_out_km=50.0)
result = model.evaluate(
    nodes=[
        {"name": "Host", "x": 0.0, "y": 0.0, "water_depth_m": 120.0, "kind": "host"},
        {"name": "W1", "x": 8000.0, "y": 1500.0, "water_depth_m": 340.0, "kind": "well"},
        {"name": "M1", "x": 7000.0, "y": 1000.0, "water_depth_m": 320.0, "kind": "manifold"},
    ],
    host_name="Host",
    coordinate_system="cartesian",
)

print(result.step_out_km)
print(result.step_out_warning)
print(result.assumptions)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim routing and hydraulic workflows. If not, the example still runs with the public geometry logic.

## Validation Checklist

- [ ] All node coordinates and water depths are finite.
- [ ] The coordinate system matches the supplied coordinates (metres vs degrees).
- [ ] The host node exists in the node list.
- [ ] Straight-line lengths are understood to be a lower bound on routed flowline length.
- [ ] The step-out guideline is documented as a configurable public guideline only.
- [ ] Real routing, step-out feasibility, and hydraulics are redirected to validated NeqSim methods and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Distances are absurdly large or small | Coordinate system mismatch (degrees treated as metres) | Set `coordinate_system` to match the data |
| Tie-back length looks too short | Straight-line geometry ignores route corridor | Treat the result as a lower bound and route the line in detailed design |
| Step-out never flagged | `max_step_out_km` set too high | Use a service-appropriate public guideline and confirm with flow assurance |

## Limitations

- No route optimisation, corridor following, or obstacle avoidance is performed.
- No hydraulic, thermal, or flow assurance evaluation is included.
- Water depth difference, not a bathymetric profile, is used for straight-line length.
- Results are screening indicators only and are not design tie-back lengths.

## Related NeqSim Functionality

This skill only prepares layout geometry. The validated, design-grade calculations it feeds into live in NeqSim:

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — multiphase flowline pressure and temperature along a routed length.
- `neqsim.process.equipment.pipeline.AdiabaticTwoPhasePipe` — two-phase pipe hydraulics for tie-back screening.
- The NeqSim MCP `runPipeline` and `runFlowAssurance` tools for arrival-condition and hydrate screening along the route.

In Python these classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`). Detailed subsea routing and tie-back length should use validated routing data; the enterprise `enterprise-well-production-routing` skill provides the live-data counterpart.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Related community skills: `pipe-route-profile`, `bathymetry-profile-screening`, `step-out-screening`, `field-layout-import`
- Great-circle (haversine) distance on a spherical Earth is a standard public geodesy relation.
