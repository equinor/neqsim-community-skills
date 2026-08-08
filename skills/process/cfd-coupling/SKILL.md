---
name: neqsim-cfd-coupling
version: "0.3.0"
description: "Link a NeqSim process simulation and engineering documents to a CFD study, single-phase or multiphase. Merges P&ID, STID, datasheet and plant-data inputs into a traceable design basis, converts a flashed NeqSim fluid into CFD boundary conditions, takes both phases and the interfacial tension from a multiphase flash and screens which multiphase model is defensible, writes and runs a complete OpenFOAM case (steady single-phase RANS or transient volume of fluid) for arbitrary geometry, reads the solved fields back, gates the study on wall treatment / mesh independence / turbulence model, and converts local-versus-bulk results into enhancement factors for one-dimensional models. USE WHEN: a task needs local flow detail a one-dimensional model cannot generate - velocity or shear peaks at bends, welds, restrictions, tees, headers or tube bundles, flow maldistribution across a bundle or manifold, stratified or slug two-phase behaviour in a line, or a pressure-drop check on real geometry - or when an existing CFD report must be qualified before its numbers are trusted."
last_verified: "2026-08-07"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# CFD Coupling

A one-dimensional model works in bulk quantities. Damage does not: it concentrates
wherever the local flow field departs from the bulk — bends, welds, restrictions,
headers, tube bundles. Screening models bridge that gap with generic textbook
multipliers.

This skill closes the gap properly. It takes whatever is known about a component
(P&ID, STID tag register, datasheets, plant data), takes the fluid from a NeqSim
flash, builds and runs an OpenFOAM case on the real geometry, and converts the
solved field back into the factor the one-dimensional model was guessing at. When
a CFD study already exists it qualifies that study instead of running a new one.

Every layer works on its own. NeqSim and OpenFOAM are both optional: without
NeqSim the fluid state is stated directly, and without OpenFOAM the case is still
written and can be transferred and run elsewhere.

## When to Use

- A screening model needs a local enhancement factor and a generic multiplier is
  currently being assumed.
- Pressure drop, velocity or wall shear is needed on real geometry rather than on
  an equivalent-length correlation.
- Flow maldistribution across a bundle, manifold or header matters to the answer.
- Two phases share the line and the interface matters - stratified, slug or annular
  flow, a free surface, or liquid accumulating in a low point.
- A CFD report, vendor flow analysis or CFD/FEM deliverable is attached to an
  equipment tag and must be qualified before its numbers are used.
- A new CFD run must be specified and needs fluid properties, turbulence inlet
  values and near-wall mesh sizing.

## When *Not* to Use

- As a substitute for a qualified CFD engineer on a design decision. This is a
  screening and coupling toolkit, not a verification-and-validation review.
- To extract a number from a CFD study that fails the quality gate.
- For droplet break-up statistics, separation efficiency or a dense dispersed
  phase. The multiphase screening will say `lagrangian` or `euler_euler`; those
  cases are recommended with a reason but not generated here.
- For a temperature field. The generated cases solve momentum only, with the
  fluid properties frozen at the inlet flash. A stagnant or dead-leg region, a
  buoyancy-driven or thermally stratified region, or any wall-temperature
  question needs a buoyant conjugate solver (`buoyantSimpleFoam`,
  `buoyantPimpleFoam`, `chtMultiRegionFoam`) that this skill does not write.
  Use `fem-coupling` for the wall and near-wall temperature, and hand-build the
  buoyant case if the fluid-side field itself is the deliverable.

## Inputs

