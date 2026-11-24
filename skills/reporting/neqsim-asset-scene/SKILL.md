---
name: neqsim-asset-scene
calculation_basis: "screening"
version: "0.1.0"
description: "One 3D scene contract (neqsim_asset_scene.v1) for process equipment, SURF and wells, existing and proposed, coloured by NeqSim results or live values, with nozzle-to-nozzle routed piping, span/slope/clash screening and B31.3 pipe stress in NeqSim PipeStressModel. Renders GLB, an offline HTML viewer and report PNGs with provenance. USE WHEN: a study needs a 3D figure of a plant, tie-back, well path or modification option from NeqSim models, layouts, subsea layouts or trajectories."
last_verified: "2026-11-24"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# NeqSim Asset Scene

Builds one 3D picture of an asset from the outputs that already exist in a study: a NeqSim
`ProcessSystem` and its mechanical design, the plant-layout study, the subsea layout, well
trajectories. Every object says what it is (`kind`), whether it is **existing, proposed, modified or
removed** (`state`), and how good its geometry is (`verified`, `derived` or `assumed`). NeqSim results
and live values ride along on each object and can colour the scene. The same scene renders as a
GLB (CAD and web viewers), an offline interactive HTML viewer and PNG figures for Word reports.

This skill is the shared, public half of the visualisation chain. Company sources (STID tags and
coordinates, datasheet dimensions, P&ID connectivity, Echo pictures, historian values, company maps
and well databases) are added by a private enterprise skill that calls the functions below. Nothing
here reads a company system.

## When to Use

- A process, debottlenecking or capacity study needs a figure of the train with the binding equipment
  coloured by NeqSim utilisation.
- A tie-in, tie-back or SURF concept must show the existing host and subsea structures next to the
  proposed template, flowline, umbilical and well path.
- A modification study must show existing, modified, proposed and removed items in one view.
- A model-review or digital-twin task wants live values on the equipment they belong to.
- Any report where a reader gains from seeing the equipment, layout or well path in 3D.

Use `neqsim-reservoir-3d-visualisation` for reservoir grids and `neqsim-fem-coupling` for field
results inside a solid; this skill places objects, it does not render continuous fields.

## Inputs

- **Scene objects**, built through the adapters or `AssetScene.add_object(...)`:
  `id`, `kind` (equipment, vessel, column, compressor, pump, heat_exchanger, valve, instrument, line,
  pipeline, flowline, riser, umbilical, well, template, manifold, plem, plet, host, structure, deck,
  obstacle, reservoir, area, marker), `state`, `group` (facility, subsea, well, reservoir, structure),
  `geometry` (`box`, `cylinder`, `sphere`, `polyline`, `point`, metres), `source`
  (`geometry`, `quality`, `reference`), optional `attributes`, `results`, `live`, `media`.
- **Adapters:**
  - `scene_from_neqsim_process(process)` or `equipment_records_from_neqsim(process)`: sizes from
    `MechanicalDesign.toDesignDataJson()` (falls back to the getters on older jars), connections from
    `ProcessSystem.buildGraph()` with streams, mixers and recycles bridged. Run the process and
    `calcDesign()` first.
  - `from_equipment_records(records, connections)`: records with `tag`, `kind`, `diameter_m` +
    `length_m` + `orientation`, or `size_m` = [length, width, height], optional `position_m`
    (footprint centre x, y and base z; the object centre when `position_reference` is `"centre"`),
    `size_quality`, `position_quality`, `attributes`, `results`.
  - `from_layout_items(items)`: plant-layout study items with `bounds_m` = [xmin, ymin, zmin, xmax, ymax, zmax].
  - `from_subsea_nodes(nodes, lines)`: the `neqsim-subsea-layout-geometry` node shape (`name`, `x`, `y`,
    `water_depth_m`, `kind`) plus lines (`from`, `to`, `kind`, optional `route`, `diameter_m`).
    `coordinate_system="geographic"` projects lon/lat to a local frame (screening accuracy).
  - `from_well_trajectory(name, stations, wellhead_xy, datum_z)`: `md_m`/`inc_deg`/`azi_deg`
    (minimum curvature) or `north_m`/`east_m`/`tvd_m`; z = `datum_z` - TVD.
  - `attach_values(scene, {tag: {quantity: value}}, channel="results"|"live")` and
    `neqsim_results(process)` (`getMaxUtilization()`, outlet pressure and temperature).
