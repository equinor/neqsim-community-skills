---
name: neqsim-reservoir-3d-visualisation
calculation_basis: "screening"
version: "0.1.0"
description: "Render a reservoir simulation grid in 3D from its Eclipse-format output: cell-corner geometry from the EGRID so corner-point and box grids render identically, static properties from the INIT, dynamic properties from the UNRST, wells as tubes, crinkle cutaways that keep whole cells, threshold views that isolate remaining oil, and exploded layer views. USE WHEN: an OPM Flow or Eclipse run needs a presentation-grade 3D figure, a sweep or bypassed-oil claim needs visual evidence, a property field must be inspected for spatial correlation before it is trusted, or a reservoir illustration is going into a report or decision gate. Covers the vertical-exaggeration, camera-framing, corner-ordering and scalar-range traps that silently produce an empty or misleading picture."
last_verified: "2026-09-21"
requires:
  python_packages: [pyvista, resdata, numpy, matplotlib]
  java_packages: []
  env: []
  network: []
---

# Reservoir 3D Visualisation

A reservoir figure is evidence, not decoration. A sweep claim, a bypassed-oil
claim, or a "the property field looks reasonable" claim is far easier to check
in a picture than in a table — and far easier to get silently wrong.

This skill renders a simulation grid from the simulator's own output files, so
the picture shows what the simulator actually used rather than what the build
script intended.

## When to Use

- An OPM Flow or Eclipse run needs a 3D figure for a report or decision gate.
- A sweep, channelling or bypassed-oil statement needs visual support.
- A generated property field must be inspected before it is trusted.
- A model's layering, well placement or grid extent must be shown to a reviewer.

Do not use it to *measure* anything. Read numbers from the summary vectors; use
the picture to show where they came from.

## Inputs

| Group | Fields |
| --- | --- |
| Geometry | `CASE.EGRID` (cell-corner geometry, valid for box or corner-point grids) |
| Static properties | `CASE.INIT` (e.g. `PERMX`, `PORO`, `SATNUM`) |
| Dynamic properties | `CASE.UNRST` (e.g. `SWAT`, `PRESSURE`, `SGAS`) — requires `RPTRST BASIC=2` in the deck |
| Wells | Well trajectories/completions from the grid or a separate well-track source |
| Presentation choices | Vertical exaggeration factor `VE`, colour-map range `clim`, crinkle-cut plane, threshold value |

All inputs are the simulator's own output files — never hand-built geometry —
so the picture matches what the simulator actually solved.

## Outputs

- A full-block static-property render (extent, layering, well placement).
- A crinkle cutaway exposing vertical heterogeneity.
- A threshold view isolating cells above/below a dynamic-property cutoff (e.g.
  remaining oil).
- An optional exploded-layer view.
- Each figure's caption states the vertical-exaggeration factor and the `clim`
  range used, per `neqsim-professional-reporting` conventions.

## Engineering Method

1. Read cell-corner geometry from the EGRID (never rebuild from `DXV`/`DYV`/`DZV`)
   and permute Eclipse corner ordering to VTK hexahedron ordering.
2. Negate depth to elevation and apply the stated vertical exaggeration.
3. Re-centre the mesh on the origin before framing the camera.
4. Attach static (`INIT`) and dynamic (`UNRST`, last report step) property
   arrays as cell data.
5. Render the full block, a crinkle cutaway, and a threshold view, each with an
   explicit `clim`.
6. Interpret only **location** claims from the figure (sweep, channelling,
   bypassed-oil shape); take magnitudes from the summary vectors.

## Read the geometry from the EGRID, never rebuild it

Rebuilding the mesh from `DXV`/`DYV`/`DZV` works only for a box. Reading the
cell corners works for every grid, so the same script keeps working when a
corner-point grid replaces the box.

```python
from resdata.grid import Grid
grid = Grid("CASE.EGRID")
corners = [grid.get_cell_corner(n, global_index=c) for n in range(8)]
```

**Corner ordering is the first trap.** Eclipse orders corners as top
SW, SE, NW, NE then the same four on the bottom. VTK's hexahedron wants the
bottom quad counter-clockwise first, then the top. The permutation is:

```python
ECL_TO_VTK = [4, 5, 7, 6, 0, 1, 3, 2]
```

Get this wrong and the cells render as bow-ties — visible as dark self-
intersecting facets rather than as an error.

## Common Mistakes

| Trap | Symptom | Fix |
| --- | --- | --- |
| Camera set in normalized units while the mesh sits at z ≈ −29 000 m | Titles and colour bar render, **model is invisible** | Centre the mesh on the origin, then `view_isometric()` + `reset_camera()` |
| Depth used directly as elevation | Model appears upside down | Negate z; depth increases downward, elevation upward |
| No vertical exaggeration | 48 m of pay across 1.9 km is a flat sheet | Scale z by 6–10 and **state the factor in the caption** |
| Plain `clip_box` | Cut face shows triangles, not cells | `clip_box(..., crinkle=True)` keeps whole cells |

An invisible model is the dangerous one: the figure still has a title, a colour
bar and a legend, so it looks like a rendering failure rather than a framing
error, and a caption written from the intent will survive.

## Python Usage Pattern