| Stage | Input | Meaning |
|---|---|---|
| `build_design_basis` | `tag`, `component_kind`, `sources` | Equipment or line identifier, the component class from the P&ID, and one entry per source with `source`, `reference` and `values` |
| `fluid_state_from_neqsim` | flashed NeqSim system, `phase` | Density, viscosity, speed of sound and flow of the chosen phase |
| `derive_boundary_conditions` | `FluidState`, `hydraulic_diameter_m`, velocity **or** volumetric flow | Optional `turbulence_intensity`, `turbulence_length_scale_m`, `flow_area_m2` |
| `multiphase_state_from_neqsim` | flashed NeqSim system, optional `continuous_phase` / `dispersed_phase` | Both phases plus the interfacial tension between them |
| `derive_multiphase_conditions` | `MultiphaseState`, `hydraulic_diameter_m`, optional `flow_regime` | Superficial and mixture quantities, and the multiphase model screening |
| `MeshSpec` | `kind` (`pipe`, `channel`, `external`), dimensions, cell counts | Optional `first_cell_height_m` to drive near-wall grading from a y+ target |
| `OpenFoamCase` | boundary conditions, mesh, `flavour`, `wall_treatment` | `flavour` is `org` (OpenFOAM v11+, `foamRun`) or `legacy` (`simpleFoam`) |
| `assess_quality` | `turbulence_model`, `wall_treatment`, `y_plus`, `mesh_levels`, `gci_percent` | Applies to a generated case or an existing report |
| `evaluate_local_enhancement` | bulk and local peak velocity, and wall shear when available | Bulk values come from the one-dimensional model |

## Outputs

| Output | Contents |
|---|---|
| `CfdDesignBasis` | Accepted values, per-field source and confidence, conflicts, missing fields, `ready_for_meshing` |
| `CfdBoundaryConditions` | Velocity, Reynolds, Mach, flow regime, compressibility class, `k`, `epsilon`, `omega`, recommended turbulence model and solver, warnings |
| `MultiphaseBoundaryConditions` | Superficial velocities, mixture velocity/density/viscosity, Reynolds, Weber, Froude, maximum stable droplet, Stokes number, recommended multiphase model with its rationale |
| `OpenFoamCase.write` | A complete case tree: `system/`, `constant/`, `0/`, with function objects for wall shear, y+, patch fluxes and pressures |
| `VofOpenFoamCase.write` | A transient two-phase tree: `alpha.<phase>`, `p_rgh`, `constant/g`, per-phase properties, interfacial tension, `setFieldsDict`, Courant-limited control |
| `OpenFoamCase.mesh_warnings` | Near-wall grading that would over-stretch the mesh, with the cell count needed to avoid it |
| `RunOutcome` | `completed`, `failed` or `not_executed`, per-command output, and the commands needed to run the case elsewhere |
| `OpenFoamResults` | Continuity error, pressure drop, peak and mean wall shear, y+ min/mean/max, outlet dispersed fraction, peak-to-mean shear enhancement |
| `CfdQualityResult` | `usable`, `usable_with_caution` or `not_usable` with explicit findings |
| `CfdEnhancementResult` | Velocity, shear and mass-transfer enhancement factors with their source |

## Engineering Method

**Design basis by precedence.** Sources are ranked
`measurement > mechanical_datasheet > process_datasheet > vendor > stid >
plant_data > pid > estimate > assumption`. A lower-ranked source never overwrites
a higher-ranked one; if it disagrees by more than 2 % it raises a conflict. The
component class determines which geometry fields are required, so an
under-specified case is reported rather than meshed.

**Fluid to boundary condition.** Density and viscosity come from the NeqSim phase
after `initProperties()`, because transport properties are otherwise zero.
Kinematic viscosity $\nu = \mu / \rho$ is what an incompressible solver consumes.
Inlet turbulence uses the fully developed correlations

$$I = 0.16\,\mathrm{Re}^{-1/8}, \qquad \ell = 0.07\,D_h$$

$$k = \tfrac{3}{2}(U I)^2, \qquad \varepsilon = C_\mu^{3/4}\frac{k^{3/2}}{\ell},
\qquad \omega = \frac{\varepsilon}{C_\mu k}$$

Mach number $U/c$ above 0.3 switches the recommended solver from
`incompressibleFluid` to `compressibleFluid`. Reynolds below 4000 disables the
turbulence model and says so.

**Mesh.** The O-grid round duct places one core block inside four ring blocks with
arc edges on the outer circle, which is what keeps cell skewness low near the
wall. Radial grading is solved from the requested first-cell height: the per-cell
geometric ratio $r$ satisfies $h_1(r^{n}-1)/(r-1) = t$, and `simpleGrading` takes
$r^{\,n-1}$. That is how a y⁺ target derived from the NeqSim fluid reaches the
mesh. `mesh_warnings()` reports when that ratio exceeds 1.3, because the fix for a
too-thin first cell is more cells, not a stretched mesh. Any externally generated
mesh (Gmsh, Fluent, I-deas, CGNS) can be imported instead, so arbitrary geometry
is supported.

