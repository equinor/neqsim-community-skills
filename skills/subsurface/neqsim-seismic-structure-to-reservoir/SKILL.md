---
name: neqsim-seismic-structure-to-reservoir
calculation_basis: "screening"
version: "0.1.0"
description: "Seismic or mapped structure to a screening reservoir model: finds surfaces, SEG-Y, logs and ties in task folders; reads IRAP/ZMAP+/XYZ or tracks a horizon from a well seed; time-to-depth on well ties; crest, spill and closure; area and GRV per contact; builder inputs, gate records and an OPM grid. USE WHEN: a reservoir model should use seismic or interpreted horizons."
last_verified: "2026-11-15"
requires:
  python_packages: [numpy, scipy, matplotlib, segyio]
  java_packages: []
  env: []
  network: []
---

# Seismic Structure to Reservoir Model

Use this skill to take structure from seismic, or from horizons someone has already interpreted, into the reservoir-model workflow. It finds the data, builds a depth top, checks whether the top forms a trap, and computes area and gross rock volume for each contact. It then gives `neqsim-reservoir-model-builder` area, equivalent thickness and datum, plus `data_first_gate` records for the geometry ingredient, and can write a layered OPM Flow grid.

The order of preference follows the builder's data ladder:
1. A published grid (`neqsim-reservoir-model-builder` static-model route).
2. Interpreted horizons and faults.
3. One interpreted depth or time surface.
4. A horizon tracked here from seismic, the screening fallback when nobody has interpreted it yet.

## When to Use

- A task folder, a data owner or a surface service supplies a reservoir-top surface (IRAP classic ASCII, ZMAP+, XYZ points, or a binary format through xtgeo).
- Only a SEG-Y cube exists, and a top must be picked to get any structure at all. The seed is a well with a known top, or a user's pick.
- A model needs area, closure, spill point, relief or gross rock volume for a contact or a target volume, instead of an assumed play-typical block.
- An OPM Flow screening grid is needed that keeps the mapped structure and thickness.

## Inputs

- `search_paths`: folders to scan (read only). `discover` classifies published grids, depth and time surfaces, fault files, SEG-Y, well logs, well-tie tables (TWT and depth) and well-top tables (well, X, Y, formation, TVDSS). Folders holding this skill's own output (`structure_evidence.json`) and `out_dir` are skipped, so a tracked top from an earlier run is never re-read as an interpreted surface.
- Top: `top_surface` (with `surface_domain` when the name does not say), or a discovered surface whose name contains `top`. Otherwise `seismic` with a `seed` (`inline`, `crossline`, `twt_ms`) or a `well` (`x`, `y`, `top_depth_m`). When neither is given, the first discovered pick whose formation name contains `top` seeds the tracking, and a warning names it.
- Velocity: `velocity.ties` or `velocity.ties_file` (`twt_ms`, `depth_m`), or a discovered tie table; or `v0`/`k` given directly, which is labelled uncalibrated. `datum_m` is the seismic reference datum below MSL.
- Base: `base_surface` or `thickness_m`. Without either, the reservoir is as thick as the column, which gives an upper bound.
- Contact: `contact_m` or `target_grv_mm3`. Without either, the contact is placed at the spill point, which is the maximum closure and is reported as such.
- Options:
  - `crest_near` picks one structure among several.
  - `undefined_nodes`: `leak` (default) or `barrier` for fault gaps.
  - `smooth_cells`: 1 for tracked tops.
  - `min_closure_nodes`.
  - `tie_tolerance_m`: well-top misfit that triggers a warning; default 10.
  - `grid`: `nz`, `coarsen`, `porosity`, `net_to_gross`, `water_saturation`, `permeability_mD`, `kv_kh`.

## Outputs

