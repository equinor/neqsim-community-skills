"""Insulated flowline with a local insulation defect: documents to a FEM answer.

Runs the whole chain the skill exists for:

    P&ID + STID + insulation specification + inspection report
        -> traceable design basis
    NeqSim flash (or the stated fallback state)
        -> film coefficient, Biot number, element size target
    one-dimensional multilayer FEM
        -> verified heat loss and wall temperatures for the intact section
    structured Gmsh mesh + scikit-fem case
        -> two-dimensional heat loss with the defect present
    quality gate + handoff
        -> the U-value multiplier a NeqSim pipeline model should carry

Every external package is optional. Without NeqSim the fluid state is stated
directly; without Gmsh and scikit-fem the mesh and the case are still written and
the commands to run them elsewhere are printed.

Run:  python examples/insulated_flowline_defect.py
"""

from __future__ import annotations

from math import pi
from pathlib import Path

from fem_coupling import (
    BoundaryCondition,
    ConductionLayer,
    ConductionProblem,
    FemCase,
    FemCouplingModel,
    FemFluidState,
    FemMeshSpec,
    MaterialAssignment,
    MeshLayer,
    MeshSegment,
    RadialConductionModel,
    build_design_basis,
    custom_material,
    derive_thermal_conditions,
    detect_backends,
    detect_gmsh,
    evaluate_wall_stress,
    film_coefficient,
    material,
    read_case_results,
    recommend_backend,
)

CASE_DIR = Path("cases/20-P-001-defect")


def build_mesh_spec(basis, refinement: int = 1) -> FemMeshSpec:
    """The same geometry at a chosen refinement level, so the mesh can be checked."""
    return FemMeshSpec(
        kind="axisymmetric_section",
        inner_radius_m=basis.value("inside_diameter_m") / 2.0,
        layers=[
            MeshLayer("steel", "carbon-steel", basis.value("wall_thickness_m"),
                      6 * refinement),
            MeshLayer("insulation", "insulation",
                      basis.value("insulation_thickness_m"), 20 * refinement),
        ],
        segments=[
            MeshSegment("upstream", 1.5, 60 * refinement),
            MeshSegment("defect", basis.value("defect_length_m"), 32 * refinement,
                        {"insulation": "flooded-insulation"}),
            MeshSegment("downstream", 1.5, 60 * refinement),
        ],
        name=f"{basis.tag}-L{refinement}",
    )


def fluid_state() -> FemFluidState:
    """Fluid properties from NeqSim when it is installed, otherwise stated values."""
    try:
        from neqsim.thermo import TPflash, fluid  # noqa: PLC0415

        from fem_coupling import fluid_state_from_neqsim  # noqa: PLC0415

        gas = fluid("srk")
        gas.addComponent("methane", 0.82)
        gas.addComponent("ethane", 0.09)
        gas.addComponent("propane", 0.05)
        gas.addComponent("CO2", 0.04)
        gas.setMixingRule("classic")
        gas.setTemperature(45.0, "C")
        gas.setPressure(75.0, "bara")
        TPflash(gas)
        state = fluid_state_from_neqsim(gas, phase="gas", velocity_m_per_s=5.0)
        print("fluid properties from a NeqSim SRK flash")
        return state
    except Exception as error:  # NeqSim absent or the flash failed
        print(f"NeqSim unavailable ({type(error).__name__}); using stated properties")
        return FemFluidState(
            name="rich gas (stated)",
            phase="gas",
            temperature_c=45.0,
            pressure_bara=75.0,
            density_kg_per_m3=62.0,
            viscosity_pa_s=1.4e-5,
            thermal_conductivity_w_per_mk=0.043,
            heat_capacity_j_per_kgk=2500.0,
            velocity_m_per_s=5.0,
        )


