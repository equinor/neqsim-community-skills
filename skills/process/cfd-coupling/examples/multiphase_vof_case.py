"""Multiphase example: one NeqSim flash -> two phases -> an OpenFOAM VOF case.

Run with::

    python examples/multiphase_vof_case.py

A NeqSim flash already knows the phase split, the density and viscosity of each
phase, and the interfacial tension between them. That is the whole input to a
volume-of-fluid case, and it is the part usually guessed at.

The screening step matters as much as the case: volume of fluid resolves an
interface, so it is right for stratified, slug and annular flow and wrong for a
dilute droplet mist. The skill says which, and refuses to build the wrong one.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from cfd_coupling import (
    FluidState,
    MeshSpec,
    MultiphaseState,
    VofOpenFoamCase,
    derive_multiphase_conditions,
    multiphase_state_from_neqsim,
    read_case_results,
)

LINE_DIAMETER_M = 0.2032
LINE_LENGTH_M = 4.0

# 1. Two phases from one flash --------------------------------------------------
try:
    from neqsim.thermo import TPflash, fluid  # type: ignore

    wellstream = fluid("srk")
    for component, fraction in (
        ("nitrogen", 0.005),
        ("CO2", 0.015),
        ("methane", 0.620),
        ("ethane", 0.070),
        ("propane", 0.055),
        ("n-butane", 0.040),
        ("n-pentane", 0.035),
        ("n-hexane", 0.040),
        ("n-heptane", 0.060),
        ("n-octane", 0.060),
    ):
        wellstream.addComponent(component, fraction)
    wellstream.setMixingRule("classic")
    wellstream.setTemperature(40.0, "C")
    wellstream.setPressure(45.0, "bara")
    wellstream.setTotalFlowRate(90_000.0, "kg/hr")
    TPflash(wellstream)
    state = multiphase_state_from_neqsim(wellstream)
    print("Phase split taken from a NeqSim flash.")
except Exception as error:  # NeqSim missing, or a single-phase result
    state = MultiphaseState(
        continuous=FluidState(
            name="wellstream (fallback)",
            phase="gas",
            density_kg_per_m3=38.6,
            viscosity_pa_s=1.32e-5,
            pressure_bara=45.0,
            volumetric_flow_m3_per_s=0.42,
        ),
        dispersed=FluidState(
            name="wellstream (fallback)",
            phase="oil",
            density_kg_per_m3=690.0,
            viscosity_pa_s=5.4e-4,
            pressure_bara=45.0,
            volumetric_flow_m3_per_s=0.11,
        ),
        interfacial_tension_n_per_m=0.0125,
        continuous_volume_fraction=0.42 / 0.53,
        dispersed_volume_fraction=0.11 / 0.53,
    )
    print(f"NeqSim unavailable ({type(error).__name__}); using a stated two-phase state.")

print(
    f"  continuous {state.continuous.phase} "
    f"({100.0 * state.continuous_volume_fraction:.1f} vol %), "
    f"dispersed {state.dispersed.phase} "
    f"({100.0 * state.dispersed_volume_fraction:.1f} vol %)"
)
print(
    f"  interfacial tension {1e3 * state.interfacial_tension_n_per_m:.2f} mN/m | "
    f"density ratio {state.density_ratio:.1f}"
)

# 2. Mixture quantities and the model screening ----------------------------------
# Pass flow_regime from a dedicated regime screening when it is known; it is a
# stronger basis than volume fraction alone.
conditions = derive_multiphase_conditions(
    state, hydraulic_diameter_m=LINE_DIAMETER_M, flow_regime="slug"
)

print(
    f"\n  Usg {conditions.superficial_continuous_velocity_m_per_s:.2f} m/s | "
    f"Usl {conditions.superficial_dispersed_velocity_m_per_s:.2f} m/s | "
    f"Um {conditions.mixture_velocity_m_per_s:.2f} m/s"
)
print(
    f"  Re {conditions.mixture_reynolds:,.0f} | We {conditions.weber:,.0f} | "
    f"Fr {conditions.froude:.2f}"
)
print(
    f"  max stable droplet {1e6 * conditions.max_stable_droplet_m:.0f} um | "
    f"Stokes {conditions.stokes_number:.3g}"
)
print(f"  model: {conditions.recommended_model} ({conditions.recommended_solver})")
print(f"  why  : {conditions.model_rationale}")
for warning in conditions.warnings:
    print(f"  warning: {warning}")

# 3. Write the VOF case ----------------------------------------------------------
case = VofOpenFoamCase(
    boundary=conditions,
    mesh=MeshSpec(
        kind="pipe",
        diameter_m=LINE_DIAMETER_M,
        length_m=LINE_LENGTH_M,
        axial_cells=120,
        radial_cells=12,
        tangential_cells=12,
    ),
    name="two-phase-line",
    end_time=8.0,
    write_interval=0.2,
    # Gravity is perpendicular to the pipe axis, which is what lets the phases
    # stratify. A vertical line would use (0 0 -9.80665) with axis="z".
    gravity=(0.0, -9.80665, 0.0),
    extra_notes=(
        "Two-phase line, phase split and interfacial tension from a NeqSim flash",
        f"Continuous {state.continuous.phase}, dispersed {state.dispersed.phase}",
    ),
)

case_dir = Path(tempfile.mkdtemp(prefix="neqsim_vof_")) / "two_phase_line"
written = case.write(case_dir)
print(f"\nVOF case written to {case_dir} ({len(written)} files)")
for relative in written:
    print(f"  {relative}")
for warning in case.mesh_warnings():
    print(f"  mesh warning: {warning}")

# 4. Run if OpenFOAM is present, then read back ----------------------------------
outcome = case.run(case_dir)
print(f"\n  status: {outcome.status} - {outcome.message}")

results = read_case_results(case_dir)
for finding in results.findings:
    print(f"  {finding}")
if results.outlet_dispersed_fraction is not None:
    inlet_fraction = state.dispersed_volume_fraction
    print(
        f"  inlet {state.dispersed.phase} fraction {inlet_fraction:.4f} -> "
        f"outlet {results.outlet_dispersed_fraction:.4f}"
    )
