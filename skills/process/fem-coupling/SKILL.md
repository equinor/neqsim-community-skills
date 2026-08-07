---
name: neqsim-fem-coupling
version: "0.1.0"
description: "Link a NeqSim process simulation and engineering documents to a finite-element model of the solid: heat conduction through a layered wall, transient cooldown, species diffusion in porous rock, and the thermal and pressure stress that follow. Merges P&ID, STID, datasheet, insulation-specification and inspection inputs into a traceable design basis, converts a flashed NeqSim fluid into a film coefficient, a Biot and Fourier number and a mesh and time-step target, solves the layered one-dimensional problem with a dependency-free finite-element solver verified against the closed-form resistance, generates a structured Gmsh mesh and a runnable scikit-fem or FEniCSx case for two-dimensional geometry, screens which backend is defensible (scikit-fem, FEniCSx, SfePy, MFEM, OpenSeesPy, PyNite), gates the study on discretisation, mesh independence, energy balance and boundary placement, and reduces the field to the U-value, U-multiplier, hot-spot factor and no-touch time a one-dimensional NeqSim model consumes. USE WHEN: a task needs a temperature or stress field inside a solid that a one-dimensional heat-transfer coefficient cannot produce - a local insulation defect, a support or clamp short-circuit, a buried or non-radial soil path, a nozzle or wall discontinuity, a cooldown or thermal-shock transient, diffusion through a porous medium - or when an existing thermal or stress finite-element report must be qualified before its numbers are trusted."
last_verified: "2026-08-07"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# FEM Coupling

NeqSim solves the fluid. It reports a bulk temperature, a pressure and a set of
transport properties, and a one-dimensional model turns those into a single
U-value per pipe section. That works until the geometry stops being
one-dimensional: a section of insulation floods, a clamp bridges the coating, a
line is buried under a sloping seabed, a nozzle interrupts a shell. The heat then
spreads in a direction the one-dimensional model does not have, and the U-value it
was given is wrong by an amount nobody can estimate by hand.

This skill closes that gap. It takes whatever is known about the component (P&ID,
STID tag register, datasheets, insulation specification, inspection report), takes
the fluid side from a NeqSim flash, builds and solves the finite-element model of
the solid, and converts the field back into the number the one-dimensional model
needed - an effective U-value, a multiplier on it, a hot-spot factor, a no-touch
time, a wall stress. When a thermal or stress finite-element study already exists,
it qualifies that study instead of running a new one.

It is the solid-side companion to `neqsim-cfd-coupling`: same design-basis
discipline, same quality gate before any number is quoted, same handoff back into a
one-dimensional model. CFD resolves the fluid; FEM resolves the solid.

Every layer works on its own. NeqSim, Gmsh, scikit-fem and FEniCSx are all
optional: without NeqSim the fluid state is stated directly, and without a mesher
or a solver the geometry and the case are still written, with the commands needed
to run them elsewhere.

## When to Use

- A one-dimensional U-value is being assumed where the geometry is not
  one-dimensional: a local insulation defect or flooded section, a support or
  clamp, a buried line, a valve or flange with no insulation.
- A cooldown or no-touch time is needed and the wall's thermal inertia matters,
  not just the fluid's.
- A metal temperature is needed for a thermal-stress, MDMT or material-selection
  question, and the process-to-ambient difference is not the metal gradient.
- Species diffusion through a porous medium is being modelled and the molecular
  diffusivity has to come from the actual mixture.
- A thermal or thermo-mechanical finite-element report is attached to an equipment
  tag and its numbers are about to be used.
- A new finite-element run is being specified and needs film coefficients, a
  penetration depth, an element size and a time step.

## When *Not* to Use

- As a substitute for a qualified stress or thermal analyst on a design decision.
  This is a screening and coupling toolkit, not a code-compliance calculation.
- For fatigue life, fracture mechanics, creep, plasticity, buckling or contact.
  The stress layer produces elastic thermal and pressure stresses with a category
  attached; it does not perform a code assessment.