**Numerics.** Second-order `linearUpwind` on momentum, because first-order upwind
smears exactly the local peaks the coupling is trying to measure. `checkMesh` runs
before the solver. Function objects record wall shear stress, y⁺, patch fluxes and
patch-average pressures every write, which is what makes the result auditable.

**Reading results back.** Incompressible OpenFOAM reports kinematic pressure and
kinematic wall shear in m²/s²; both are multiplied by density to obtain Pa. Peak
and area-average wall shear on the wall patch give the peak-to-mean enhancement
directly. Mass-transfer enhancement follows the friction velocity
$u^{*} = \sqrt{\tau/\rho}$:

$$\text{mass transfer enhancement} = \sqrt{\text{shear enhancement}}$$

**Quality gate.** Three things decide whether a local CFD value means anything.

| Check | Requirement |
|---|---|
| Wall treatment | Wall functions need 30 ≤ y⁺ ≤ 300; a resolved low-Reynolds treatment needs y⁺ of order 1 |
| Mesh independence | At least three mesh levels, or a grid-convergence index below about 5 % |
| Turbulence model | RANS under-predicts local peaks in separated or unsteady flow; scale-resolving models (LES, DES, SAS) capture them |

**Multiphase.** One flash gives both phases and the interfacial tension, so the
superficial velocities follow from the phase volumetric flows and the mixture
quantities from the no-slip volume-fraction average. Three dimensionless groups
then decide the model:

$$\mathrm{We} = \frac{\rho_c U_m^2 D}{\sigma}, \qquad
\mathrm{Fr} = \frac{U_m}{\sqrt{gD}}, \qquad
\mathrm{St} = \frac{\rho_d d^2 U_m}{18 \mu_c D}$$

The maximum stable droplet follows Hinze turbulent break-up,
$d_{\max} = 0.725 (\sigma/\rho_c)^{3/5} \varepsilon^{-2/5}$, with the duct
dissipation rate $\varepsilon = f U_m^3 / 2D$. The screening then reports:

| Verdict | Meaning | Generated |
|---|---|---|
| `vof` | The interface is a large-scale, resolvable feature - stratified, slug, annular, free surface | Yes, `VofOpenFoamCase` |
| `lagrangian` | Dilute dispersed phase that largely follows the carrier - mist, fine droplets | Carrier solve only; the parcel cloud must be added |
| `euler_euler` | Dense dispersed phase with no resolvable interface | No; specify with a CFD engineer |

`VofOpenFoamCase` refuses to build a case the screening did not recommend unless
`allow_unrecommended_model=True` is passed, so the wrong model is a deliberate,
recorded decision rather than an accident. The VOF case is transient by necessity
(an interface has no steady state), Courant-limited on both the flow and the phase
fraction, and uses a compressive `vanLeer` scheme on `alpha` so the interface stays
sharp. `p_rgh` carries the hydrostatic head separately, which is what makes gravity
driven separation behave.

## Python Usage Pattern

### Single-phase