- **Connections:** `scene.add_connection(a, b, line_number=..., diameter=..., route=[[x, y, z], ...],
  route_reference="ISO ...", from_port=..., to_port=..., min_slope=..., wall_thickness_m=...,
  operating_temperature_C=..., fluid_density_kg_m3=..., material=...)`, or the same keys (with
  `route_m` / `diameter_m`) on the connections passed to `from_equipment_records`. `diameter` is the
  pipe outer diameter in metres; without it the pipe is drawn but not screened. Without a route the
  pipe is auto-routed (see Engineering Method).
- **Nozzles:** `nozzles={"N2": {"offset_m": [dx, dy, dz], "direction": [0, 0, 1], "service": "gas_outlet"}}`
  on `add_object` (or `nozzles` on an equipment record) from the datasheet nozzle schedule; a
  connection whose `from_port`/`to_port` names the nozzle id or service starts or ends there.
  The NeqSim adapter sets `from_port` (`gas_outlet`, `liquid_outlet`, `water_outlet`) and
  `operating_temperature_C` from the separator outlet streams.
- **Stress inputs** (for `analyse_pipe_stress`), on the connection: `design_pressure_barg`,
  `corrosion_allowance_m`, `friction` (support friction, default 0.3), `allowable_stress_Pa`,
  `material` (`carbon_steel`, `stainless_steel`, `duplex`). On the end objects:
  `attributes["design_pressure_barg"]` (used when the line has none) and
  `attributes["nozzle_allowables"] = {"N2" | "default": {"force_N": ..., "moment_Nm": ...}}` from the
  vendor (API 610, API 617) or a WRC 297 calculation.

## Outputs

- `scene.json` (`neqsim_asset_scene.v1`), `*.glb` (metres, glTF Y-up, one named node per tag with
  provenance in `extras`), `*.html` (self-contained viewer: rotate, Shift-drag pan, wheel zoom,
  iso/plan/side, vertical exaggeration, state and group filters, hover table with tag, kind, state,
  geometry source, attributes, NeqSim results and live values with timestamps), `*_iso.png`,
  `*_plan.png`, `*_elevation.png`.
- `scene_caption(...)`: caption naming the colour meaning and how many objects are verified,
  derived and assumed.
- `coverage_table(scene)` and `results_fragment(scene, render_result)`: `figure_captions`, a
  provenance table, `assumptions` and `data_gaps` (gap, source, status, assumed, effect) ready for
  `merge_into_results(results, fragment)`.
- `stale_live_values(scene, max_age_s)`: objects whose live value is older than the limit.
- `analyse_piping(scene)`: per pipe the route, which end rule was used (nozzle, port convention,
  face), length, maximum support span and support positions, slope result, ASME B31.3 319.4.1
  flexibility ratio with the temperature and its source, and clashes; plus a summary.
  `add_pipe_supports(scene, report)` draws the supports; `piping_fragment(report, name)` gives the
  `results.json` table, basis and gaps.
- `analyse_pipe_stress(scene, report, seismic_g=..., wind_pressure_pa=...)`: adds `stress` to each
  sized pipe: status, sustained, expansion and occasional ratios, pressure design, supports that lift
  off or slide, support and nozzle loads with nozzle status, maximum operating displacement, and the
  basis of the design pressure and corrosion allowance. `stress_fragment(report, name)` gives the
  `results.json` table, method assumption and gaps.

## Engineering Method

The scene is a list of primitives in one local metric frame (x east, y north, z up, metres). Vessels
and columns are cylinders from diameter and tangent length; rotating equipment and packages are boxes
from the module envelope; lines, risers and wells are tubes along a path. Equipment without a position
is placed in process-flow order (longest path through the NeqSim graph, recycles ignored), one column
per level, and the placement is recorded as `assumed`. An object's quality is the worse of its size
and position quality.