- For the flow field. Velocity, wall shear and flow maldistribution belong to
  `neqsim-cfd-coupling`; this skill consumes a film coefficient, it does not
  resolve the boundary layer that produces it.
- To extract a number from a study that fails the quality gate.

## Inputs

| Stage | Input | Meaning |
|---|---|---|
| `build_design_basis` | `tag`, `model_kind`, `sources` | Equipment or line identifier, the model class (`insulated_pipe`, `pipe_wall`, `buried_pipeline`, `vessel_wall`, `plate`, `nozzle`, `wellbore`, `porous_block`), and one entry per source with `source`, `reference` and `values` |
| `material` / `custom_material` | material key, or a base plus overrides | Conductivity, heat capacity, modulus, expansion, allowable - with the basis recorded in `source` |
| `fluid_state_from_neqsim` | flashed NeqSim system, `phase`, optional `velocity_m_per_s`, `diffusing_components` | Density, viscosity, thermal conductivity, heat capacity and molecular diffusivities of the chosen phase |
| `film_coefficient` | `FemFluidState`, `hydraulic_diameter_m`, velocity | Optional `correlation` (`auto`, `gnielinski`, `dittus-boelter`, `laminar`) |
| `derive_thermal_conditions` | wall thickness, solid conductivity and diffusivity, both film coefficients and bulk temperatures | Optional `transient_duration_s` to obtain a penetration depth, element size and time step |
| `RadialConductionModel` | `ConductionLayer` stack, `inner_radius_m`, `geometry` | `cylindrical` or `planar`; each layer carries its material, thickness and element count |
| `solve_transient` | initial profile, duration, time step, both boundaries | Optional `inner_fluid_capacity` (`rho cp A_bore`) to make it a cooldown rather than a thermal-shock model |
| `FemMeshSpec` | `kind`, `layers`, `segments`, `inner_radius_m`, `element_order` | A structured layered grid; a `MeshSegment` override assigns a different material over part of the length |
| `recommend_backend` | `dimension`, `physics`, `coupled`, `nonlinear`, `structural_frame`, `estimated_dof` | Which finite-element package is defensible, and why |
| `ConductionProblem` / `FemCase` | mesh, `MaterialAssignment` list, `BoundaryCondition` list, optional `TransientSettings` | Boundary kinds are `robin`, `dirichlet`, `flux`, `adiabatic` |
| `assess_quality` | element order, elements across the controlling layer, mesh levels, energy balance, far-field ratio | Applies to a generated case or an existing report |
| `evaluate_thermal_handoff` | finite-element heat flow, reference area, bulk temperatures, one-dimensional heat flow | Produces the U-value and the multiplier a NeqSim pipeline model carries |
| `evaluate_wall_stress` | material, inner and outer **metal** temperatures, radii, pressure | Not the process and ambient temperatures - the metal surface temperatures the model produced |

## Outputs

| Output | Contents |
|---|---|
| `FemDesignBasis` | Accepted values, per-field source and confidence, conflicts, missing fields, `ready_for_meshing` |
| `FilmCoefficient` | Film coefficient, Reynolds, Prandtl, Nusselt, the correlation used, warnings |
| `FemThermalConditions` | Biot, lumped-capacitance verdict, thermal penetration depth, maximum element size, recommended time step, Fourier number, warnings |
| `SteadyConductionResult` | Node temperatures, per-layer interface temperatures, inner heat flux, heat flow per unit length, overall U, thermal resistance, and the deviation from the closed-form composite resistance |
| `TransientConductionResult` | Temperature history through the wall, bore-fluid history, and `time_to_reach` for a no-touch or cooldown time |
| `FemMeshSpec.geo_script` / `generate` | A structured Gmsh geometry and mesh with a physical group per material and per face, and explicit deterministic tags |
| `FemMeshSpec.mesh_warnings` | Layers with too few elements, excessive aspect ratio, elements coarser than the penetration depth |
| `BackendRecommendation` | The defensible backend with its rationale, the alternatives, and whether this skill can generate the case |
| `FemCase.write` / `run` | A self-contained case: `inputs.json`, `case.py`, the mesh, a README; run outcome or the command to run it elsewhere |
| `FemResults` | Degrees of freedom, element count, temperature range, per-boundary heat flow and mean temperature, transient history, energy-balance error |
| `FemQualityResult` | `usable`, `usable_with_caution` or `not_usable` with explicit findings |
| `FemThermalHandoff` | Overall U-value, U-multiplier against the one-dimensional model, hot-spot factor |
| `ThermalStressResult` | Thermal stress with its category, Lame pressure stresses, combined von Mises, utilisation against the right allowable, verdict |