```python
from cfd_coupling import (
    CfdCouplingModel, MeshSpec, OpenFoamCase, build_design_basis,
    derive_boundary_conditions, fluid_state_from_neqsim, read_case_results,
)

# 1. Everything known about the component, from wherever it came from.
basis = build_design_basis(
    tag="20-P-001",
    component_kind="pipe",
    sources=[
        {"source": "pid", "reference": "P&ID 20-PID-001 rev C",
         "values": {"nominal_size_inch": 12.0}},
        {"source": "stid", "reference": "STID line 20-P-001",
         "values": {"inside_diameter_m": 0.3048, "length_m": 6.0}},
        {"source": "process_datasheet", "reference": "20-DS-014 rev 2",
         "values": {"temperature_c": 45.0, "pressure_bara": 65.0,
                    "mass_flow_kg_per_h": 120_000.0}},
    ],
)
assert basis.ready_for_meshing, (basis.missing_fields, basis.conflicts)

# 2. Fluid from NeqSim, at the condition on the datasheet.
from neqsim.thermo import TPflash, fluid

gas = fluid("srk")
gas.addComponent("methane", 0.90)
gas.addComponent("ethane", 0.10)
gas.setMixingRule("classic")
gas.setTemperature(basis.value("temperature_c"), "C")
gas.setPressure(basis.value("pressure_bara"), "bara")
gas.setTotalFlowRate(basis.value("mass_flow_kg_per_h"), "kg/hr")
TPflash(gas)
state = fluid_state_from_neqsim(gas, phase="gas")

# 3. Boundary conditions, then a near-wall cell sized for the wall treatment.
boundary = derive_boundary_conditions(
    state, hydraulic_diameter_m=basis.value("inside_diameter_m")
)
model = CfdCouplingModel()
plan = model.plan_wall_resolution(
    density=state.density_kg_per_m3, viscosity=state.viscosity_pa_s,
    velocity=boundary.velocity_m_per_s,
    hydraulic_diameter=boundary.hydraulic_diameter_m, target_y_plus=50.0,
)

# 4. Write, run, read back.
case = OpenFoamCase(
    boundary=boundary,
    mesh=MeshSpec(kind="pipe", diameter_m=basis.value("inside_diameter_m"),
                  length_m=basis.value("length_m"),
                  first_cell_height_m=plan.first_cell_height_m),
    name=basis.tag,
)
case.write("cases/20-P-001")
outcome = case.run("cases/20-P-001")          # "not_executed" without OpenFOAM
results = read_case_results("cases/20-P-001",
                            density_kg_per_m3=state.density_kg_per_m3)

# 5. Gate before using any number, then convert to an engineering factor.
gate = model.assess_quality(
    turbulence_model=boundary.recommended_turbulence_model,
    wall_treatment="wall_function", y_plus=results.y_plus_mean, mesh_levels=1,
)
if gate.verdict != "not_usable" and results.wall_shear_enhancement:
    factor = model.evaluate_local_enhancement(
        location="20-P-001 wall", bulk_velocity=boundary.velocity_m_per_s,
        local_peak_velocity=boundary.velocity_m_per_s,
        bulk_wall_shear=results.mean_wall_shear_pa,
        local_peak_wall_shear=results.peak_wall_shear_pa,
    )
```

### Multiphase

```python
from cfd_coupling import (
    MeshSpec, VofOpenFoamCase, derive_multiphase_conditions,
    multiphase_state_from_neqsim, read_case_results,
)

TPflash(wellstream)                      # a flash that produces gas and liquid
state = multiphase_state_from_neqsim(wellstream)   # both phases plus sigma

conditions = derive_multiphase_conditions(
    state, hydraulic_diameter_m=0.2032, flow_regime="slug",
)
print(conditions.recommended_model, conditions.model_rationale)

if conditions.recommended_model == "vof":
    case = VofOpenFoamCase(
        boundary=conditions,
        mesh=MeshSpec(kind="pipe", diameter_m=0.2032, length_m=4.0, axial_cells=120),
        end_time=8.0,
        gravity=(0.0, -9.80665, 0.0),      # perpendicular to a horizontal pipe axis
    )
    case.write("cases/two-phase-line")
    case.run("cases/two-phase-line")
    results = read_case_results("cases/two-phase-line")
    # results.outlet_dispersed_fraction vs state.dispersed_volume_fraction
```

## Near-wall resolution: let the library solve it, and verify what you got

`MeshSpec.first_cell_height_m` exists so a y+ target from the fluid state reaches the
mesh. The grading is solved by `_wall_grading`, which brackets the root properly and
is reported through `mesh_warnings()`. **Use it. Do not hand-roll the grading maths.**

The arithmetic is easy to get wrong in a way that produces a *valid-looking* mesh.
Solving for a fixed **last** cell is ill-posed: if the cell count cannot span the
thickness there is no root, the bisection returns an endpoint, and the endpoint is
an expansion ratio of 1 — a perfectly clean uniform mesh. In one case that put the
first cell at y+ 27 instead of the requested 0.15, so a 10 um concentration boundary
layer sat inside a single 219 um cell and the wall gradient was meaningless. Posed
from the wall outwards the sum is monotonic in the expansion ratio and the bisection
is well conditioned.