```python
import numpy as np, pyvista as pv
from resdata.grid import Grid
from resdata.resfile import ResdataFile

pv.OFF_SCREEN = True
VE = 8.0                                   # vertical exaggeration - state it

grid = Grid("CASE.EGRID")
ncell = grid.get_nx() * grid.get_ny() * grid.get_nz()
ECL_TO_VTK = [4, 5, 7, 6, 0, 1, 3, 2]

points = np.empty((ncell * 8, 3))
cells = np.empty((ncell, 9), dtype=np.int64)
for c in range(ncell):
    xyz = np.array([grid.get_cell_corner(n, global_index=c) for n in range(8)])
    xyz[:, 2] *= -VE                       # depth -> exaggerated elevation
    points[c * 8:c * 8 + 8] = xyz[ECL_TO_VTK]
    cells[c, 0] = 8
    cells[c, 1:] = np.arange(c * 8, c * 8 + 8)

mesh = pv.UnstructuredGrid(cells.ravel(),
                           np.full(ncell, pv.CellType.HEXAHEDRON), points)
origin = np.array(mesh.center)             # keep the camera near the data
mesh.translate(-origin, inplace=True)

mesh.cell_data["PERMX"] = np.array(ResdataFile("CASE.INIT")["PERMX"][0])
mesh.cell_data["SOIL"] = 1.0 - np.array(ResdataFile("CASE.UNRST")["SWAT"][-1])
```

`INIT` holds the static arrays and `UNRST` the dynamic ones; `[-1]` is the last
report step. A restart file only exists if the deck requested it
(`RPTRST BASIC=2`).

## The three views worth producing

1. **Full block, static property.** Shows extent, layering and well placement.
2. **Crinkle cutaway.** Shows vertical heterogeneity the outer faces hide.
3. **Threshold on the dynamic property.** `mesh.threshold(0.55, scalars="SOIL")`
   plus `mesh.outline()` isolates the cells that still hold oil. This is the
   view that makes a bypassed-oil claim checkable, because the bypassed volume
   appears as a shape with a location rather than as a percentage.

An exploded layer view (translate each k-layer apart) is worth adding when
layer-to-layer contrast is the point.

## Fix the colour range, or the figure lies

`clim` must be set explicitly and held constant across any figures being
compared. Left to autoscale, two panels of the same property use different
scales and a reader compares colours that do not correspond. For a saturation
figure, set `clim=[0.1, 0.9]` rather than `[0, 1]`: the connate and residual
endpoints are never reached, so the full range wastes most of the colour map.

## What the picture is allowed to establish

A figure can support a claim about **location** — which region is swept, where a
high-permeability path runs, which layer the water enters. It cannot establish a
magnitude; take that from the summary vectors.

One pattern recurs and is worth looking for: remaining oil forming a **rim at
the model boundary**. That is usually the no-flow outer boundary with no well
near it, i.e. an artefact of the model extent and well placement rather than a
property of the reservoir. Check whether the rim disappears when the pattern is
extended before reporting it as bypassed oil.

A second pattern: a property field that looks like salt-and-pepper noise has no
spatial correlation, so it has no connected flow paths. It cannot channel, and
it will flatter the sweep. Correlated fields (a smoothed Gaussian field) break
through earlier than uncorrelated ones at the same mean and variance.

## Environment

`pyvista` needs VTK, which ships as a wheel on all three platforms. Off-screen
rendering (`pv.OFF_SCREEN = True`) needs no display on Windows or macOS; on a
headless Linux box call `pv.start_xvfb()` first.

If PyVista cannot be installed, an exposed-face renderer built on
`matplotlib`'s `Poly3DCollection` produces an acceptable block view — draw only
the faces whose neighbour is outside the shown cell set, and shade by layer
index for a depth cue. It is markedly slower above ~50 000 cells and has no
real lighting, so prefer PyVista when it is available.

## Validation Checklist

- [ ] Geometry read from the EGRID cell corners, not rebuilt from `DXV`/`DYV`/`DZV`.
- [ ] Corner order permuted with `ECL_TO_VTK = [4, 5, 7, 6, 0, 1, 3, 2]` (no
      bow-tie facets).
- [ ] Mesh re-centred on the origin before `view_isometric()` / `reset_camera()`.
- [ ] Vertical exaggeration factor chosen, applied, and stated in the caption.
- [ ] `clim` set explicitly (not autoscaled) and held constant across compared
      figures.
- [ ] Cutaways use `crinkle=True` so cut faces show whole cells.
- [ ] Any "bypassed oil" or "sweep" claim is checked against the summary
      vectors, not read as a magnitude off the figure.
- [ ] A rim of remaining oil at the model boundary is checked against well
      placement/model extent before being reported as bypassed oil.

## Limitations

- Establishes **location**, not magnitude — pressures, saturations and volumes
  must be read from the simulator's summary vectors.
- A restart file (`UNRST`) only exists if the deck requested it
  (`RPTRST BASIC=2`); without it, no dynamic-property view is possible.
- The `matplotlib` fallback (no PyVista) is slow above ~50 000 cells and has no
  real lighting/shadowing, so depth cues are weaker.
- Headless Linux rendering needs `pv.start_xvfb()`; without a display or Xvfb,
  off-screen rendering can fail silently.
- Does not model or check flow-simulation validity — it only visualises
  results a separate simulator (OPM Flow/Eclipse) already produced.

## References

- Eclipse Reference Manual — grid geometry, `EGRID`/`INIT`/`UNRST` file formats.
- `resdata` (equinor/resdata) documentation — `Grid`, `ResdataFile` APIs.
- PyVista documentation — `UnstructuredGrid`, `clip_box`, `threshold`, camera
  and colour-map (`clim`) controls.

## Related Skills

- `neqsim-near-well-and-injectivity` — builds and runs the OPM Flow deck this
  skill renders.
- `neqsim-reservoir-model-builder` — assembles the static model.
- `neqsim-professional-reporting` — figure, caption and discussion conventions
  for the report the figure ends up in.