def main() -> None:
    # 1. Everything known about the line, from wherever it came from.
    basis = build_design_basis(
        tag="20-P-001",
        model_kind="insulated_pipe",
        sources=[
            {
                "source": "stid",
                "reference": "STID line 20-P-001",
                "values": {"inside_diameter_m": 0.254, "wall_thickness_m": 0.0127,
                           "wall_material": "carbon-steel"},
            },
            {
                "source": "insulation_specification",
                "reference": "SPEC-INS-004 rev 1",
                "values": {"insulation_thickness_m": 0.05,
                           "insulation_material": "polyurethane-insulation"},
            },
            {
                "source": "process_datasheet",
                "reference": "20-DS-014 rev 2",
                "values": {"internal_temperature_c": 45.0,
                           "external_temperature_c": 4.0,
                           "external_film_coefficient_w_per_m2k": 300.0},
            },
            {
                "source": "inspection_report",
                "reference": "ROV-2026-118",
                "values": {"defect_length_m": 0.4},
            },
        ],
    )
    print(f"\ndesign basis ready for meshing: {basis.ready_for_meshing}")
    if basis.missing_fields:
        print("  missing:", ", ".join(basis.missing_fields))
    for conflict in basis.conflicts:
        print(f"  conflict on {conflict.field}: {conflict.accepted_value} "
              f"({conflict.accepted_source}) vs {conflict.rejected_value} "
              f"({conflict.rejected_source})")
    if not basis.ready_for_meshing:
        raise SystemExit("resolve the design basis before meshing")

    inner_radius = basis.value("inside_diameter_m") / 2.0
    steel = material(basis.value("wall_material"))
    insulation = material(basis.value("insulation_material"))
    # Water ingress into a damaged section: the pores fill, so the layer conducts
    # like seawater rather than like foam.
    flooded = custom_material(
        insulation,
        name="seawater-flooded insulation",
        conductivity_w_per_mk=0.60,
        source="Water-filled porosity; conductivity taken as seawater.",
    )

    # 2. Fluid side from NeqSim, then the film coefficient and the mesh targets.
    gas = fluid_state()
    film = film_coefficient(gas, hydraulic_diameter_m=basis.value("inside_diameter_m"))
    print(f"\nRe = {film.reynolds:,.0f}   Pr = {film.prandtl:.2f}   "
          f"h_i = {film.h_w_per_m2k:.0f} W/m2K   ({film.correlation})")

    conditions = derive_thermal_conditions(
        wall_thickness_m=basis.value("wall_thickness_m")
        + basis.value("insulation_thickness_m"),
        solid_conductivity_w_per_mk=insulation.conductivity_w_per_mk,
        solid_thermal_diffusivity_m2_per_s=insulation.thermal_diffusivity_at(25.0),
        inner_film=film,
        inner_bulk_temperature_c=basis.value("internal_temperature_c"),
        outer_film_coefficient_w_per_m2k=basis.value(
            "external_film_coefficient_w_per_m2k"
        ),
        outer_bulk_temperature_c=basis.value("external_temperature_c"),
        transient_duration_s=12.0 * 3600.0,
    )
    print(f"Biot = {conditions.biot:.2f}   penetration depth = "
          f"{conditions.penetration_depth_m * 1000.0:.1f} mm   "
          f"element size target = {conditions.max_element_size_m * 1000.0:.1f} mm")
    for warning in conditions.warnings:
        print("  !", warning)

    # 3. The intact section, one-dimensional and checkable against the closed form.
    layers = [
        ConductionLayer("steel", steel, basis.value("wall_thickness_m"), 8),
        ConductionLayer("insulation", insulation, basis.value("insulation_thickness_m"), 20),
    ]
    intact = RadialConductionModel(layers, inner_radius_m=inner_radius).solve_steady(
        inner_film_coefficient_w_per_m2k=film.h_w_per_m2k,
        inner_bulk_temperature_c=basis.value("internal_temperature_c"),
        outer_film_coefficient_w_per_m2k=basis.value(
            "external_film_coefficient_w_per_m2k"
        ),
        outer_bulk_temperature_c=basis.value("external_temperature_c"),
    )
    print(f"\nintact section: {intact.heat_flow_per_length_w_per_m:.1f} W/m, "
          f"U = {intact.overall_u_inner_w_per_m2k:.2f} W/m2K, "
          f"bore metal {intact.inner_surface_temperature_c:.2f} degC, "
          f"deviation from the closed form {intact.analytic_deviation_percent:.3f} %")

    # 4. The defect needs two dimensions: heat spreads axially around it.
    recommendation = recommend_backend(dimension=2, physics="conduction")
    print(f"\nbackend: {recommendation.backend} - {recommendation.rationale}")

    spec = build_mesh_spec(basis)
    for warning in spec.mesh_warnings(max_element_size_m=conditions.max_element_size_m):
        print("  !", warning)

    print(f"\ngmsh: {detect_gmsh() or 'not installed'}   "
          f"scikit-fem: {'yes' if detect_backends()['scikit-fem'] else 'no'}")

    def solve(mesh_spec: FemMeshSpec, directory: Path):
        """Mesh, write, run and read one refinement level."""
        mesh_outcome = mesh_spec.generate(directory / "mesh")
        problem = ConductionProblem.from_mesh_spec(
            mesh_spec,
            name=f"{basis.tag} with insulation defect",
            mesh_file=str(mesh_outcome.mesh_path or (directory / "mesh" / "mesh.msh")),
            materials=[
                MaterialAssignment("carbon-steel", steel.conductivity_w_per_mk,
                                   steel.volumetric_heat_capacity_j_per_m3k()),
                MaterialAssignment("insulation", insulation.conductivity_w_per_mk,
                                   insulation.volumetric_heat_capacity_j_per_m3k()),
                MaterialAssignment("flooded-insulation", flooded.conductivity_w_per_mk,
                                   flooded.volumetric_heat_capacity_j_per_m3k()),
            ],
            boundaries=[
                BoundaryCondition("inner", "robin", film.h_w_per_m2k,
                                  basis.value("internal_temperature_c")),
                BoundaryCondition("outer", "robin",
                                  basis.value("external_film_coefficient_w_per_m2k"),
                                  basis.value("external_temperature_c")),
                # The modelled length is cut out of a long line, so the cut faces
                # are symmetry planes rather than real boundaries.
                BoundaryCondition("west", "adiabatic"),
                BoundaryCondition("east", "adiabatic"),
            ],
        )
        case = FemCase(problem, backend="scikit-fem")
        case.write(directory)
        outcome = case.run(directory)
        print(f"  {mesh_spec.name}: mesh {mesh_outcome.status}, solve {outcome.status}")
        if not outcome.executed:
            print(f"  run '{case.command()}' in {directory} where scikit-fem is installed")
            return None
        return read_case_results(directory)

    print("")
    results = solve(spec, CASE_DIR)
    if results is None:
        return

    # Mesh independence is cheap for conduction, so there is no excuse for one mesh.
    refined = solve(build_mesh_spec(basis, refinement=2), CASE_DIR.with_name(
        CASE_DIR.name + "-refined"))
    convergence = None
    if refined is not None:
        base_flow = results.boundary_heat_flow_w["inner"]
        convergence = 100.0 * (
            refined.boundary_heat_flow_w["inner"] - base_flow
        ) / base_flow

    print(f"\nheat flow over {spec.total_length_m:.1f} m: "
          f"{results.boundary_heat_flow_w['inner']:.1f} W   "
          f"(energy balance {results.energy_balance_error_percent:.4f} %)")
    if convergence is not None:
        print(f"change on refinement: {convergence:+.2f} %")

    # 5. Gate the study, then reduce it to what a one-dimensional model consumes.
    model = FemCouplingModel()
    gate = model.assess_quality(
        element_order=spec.element_order,
        elements_across_critical_layer=spec.layers[1].cells,
        mesh_levels=2 if refined is not None else 1,
        convergence_percent=convergence,
        max_aspect_ratio=spec.max_aspect_ratio(),
        energy_balance_error_percent=results.energy_balance_error_percent,
        biot=conditions.biot,
    )
    print(f"\nquality gate: {gate.verdict}")
    for finding in gate.findings:
        print("  -", finding)

    handoff = model.evaluate_thermal_handoff(
        location=f"{basis.tag} defect section",
        heat_flow_w=results.boundary_heat_flow_w["inner"],
        reference_area_m2=pi * basis.value("inside_diameter_m") * spec.total_length_m,
        inner_bulk_temperature_c=basis.value("internal_temperature_c"),
        outer_bulk_temperature_c=basis.value("external_temperature_c"),
        one_dimensional_heat_flow_w=intact.heat_flow_per_length_w_per_m
        * spec.total_length_m,
    )
    print(f"\nU (two-dimensional) = {handoff.overall_u_w_per_m2k:.3f} W/m2K")
    print(f"U multiplier for the NeqSim pipeline model = {handoff.u_multiplier}")

    # 6. The metal gradient this produces, and what it does to the steel.
    stress = evaluate_wall_stress(
        steel,
        location=f"{basis.tag} bore",
        inner_wall_temperature_c=intact.inner_surface_temperature_c,
        outer_wall_temperature_c=dict(intact.interface_temperatures_c)[
            "steel outer face"
        ],
        inner_radius_m=inner_radius,
        outer_radius_m=inner_radius + basis.value("wall_thickness_m"),
        internal_pressure_pa=75.0e5,
    )
    print(f"\nwall stress: {stress.combined_von_mises_pa / 1e6:.1f} MPa von Mises, "
          f"utilisation {stress.utilisation}, verdict {stress.verdict}")
    for warning in stress.warnings:
        print("  !", warning)


if __name__ == "__main__":
    main()