**Rules:**

- Call `mesh_warnings()` and **print it**, every case. Treat *"no grading was applied
and the y+ target will not be met"* as a stop, not a note.
- A mesh helper that cannot satisfy its target must **raise**, not silently degrade.
  Guard both ends: expansion ratio above about 1.25, and a wall cell too coarse for
  the layer being resolved.
- **Verify the achieved resolution from the solution, not from the request.** Write
  the `yPlus` field and read it back. A requested y+ and an achieved y+ are different
  numbers, and only one of them is evidence.
- Where the answer depends on the near-wall layer, **validate against a correlation on
  the same mesh before quoting a local value** — the developed run upstream of the
  feature should reproduce the analytical wall shear, and for a scalar the textbook
  Sherwood number. A validation that fails by two orders of magnitude is a good
  validation; one that is never run lets a plausible wrong number through.

## Running the case in a container

OpenFOAM is usually run from an image rather than a host install. **Everything the
case writes lives inside the container filesystem unless it is on a bind mount**, so
the case root must be mounted before the solver starts, not after it finishes.

```bash
docker run --rm \
  -v "$TASK:/task" \
  -v "$SKILL_SRC:/skill:ro" \
  -v "$HOST_WORK:/work" \
  -e PYTHONPATH=/skill:/task/step2_analysis \
  <cfd-image> bash -lc "cd /task/step2_analysis && python3 my_case.py"
```

The third mount is the one that gets forgotten: it is the case root.

**Rule: mount the case root, or drop `--rm`.** `--rm` deletes the container
filesystem the moment the process exits. If `CASE_ROOT` (commonly `/work/cases`) is
not bind-mounted, then on exit you lose the mesh, the solved fields and every time
directory — leaving only whatever JSON was written to a mounted path. The summary
numbers survive; **the fields do not**, so any later step that samples the solution
(surface samples, section planes, figures, a mass-transfer post-solve) forces a full
re-solve. On a several-hundred-thousand-cell bend that is tens of minutes thrown away
for a missing `-v`.

Two practical consequences:

- **Sample in the same container run that solves.** Chain the solve and the sampling
  in one `bash -lc "... && ..."` so the fields are guaranteed to still exist, even when
  the case root is mounted.
- **Make the case subset selectable.** Expose the geometry variants and mesh levels
  through environment variables so one case can be re-solved for sampling without
  repeating the whole matrix, and so the summary JSON can be written to a scratch path
  rather than overwriting a good result.

## Validation Checklist

- [ ] `basis.ready_for_meshing` is true
- [ ] `basis.ready_for_meshing` is true, or every missing field and conflict is
      resolved and recorded.
- [ ] `initProperties()` ran before properties were read; density and viscosity
      are non-zero and physical for the phase.
- [ ] Reynolds number is above 4000, or the laminar warning has been accepted.
- [ ] Mach number is below 0.3, or a compressible solver is used.
- [ ] `checkMesh` reported no failed mesh checks.
- [ ] `mesh_warnings()` is empty, or the near-wall expansion has been accepted.
- [ ] `mesh_warnings()` was printed, and it does not report that no grading was
      applied.
- [ ] The **achieved** y+ was read back from the solved `yPlus` field, not assumed
      from the requested first-cell height.
- [ ] Inlet and outlet volumetric flow agree to better than 1 %.
- [ ] y⁺ lies inside the band for the wall treatment actually used.
- [ ] At least two mesh levels were run before a local peak is quoted.
- [ ] Wall shear and pressure were converted from kinematic units to Pa.
- [ ] The case root is a bind mount, or the container is not run with `--rm`, so the
      solved fields survive for sampling and figures.
- [ ] The quality-gate verdict and all findings are carried into the receiving
      report's assumptions register.

Multiphase, additionally:

- [ ] The flash produced the phases expected at the inlet condition, and the
      continuous phase is the one that actually wets the wall.