## Engineering Method

**Design basis by precedence.** Sources are ranked `measurement >
mechanical_datasheet > material_certificate > insulation_specification >
process_datasheet > vendor > stid > inspection_report > plant_data > pid >
estimate > assumption`. A lower-ranked source never overwrites a higher-ranked
one; if it disagrees by more than 2 % it raises a conflict, and any disagreement
about a non-numeric field such as a material grade is always a conflict. The model
kind determines which fields are required, so an under-specified model is reported
rather than meshed.

**Fluid to boundary condition.** A finite-element model consumes a film
coefficient, not a fluid. Properties come from the NeqSim phase after
`initProperties()`, because thermal conductivity and viscosity are otherwise zero.
The default correlation is Gnielinski with the Petukhov friction factor,

$$f = (0.79 \ln \mathrm{Re} - 1.64)^{-2}, \qquad
\mathrm{Nu} = \frac{(f/8)(\mathrm{Re} - 1000)\,\mathrm{Pr}}
{1 + 12.7\sqrt{f/8}\,\left(\mathrm{Pr}^{2/3} - 1\right)}$$

valid over a far wider Prandtl range than Dittus-Boelter, which matters because a
dense-phase gas and a glycol are on opposite sides of that range. Below
Re = 2300 the fully developed laminar value Nu = 3.66 is used and said so.

**Do I even need a mesh?** The Biot number over the *whole* conduction path,
$\mathrm{Bi} = h L / k$ with $h$ the smaller of the two surface coefficients,
decides it. Below 0.1 the solid is nearly isothermal and a lumped model answers
the question. The skill says so rather than meshing anyway.

**Discretisation from the physics.** For a transient, the thermal penetration
depth $\delta = \sqrt{\alpha t}$ is how far the front has moved after the time of
interest; elements coarser than $\delta/4$ cannot represent it. The time step
targets a mesh Fourier number $\alpha \Delta t / \Delta x^2$ of about 0.5 - an
implicit scheme is stable at any step, so the step is chosen to resolve the front,
not to keep the solve from diverging.

**One dimension, verified.** Layered walls are assembled as linear P1 elements on a
one-dimensional mesh with every layer interface on a node, in cylindrical or planar
coordinates, with Robin conditions on both surfaces. Temperature-dependent
conductivity is handled by Picard sweeps on the layer mean temperature. The steady
result is checked against the closed-form composite resistance

$$R' = \frac{1}{h_i 2\pi r_i}
+ \sum_j \frac{\ln(r_{j+1}/r_j)}{2\pi k_j}
+ \frac{1}{h_o 2\pi r_o}$$

and the deviation is reported. That check is the reason to start in one dimension:
a two-dimensional field cannot be verified this way, so if the one-dimensional
answer is not understood first, nothing downstream is.

**Cooldown.** Holding the bore fluid at a fixed bulk temperature models a thermal
shock, not a cooldown - a shut-in line has no source keeping it warm. Supplying
`inner_fluid_capacity` = $\rho c_p A_\text{bore}$ adds the inventory as one lumped
node coupled to the wall through the inner film, and the system stays tridiagonal.
NeqSim supplies the density and heat capacity of the shut-in fluid and the hydrate
or wax temperature the cooldown is measured against.

