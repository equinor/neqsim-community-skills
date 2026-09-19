# neqsim-fem-coupling

Link a NeqSim process simulation and engineering documents to a finite-element
model of the solid.

The skill has nine layers, each usable on its own:

| Module | Purpose |
|---|---|
| `design_basis` | Merge P&ID, STID, datasheet, insulation-specification, inspection and plant-data inputs into one traceable design basis; report conflicts and missing fields before meshing |
| `materials` | Solid-side properties - conductivity, heat capacity, modulus, expansion, allowable - with the basis recorded, because NeqSim supplies only the fluid side |
| `thermal` | Turn a flashed NeqSim fluid into a film coefficient, a Biot and Fourier number, a thermal penetration depth, and the element size and time step that follow |
| `conduction` | A dependency-free one-dimensional multilayer finite-element solver, steady and transient, verified against the closed-form composite resistance; includes the cooldown model with a lumped bore inventory, and calibration of an unmeasured far boundary |
| `mesh` | A structured Gmsh mesh for layered geometry - two-dimensional, or swept into three by revolving a pipe wall or extruding a plate - every layer interface on an element boundary, a physical group per material and per face |
| `solver` | Screen which finite-element backend is defensible, then write, run and read back a scikit-fem or FEniCSx case driven by one shared `inputs.json` |
| `visualise` | Render the mesh and the solved field off-screen with PyVista: one surface view in two dimensions, and surface, cut-plane and clipped views in three |
| `stress` | Convert the temperature field into thermal and pressure stress with the right stress category attached |
| `model` | Gate the study on discretisation, mesh independence, energy balance and boundary placement, and reduce it to the U-value, U-multiplier and hot-spot factor a one-dimensional NeqSim model consumes |

This is the solid-side companion to `neqsim-cfd-coupling`. CFD resolves the fluid
and produces a film coefficient; FEM consumes it and resolves the solid.

NeqSim, Gmsh, scikit-fem, FEniCSx and PyVista are all optional. Without NeqSim the
fluid state is supplied directly; without a mesher, a solver or a renderer the
geometry, the case and the field file are still written, and the commands needed to
run them elsewhere are returned.

## Install and test

```bash
pip install -e ".[test]"
pytest

# optional, to actually mesh and solve two- and three-dimensional cases:
pip install -e ".[fem]"

# optional, to render the mesh and the solved field:
pip install -e ".[viz]"
```

## Run the examples

```bash
python examples/insulated_flowline_defect.py   # documents -> NeqSim -> 1D -> 2D -> U-multiplier
python examples/subsea_cooldown.py             # NeqSim inventory + hydrate temperature -> no-touch time
```

The first takes a line from a STID register, an insulation specification and an ROV
inspection report, flashes the fluid in NeqSim, derives the film coefficient and the
mesh targets, solves the intact section in one dimension against a closed-form
check, meshes the damaged section, runs it at two refinement levels, gates the
result, and converts it into the U-value multiplier a NeqSim pipeline model should
carry.

The second takes the shut-in inventory and the hydrate temperature from a NeqSim CPA
flash and produces a no-touch time from the transient wall model.

## Why one dimension first

The one-dimensional steady solution is checked against the analytic composite
resistance and reports the deviation. A two-dimensional field cannot be verified
that way, so if the one-dimensional answer is not understood first, nothing
downstream of it can be defended.

## Reference notebook

A worked, executed version of the NeqSim -> Gmsh -> scikit-fem / FEniCSx ->
PyVista stack lives in the NeqSim-Colab repository:

- `notebooks/fluidflow/finite_element_methods_oil_gas_neqsim.ipynb` - radial
  insulated-pipe heat transfer, a damaged-insulation section, NeqSim-derived
  diffusion in porous rock, and wellbore-to-formation conduction.

See `SKILL.md` for the engineering method, validation checklist and limitations.