Well paths use the minimum-curvature method; subsea lines that end at a host get a vertical riser to
sea level. On field-scale scenes (span over 500 m) the HTML and PNG views enlarge small structures to
1.5 % of the span so templates stay visible, and the caption says so; the GLB keeps true sizes.

**Pipe routing.** Every connection is drawn as a routed pipe, chosen per connection:

- `supplied`: the connection has a `route` ([[x, y, z], ...] in the scene frame) from an isometric,
  a 3D piping model export, a layout study or a surveyed line; it is joined to the end nozzles.
- `orthogonal` (plant scale, default): the pipe leaves the source nozzle, rises to a pipe-rack
  elevation that clears every object under its run (1 m clearance), runs along x then y, drops and
  enters the target nozzle. A pipe from a bottom (liquid) nozzle first steps sideways clear of its
  own vessel. Parallel pipes get separate rack lanes; pipes sharing a vessel face get side-by-side
  nozzle slots; a pipe that still clashes with another pipe or an item is moved to the next free
  lane (up to 8 tries). With `min_slope` the rack run falls toward the target by at least that
  gradient.
- `seabed` (field scale, span over 500 m): along the seabed between the object bases.

Pipe ends, in order: a named nozzle (`nozzles` on the object), the port convention (gas, vapour,
overhead, vent -> top centre; liquid, oil, water, condensate, drain -> bottom centre), the face
toward the other end. The report counts each so readers know how many nozzle positions are real.

Pass `routing="orthogonal" | "seabed" | "straight"` to `render_all` to force one mode. The caption
counts each mode; auto-routed connections are a data gap ("no piping route") so nobody reads an
illustrative path as the as-built path, which only a supplied route can give. The GLB stores each
route and its mode in the node `extras`, and the viewer's hover table shows the mode and length.

**Piping screening** (`analyse_piping`), screening level only:

- *Support spacing*: simply supported span with mid-span sag of 2.5 mm and sustained bending stress
  of 15.9 MPa, fluid-filled (water by default), times 0.9. Benchmark (2026-11-22): 2 / 6 / 12 inch
  standard-wall carbon steel give 3.1 / 5.0 / 6.7 m against MSS SP-69 water-filled table spans of
  3.0 / 5.2 / 7.0 m. Supports go at both ends of each horizontal run and at equal spacing within the
  span. Wall thickness defaults to about schedule 40 (flagged) when the piping class is not given.
- *Slope*: every horizontal run of a line with `min_slope` must fall at least that much per metre in
  the flow direction; supplied routes that do not are reported.
- *Thermal flexibility*: ASME B31.3 para. 319.4.1, D*y/(L-U)^2 <= 208.3 (D, y in mm; L, U in m),
  end nozzles as anchors, y = alpha * |T - 20 C| * U. Temperature from the connection, the NeqSim
  result or the live value of the source equipment, else a data gap. A fail means "do a stress
  analysis".
- *Clashes*: pipe-to-pipe by segment distance against the sum of radii plus 50 mm; pipe-to-item
  through envelopes, including a pipe passing back through its own vessel beyond the nozzle stub.

**Pipe stress analysis** (`analyse_pipe_stress`): the physics is in NeqSim Java,
`neqsim.process.mechanicaldesign.piping.PipeStressModel` (NeqSim 3.29.0 or later). For each sized
pipe the route (nozzle to nozzle, with the screening support positions) becomes a 3D beam model:

- end nozzles are anchors, checked against the nozzle allowables when the end object has them;
- supports are one-way rest supports with Coulomb friction (stick/slip), so a support can lift off
  or slide in operation;
- direction changes are long-radius elbows with the B31.3 flexibility factor 1.65/h and SIF 0.9/h^(2/3);
- load cases: OPE (weight, thermal, pressure; contact and friction iterated), SUS (weight and
  pressure on the corroded wall, OPE support states), EXP = OPE - SUS, OCC (static seismic g and
  wind in x and y);
- checks: B31.3 304.1.2 pressure design, 320 sustained S_L <= S_h, 319.4.4 expansion S_E <= S_A
  (liberal form), 302.3.6 occasional <= 1.33 S_h.