**Mesh.** Layered geometry wants a structured tensor grid, one block per (axial
segment, through-thickness layer), because an unstructured mesh dropped over a
12 mm wall next to 50 mm of insulation puts one element across the wall - and the
wall gradient is what sets the thermal stress. Interfaces sit on element
boundaries, physical groups carry the material assignment and the faces, and the
group ids are written explicitly so a name-based reader (meshio, scikit-fem) and a
tag-based reader (dolfinx) see the same partition. A local defect is represented by
overriding a segment's material - water-flooded insulation conducts like seawater,
which is what actually happens.

**Backend screening.** Python has no single dominant finite-element package, so
the choice is stated rather than defaulted:

| Verdict | When | Generated |
|---|---|---|
| built-in `RadialConductionModel` | One-dimensional layered conduction or diffusion | Yes - and it is the only one that can be checked against a closed form |
| `scikit-fem` | Two-dimensional linear scalar problems; pure NumPy and SciPy, installs anywhere including Colab | Yes |
| `fenicsx` | Coupled, nonlinear or thermo-mechanical; three-dimensional continuum | Yes |
| `sfepy` | General multiphysics with built-in terms | No - set up by hand |
| `mfem` | Very large or high-order solves, parallel and GPU | No - set up by hand |
| `openseespy` | Nonlinear or dynamic structural frames | No - set up by hand |
| `pynite` | Linear beams, frames and plates | No - set up by hand |

**Case as data.** `inputs.json` holds the mesh reference, the per-material
properties and the boundary conditions; `case.py` is a fixed script that reads it.
The same `inputs.json` drives the scikit-fem and the FEniCSx script, so a model is
promoted from the light backend to the heavy one without being rebuilt.

**Quality gate.** Four things decide whether a finite-element number means anything.

| Check | Requirement |
|---|---|
| Discretisation | At least three linear (or two quadratic) elements across the layer that controls the answer, and an aspect ratio below about 20 |
| Mesh independence | At least two mesh levels, with the quantity of interest moving less than about 2 % on refinement. Refinement is cheap for conduction |
| Energy balance | Boundary heat flows must sum to a small fraction of a percent. A larger residual usually means a missing boundary condition or an unassigned material group |
| Boundary placement | A far-field boundary must sit at least three penetration depths away, or it becomes an input to the answer |

For a transient, the mesh Fourier number and the number of time steps are checked
too: an implicit scheme stays stable while smearing the front, which flatters a
cooldown time and understates a thermal shock.

**Handoff.** The field is reduced to what a one-dimensional model consumes. The
overall U-value follows from the boundary heat flow and the reference area, and the
**U-multiplier** - the ratio of the finite-element heat flow to the
one-dimensional heat flow over the same length - is the number a NeqSim pipeline or
cooldown model carries. It is what transports a local defect, a support
short-circuit or a non-radial soil path into a model that cannot represent them.

**Stress category.** Pressure stress is primary: it does not relax, and exceeding
the allowable means the wall fails. Restrained-expansion and through-wall-gradient
stresses are secondary and self-limiting, so they are assessed against a range
allowable of order $3S$ and against fatigue, not against the primary membrane
allowable. Thermal stresses used here are

$$\sigma_\text{axial} = E\alpha\,\Delta T, \qquad
\sigma_\text{biaxial} = \frac{E\alpha\,\Delta T}{1-\nu}, \qquad
\sigma_\text{gradient} = \frac{E\alpha\,\Delta T}{2(1-\nu)}$$

with the Lame thick-wall pressure solution superposed. Comparing a thermal stress
with a primary allowable is the most common way to condemn a wall that is
acceptable - or to pass one that will crack in cyclic service.

## Python Usage Pattern

### One dimension first - and verified

