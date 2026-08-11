---
name: neqsim-surf-field-layout-design
version: "0.1.0"
description: "Design a screening subsea (SURF) field layout and place the host from open map, bathymetry and licence-block data: group wells into drill centres, place Xmas trees, templates, manifolds, PLEMs and riser bases, position an FPSO or fixed host, route and size every production, injection, service, umbilical and riser line, and export the result as georeferenced GeoJSON and a map. USE WHEN: a task needs a field layout designed rather than an existing one screened - deciding how many drill centres and templates are needed, where the host should sit, which flowline architecture to use (loop, single line or daisy chain), what size the flowlines and risers should be, how long the umbilicals are, or a georeferenced layout to hand to flow assurance, cost estimation or a NeqSim production-network model."
last_verified: "2026-08-12"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# SURF Field Layout Design

Use this skill to turn a well count, a reservoir footprint and a water depth into
a placed and routed subsea layout: drill centres, wells, Xmas trees, templates
and manifolds, PLEMs, riser bases, the host, and every flowline, riser and
umbilical between them — each line sized on velocity and each item carrying a
latitude and longitude so the result drops straight into a map or a GIS.

It is the design counterpart to `neqsim-subsea-layout-geometry`, which screens a
layout that already exists. Use this skill first to create the layout, then that
skill to screen step-outs, and `neqsim-pipe-route-profile` to put the routes on a
real seabed profile.

## When to Use

- A concept study needs a subsea architecture before any layout drawing exists.
- The number of drill centres, templates and Xmas trees must follow from the
  well count and the slots per template.
- The host has to be placed relative to the field, and the riser base with it.
- A flowline architecture must be chosen: a round-trip-piggable dual loop, one
  dedicated line per drill centre, or a daisy chain.
- Flowline, riser and injection-line sizes are needed at a screening level.
- Total flowline, riser and umbilical lengths are needed for a SURF cost
  estimate.
- The layout must be georeferenced — on a licence block, on a map, as GeoJSON.
- A production-network or flow-assurance model needs node positions and segment
  lengths.

Do not use it for detailed routing, crossing design, on-bottom stability,
free-span, expansion, installation or mooring analysis.

## Inputs

| Group | Fields |
| --- | --- |
| Identity and position | `field_name`, `centre_latitude_deg`, `centre_longitude_deg`, `water_depth_m` |
| Wells | `producers`, `water_injectors`, `gas_injectors`, `slots_per_template`, `slot_spacing_m` |
| Footprint | `reservoir_length_km`, `reservoir_width_km`, `field_axis_bearing_deg`, `injector_offset_km`, `seabed_slope_deg` |
| Host | `host_type`, `host_offset_km`, `host_bearing_deg`, `riser_base_offset_m` |
| Architecture | `production_architecture` (`dual_loop`, `single_line`, `daisy_chain`) |
| Sizing | `design_liquid_rate_m3_per_s`, `design_water_injection_rate_m3_per_s`, `design_gas_injection_rate_am3_per_s`, densities, target velocities |

Rates are **actual** volumetric rates at the flowing condition, not standard
volumes. Convert a standard rate with the formation volume factor before passing
it in, or the sizing is wrong by that factor.

## Outputs

- `nodes` — wells, Xmas trees, templates/manifolds, PLEMs, riser base and host,
  each with a tag, local east/north, latitude, longitude and water depth.
- `lines` — every flowline, injection line, umbilical and riser, with its
  service, type, endpoints, length and selected size.
- `summary` — drill-centre and tree counts, architecture, maximum step-out, and
  total flowline, umbilical and riser lengths.
- `to_geojson()` — a WGS84 FeatureCollection of points, lines and the reservoir
  outline, ready for any map or GIS.
- `warnings` and `assumptions` — what was assumed and what a reviewer must check.

## Open Map and Sea Data

`geodata` registers openly licensed sources and plans read-only requests. It
**never opens a connection of its own**: `execute` returns the plan as a manifest
unless the caller supplies its own `fetch` adapter, so the same code runs in a
sandbox and on a connected workstation.