Allowables default to S = 138 MPa (A106 B), 115 MPa (316L) or 207 MPa (duplex); corrosion
allowance defaults to 3 mm for carbon steel and is flagged. Design pressure comes from the line,
then the source equipment's `design_pressure_barg`, else zero (gap). When the installed NeqSim has
no `PipeStressModel`, every line gets status `unavailable` and a gap. The solver is checked in
NeqSim against closed-form beam, thermal-force, friction and B31.3 bend-factor results
(`PipeStressModelTest`).

Colours: grey = existing (tinted by group), blue = proposed, orange = modified, translucent red =
removed. `ColorBy("results", "utilisation", mode="utilisation")` uses green-amber-red with breakpoints
at 0.8 and 1.0; `mode="sequential"` spans the data range. Objects without a value are light grey.

## Realistic primitives, source register and optional NeqSim binding (added 2026-11-24)

**`asset_scene.realistic`** (pure Python, tested in `tests/test_realistic.py`) replaces boxes and 12-sided tubes where a figure must look like the
real plant: `vessel_mesh`/`vessel_parts` (ellipsoidal, hemispherical, torispherical or flat heads, saddles or skirt, nozzles with flanges),
`fillet_path` + `swept_tube` + `pipe_parts` (long-radius elbows, parallel-transport frames, flanges), `valve_parts`, `jacket_parts`, `deck_parts`,
`module_parts`, `flare_boom_parts`, `helideck_parts`, `crane_parts`, `xmas_tree_parts`, `template_parts`, `Seabed` (relief, flattened sites,
`z(x, y)` to place structures), `sea_surface_mesh`, `well_string_parts` (telescoping casing and tubing), `reservoir_layer`, and converters
`to_pyvista` (smooth normals), `to_plotly_arrays`, `merge_parts`. Materials are keys of `MATERIALS`; `"schematic"` is the neutral translucent material
for anything that is not sourced.

**Realism checklist** (before a 3D figure is accepted): proper vessel heads and saddles, pipes with elbows and flanges, valves with bonnet and handwheel,
structures as lattices (not slabs), seabed relief with flattened sites, well strings drawn as strings, light with shadows (PyVista SSAO) and depth haze,
perspective camera, one pressure colour scale with log ticks, consistent scale and a stated enlargement factor, annotations drawn with matplotlib (Norwegian
letters and exact fonts), and a footnote that names what is assumed.

**`asset_scene.register`** (tested in `tests/test_register.py`): an illustration source register. Every drawn element is `SOURCED` (P&ID, datasheet, line list, trajectory;
needs `source.type` and `source.file`, ideally `doc_no` and `page`), `DERIVED` (from a task `results.json` or model file) or `ASSUMED` (needs `reason`).
`check_register(register, legend_texts=...)` fails on a missing source, an ASSUMED element without reason, or an ASSUMED element in a figure whose
legend/footnote does not say *antatt/skjematisk* (`legend_line()` writes the sentence). `to_markdown`/`save` produce `illustration_sources.md/json`. Draw unsourced equipment
with the `"schematic"` material, never as real. **`neqsim_binding` is optional**: add `{unit, address, value, tolerance_rel}` only where a shown number comes from a NeqSim
run (pressure colours, peak pressure versus design); only bound elements are compared with a fresh run through the `fresh` callable. Pure geometry needs no binding.
Worked example: neqsim-task-solve `2026-11-24_oseberg_309_p_4_b_vest_high_pressure_gas_well_against_lp/step2_analysis/illustrations/` (`illustration_register_def.py`, `10_finalize.py`, `scene_delta.py` for a template built from sourced slot positions).

**`asset_scene.subsea`** (tested in `tests/test_subsea.py`): recognisable subsea equipment with the same `(name, mesh, material)` parts as `realistic`: `xmas_tree_parts`, `plet_parts` (PLET or inline PLEM), `manifold_parts`,
`jumper_parts` (M, W or U shape), `flowline_parts` (field joints), `riser_base_parts` (gooseneck, SSIV), `umbilical_parts`, `uta_parts`, `mudmat_parts`, `hub_parts`. Dimensions are typical North Sea values: unless a drawing
gives the real size, register the item as ASSUMED and draw it with the figure labelled *antatt/skjematisk*.