- [ ] NeqSim returned a physical interfacial tension for the phase pair.
- [ ] The recommended model was used, or the override is recorded with a reason.
- [ ] A flow-regime screening was supplied rather than relying on volume fraction.
- [ ] The outlet dispersed fraction was compared with the inlet flash split.
- [ ] The case ran long enough for the interface to develop; a VOF result read at
      an arbitrary early time is a transient, not an answer.

## Common Mistakes

| Mistake | Why it matters |
|---|---|
| Reading properties without `initProperties()` | Viscosity and thermal conductivity come back as zero, so the CFD case runs at an absurd Reynolds number |
| Using water tables for the CFD fluid | Glycol, condensate and hydrocarbon mixtures differ substantially; take properties from a NeqSim flash |
| Quoting a model-wide maximum as a local value | It is often a single-cell artefact. Use section-plane maxima or area-averaged values |
| Reading kinematic pressure as Pa | Incompressible OpenFOAM reports `p` in m²/s²; multiply by density |
| Different cell counts between load cases read as a mesh study | Meshes usually differ because geometry differs, not for convergence testing |
| A steady RANS peak used for a fatigue or erosion question | Steady RANS smooths exactly the fluctuations those questions depend on |
| Ignoring the operating case | Enhancement factors are case-specific. Maldistribution is usually worst at low flow, which is often the throttled control condition |
| Gas-side CFD applied to a liquid-side question | Gas-side CFD constrains the heat-flux distribution, which sets the liquid-side film temperature; it does not give liquid-side velocities |
| A photograph treated as dimensional authority | Only valid with a calibrated scale reference and perspective correction |
| Volume of fluid used on a dilute droplet mist | The interface is far below cell size, so the solve is expensive and wrong. The screening says `lagrangian` for a reason |
| A single flash used along the whole geometry | Phase split, density and interfacial tension change with pressure and temperature; the case fixes them at the inlet |
| A VOF result read before the interface develops | The first residence times are start-up transient, not the flow pattern |
| A forced-convection film coefficient carried into a stagnant or dead-leg region | With no through-flow the inside coefficient collapses from forced-convection to natural-convection values, so the same wall heat flux produces a film temperature rise one to two orders of magnitude larger. Solve it as a buoyancy problem, not by rescaling velocity |
| `docker run --rm` with the case root inside the container | The mesh and solved fields are destroyed on exit. Only files written to a bind mount survive, so sampling, section planes and figures all need a full re-solve. Mount the case root, or drop `--rm` |
| A geometry constant hard-coded under a block comment claiming document provenance | The comment can be true for one constant and false for the next. A bend angle assumed as 90° where the drawings said 180° moved the computed geometry factor by 9 %. Source each geometry constant individually |
| Hand-rolled near-wall grading instead of `MeshSpec.first_cell_height_m` | Solved for a fixed last cell the problem has no root when the cell count cannot span the thickness, and the bisection returns an expansion ratio of 1 — a clean-looking uniform mesh that misses the y+ target by two orders of magnitude |
| `mesh_warnings()` collected but not printed | It already reports "no grading was applied and the y+ target will not be met". That is the one warning that invalidates every local value in the case |
| A requested y+ quoted as the achieved y+ | Only the solved `yPlus` field is evidence. Write it and read it back |
| Wall shear converted to a mass-transfer coefficient at a separated feature | `k_m ~ sqrt(tau_w)` holds for an attached boundary layer. At a weld root, orifice or sudden expansion the flow reattaches, and `tau_w` passes through zero where mass transfer peaks — so the shear map puts its minimum near the worst metal loss. Solve a passive scalar instead |

## Limitations

Single-phase steady RANS and two-phase volume of fluid are what this skill
generates. Lagrangian parcel clouds and Euler-Euler dispersed models are
recommended with a reason but not written. Phase change, cavitation, combustion,
conjugate heat transfer and mass transfer across the interface are outside scope,
and the multiphase case fixes the phase properties at the inlet flash rather than
re-flashing along the geometry. The quality gate is a screening filter, not a
verification-and-validation review: a `usable_with_caution` verdict means any
derived factor must carry an explicit uncertainty band. Human review by a qualified
CFD engineer is required before a CFD-derived factor is used in a design decision.
The generated case targets OpenFOAM.org v11+ by default; the `legacy` flavour
covers `simpleFoam`/`interFoam`-era releases and the ESI fork, and neither is
tested against every intermediate version.

