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

## The four traps that produce a wrong or empty picture

| Trap | Symptom | Fix |
| --- | --- | --- |
| Camera set in normalized units while the mesh sits at z ≈ −29 000 m | Titles and colour bar render, **model is invisible** | Centre the mesh on the origin, then `view_isometric()` + `reset_camera()` |
| Depth used directly as elevation | Model appears upside down | Negate z; depth increases downward, elevation upward |
| No vertical exaggeration | 48 m of pay across 1.9 km is a flat sheet | Scale z by 6–10 and **state the factor in the caption** |
| Plain `clip_box` | Cut face shows triangles, not cells | `clip_box(..., crinkle=True)` keeps whole cells |

An invisible model is the dangerous one: the figure still has a title, a colour
bar and a legend, so it looks like a rendering failure rather than a framing
error, and a caption written from the intent will survive.

## Core recipe

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

## Related Skills

- `neqsim-near-well-and-injectivity` — builds and runs the OPM Flow deck this
  skill renders.
- `neqsim-reservoir-model-builder` — assembles the static model.
- `neqsim-professional-reporting` — figure, caption and discussion conventions
  for the report the figure ends up in.