**Source-register practice** (learned on the Oseberg task): split an element into what is sourced and what is assumed (for example slot count, slot-4 position, hub sides and line lengths SOURCED from the design basis and the
well report, frame and equipment dimensions ASSUMED); give `source.revision` and `page` (`to_markdown` prints them); derive orientations from coordinates where possible (two vessels with centres 4.3 m apart and 13.1 m long
cannot be parallel to the line joining their centres) and register them as DERIVED; check names such as "161.5 m" against their origin before labelling them water depth; record the exact blocker (HTTP code, missing key,
placeholder file size) for every source that could not be read. Never draw a route or structure that no source supports as if it were real.

**Still open**: a scene-from-ProcessSystem helper is not implemented; `template_parts` and `xmas_tree_parts` stay simplified.

## Python Usage Pattern

```python
from asset_scene import (AssetScene, ColorBy, attach_values, from_equipment_records,
                         from_subsea_nodes, from_well_trajectory, render_all, results_fragment)

records = [
    {"tag": "20-VA-001", "kind": "vessel", "diameter_m": 3.2, "length_m": 11.0, "orientation": "horizontal"},
    {"tag": "23-KA-001", "kind": "compressor", "size_m": [7.0, 4.0, 4.5]},
    {"tag": "23-KA-002", "kind": "compressor", "size_m": [7.0, 4.0, 4.5], "state": "proposed"},
]
scene = from_equipment_records(records, [{"from": "20-VA-001", "to": "23-KA-001"}],
                               scene=AssetScene("Gas compression"))
attach_values(scene, {"23-KA-001": {"utilisation": 0.97}})
out = render_all(scene, "figures", "compression",
                 color_by=ColorBy("results", "utilisation", mode="utilisation"))

field = from_subsea_nodes(
    [{"name": "HOST", "x": 0, "y": 0, "water_depth_m": 120, "kind": "host"},
     {"name": "T-B", "x": 5200, "y": 3100, "water_depth_m": 135, "kind": "template", "state": "proposed"}],
    [{"from": "T-B", "to": "HOST", "kind": "flowline", "state": "proposed"}])
from_well_trajectory("B-1 H", [{"md_m": 0, "inc_deg": 0, "azi_deg": 35},
                               {"md_m": 2500, "inc_deg": 55, "azi_deg": 35}],
                     (5200, 3100), datum_z=-135.0, scene=field, state="proposed", quality="assumed")
fragment = results_fragment(field, render_all(field, "figures", "field"))
```

With NeqSim: `scene = scene_from_neqsim_process(process)` then
`attach_values(scene, neqsim_results(process))`. Piping screening before rendering:

```python
from asset_scene import add_pipe_supports, analyse_piping, piping_fragment

for conn in scene.connections:
    conn["diameter"] = 0.2731            # from the line list
report = analyse_piping(scene)          # spans, slope, B31.3 319.4.1, clashes
add_pipe_supports(scene, report)
render_all(scene, "figures", "train_piping")
fragment = piping_fragment(report, scene.name)
```

Pipe stress in NeqSim (needs a NeqSim jar with `PipeStressModel`):

```python
from asset_scene import analyse_pipe_stress, stress_fragment

conn = scene.connections[0]
conn.update(wall_thickness_m=0.0151, design_pressure_barg=95.0, operating_temperature_C=140.0)
report = analyse_pipe_stress(scene, analyse_piping(scene), seismic_g=0.1)
stress = report["connections"][0]["stress"]   # status, ratios, lift_off, sliding, nozzles
fragment = stress_fragment(report, scene.name)
```

Command line:
`python -m asset_scene render scene.json --out figures --color-by results:utilisation --mode utilisation`.
`examples/asset_scene_example.py` builds the topside, utilisation and tie-back figures.

## Validation Checklist

