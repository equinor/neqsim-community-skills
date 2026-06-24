---
name: neqsim-field-layout-import
version: "0.1.0"
description: "Educational subsea field-layout import and normalization from supplied GeoJSON or tabular rows. USE WHEN: a task needs to turn an already-parsed subsea map (GeoJSON point features or CSV-like rows) into a clean, validated node list of wells, manifolds, and a host before geometry and routing screening."
last_verified: "2026-05-31"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Field Layout Import

Use this skill to normalize a supplied subsea map into a clean node list for downstream geometry and routing screening. It accepts an already-parsed GeoJSON `FeatureCollection` of point features or a list of CSV-like rows, and produces a validated list of nodes (well, manifold, host, riser base) with coordinates, water depth, and kind. It is intentionally simple, performs no file or network I/O, and should feed validated NeqSim routing and hydraulic workflows.

## When to Use

- When a user supplies a parsed GeoJSON layout or a table of node coordinates and wants a clean, validated node list.
- When an agent needs a normalized layout to feed `subsea-layout-geometry` or `pipe-route-profile`.
- When data quality issues (missing depth, duplicate names, unknown kind) should be flagged before screening.

## Inputs

- `from_geojson(obj)`: an already-parsed GeoJSON `FeatureCollection` dict with `Point` features. Each feature's `geometry.coordinates` is `[x, y]` (or `[longitude, latitude]`), and `properties` may include `name`, `water_depth_m`, and `kind`.
- `from_rows(rows)`: a list of dicts with `name`, `x`/`y` (or `longitude`/`latitude`), optional `water_depth_m`, and optional `kind`.

## Outputs

- `nodes`: the normalized node list, each with `name`, `x`, `y`, `water_depth_m`, and `kind`.
- `node_count`: the number of normalized nodes.
- `issues`: data-quality findings (missing depth defaulted, unknown kind normalized, duplicate name, skipped feature).
- `neqsim_available`: whether the optional NeqSim package is importable.
- `assumptions`: public assumptions and required follow-up.

## Engineering Method

Each feature or row is mapped to a node with a non-empty `name`, finite `x` and `y` coordinates, a non-negative `water_depth_m` (defaulted to 0 with an issue when missing), and a `kind` normalized to a known set (`well`, `manifold`, `host`, `riser_base`, `template`, `tie_in`); unknown kinds are coerced to `well` with an issue. Duplicate names and features that cannot be parsed are recorded as issues rather than raising, so a partial map still yields a usable node list. This is a data-shaping step only and performs no geometry, routing, or hydraulic calculation.

The skill never reads files or fetches URLs; callers parse GeoJSON or load tabular data themselves and pass already-parsed Python objects. This keeps the skill public, offline, and free of credentials or proprietary sources.

## Python Usage Pattern

```python
from field_layout_import import FieldLayoutImporter

importer = FieldLayoutImporter()

geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            "properties": {"name": "Host", "water_depth_m": 120.0, "kind": "host"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [8000.0, 1500.0]},
            "properties": {"name": "W1", "water_depth_m": 340.0, "kind": "well"},
        },
    ],
}

result = importer.from_geojson(geojson)
print(result.node_count)
print(result.nodes)
print(result.issues)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim routing and hydraulic workflows. If not, the example still runs with the public normalization logic.

## Validation Checklist

- [ ] GeoJSON or rows are parsed by the caller before being passed in.
- [ ] Coordinate convention (metres vs longitude/latitude) is known and consistent.
- [ ] Missing water depths flagged in `issues` are resolved before geometry screening.
- [ ] Duplicate names flagged in `issues` are de-duplicated.
- [ ] No proprietary coordinates, survey data, or internal sources are embedded in the input.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Many `unknown kind` issues | Source uses custom type labels | Map source labels to the known kind set before import |
| Coordinates look wrong downstream | Longitude/latitude treated as metres | Choose the matching coordinate system in the geometry skill |
| Node silently missing | Feature failed to parse and was skipped | Check `issues` for skipped features and fix the source record |

## Limitations

- No file reading, URL fetching, or projection/transform is performed.
- No geometry, routing, or hydraulic calculation is included.
- GeoJSON support is limited to `Point` features.
- Results are a normalized node list only, not a verified field layout.

## Related NeqSim Functionality

This skill only normalizes layout data. The geometry and validated calculations it feeds into live in the community skills and NeqSim:

- Community `subsea-layout-geometry` — step-out distances and a distance matrix from the normalized nodes.
- Community `pipe-route-profile` — route length and elevation profile from ordered waypoints.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` and the NeqSim MCP `runPipeline` / `runFlowAssurance` tools for validated route hydraulics.

In Python the NeqSim classes are reachable through the `neqsim` package (for example `from neqsim import jneqsim`). For governed, live layout extraction from controlled engineering sources, the enterprise `enterprise-well-production-routing` skill is the counterpart.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- GeoJSON: RFC 7946 (public specification for `Point` features and `FeatureCollection`).
- Related community skills: `subsea-layout-geometry`, `pipe-route-profile`, `step-out-screening`