| Source | Use | Licence |
| --- | --- | --- |
| EMODnet Bathymetry | seabed depth over the field, European seas | CC BY 4.0 |
| GEBCO grid | global bathymetry fallback | free, attribution required |
| NOAA ETOPO | global relief fallback | public domain |
| Sodir FactMaps | quadrants, blocks, wellbores, discoveries, fields, facilities, pipelines | NLOD |
| Sodir FactPages | wellbore coordinates and field records as tables | NLOD |
| Natural Earth | coastline for a locator map | public domain |
| Copernicus Marine, MET Norway NORA3 | wave, wind and current statistics for the host heading | CC BY 4.0 / open |

```python
from surf_field_layout_design import plan_layout_data_package, execute, attribution_block

plan = plan_layout_data_package(west=24.0, south=73.0, east=26.0, north=74.0)
manifest = execute(plan)                       # offline: returns the plan only
manifest = execute(plan, fetch=my_read_only_get)   # connected: retrieves it
print(attribution_block(["emodnet_bathymetry", "sodir_factmaps"]))
```

Reproduce the attribution lines on any map you publish.

### Norwegian blocks

`quadrant_bounds("7324")` returns the quadrant box, which is exact north of
62 degN: the label is the latitude of the southern edge and the longitude of the
western edge, spanning one degree by two. `block_bounds("7324/8")` divides that
into twelve 15-by-40-arc-minute blocks — but the **numbering direction is a
documented assumption**, not a calculation, and the returned dictionary says so.
Take the real position from the open Sodir wellbore layer and use the block box
only for orientation.

## Engineering Method

**Drill centres.** Wells of each service are grouped into templates of
`slots_per_template` slots, and the resulting drill centres are spaced evenly
over 70 % of the reservoir length along the field axis. Water injectors are
offset down one flank and gas injectors up the other by `injector_offset_km`.
This is geometry, not a sweep study.

**Host and riser base.** The host sits `host_offset_km` from the field centre on
`host_bearing_deg`; the riser base PLEM sits `riser_base_offset_m` short of it on
the reverse bearing. Riser length is the straight riser-base-to-host distance
with a 25 % lazy-wave allowance.

**Architecture.** `dual_loop` runs two legs through the production drill centres
in opposite order, giving a round-trip pigging loop. `single_line` gives one
dedicated line per drill centre. `daisy_chain` runs one line through them all and
is flagged as not round-trip piggable.

**Line sizing.** The smallest standard nominal size whose velocity stays under
both the target velocity and the API RP 14E erosional velocity,

$$
v_e = \frac{1.22\,c}{\sqrt{\rho}}
$$

with $v_e$ in m/s, $\rho$ in kg/m³ and $c = 100$ for continuous service. Inner
diameter follows a fixed diameter-to-wall ratio of 20; that is a screening
geometry, **not** a pressure-containment design.

## Python Usage Pattern

```python
from surf_field_layout_design import design_surf_layout, plot_layout_map

layout = design_surf_layout(
    field_name="Example field",
    centre_latitude_deg=73.375,
    centre_longitude_deg=25.0,
    water_depth_m=400.0,
    producers=8,
    water_injectors=6,
    gas_injectors=2,
    slots_per_template=4,
    reservoir_length_km=6.0,
    reservoir_width_km=3.1,
    field_axis_bearing_deg=30.0,
    host_offset_km=2.5,
    host_bearing_deg=270.0,
    production_architecture="dual_loop",
    design_liquid_rate_m3_per_s=28500.0 / 86400.0,
    design_water_injection_rate_m3_per_s=20000.0 / 86400.0,
    design_gas_injection_rate_am3_per_s=0.63e6 * 0.012 / 86400.0,
)

print(layout.summary["drill_centres"], layout.summary["flowline_length_km"], "km")
plot_layout_map(layout, "layout_map.png")
open("layout.geojson", "w").write(json.dumps(layout.to_geojson()))
```

### Handing the layout on

- **Flow assurance and hydraulics.** Each `Line` gives the endpoints, length and
  inner diameter that `neqsim.process.equipment.pipeline.PipeBeggsAndBrills`
  needs; take the elevation profile from `neqsim-pipe-route-profile` or an open
  bathymetry grid rather than the flat default.
- **Production network.** Drill centres map to a `Mixer` manifold and wells to
  `WellFlow` inflow, as in `neqsim-production-network-routing`.