```python
from fem_coupling import (
    ConductionLayer, RadialConductionModel, build_design_basis,
    derive_thermal_conditions, film_coefficient, fluid_state_from_neqsim, material,
)

basis = build_design_basis(
    tag="20-P-001",
    model_kind="insulated_pipe",
    sources=[
        {"source": "stid", "reference": "STID line 20-P-001",
         "values": {"inside_diameter_m": 0.254, "wall_thickness_m": 0.0127,
                    "wall_material": "carbon-steel"}},
        {"source": "insulation_specification", "reference": "SPEC-INS-004 rev 1",
         "values": {"insulation_thickness_m": 0.05,
                    "insulation_material": "polyurethane-insulation"}},
        {"source": "process_datasheet", "reference": "20-DS-014 rev 2",
         "values": {"internal_temperature_c": 45.0, "external_temperature_c": 4.0,
                    "external_film_coefficient_w_per_m2k": 300.0}},
    ],
)
assert basis.ready_for_meshing, (basis.missing_fields, basis.conflicts)

from neqsim.thermo import TPflash, fluid

gas = fluid("srk")
gas.addComponent("methane", 0.85)
gas.addComponent("ethane", 0.10)
gas.addComponent("CO2", 0.05)
gas.setMixingRule("classic")
gas.setTemperature(basis.value("internal_temperature_c"), "C")
gas.setPressure(75.0, "bara")
TPflash(gas)
state = fluid_state_from_neqsim(gas, phase="gas", velocity_m_per_s=5.0)
film = film_coefficient(state, hydraulic_diameter_m=basis.value("inside_diameter_m"))

steel = material(basis.value("wall_material"))
insulation = material(basis.value("insulation_material"))
conditions = derive_thermal_conditions(
    wall_thickness_m=basis.value("wall_thickness_m")
    + basis.value("insulation_thickness_m"),
    solid_conductivity_w_per_mk=insulation.conductivity_w_per_mk,
    solid_thermal_diffusivity_m2_per_s=insulation.thermal_diffusivity_at(25.0),
    inner_film=film,
    inner_bulk_temperature_c=basis.value("internal_temperature_c"),
    outer_film_coefficient_w_per_m2k=basis.value("external_film_coefficient_w_per_m2k"),
    outer_bulk_temperature_c=basis.value("external_temperature_c"),
)

wall = RadialConductionModel(
    [ConductionLayer("steel", steel, basis.value("wall_thickness_m"), 8),
     ConductionLayer("insulation", insulation, basis.value("insulation_thickness_m"), 20)],
    inner_radius_m=basis.value("inside_diameter_m") / 2.0,
)
steady = wall.solve_steady(
    inner_film_coefficient_w_per_m2k=film.h_w_per_m2k,
    inner_bulk_temperature_c=basis.value("internal_temperature_c"),
    outer_film_coefficient_w_per_m2k=basis.value("external_film_coefficient_w_per_m2k"),
    outer_bulk_temperature_c=basis.value("external_temperature_c"),
)
assert steady.analytic_deviation_percent < 1.0   # the closed-form check
```

### Two dimensions, when the geometry stops being radial

```python
from fem_coupling import (
    BoundaryCondition, ConductionProblem, FemCase, FemCouplingModel, FemMeshSpec,
    MaterialAssignment, MeshLayer, MeshSegment, read_case_results, recommend_backend,
)

print(recommend_backend(dimension=2, physics="conduction").rationale)

spec = FemMeshSpec(
    kind="axisymmetric_section",
    inner_radius_m=0.127,
    layers=[MeshLayer("steel", "carbon-steel", 0.0127, 6),
            MeshLayer("insulation", "insulation", 0.05, 20)],
    segments=[MeshSegment("upstream", 1.5, 60),
              # A flooded section: the pores fill, so it conducts like seawater.
              MeshSegment("defect", 0.4, 32, {"insulation": "flooded-insulation"}),
              MeshSegment("downstream", 1.5, 60)],
    name="20-P-001",
)
for warning in spec.mesh_warnings(max_element_size_m=conditions.max_element_size_m):
    print(warning)

mesh = spec.generate("cases/20-P-001/mesh")     # "not_executed" without Gmsh
problem = ConductionProblem.from_mesh_spec(
    spec, name="20-P-001 defect", mesh_file=str(mesh.mesh_path),
    materials=[MaterialAssignment("carbon-steel", 45.0, 7850 * 490),
               MaterialAssignment("insulation", 0.17, 700 * 1500),
               MaterialAssignment("flooded-insulation", 0.60, 1025 * 3900)],
    boundaries=[BoundaryCondition("inner", "robin", film.h_w_per_m2k, 45.0),
                BoundaryCondition("outer", "robin", 300.0, 4.0),
                BoundaryCondition("west", "adiabatic"),
                BoundaryCondition("east", "adiabatic")],
)
case = FemCase(problem, backend="scikit-fem")
case.write("cases/20-P-001")
case.run("cases/20-P-001")                       # "not_executed" without scikit-fem
results = read_case_results("cases/20-P-001")

model = FemCouplingModel()
gate = model.assess_quality(
    element_order=1, elements_across_critical_layer=20, mesh_levels=2,
    convergence_percent=0.3, max_aspect_ratio=spec.max_aspect_ratio(),
    energy_balance_error_percent=results.energy_balance_error_percent,
    biot=conditions.biot,
)
if gate.verdict != "not_usable":
    handoff = model.evaluate_thermal_handoff(
        location="20-P-001 defect section",
        heat_flow_w=results.boundary_heat_flow_w["inner"],
        reference_area_m2=3.1416 * 0.254 * spec.total_length_m,
        inner_bulk_temperature_c=45.0, outer_bulk_temperature_c=4.0,
        one_dimensional_heat_flow_w=steady.heat_flow_per_length_w_per_m
        * spec.total_length_m,
    )
    print(handoff.u_multiplier)   # what the NeqSim pipeline model should carry
```