- [ ] `scene.validate()` returns no issues before rendering.
- [ ] Every object has a `source.quality`; the caption counts match the coverage table.
- [ ] Assumed positions and placeholder sizes appear as data gaps in `results.json`.
- [ ] The PNG and HTML were opened and show the intended objects; labels are readable.
- [ ] Field-scale views state that small structures are enlarged; the GLB is used for true sizes.
- [ ] Live values carry timestamps and `stale_live_values` was checked before publishing.
- [ ] Geographic inputs were projected or supplied in a metric frame; never mix degrees and metres.
- [ ] Piping screening run: no clashes, slopes met; pipe sizes, wall thickness, temperatures and
      nozzle positions supplied or listed as gaps.
- [ ] Pipe stress run for hot or flexibility-fail lines: `converged` is true, every fail and every
      nozzle without allowables is in `data_gaps`, and assumed corrosion allowance or design pressure
      is stated.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Templates invisible on the field view | Real 20 m structures on a 6 km scene | Keep the default display floor, or set `min_feature` |
| Well path squashed or stretched | Vertical exaggeration on a scene with wells | Use exaggeration 1 for wells; use it only for flat seabed views |
| All NeqSim equipment marked assumed | No positions supplied, auto layout used | Supply `position_m` from a layout study or STID coordinates |
| Vessel drawn as a placeholder | `calcDesign()` not run or diameter infinite | Run the process and `getMechanicalDesign().calcDesign()` first |
| Compressor drawn as a tiny cylinder | Impeller dimensions used as package size | Adapters use the module envelope for rotating equipment; supply `size_m` |
| Objects in two places | Mixed coordinate frames (plant grid and UTM) | Translate one scene with `scene.translate(...)` before `merge` |
| Pipe climbs high over the whole plant | A tall item (column, flare) sits under the auto route | Supply the real `route`, or accept it as illustrative; the caption says auto-routed |
| Supplied route detached from equipment | Route in another frame than the scene | Give routes in the scene frame (metres), or translate them with the scene |
| Pipe has no supports or flexibility result | No `diameter` on the connection | Give the outer diameter from the line list; the drawn thickness is not a size |
| Pipe starts mid-face instead of at the nozzle | No nozzle schedule and no port name | Add `nozzles` from the datasheet or set `from_port`/`to_port` |
| Every stress result is `unavailable` | Installed NeqSim jar older than 3.29.0 | Update NeqSim, or start the JVM with a newer jar before importing `neqsim` |
| Nozzle status `no_allowable` | End object has no `nozzle_allowables` | Add the vendor allowables; until then nozzle loads are reported, not judged |

## Limitations

- Auto-routed pipes show a feasible illustrative path, not the as-built path; only a supplied route
  (isometric, 3D model export, surveyed line) shows where a pipe really runs.
- The piping screening (spans, slope, B31.3 319.4.1) applies to uniform-size lines between two
  anchors; use `analyse_pipe_stress` for the load cases, support and nozzle loads.
- The pipe stress analysis is static and linear-elastic: no response-spectrum or time-history
  dynamics (slug, surge, water hammer), no creep, no fatigue spectrum beyond the range factor f;
  bends are flexible tangent elements; supports sit at the screening positions unless you move them.
  Its accuracy is only as good as the route: on auto-routed pipes it is a concept-stage check, and a
  critical line still needs a formal stress analysis on the real isometric.
- Geographic projection is equirectangular about the scene centre (screening accuracy).
- The HTML viewer is a lightweight painter's-algorithm renderer for hundreds of objects, not a full
  CAD model viewer; use the GLB in a CAD or web viewer for large models.
- Live values are attached as snapshots; refreshing them is the caller's job.

## References

- glTF 2.0 specification (Khronos Group), binary GLB container.
- ASME B31.3 Process Piping, para. 319.4.1 (simplified flexibility analysis), 304.1.2, 319, 320
  and Appendix D (flexibility and stress intensification factors).
- NeqSim `PipeStressModel`: `docs/process/mechanical_design/pipe_stress_model.md` in the NeqSim repo.
- MSS SP-69 / SP-58 pipe hanger spacing tables (water-filled steel pipe), used as benchmark.
- Minimum-curvature survey calculation (standard directional-survey method).
- Related skills: `neqsim-plant-layout-study`, `neqsim-subsea-layout-geometry`,
  `neqsim-well-trajectory-anticollision`, `neqsim-reservoir-3d-visualisation`,
  `neqsim-professional-reporting`.