- **Cost.** `flowline_length_km`, `umbilical_length_km`, `riser_length_km` and
  the tree, template and PLEM counts are the quantity take-off a SURF cost
  estimate needs.
- **Screening.** Feed the node list to `neqsim-subsea-layout-geometry` for
  step-out and tie-back distance checks.

## Validation Checklist

- [ ] The field position comes from an open wellbore or discovery record, not
      from the block-grid assumption.
- [ ] Design rates are actual volumetric rates at the flowing condition.
- [ ] Every line size is inside the target velocity and the erosional limit, or
      the deviation is explained.
- [ ] The flowline architecture matches the pigging and shutdown philosophy.
- [ ] The seabed is a real bathymetry grid, not the flat default, before any
      route length or riser length is used for cost or hydraulics.
- [ ] The host offset respects the safety zone and the drill-centre envelope.
- [ ] Wall thickness has been replaced by a real pressure design.
- [ ] A qualified subsea engineer has reviewed the layout.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Flowlines come out far too small | Standard rates passed where actual rates are expected | Multiply by the formation volume factor first |
| Only one drill centre for many wells | `slots_per_template` left at a large value | Set the real slot count per template |
| The reservoir outline does not line up with the drill centres | `field_axis_bearing_deg` changed but the footprint not re-checked | The outline follows the same axis; check the footprint dimensions |
| Riser length equals the water depth | Riser configuration allowance ignored | The skill adds 25 % for a lazy wave; replace with a real riser analysis |
| Umbilical length looks short | Umbilicals are routed host-to-drill-centre in a straight line | Add a routing allowance, or route via the real corridor |
| The block box does not match the operator's map | The block numbering assumption | Take the position from the Sodir wellbore layer |

## Limitations

- Screening geometry only: straight-line routes, no obstacle avoidance, no
  crossings, no corridor or approach design.
- Drill-centre placement is geometric spacing, not a well-placement or sweep
  optimisation.
- No on-bottom stability, free-span, expansion, buckling, installation, mooring
  or riser-response analysis.
- Wall thickness follows a fixed D/t ratio and is not a pressure design.
- Line sizing is a velocity check only; no pressure-drop, slugging, erosion-rate
  or thermal calculation.
- Met-ocean sources are registered but the host heading is not calculated.
- No proprietary or confidential data is used.

## Related NeqSim Functionality

- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` — flowline and riser
  hydraulics on the routed segments.
- `neqsim.process.equipment.reservoir.WellFlow` — well inflow at each tree.
- `neqsim.process.equipment.subsea.SubseaWell`, `SubseaTree` — subsea equipment.
- `neqsim.process.mechanicaldesign.subsea` — SURF mechanical design and cost.
- The NeqSim MCP `runPipeline` and `runFieldEconomics` tools.

## Related Skills

- `neqsim-subsea-layout-geometry` — screens step-outs and tie-back distances for
  the layout produced here.
- `neqsim-pipe-route-profile` — turns the routes here into an elevation profile.
- `neqsim-bathymetry-profile-screening` — processes the open bathymetry grid
  this skill plans the request for.
- `neqsim-production-network-routing` — takes the drill centres and wells through
  manifolds and flowlines to an arrival pressure.
- `neqsim-step-out-screening` — checks the tie-back distance and arrival pressure.
- `neqsim-reservoir-model-builder` — supplies the well count and the plateau rate.
- `neqsim-capex-opex-screening` — turns the quantity take-off into a cost.

## References

- API RP 14E, *Design and Installation of Offshore Production Platform Piping
  Systems* — erosional velocity.
- DNV-ST-F101 *Submarine pipeline systems* and DNV-RP-F109/F105 for the design
  checks this skill deliberately does not perform.
- EMODnet Bathymetry: https://emodnet.ec.europa.eu/en/bathymetry
- GEBCO: https://www.gebco.net/
- Norwegian Offshore Directorate FactMaps: https://factmaps.sodir.no/
- Natural Earth: https://www.naturalearthdata.com/
- Copernicus Marine Service: https://marine.copernicus.eu/
- MET Norway NORA3 hindcast: https://thredds.met.no/
- NeqSim: https://github.com/equinor/neqsim
