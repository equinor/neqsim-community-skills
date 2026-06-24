---
name: neqsim-bathymetry-profile-screening
version: "0.1.0"
description: "Educational bathymetry profile screening from supplied soundings. USE WHEN: a task needs public, screening-level seabed depth interpolation along a route, slope screening, and steep-section flags from sounding points before detailed free-span and on-bottom-stability design."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Bathymetry Profile Screening

Use this skill for a quick, public screening of a seabed bathymetry profile along a route. Given a set of sounding points (distance along route and water depth), it sorts and linearly interpolates depth at requested distances, computes seabed slopes between soundings, and flags candidate steep sections. It is intentionally simple and should guide users toward validated free-span, on-bottom-stability, and NeqSim hydraulic workflows.

## When to Use

- When a user supplies seabed soundings along a route and wants an interpolated depth profile.
- When an engineer needs slope screening and candidate steep-section flags for early planning.
- When an agent should explain that validated span and stability analyses are required for design-grade work.

## Inputs

- `soundings`: a list of seabed points, each with `distance_m` (along route) and `depth_m` (water depth, positive downwards).
- `query_distances`: optional list of distances at which to interpolate depth.
- `max_slope_deg`: configurable public seabed-slope guideline (constructor, default 10 degrees).

## Outputs

- `sorted_soundings`: the soundings sorted by distance.
- `interpolated`: depth at each requested query distance (linear interpolation).
- `slopes`: per-interval seabed slope between consecutive soundings.
- `steep_sections`: intervals whose slope is at or above the guideline.
- `max_slope_deg`: the steepest interval slope.
- `min_depth_m` and `max_depth_m`: shallowest and deepest soundings.
- `slope_warning`: `ok`, `watch`, or `high` against the public slope guideline.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

Soundings are sorted by along-route distance. Depth at a query distance is found by linear interpolation between the two bracketing soundings; query distances outside the sounding range are clamped to the nearest end and flagged. The slope of each interval is `atan2(|depth_change|, distance_change)` in degrees. Any interval at or above the `max_slope_deg` guideline is reported as a candidate steep section. The slope warning compares the steepest interval to the guideline: at or above is `high`, above 80 % is `watch`, otherwise `ok`.

This is a screening of the supplied soundings only. It does not predict free spans, on-bottom stability, scour, or soil behaviour, and the resolution of the result is limited by the spacing of the soundings.

## Python Usage Pattern

```python
from bathymetry_profile_screening import BathymetryProfileModel

model = BathymetryProfileModel(max_slope_deg=10.0)
result = model.evaluate(
    soundings=[
        {"distance_m": 0.0, "depth_m": 340.0},
        {"distance_m": 2000.0, "depth_m": 300.0},
        {"distance_m": 4000.0, "depth_m": 305.0},
        {"distance_m": 8000.0, "depth_m": 120.0},
    ],
    query_distances=[1000.0, 5000.0],
)

print(result.interpolated)
print(result.max_slope_deg)
print(result.slope_warning)
print(result.assumptions)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim hydraulic workflows. If not, the example still runs with the public interpolation logic.

## Validation Checklist

- [ ] Soundings cover the route range of interest.
- [ ] All distances and depths are finite and depths are non-negative.
- [ ] Query distances are within (or knowingly clamped to) the sounding range.
- [ ] Slope resolution is understood to be limited by sounding spacing.
- [ ] The slope guideline is documented as a configurable public guideline only.
- [ ] Real free-span and on-bottom-stability analyses are redirected to qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Interpolated depth looks flat over a rough seabed | Sparse soundings | Add more soundings to capture seabed roughness |
| Query depth clamped unexpectedly | Query distance outside sounding range | Provide soundings spanning the query range |
| No steep sections flagged | Guideline set too high or soundings too sparse | Use a service-appropriate guideline and denser soundings |

## Limitations

- No free-span, on-bottom-stability, scour, or soil analysis is performed.
- Resolution is limited by the spacing of the supplied soundings.
- Linear interpolation does not capture seabed features between soundings.
- Results are screening indicators only and are not design profiles.

## Related NeqSim Functionality

This skill only prepares a seabed depth and slope profile. The validated calculations it supports live in NeqSim and in qualified pipeline engineering tools:

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — uses an elevation profile for multiphase pressure and temperature along a route.
- The NeqSim MCP `runPipeline` and `runFlowAssurance` tools for arrival-condition and hydrate screening along the route.

In Python the NeqSim classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`). The interpolated depth profile from this skill is an input to those route hydraulic workflows. Free-span and on-bottom-stability design require dedicated qualified analysis.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Related community skills: `pipe-route-profile`, `subsea-layout-geometry`, `step-out-screening`
- Linear interpolation and slope from `atan2` are standard public numerical relations.