### Cooldown and no-touch time

```python
from math import pi
from neqsim.thermo import hydt

hydrate_c = float(hydt(wet_gas)) - 273.15
inventory = wet_gas.getDensity("kg/m3") * wet_gas.getCp("J/kgK") * pi * 0.127**2

cooldown = wall.solve_transient(
    initial_temperature_c=steady.temperatures_c,   # the shutdown profile, not a uniform one
    duration_s=48 * 3600.0, time_step_s=120.0,
    inner_film_coefficient_w_per_m2k=50.0,         # natural convection after shutdown
    inner_bulk_temperature_c=45.0,
    outer_film_coefficient_w_per_m2k=300.0, outer_bulk_temperature_c=4.0,
    inner_fluid_capacity=inventory,                # makes it a cooldown, not a shock
)
no_touch_s = cooldown.time_to_reach(hydrate_c, location="inner_fluid")
```

### Wall stress from the metal temperatures

```python
from fem_coupling import evaluate_wall_stress

stress = evaluate_wall_stress(
    steel, location="20-P-001 bore",
    inner_wall_temperature_c=steady.inner_surface_temperature_c,
    outer_wall_temperature_c=dict(steady.interface_temperatures_c)["steel outer face"],
    inner_radius_m=0.127, outer_radius_m=0.1397, internal_pressure_pa=75.0e5,
)
print(stress.verdict, stress.utilisation, stress.stress_category)
```

## Validation Checklist

- [ ] `basis.ready_for_meshing` is true, or every missing field and conflict is
      resolved and recorded.
- [ ] `initProperties()` ran before properties were read; density, viscosity,
      thermal conductivity and heat capacity are non-zero and physical.
- [ ] Material properties come from a data sheet or a certificate where one
      exists; a library value is marked as indicative in the assumptions register.
- [ ] The Biot number is above 0.1, or the lumped-model warning has been accepted.
- [ ] The one-dimensional steady result was computed first, and
      `analytic_deviation_percent` is below 1 %.
- [ ] Every layer carries at least three linear (or two quadratic) elements.
- [ ] `mesh_warnings()` is empty, or each warning has been accepted with a reason.
- [ ] The element size is no coarser than a quarter of the thermal penetration
      depth for the transient window of interest.
- [ ] At least two mesh levels were run, and the quantity of interest moved less
      than about 2 %.
- [ ] The boundary energy balance closes to better than 1 %.
- [ ] A far-field boundary sits at least three penetration depths away.
- [ ] A cooldown model carries `inner_fluid_capacity`; a fixed bulk temperature is
      a thermal-shock model, not a cooldown.
- [ ] Thermal stress was computed from the **metal** surface temperatures, not from
      the process-to-ambient difference.
