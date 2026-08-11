# SURF Field Layout Design

Screening design of a subsea field layout and its host, from open map, bathymetry and licence-block data.

Given a well count, a reservoir footprint and a water depth, `design_surf_layout` groups wells into drill centres, places Xmas trees, templates and manifolds, PLEMs, the riser base and the host, routes every production, injection, service and umbilical line plus the risers, and sizes each line against a target velocity and the API RP 14E erosional limit. Every item carries a latitude and longitude, so the layout exports directly as WGS84 GeoJSON and renders on latitude/longitude axes.

This is the design counterpart to `subsea-layout-geometry`, which screens a layout that already exists.

## Install

```bash
python -m pip install -e skills/subsea/surf-field-layout-design
# optional: the geographic map
python -m pip install -e "skills/subsea/surf-field-layout-design[plot]"
```

## Run Example

```bash
python skills/subsea/surf-field-layout-design/examples/design_barents_style_layout.py
```

It writes `layout.geojson`, `layout.json` and `layout_map.png` next to the script.

## Run Tests

```bash
python -m pytest skills/subsea/surf-field-layout-design/tests
```

## Open Data

`geodata` registers openly licensed bathymetry (EMODnet, GEBCO, ETOPO), licence-block and infrastructure (Sodir FactMaps and FactPages), coastline (Natural Earth) and met-ocean (Copernicus Marine, MET Norway NORA3) sources, and plans read-only requests against them. **No network connection is opened by this package**: `execute` returns the plan as a manifest unless the caller supplies its own `fetch` adapter. Reproduce `attribution_block(...)` on any published map.

## Public Scope

No proprietary field layouts, confidential well coordinates, route corridors or company-specific design rules. Routes are straight lines with no obstacle avoidance or crossing design; there is no on-bottom stability, free-span, expansion, installation, mooring or riser-response analysis, and the wall thickness follows a fixed diameter-to-thickness ratio rather than a pressure design. For real work use validated NeqSim routing, hydraulic and mechanical-design workflows and a qualified subsea engineering review.