## Related NeqSim Functionality

- `neqsim.thermodynamicoperations.ThermodynamicOperations#TPflash()` and
  `neqsim.thermo.system.SystemInterface#initProperties()` — the flash and the
  property initialisation that supply density, viscosity and speed of sound.
  Reached from Python as `from neqsim.thermo import TPflash, fluid`, or as
  `from neqsim import jneqsim` for the full Java API.
- `neqsim.thermo.phase.PhaseInterface#getDensity`, `#getViscosity`,
  `#getSoundSpeed`, `#getFlowRate` — the per-phase accessors read by
  `fluid_state_from_neqsim`.
- `neqsim.thermo.system.SystemInterface#getInterfacialTension(int, int)` — the
  interfacial tension between two phases, read by `multiphase_state_from_neqsim`
  and written straight into the VOF `sigma` entry.
- `neqsim.process.equipment.stream.Stream` — the process-model object a coupled
  study normally starts from; pass `stream.getThermoSystem()` to
  `fluid_state_from_neqsim`.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` and
  `neqsim.process.equipment.pipeline.AdiabaticTwoPhasePipe` — the one-dimensional
  hydraulic models whose bulk results the CFD enhancement factors refine.
- This skill does not run any NeqSim calculation itself. It reads a fluid state
  from a system NeqSim has already flashed, and hands enhancement factors back to
  NeqSim-based screening models.

## Related Skills
- `neqsim-fem-coupling` - the solid-side companion. This skill resolves the fluid
  and the boundary layer; that one consumes the resulting film coefficient and
  resolves the temperature and stress field inside the wall. Hand it the film
  coefficient and the near-wall heat-flux distribution; take back an effective
  U-value, a U-multiplier and a metal temperature.- `neqsim-flow-accelerated-corrosion` — consumes the mass-transfer enhancement factor
- `neqsim-two-phase-flow-regime-screening`,
  `neqsim-multiphase-flow-slug-screening` — supply the `flow_regime` that drives
  the multiphase model choice
- `neqsim-line-velocity-check`, `neqsim-pressure-drop-screening` — the
  one-dimensional models CFD refines
- `neqsim-flow-induced-vibration-screening`,
  `neqsim-acoustic-induced-vibration-screening` — pair with unsteady CFD
- `neqsim-pid-process-operations`, `neqsim-technical-document-reading` — supply the
  P&ID topology and the datasheet values that feed the design basis

## References

- OpenFOAM Foundation, *OpenFOAM User Guide*, v11 and later — `foamRun`,
  `incompressibleFluid`, `blockMesh`, function objects.
- Menter, F. R. (1994). Two-equation eddy-viscosity turbulence models for
  engineering applications. *AIAA Journal*, 32(8), 1598–1605.
- Roache, P. J. (1994). Perspective: a method for uniform reporting of grid
  refinement studies. *Journal of Fluids Engineering*, 116(3), 405–413.
- ASME V&V 20-2009, *Standard for Verification and Validation in Computational
  Fluid Dynamics and Heat Transfer*.
- Hirt, C. W., & Nichols, B. D. (1981). Volume of fluid (VOF) method for the
  dynamics of free boundaries. *Journal of Computational Physics*, 39(1), 201-225.
- Hinze, J. O. (1955). Fundamentals of the hydrodynamic mechanism of splitting in
  dispersion processes. *AIChE Journal*, 1(3), 289-295.
- Pope, S. B. (2000). *Turbulent Flows*. Cambridge University Press — wall
  functions, friction velocity, near-wall scaling.
- Hirt, C. W., & Nichols, B. D. (1981). Volume of fluid (VOF) method for the
  dynamics of free boundaries. *Journal of Computational Physics*, 39(1), 201–225.
- Hinze, J. O. (1955). Fundamentals of the hydrodynamic mechanism of splitting in
  dispersion processes. *AIChE Journal*, 1(3), 289–295.