- `structure_evidence.v1` (`structure_evidence.json`), always `unverified`, with:
  - status (`ok`, `no_closure`, `blocked`) and the missing items;
  - inventory, geometry candidates, well tops, sources, seed and velocity record;
  - `well_tie_check`: mapped top against each well `top` pick, as surface minus pick;
  - closure (crest, spill, spill reason, relief), surface roughness, the contact sweep (area and GRV for each contact), volumes at the chosen contact;
  - `builder_inputs` (`area_km2`, `gross_thickness_m` as GRV / area, `datum_depth_m_tvdmsl` as the mean depth of the hydrocarbon column, and `field_provenance`: `interpreted` for a supplied surface, `derived` for a tracked top);
  - geometry `gate_attempts`, warnings and required checks.

  Gate records cover only rungs down to the one used. A higher rung with no data found is `absent`. A higher rung whose data was found but not used (a published grid, horizons with faults) gets no record, so `data_first_gate` blocks until someone tries it. A warning says so.
- Depth top as IRAP ASCII, a closure map PNG and an optional `grid.grdecl` (DX, DY, DZ, TOPS, ACTNUM, PORO, NTG, PERMX/Y/Z; RUNSPEC needs `DIMENS nx ny nz /`). The grid summary reports the net pore volume above the contact, and also `hcpv_mm3` when `water_saturation` is given.
- Library: `Surface` (sample, resample, smooth, coarsen, normalise `yflip`), `read_surface`, `write_irap`, `write_zmap`, `grid_points`, `calibrate_velocity`, `time_to_depth`, `load_cube`, `track_horizon`, `seed_from_well`, `analyse_closure`, `volumes_at_contact`, `contact_sweep`, `contact_for_volume`, `build_layered_grid`, `discover`, `geometry_attempts`, `run_structure_workflow`.

## Engineering Method

1. **Geometry.** Node `(i, j)` lies at `x = xori + i·xinc·cos r − j·yinc·yflip·sin r` and `y = yori + i·xinc·sin r + j·yinc·yflip·cos r`. This is the convention of surface-grid services and xtgeo, so served grids load without reordering.
2. **Tracking.**
   - The seed snaps to the strongest extremum within ±12 ms.
   - Growth always expands the strongest accepted pick first. A neighbour is accepted when it has an extremum of the same polarity within `max_jump_samples` and at least `min_amplitude_ratio` of the seed amplitude, refined with a parabolic fit.
   - Geometry is a least-squares fit of the trace coordinates to the inline/crossline grid.
3. **Depth conversion.** `V(z) = v0 + k z` below the datum, giving `z = (v0/k)(e^{k t} − 1)` with one-way time `t`. One tie fixes `v0`; two or more also fit `k`. The tie RMS is reported.
4. **Closure.**
   - A priority flood from the crest adds nodes in depth order; the running maximum is the fill level.
   - The spill is the first level at which the fill reaches the grid edge, a footprint boundary, an undefined node (when gaps leak), or climbs into a neighbouring high over a saddle (more than `min_neighbour_relief_m` higher).
   - The region above any contact shallower than the spill is the set of nodes reached below it, so one flood gives every contact without stepping.
5. **Volumes.** GRV = Σ max(0, min(base, contact) − top) × cell area over the closure. The equivalent thickness GRV / area makes the builder's `area × thickness` reproduce the mapped volume.
6. **Noise and coverage guards.** Closures of fewer than `min_closure_nodes` nodes are rejected. A relief below three times the map roughness (median absolute second difference) is flagged. A spill at the edge of the mapped area is flagged as a minimum, limited by data coverage. Every well `top` pick is compared with the mapped top.
7. **Grid.** Each surface node becomes a column of `nz` proportional layers between top and base, in local Cartesian geometry. Properties pass the builder's `build_static_model_deck_input` checks, and the grid GRV above the contact equals the closure GRV.

## Python Usage Pattern

