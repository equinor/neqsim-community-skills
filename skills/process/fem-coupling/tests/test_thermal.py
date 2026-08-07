import pytest

from fem_coupling import (
    FemFluidState,
    derive_thermal_conditions,
    effective_diffusivity,
    film_coefficient,
    material,
)


def _gas():
    return FemFluidState(
        name="rich gas",
        phase="gas",
        temperature_c=45.0,
        pressure_bara=75.0,
        density_kg_per_m3=62.0,
        viscosity_pa_s=1.4e-5,
        thermal_conductivity_w_per_mk=0.043,
        heat_capacity_j_per_kgk=2500.0,
        velocity_m_per_s=5.0,
    )


def test_prandtl_and_diffusivity_are_consistent():
    gas = _gas()
    assert gas.prandtl == pytest.approx(2500.0 * 1.4e-5 / 0.043)
    assert gas.thermal_diffusivity_m2_per_s == pytest.approx(
        0.043 / (62.0 * 2500.0)
    )


def test_gnielinski_is_used_for_turbulent_flow():
    result = film_coefficient(_gas(), hydraulic_diameter_m=0.254)
    assert result.reynolds > 1.0e5
    assert "Gnielinski" in result.correlation
    # A high-pressure gas at 5 m/s in a 10-inch line sits in the hundreds of W/m2K.
    assert 200.0 < result.h_w_per_m2k < 3000.0


def test_laminar_flow_falls_back_to_the_fully_developed_nusselt():
    slow = FemFluidState(
        name="glycol",
        phase="oil",
        temperature_c=20.0,
        pressure_bara=5.0,
        density_kg_per_m3=1100.0,
        viscosity_pa_s=0.5,
        thermal_conductivity_w_per_mk=0.25,
        heat_capacity_j_per_kgk=2400.0,
        velocity_m_per_s=0.05,
    )
    result = film_coefficient(slow, hydraulic_diameter_m=0.05)
    assert result.reynolds < 2300.0
    assert result.nusselt == pytest.approx(3.66)


def test_transitional_flow_is_flagged():
    gas = _gas()
    result = film_coefficient(gas, hydraulic_diameter_m=0.254, velocity_m_per_s=0.0022)
    assert 2300.0 <= result.reynolds < 3000.0
    assert any("transitional" in warning for warning in result.warnings)


def test_a_genuinely_laminar_case_is_not_flagged_as_transitional():
    gas = _gas()
    result = film_coefficient(gas, hydraulic_diameter_m=0.254, velocity_m_per_s=0.001)
    assert result.reynolds < 2300.0
    assert result.nusselt == pytest.approx(3.66)
    assert result.warnings == ()


def test_velocity_must_come_from_somewhere():
    gas = FemFluidState(
        name="gas",
        phase="gas",
        temperature_c=45.0,
        pressure_bara=75.0,
        density_kg_per_m3=62.0,
        viscosity_pa_s=1.4e-5,
        thermal_conductivity_w_per_mk=0.043,
        heat_capacity_j_per_kgk=2500.0,
    )
    with pytest.raises(ValueError, match="velocity"):
        film_coefficient(gas, hydraulic_diameter_m=0.254)


def test_biot_number_uses_the_whole_conduction_path():
    insulation = material("polyurethane-insulation")
    conditions = derive_thermal_conditions(
        wall_thickness_m=0.0627,
        solid_conductivity_w_per_mk=insulation.conductivity_w_per_mk,
        solid_thermal_diffusivity_m2_per_s=insulation.thermal_diffusivity_at(30.0),
        inner_film=film_coefficient(_gas(), hydraulic_diameter_m=0.254),
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    assert conditions.biot > 0.1
    assert not conditions.lumped_capacitance_valid
    assert conditions.regime == "steady"
    assert conditions.penetration_depth_m is None


def test_transient_window_sets_the_element_size_and_time_step():
    insulation = material("polyurethane-insulation")
    conditions = derive_thermal_conditions(
        wall_thickness_m=0.0627,
        solid_conductivity_w_per_mk=insulation.conductivity_w_per_mk,
        solid_thermal_diffusivity_m2_per_s=insulation.thermal_diffusivity_at(30.0),
        inner_film=800.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
        transient_duration_s=3600.0,
    )
    assert conditions.regime == "transient"
    assert conditions.penetration_depth_m is not None
    assert conditions.recommended_time_step_s is not None
    # Four elements across the penetration depth, and no coarser than L/10.
    assert conditions.max_element_size_m <= conditions.penetration_depth_m / 4.0 + 1e-12


def test_a_nearly_isothermal_solid_is_told_it_does_not_need_a_mesh():
    steel = material("carbon-steel")
    conditions = derive_thermal_conditions(
        wall_thickness_m=0.0127,
        solid_conductivity_w_per_mk=steel.conductivity_w_per_mk,
        solid_thermal_diffusivity_m2_per_s=steel.thermal_diffusivity_at(45.0),
        inner_film=50.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=20.0,
        outer_bulk_temperature_c=4.0,
    )
    assert conditions.lumped_capacitance_valid
    assert any("lumped" in warning for warning in conditions.warnings)


def test_effective_diffusivity_scales_with_porosity_over_tortuosity():
    value, assumptions = effective_diffusivity(2.0e-6, porosity=0.22, tortuosity=2.5)
    assert value == pytest.approx(0.22 * 2.0e-6 / 2.5)
    assert any("tortuosity" in text.lower() for text in assumptions)


def test_porosity_must_be_a_fraction():
    with pytest.raises(ValueError, match="porosity"):
        effective_diffusivity(2.0e-6, porosity=22.0)
