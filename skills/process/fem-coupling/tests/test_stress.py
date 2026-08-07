import pytest

from fem_coupling import (
    evaluate_wall_stress,
    material,
    pressure_stress,
    thermal_stress,
    von_mises,
)


def test_free_expansion_produces_no_stress():
    assert thermal_stress(material("carbon-steel"), delta_temperature_k=80.0,
                          restraint="free") == 0.0


def test_axial_restraint_is_e_alpha_delta_t():
    steel = material("carbon-steel")
    value = thermal_stress(steel, delta_temperature_k=50.0, restraint="axial")
    assert value == pytest.approx(
        steel.youngs_modulus_pa * steel.thermal_expansion_1_per_k * 50.0
    )


def test_restraint_ordering_is_physical():
    steel = material("carbon-steel")
    axial = thermal_stress(steel, delta_temperature_k=50.0, restraint="axial")
    biaxial = thermal_stress(steel, delta_temperature_k=50.0, restraint="biaxial")
    gradient = thermal_stress(
        steel, delta_temperature_k=50.0, restraint="through_wall_gradient"
    )
    assert biaxial > axial > gradient
    assert gradient == pytest.approx(biaxial / 2.0)


def test_a_material_without_mechanical_properties_is_refused():
    with pytest.raises(ValueError, match="no modulus"):
        thermal_stress(
            material("polyurethane-insulation"), delta_temperature_k=50.0
        )


def test_lame_hoop_stress_exceeds_the_thin_wall_value_at_the_bore():
    result = pressure_stress(
        inner_radius_m=0.100,
        outer_radius_m=0.130,
        internal_pressure_pa=200.0e5,
    )
    assert result.hoop_pa > result.thin_wall_hoop_pa
    assert result.radial_pa == pytest.approx(-200.0e5)
    assert result.thick_wall_required


def test_external_pressure_reduces_the_hoop_stress():
    bare = pressure_stress(
        inner_radius_m=0.127, outer_radius_m=0.1397, internal_pressure_pa=150.0e5
    )
    submerged = pressure_stress(
        inner_radius_m=0.127,
        outer_radius_m=0.1397,
        internal_pressure_pa=150.0e5,
        external_pressure_pa=30.0e5,
    )
    assert submerged.hoop_pa < bare.hoop_pa


def test_evaluating_at_a_radius_outside_the_wall_is_rejected():
    with pytest.raises(ValueError, match="inside the wall"):
        pressure_stress(
            inner_radius_m=0.1,
            outer_radius_m=0.12,
            internal_pressure_pa=1.0e5,
            at_radius_m=0.2,
        )


def test_von_mises_of_a_hydrostatic_state_is_zero():
    assert von_mises(10.0, 10.0, 10.0) == pytest.approx(0.0)


def test_a_well_insulated_wall_carries_a_small_thermal_stress():
    steel = material("carbon-steel")
    result = evaluate_wall_stress(
        steel,
        location="20-P-001 wall",
        inner_wall_temperature_c=44.82,
        outer_wall_temperature_c=44.70,
        inner_radius_m=0.127,
        outer_radius_m=0.1397,
        internal_pressure_pa=100.0e5,
    )
    assert result.stress_category == "primary_plus_secondary"
    assert result.thermal_stress_pa < 1.0e6
    assert result.verdict == "acceptable"
    assert any("negligible" in warning for warning in result.warnings)


def test_a_thermal_shock_dominates_the_combined_stress():
    steel = material("carbon-steel")
    result = evaluate_wall_stress(
        steel,
        location="cold-blowdown wall",
        inner_wall_temperature_c=-40.0,
        outer_wall_temperature_c=20.0,
        restraint="biaxial",
    )
    assert result.delta_temperature_k == pytest.approx(-60.0)
    assert result.combined_von_mises_pa > 100.0e6
    assert result.stress_category == "secondary"


def test_the_pressure_stress_alone_can_condemn_the_wall():
    steel = material("carbon-steel")
    result = evaluate_wall_stress(
        steel,
        location="thin wall",
        inner_wall_temperature_c=60.0,
        outer_wall_temperature_c=55.0,
        inner_radius_m=0.127,
        outer_radius_m=0.130,
        internal_pressure_pa=100.0e5,
    )
    assert result.verdict == "exceeds_allowable"
    assert any("wall-thickness problem" in warning for warning in result.warnings)


def test_secondary_stress_is_assessed_against_a_range_allowable():
    steel = material("carbon-steel")
    result = evaluate_wall_stress(
        steel,
        location="gradient only",
        inner_wall_temperature_c=100.0,
        outer_wall_temperature_c=60.0,
        allowable_stress_pa=100.0e6,
    )
    assert result.allowable_pa == pytest.approx(300.0e6)
    assert result.utilisation == pytest.approx(
        result.combined_von_mises_pa / 300.0e6, rel=1e-3
    )
    assert any("self-limiting" in text for text in result.assumptions)