- [ ] Thermal stress was assessed against a range allowable, and pressure stress
      separately against the primary membrane allowable.
- [ ] The quality-gate verdict and all findings are carried into the receiving
      report's assumptions register.

## Common Mistakes

| Mistake | Why it matters |
|---|---|
| Reading properties without `initProperties()` | Thermal conductivity and viscosity come back as zero, so the film coefficient is meaningless |
| Using the process-to-ambient temperature difference as the metal gradient | On a well-insulated line almost all of the drop falls across the insulation; the steel gradient can be a hundredth of it, and so is the thermal stress |
| Meshing a problem with a Biot number below 0.1 | The solid is nearly isothermal; a lumped model answers it in one line |
| An unstructured mesh over a layered wall | One element across a 12 mm wall next to forty across the insulation; the wall gradient that drives the stress is unrepresented |
| One mesh reported as a converged solution | Differences in cell count between load cases are not a convergence study. Refinement is cheap for conduction |
| An unreported energy balance | For conduction it should close to a fraction of a percent, so an unreported balance usually means it was never checked |
| A far-field boundary placed for convenience | Inside three penetration depths the boundary condition becomes an input to the answer |
| A fixed bore temperature used for a cooldown | It models a thermal shock. A shut-in line has no source keeping the fluid warm |
| The forced-convection film coefficient reused after shutdown | Forced convection stops; what remains is natural convection, one to two orders of magnitude lower |
| A large implicit time step because the scheme is stable | Stability is not accuracy. A smeared front flatters a cooldown time and understates a thermal shock |
| Thermal stress compared with a primary membrane allowable | It is secondary and self-limiting; the comparison condemns acceptable walls and passes ones that will crack in cyclic service |
| A library material value used as if it were certified | Insulation conductivity in particular varies by a factor of two between products and with water ingress |
| Perfect thermal contact assumed between layers | Air gaps, delamination and water ingress at an interface can dominate the whole build-up |
| A two-dimensional result quoted without the one-dimensional check | The one-dimensional answer can be verified against a closed form; the two-dimensional one cannot |

## Limitations

Linear heat conduction and species diffusion are what this skill solves, with
temperature-dependent conductivity handled by Picard iteration. Radiation,
convection inside the solid domain, phase change, latent heat, freezing, curing and
moisture transport are outside scope. The built-in solver is one-dimensional
cylindrical or planar; two-dimensional axisymmetric and plane geometry is delegated
to scikit-fem or FEniCSx, and three-dimensional geometry needs an externally
generated mesh. The structured mesh generator expresses a local defect as a
material change over a segment, not as a change of thickness. The stress layer is
linear elastic and produces membrane and gradient stresses with a category
attached; it does not perform a code assessment, a fatigue evaluation or a local
stress-concentration analysis, and geometry discontinuities such as nozzles,
supports and welds need a local model. The thermal and mechanical problems are
solved one way - a temperature field produces a stress, and the deformation does
not feed back into the thermal problem. The quality gate is a screening filter, not
a verification-and-validation review: a `usable_with_caution` verdict means any
derived factor must carry an explicit uncertainty band, and a converged solve of
the wrong boundary condition passes every one of its checks. Human review by a
qualified thermal or stress analyst is required before a finite-element-derived
number is used in a design decision. The generated scikit-fem script targets
scikit-fem 8 and later and the FEniCSx script targets DOLFINx 0.8 and later.

## Related NeqSim Functionality

- `neqsim.thermodynamicoperations.ThermodynamicOperations#TPflash()` and
  `neqsim.thermo.system.SystemInterface#initProperties()` - the flash and the
  property initialisation that supply density, viscosity, thermal conductivity and
  heat capacity. Reached from Python as `from neqsim.thermo import TPflash, fluid`,
  or as `from neqsim import jneqsim` for the full Java API.
- `neqsim.thermo.phase.PhaseInterface#getThermalConductivity`, `#getCp`,
  `#getDensity`, `#getViscosity` - the per-phase accessors read by
  `fluid_state_from_neqsim`.
