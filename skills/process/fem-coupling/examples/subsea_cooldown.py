"""Subsea cooldown: how long before an insulated line reaches the hydrate temperature.

The one-dimensional transient conduction model with a lumped bore inventory is the
cooldown model. NeqSim supplies three things it cannot invent: the density and
heat capacity of the shut-in fluid (which set the inventory the wall has to cool),
the internal film coefficient before shutdown, and the hydrate equilibrium
temperature that defines the target.

The answer is a no-touch time. That is a flow-assurance number, not a
finite-element one, which is the point: the finite-element model exists to produce
something a flow-assurance model can use.

Run:  python examples/subsea_cooldown.py
"""

from __future__ import annotations

from math import pi

from fem_coupling import (
    ConductionLayer,
    FemCouplingModel,
    RadialConductionModel,
    derive_thermal_conditions,
    material,
)

INNER_DIAMETER_M = 0.254
WALL_THICKNESS_M = 0.0127
INSULATION_THICKNESS_M = 0.05
SEABED_TEMPERATURE_C = 4.0
EXTERNAL_FILM_W_PER_M2K = 300.0
OPERATING_TEMPERATURE_C = 45.0

# Shut-in film coefficient. Forced convection stops at shutdown, so what remains is
# natural convection inside the bore - one to two orders of magnitude lower.
SHUT_IN_FILM_W_PER_M2K = 50.0


def fluid_properties() -> tuple[float, float, float]:
    """Shut-in density, heat capacity and hydrate temperature.

    Taken from NeqSim when it is installed, otherwise stated. The hydrate
    temperature is the target the cooldown is measured against, so it belongs to
    the thermodynamics, not to the finite-element model.
    """
    try:
        from neqsim.thermo import TPflash, fluid, hydt  # noqa: PLC0415

        wet_gas = fluid("cpa")
        wet_gas.addComponent("methane", 0.85)
        wet_gas.addComponent("ethane", 0.07)
        wet_gas.addComponent("propane", 0.04)
        wet_gas.addComponent("CO2", 0.04)
        wet_gas.addComponent("water", 0.02)
        wet_gas.setMixingRule(10)
        wet_gas.setMultiPhaseCheck(True)
        wet_gas.setTemperature(OPERATING_TEMPERATURE_C, "C")
        wet_gas.setPressure(120.0, "bara")
        TPflash(wet_gas)
        wet_gas.initProperties()
        density = float(wet_gas.getDensity("kg/m3"))
        heat_capacity = float(wet_gas.getCp("J/kgK"))
        hydrate_c = float(hydt(wet_gas)) - 273.15
        print("fluid and hydrate temperature from NeqSim (CPA)")
        return density, heat_capacity, hydrate_c
    except Exception as error:  # NeqSim absent, or the hydrate solve did not converge
        print(f"NeqSim unavailable ({type(error).__name__}); using stated properties")
        return 95.0, 2600.0, 20.0


def main() -> None:
    density, heat_capacity, hydrate_temperature_c = fluid_properties()
    inner_radius = INNER_DIAMETER_M / 2.0

    steel = material("carbon-steel")
    insulation = material("polyurethane-insulation")
    layers = [
        ConductionLayer("steel", steel, WALL_THICKNESS_M, 8),
        ConductionLayer("insulation", insulation, INSULATION_THICKNESS_M, 24),
    ]
    wall = RadialConductionModel(layers, inner_radius_m=inner_radius)

    conditions = derive_thermal_conditions(
        wall_thickness_m=WALL_THICKNESS_M + INSULATION_THICKNESS_M,
        solid_conductivity_w_per_mk=insulation.conductivity_w_per_mk,
        solid_thermal_diffusivity_m2_per_s=insulation.thermal_diffusivity_at(25.0),
        inner_film=SHUT_IN_FILM_W_PER_M2K,
        inner_bulk_temperature_c=OPERATING_TEMPERATURE_C,
        outer_film_coefficient_w_per_m2k=EXTERNAL_FILM_W_PER_M2K,
        outer_bulk_temperature_c=SEABED_TEMPERATURE_C,
        transient_duration_s=24.0 * 3600.0,
    )
    time_step = conditions.recommended_time_step_s or 60.0
    print(f"\nhydrate temperature: {hydrate_temperature_c:.1f} degC")
    print(f"time-step target from the penetration depth: {time_step:.0f} s")

    # The steady state at shutdown is the starting temperature profile - not a
    # uniform temperature, which would flatter the cooldown.
    steady = wall.solve_steady(
        inner_film_coefficient_w_per_m2k=900.0,
        inner_bulk_temperature_c=OPERATING_TEMPERATURE_C,
        outer_film_coefficient_w_per_m2k=EXTERNAL_FILM_W_PER_M2K,
        outer_bulk_temperature_c=SEABED_TEMPERATURE_C,
    )
    print(f"steady heat loss before shutdown: "
          f"{steady.heat_flow_per_length_w_per_m:.1f} W/m "
          f"(U = {steady.overall_u_inner_w_per_m2k:.2f} W/m2K)")

    # The bore inventory the wall has to cool, per unit length.
    inventory_capacity = density * heat_capacity * pi * inner_radius**2
    print(f"bore inventory: {inventory_capacity / 1000.0:.1f} kJ/m.K")

    cooldown = wall.solve_transient(
        initial_temperature_c=steady.temperatures_c,
        duration_s=48.0 * 3600.0,
        time_step_s=min(time_step, 120.0),
        inner_film_coefficient_w_per_m2k=SHUT_IN_FILM_W_PER_M2K,
        inner_bulk_temperature_c=OPERATING_TEMPERATURE_C,
        outer_film_coefficient_w_per_m2k=EXTERNAL_FILM_W_PER_M2K,
        outer_bulk_temperature_c=SEABED_TEMPERATURE_C,
        inner_fluid_capacity=inventory_capacity,
        sample_count=200,
    )

    no_touch = cooldown.time_to_reach(hydrate_temperature_c, location="inner_fluid")
    if no_touch is None:
        print("\nthe fluid does not reach the hydrate temperature within 48 h")
    else:
        print(f"\nno-touch time to {hydrate_temperature_c:.1f} degC: "
              f"{no_touch / 3600.0:.1f} h")
    print(f"fluid temperature after 48 h: {cooldown.inner_fluid_history_c[-1]:.1f} degC")
    for warning in cooldown.warnings:
        print("  !", warning)

    gate = FemCouplingModel().assess_quality(
        element_order=1,
        elements_across_critical_layer=24,
        mesh_levels=1,
        energy_balance_error_percent=0.0,
        steady_state=False,
        time_steps=cooldown.steps,
        mesh_fourier_number=insulation.thermal_diffusivity_at(25.0)
        * cooldown.time_step_s
        / (INSULATION_THICKNESS_M / 24.0) ** 2,
        biot=conditions.biot,
    )
    print(f"\nquality gate: {gate.verdict}")
    for finding in gate.findings:
        print("  -", finding)
    print("\nassumptions carried into the receiving report:")
    for assumption in cooldown.assumptions:
        print("  *", assumption)


if __name__ == "__main__":
    main()
