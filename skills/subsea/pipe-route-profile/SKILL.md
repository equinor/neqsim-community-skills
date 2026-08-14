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

## Sourcing Waypoints and Depths From Open Data

The skill takes waypoints and depths as given. When a route has to be built for a
real field with no survey in hand, both can come from public sources:

- **End points.** For the Norwegian Continental Shelf the Norwegian Offshore
  Directorate FactPages publish CSV exports of every exploration wellbore
  (`wellbore_exploration_all`: `wlbNsDecDeg`, `wlbEwDecDeg`, `wlbWaterDepth`) and
  every fixed facility (`facility_fixed`: degree/minute/second columns plus
  `fclWaterDepth`). Export URL pattern:
  `https://factpages.sodir.no/public?/Factpages/external/tableview/<table>&rs:Command=Render&rs:Format=CSV&Top100=false`.
  GOTCHA: the wellbore table has decimal-degree columns but the facility table
  only has DMS, so convert. Both are ED50, which differs from WGS84 by of order
  100 m on the NCS -- negligible for screening lengths, not for a survey route.
- **Seabed depth.** The EMODnet Bathymetry DTM has a public point REST API,
  `https://rest.emodnet-bathymetry.eu/depth_sample?geom=POINT(<lon> <lat>)`,
  which returns `avg`/`min`/`max` **elevation** in metres, negative downwards;
  negate it to get the depth this skill expects. Cache responses to disk -- a
  500 m-spaced profile over a 70 km route is around 150 calls.
- **Intermediate waypoints.** With only two end points, interpolate along the
  great circle (spherical slerp) at a fixed spacing and sample the DTM at each
  point. That yields a straight-corridor screening profile; it is not a routed
  corridor and carries no obstacle avoidance.
- **Sanity check.** Compare the DTM depth at each end point against the water
  depth reported for the well or facility. Agreement to a few metres is the
  cheapest available validation that the coordinates and the datum are right.

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
- Use `pipeline-survey-processing` instead when the profile comes from an as-built survey
  export rather than planned waypoints; it adds sign normalisation, resolution filtering,
  erroneous-point flagging, span and cover candidates, and a processing log.
- Great-circle (haversine) distance on a spherical Earth is a standard public geodesy relation.
- Norwegian Offshore Directorate FactPages (open data): https://factpages.sodir.no/
- EMODnet Bathymetry DTM and REST API (open data): https://emodnet.ec.europa.eu/en/bathymetry