- `neqsim.physicalproperties.PhysicalPropertyHandler` diffusion-coefficient models
  (for example `Fuller-Schettler-Giddings`) - the molecular diffusivities read for
  a species-transport model and scaled to an effective porous-medium value.
- `neqsim.thermodynamicoperations.ThermodynamicOperations#hydrateFormationTemperature()`
  (Python `from neqsim.thermo import hydt`) - the target a cooldown no-touch time
  is measured against.
- `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` and
  `neqsim.process.equipment.pipeline.AdiabaticTwoPhasePipe` - the one-dimensional
  models whose U-value the finite-element multiplier corrects.
- `neqsim.pvtsimulation.flowassurance.SurfCooldownAnalyzer` - the flow-assurance
  cooldown model this skill supplies an effective U-value and a wall thermal
  inertia to.
- This skill does not run any NeqSim calculation itself. It reads a fluid state
  from a system NeqSim has already flashed, and hands U-values, multipliers and
  no-touch times back to NeqSim-based models.

## Related Skills

- `neqsim-cfd-coupling` - the fluid-side companion. It resolves the boundary layer
  and produces the wall shear and the local velocity field; this skill consumes the
  film coefficient that follows and resolves the solid. The two share the same
  design-basis discipline and the same gate-before-quoting rule.
- `neqsim-surf-cooldown-screening` - consumes the no-touch time and the effective
  U-value from the transient model.
- `neqsim-hydrate-margin-check`, `neqsim-wax-margin-check` - supply the target
  temperature a cooldown is measured against.
- `neqsim-pipe-wall-thickness-screening`, `neqsim-piping-flexibility-screening` -
  the screening-level stress checks this skill refines with a real metal
  temperature gradient.
- `neqsim-flow-accelerated-corrosion` - consumes the metal surface temperature,
  which sets the film temperature that drives the corrosion rate.
- `neqsim-technical-document-reading`, `neqsim-pid-process-operations` - supply the
  P&ID topology, insulation specification and datasheet values that feed the design
  basis.

## References

- Gnielinski, V. (1976). New equations for heat and mass transfer in turbulent pipe
  and channel flow. *International Chemical Engineering*, 16(2), 359-368.
- Incropera, F. P., & DeWitt, D. P. *Fundamentals of Heat and Mass Transfer*, Wiley
  - composite-cylinder resistance, Biot and Fourier numbers, lumped capacitance.
- Zienkiewicz, O. C., Taylor, R. L., & Zhu, J. Z. (2013). *The Finite Element
  Method: Its Basis and Fundamentals*, 7th ed., Butterworth-Heinemann.
- Gustafsson, T., & McBain, G. D. (2020). scikit-fem: a Python package for finite
  element assembly. *Journal of Open Source Software*, 5(52), 2369.
- Baratta, I. A., et al. (2023). DOLFINx: the next generation FEniCS problem solving
  environment. Zenodo. doi:10.5281/zenodo.10447666
- Geuzaine, C., & Remacle, J.-F. (2009). Gmsh: a three-dimensional finite element
  mesh generator with built-in pre- and post-processing facilities. *International
  Journal for Numerical Methods in Engineering*, 79(11), 1309-1331.
- Anderson, R., et al. (2021). MFEM: a modular finite element methods library.
  *Computers & Mathematics with Applications*, 81, 42-74.
- Cimrman, R., Lukes, V., & Rohan, E. (2019). Multiscale finite element calculations
  in Python using SfePy. *Advances in Computational Mathematics*, 45, 1897-1921.
- ASME Boiler and Pressure Vessel Code, Section VIII Division 2, Part 5 -
  classification of primary, secondary and peak stresses.
- ASME B31.3, *Process Piping* - displacement stress range and the allowable
  stress basis for restrained thermal expansion.
- Roache, P. J. (1994). Perspective: a method for uniform reporting of grid
  refinement studies. *Journal of Fluids Engineering*, 116(3), 405-413.
- ASME V&V 10-2019, *Standard for Verification and Validation in Computational
  Solid Mechanics*.
