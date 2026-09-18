"""End-to-end example: P&ID and STID inputs -> NeqSim -> OpenFOAM case.

Run with::

    python examples/pid_to_openfoam_case.py

NeqSim and OpenFOAM are both optional. Without NeqSim the fluid state is supplied
directly; without OpenFOAM the case is still written and the commands needed to run
it elsewhere are printed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from cfd_coupling import (
    CfdCouplingModel,
    FluidState,
    MeshSpec,
    OpenFoamCase,
    build_design_basis,
    derive_boundary_conditions,
    detect_openfoam,
    fluid_state_from_neqsim,
    friction_velocity,
    read_case_results,
)

# 1. Everything known about the component, from wherever it came from ------------
basis = build_design_basis(
    tag="20-P-001",
    component_kind="pipe",
    sources=[
        {
            "source": "pid",
            "reference": "P&ID 20-PID-001 rev C",
            "values": {"nominal_size_inch": 12.0, "service": "wet gas"},
        },
        {
            "source": "stid",
            "reference": "STID line 20-P-001",
            "values": {"inside_diameter_m": 0.3048, "length_m": 6.0, "material": "carbon steel"},
        },
        {
            "source": "process_datasheet",
            "reference": "Process datasheet 20-DS-014 rev 2",
            "values": {
                "temperature_c": 45.0,
                "pressure_bara": 65.0,
                "mass_flow_kg_per_h": 120_000.0,
            },
        },
    ],
)

print(f"Design basis for {basis.tag} ({basis.component_kind})")
for row in basis.traceability_rows():
    print(f"  {row['field']:<24} {row['value']!s:<16} {row['source']:<20} {row['reference']}")
print(f"  missing fields : {basis.missing_fields or 'none'}")
print(f"  conflicts      : {len(basis.conflicts)}")
print(f"  ready to mesh  : {basis.ready_for_meshing}")

# 2. Fluid state, from NeqSim when it is installed -------------------------------
try:
    from neqsim.thermo import TPflash, fluid  # type: ignore

    process_fluid = fluid("srk")
    for component, fraction in (
        ("nitrogen", 0.007),
        ("CO2", 0.020),
        ("methane", 0.870),
        ("ethane", 0.060),
        ("propane", 0.030),
        ("n-butane", 0.013),
    ):
        process_fluid.addComponent(component, fraction)
    process_fluid.setMixingRule("classic")
    process_fluid.setTemperature(basis.value("temperature_c"), "C")
    process_fluid.setPressure(basis.value("pressure_bara"), "bara")
    process_fluid.setTotalFlowRate(basis.value("mass_flow_kg_per_h"), "kg/hr")
    TPflash(process_fluid)
    state = fluid_state_from_neqsim(process_fluid, phase="gas")
    print("\nFluid state taken from a NeqSim flash.")
except Exception as error:  # NeqSim not installed, or no gas phase at this condition
    state = FluidState(
        name="wet gas (fallback)",
        phase="gas",
        density_kg_per_m3=52.4,
        viscosity_pa_s=1.45e-5,
        speed_of_sound_m_per_s=395.0,
        volumetric_flow_m3_per_s=120_000.0 / 3_600.0 / 52.4,
    )
    print(f"\nNeqSim unavailable ({type(error).__name__}); using a stated fluid state.")

# 3. CFD boundary conditions -----------------------------------------------------
boundary = derive_boundary_conditions(
    state,
    hydraulic_diameter_m=basis.value("inside_diameter_m"),
)
print(
    f"  velocity {boundary.velocity_m_per_s:.2f} m/s | Re {boundary.reynolds:,.0f} | "
    f"{boundary.flow_regime} | {boundary.compressibility} | "
    f"solver {boundary.recommended_solver} | model {boundary.recommended_turbulence_model}"
)
for warning in boundary.warnings:
    print(f"  warning: {warning}")

# 4. Size the near-wall cell for the wall treatment -------------------------------
model = CfdCouplingModel()
wall_plan = model.plan_wall_resolution(
    density=state.density_kg_per_m3,
    viscosity=state.viscosity_pa_s,
    velocity=boundary.velocity_m_per_s,
    hydraulic_diameter=boundary.hydraulic_diameter_m,
    target_y_plus=50.0,
)
print(
    f"  u* {friction_velocity(state, boundary.velocity_m_per_s, boundary.reynolds):.4f} m/s | "
    f"first cell {wall_plan.first_cell_height_m * 1e3:.3f} mm for y+ 50"
)

# 5. Write the OpenFOAM case ------------------------------------------------------
case = OpenFoamCase(
    boundary=boundary,
    mesh=MeshSpec(
        kind="pipe",
        diameter_m=basis.value("inside_diameter_m"),
        length_m=basis.value("length_m"),
        axial_cells=80,
        radial_cells=14,
        tangential_cells=12,
        first_cell_height_m=wall_plan.first_cell_height_m,
    ),
    name=basis.tag,
    wall_treatment="wall_function",
    extra_notes=(
        f"Equipment tag {basis.tag}",
        f"Geometry source: {basis.source_of('inside_diameter_m')}",
        f"Process source: {basis.source_of('pressure_bara')}",
    ),
)

case_dir = Path(tempfile.mkdtemp(prefix="neqsim_cfd_")) / basis.tag
written = case.write(case_dir)
print(f"\nCase written to {case_dir} ({len(written)} files)")
for relative in written:
    print(f"  {relative}")
for warning in case.mesh_warnings():
    print(f"  mesh warning: {warning}")

# 6. Run if OpenFOAM is present, then read the results back ------------------------
print(f"\nOpenFOAM environment: {detect_openfoam() or 'not found'}")
outcome = case.run(case_dir)
print(f"  status: {outcome.status} - {outcome.message}")

results = read_case_results(case_dir, density_kg_per_m3=state.density_kg_per_m3)
for finding in results.findings:
    print(f"  {finding}")
if results.wall_shear_enhancement:
    factor = model.evaluate_local_enhancement(
        location=f"{basis.tag} wall",
        bulk_velocity=boundary.velocity_m_per_s,
        local_peak_velocity=boundary.velocity_m_per_s,
        bulk_wall_shear=results.mean_wall_shear_pa,
        local_peak_wall_shear=results.peak_wall_shear_pa,
    )
    print(f"  mass-transfer enhancement: {factor.mass_transfer_enhancement:.2f}")
