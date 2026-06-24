---
name: neqsim-pipe-route-profile
version: "0.1.0"
description: "Educational pipe-route length and elevation-profile screening from supplied waypoints. USE WHEN: a task needs a public, screening-level flowline or riser route length, segment list, and seabed elevation profile from a subsea map before detailed pressure-drop and flow assurance design."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Pipe Route Profile

Use this skill for a quick, public route geometry screening of a subsea flowline or riser. Given an ordered list of waypoints with seabed depths, it builds segment lengths, a cumulative kilometre-point (KP) profile, total route length, and an elevation profile (rise, descent, net change, maximum slope). It is intentionally simple and should guide users toward validated NeqSim hydraulic and flow assurance workflows.

## When to Use

- When a user supplies an ordered route (waypoints with seabed depths) and wants the total length and elevation profile.
- When an engineer needs a segment list and KP profile to feed pressure-drop or hydrate screening.
- When an agent should explain that validated NeqSim hydraulic methods are required for design-grade work.

## Inputs

- `waypoints`: an ordered list, each with `name`, `x`, `y`, and `depth_m` (seabed water depth, positive downwards).
- `coordinate_system`: `cartesian` (x, y in metres) or `geographic` (x = longitude, y = latitude in degrees).
- `max_slope_deg`: configurable public seabed-slope guideline (constructor, default 15 degrees).

## Outputs

- `segments`: per-segment horizontal length, 3D length, depth change, and slope.
- `total_horizontal_length_km`: planar route length.
- `total_route_length_km`: 3D (as-laid) route length including depth change.
- `kp_profile`: cumulative horizontal KP and seabed depth at each waypoint.
- `net_elevation_change_m`: start depth minus end depth (positive means the route ends shallower).
- `total_rise_m` and `total_descent_m`: summed upward and downward seabed change.
- `max_slope_deg`: steepest segment slope.
- `slope_warning`: `ok`, `watch`, or `high` against the public slope guideline.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

For each consecutive waypoint pair, the horizontal length is the planar Euclidean distance (`cartesian`) or the great-circle haversine distance (`geographic`). The depth change is the difference in seabed depth, the 3D segment length is `sqrt(horizontal^2 + depth_change^2)`, and the slope is `atan2(|depth_change|, horizontal)` in degrees (a vertical step gives 90 degrees). Cumulative KP is the running sum of horizontal lengths. Rise is summed where the route gets shallower and descent where it gets deeper.

The slope warning compares the steepest segment slope to the configurable `max_slope_deg` guideline: at or above the guideline is `high`, above 80 % is `watch`, otherwise `ok`. This flags candidate free-span or steep-slope sections for follow-up, but is not a span or on-bottom-stability analysis.

This is not a hydraulic model. Pressure drop, temperature loss, hydrate margin, and flow regime along the route must come from validated NeqSim workflows.

## Python Usage Pattern

```python
from pipe_route_profile import PipeRouteModel

model = PipeRouteModel(max_slope_deg=15.0)
result = model.evaluate(
    waypoints=[
        {"name": "Tree", "x": 0.0, "y": 0.0, "depth_m": 340.0},
        {"name": "KP2", "x": 2000.0, "y": 200.0, "depth_m": 300.0},
        {"name": "Riser base", "x": 8000.0, "y": 1500.0, "depth_m": 120.0},
    ],
    coordinate_system="cartesian",
)

print(result.total_route_length_km)
print(result.net_elevation_change_m)
print(result.slope_warning)
print(result.assumptions)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim hydraulic and flow assurance workflows. If not, the example still runs with the public geometry logic.

## Validation Checklist

- [ ] Waypoints are ordered along the intended route.
- [ ] All coordinates and depths are finite and depths are non-negative.
- [ ] The coordinate system matches the supplied coordinates (metres vs degrees).
- [ ] The route length is understood to follow the supplied waypoints, not an optimised corridor.
- [ ] The slope guideline is documented as a configurable public guideline only.
- [ ] Real hydraulics, span, and flow assurance are redirected to validated NeqSim methods and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Route is much shorter than expected | Too few waypoints over a curved corridor | Add intermediate waypoints to capture the route shape |
| Slope flags everywhere | Sparse waypoints with large depth jumps | Add intermediate soundings or use `bathymetry-profile-screening` |
| Elevation sign confusion | Depth is positive downwards | Net positive change means the route ends shallower |

## Limitations

- No route optimisation, corridor following, or obstacle avoidance is performed.
- No span, on-bottom stability, or pipeline mechanical analysis is included.
- No hydraulic, thermal, or flow assurance evaluation is performed.
- Results are screening indicators only and are not design route lengths or profiles.

## Related NeqSim Functionality

This skill only prepares route geometry. The validated calculations it feeds into live in NeqSim:

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — multiphase pressure and temperature along the route length and elevation profile.
- `neqsim.process.equipment.pipeline.AdiabaticTwoPhasePipe` — two-phase hydraulics for a routed segment.
- The NeqSim MCP `runPipeline` and `runFlowAssurance` tools for arrival-condition, hydrate, and flow-regime screening along the profile.

In Python these classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`). The total length and elevation profile from this skill are inputs to those hydraulic workflows.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Related community skills: `subsea-layout-geometry`, `bathymetry-profile-screening`, `pressure-drop-screening`, `step-out-screening`
- Great-circle (haversine) distance on a spherical Earth is a standard public geodesy relation.