```python
from seismic_structure import run_structure_workflow, discover

print(discover(["<task>/step1_scope_and_research/references"]))
evidence = run_structure_workflow({
    "field_name": "Example", "fluid_type": "oil",
    "search_paths": ["<task>/step1_scope_and_research/references"],
    "seismic": {"well": {"x": 456200.0, "y": 6781300.0, "top_depth_m": 2105.0}},
    "velocity": {"ties_file": "<task>/step1_scope_and_research/references/checkshot.csv"},
    "thickness_m": 45.0, "contact_m": None,
    "grid": {"nz": 8, "porosity": 0.22, "net_to_gross": 0.8, "permeability_mD": 150, "kv_kh": 0.1},
    "out_dir": "<task>/step2_analysis/structure",
})
print(evidence["status"], evidence["closure"], evidence["builder_inputs"], evidence["warnings"])
```

Hand-off: pass `evidence["builder_inputs"]` to `reservoir_model_builder.build_reservoir_model(...)`, together with the rock and fluid inputs. Merge your own `field_provenance` for those inputs (`default` for user assumptions, `measured` for log or core values). Then add `evidence["gate_attempts"]["geometry"]` to the `data_first_gate` attempts.

Command line: `<python> -m seismic_structure discover <folder> --out inventory.json` writes the inventory, `geometry_candidates` and absent rungs. `<python> -m seismic_structure run config.json` prints a one-line summary and exits with 2 when the run is blocked.

## Validation Checklist

- [ ] The horizon is the reservoir top: the depth at each well matches its top in the same datum. A mismatch beyond the stated uncertainty means the wrong horizon or the wrong velocity.
- [ ] Domain, depth sign, datum and CRS are confirmed, and the well coordinates are in the surface CRS.
- [ ] The velocity model is calibrated on ties, with the tie RMS reported. An uncalibrated `v0` is stated as an assumption.
- [ ] The spill reason is plausible. Undefined nodes are treated as barriers only when someone has agreed they are sealing faults.
- [ ] A contact at the spill point is described as the maximum closure, not as a contact.
- [ ] The closure is larger than the noise guards. For tracked tops, the map is inspected for cycle-skipping (checkerboard patterns).
- [ ] The builder volumes reproduce the evidence GRV × NTG × porosity × (1 − Sw).

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Closure of a few nodes or a few metres | Picking noise or cycle-skips on a weak event | Seed on a strong, continuous reflector; smooth; check the roughness warning |
| Volume too large by several times | No base or thickness: reservoir as thick as the column | Give `thickness_m` or a base surface |
| Spill far too shallow | Fault gaps treated as leaks | Decide with the interpreter; set `undefined_nodes: barrier` only for sealing faults |
| Two structures merged | Crest of the wrong high | Pass `crest_near` with the prospect location |
| Depth off by tens of metres | Uncalibrated velocity, or datum not MSL | Calibrate on ties; set `datum_m` |
| Status `blocked` | Time surface without velocity, or no top and no seed | Supply what `missing` lists |

## Limitations

- Tracking follows one continuous reflector. It does not cross faults reliably or separate interfering events, and it is not interpretation.
- There are no fault surfaces or fault blocks. The grid has local Cartesian geometry (no rotation, no corner points) and constant properties.
- Depth conversion is a single linear velocity function, with no lateral velocity variation.
- Volumes are gross rock volumes; net-to-gross, porosity, saturation and formation volume factor come from the builder or from logs.

## Related NeqSim Functionality

- `neqsim-seismic-segy-reading`: inspect SEG-Y first (extent, CRS hints, pre-stack, domain). It supplies the cube reader used here.
- `neqsim-well-log-reading`: well tops, porosity and NTG per zone, which feed the builder and the depth tie.
- `neqsim-reservoir-model-builder`: volumetrics, the data-first gate and the static-model checks used by the grid.
- `neqsim-reservoir-3d-visualisation` and `neqsim-opm-open-reservoir-decks`: run and view the grid in OPM Flow.

## References

- Gluyas, J. and Swarbrick, R. (2004), Petroleum Geoscience, Blackwell (trap geometry, spill point and gross rock volume).
- Barnes, R., Lehman, C. and Mulla, D. (2014), Priority-flood: an optimal depression-filling and watershed-labeling algorithm, Computers & Geosciences 62, 117-127.
- Al-Chalabi, M. (1997), Instantaneous slowness versus depth functions, Geophysics 62(1) (linear velocity functions).
