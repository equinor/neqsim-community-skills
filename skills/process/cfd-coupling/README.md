# neqsim-cfd-coupling

Link a NeqSim process simulation and engineering documents to a CFD study.

The skill has five layers, each usable on its own:

| Module | Purpose |
|---|---|
| `design_basis` | Merge P&ID, STID, datasheet, plant-data and estimated inputs into one traceable design basis; report conflicts and missing fields before meshing |
| `boundary` | Turn a flashed NeqSim fluid into single-phase CFD boundary conditions, turbulence inlet state, flow regime and solver class |
| `multiphase` | Take both phases and the interfacial tension from one flash, derive the superficial and mixture quantities, and screen which multiphase model is defensible |
| `openfoam` | Write, run and read back a complete OpenFOAM case - steady single-phase RANS or transient volume of fluid - on pipe, duct or arbitrary imported geometry |
| `model` | Gate a CFD study on quality and convert local-versus-bulk results into enhancement factors |

NeqSim and OpenFOAM are both optional. Without NeqSim the fluid state is supplied
directly; without OpenFOAM the case is still written, and the commands needed to
run it elsewhere are returned.

## Install and test

```bash
pip install -e ".[test]"
pytest
```

## Run the examples

```bash
python examples/pid_to_openfoam_case.py     # P&ID + STID -> NeqSim -> steady case
python examples/multiphase_vof_case.py      # two-phase flash -> VOF case
```

The first takes a line from a P&ID and a STID tag register, flashes the fluid in
NeqSim, derives boundary conditions, sizes the near-wall cell for a y+ target,
writes a complete OpenFOAM case, runs it when OpenFOAM is available, and converts
the solved wall shear into a mass-transfer enhancement factor.

The second flashes a wellstream into gas and liquid, reads the interfacial tension
straight out of NeqSim, screens whether volume of fluid is the right model, and
writes the transient two-phase case when it is.

## Reference notebooks

Worked, executed versions of this workflow live in the NeqSim-Colab repository
under `notebooks/fluidflow/`:

- `pid_datasheet_to_cad_cfd_neqsim.ipynb` — P&ID and datasheets to CAD, mesh and CFD
- `neqsim_cadquery_gmsh_openfoam_workflow.ipynb` — CadQuery and Gmsh geometry chain
- `neqsim_openfoam_cfd.ipynb` — the minimal NeqSim-to-OpenFOAM coupling
- `neqsim_openfoam_compressor_inlet_wet_gas.ipynb` — wet gas at a compressor inlet
- `neqsim_openfoam_flashing_valve.ipynb` — flashing liquid across a valve

See `SKILL.md` for the engineering method, validation checklist and limitations.
