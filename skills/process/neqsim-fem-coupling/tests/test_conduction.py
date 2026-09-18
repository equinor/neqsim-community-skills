from math import pi

import pytest

from fem_coupling import (
    ConductionLayer,
    RadialConductionModel,
    analytic_composite_resistance,
    custom_material,
    material,
)


def _layers(steel_elements=20, insulation_elements=40):
    steel = custom_material(
        "carbon-steel", conductivity_w_per_mk=50.0, conductivity_temp_coeff_w_per_mk2=0.0
    )
    insulation = custom_material(
        "polyurethane-insulation",
        conductivity_w_per_mk=0.17,
        conductivity_temp_coeff_w_per_mk2=0.0,
    )
    return [
        ConductionLayer("steel", steel, 0.0127, steel_elements),
        ConductionLayer("insulation", insulation, 0.05, insulation_elements),
    ]


def test_steady_solution_matches_the_closed_form_resistance():
    layers = _layers()
    model = RadialConductionModel(layers, inner_radius_m=0.127)
    result = model.solve_steady(
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    resistance = analytic_composite_resistance(
        layers,
        inner_radius_m=0.127,
        inner_film_coefficient_w_per_m2k=1000.0,
        outer_film_coefficient_w_per_m2k=300.0,
    )
    expected = (45.0 - 4.0) / resistance
    assert result.heat_flow_per_length_w_per_m == pytest.approx(expected, rel=1e-3)
    assert result.analytic_deviation_percent < 0.1
    assert result.warnings == ()


def test_most_of_the_temperature_drop_falls_across_the_insulation():
    model = RadialConductionModel(_layers(), inner_radius_m=0.127)
    result = model.solve_steady(
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    interfaces = dict(result.interface_temperatures_c)
    steel_drop = interfaces["steel inner face"] - interfaces["steel outer face"]
    insulation_drop = (
        interfaces["insulation inner face"] - interfaces["insulation outer face"]
    )
    assert steel_drop < 0.2
    assert insulation_drop > 35.0


def test_a_planar_wall_reproduces_the_series_resistance():
    steel = custom_material(
        "carbon-steel", conductivity_w_per_mk=50.0, conductivity_temp_coeff_w_per_mk2=0.0
    )
    model = RadialConductionModel(
        [ConductionLayer("plate", steel, 0.02, 10)], geometry="planar"
    )
    result = model.solve_steady(
        inner_film_coefficient_w_per_m2k=500.0,
        inner_bulk_temperature_c=100.0,
        outer_film_coefficient_w_per_m2k=25.0,
        outer_bulk_temperature_c=20.0,
    )
    expected_resistance = 1.0 / 500.0 + 0.02 / 50.0 + 1.0 / 25.0
    assert result.heat_flux_inner_w_per_m2 == pytest.approx(
        (100.0 - 20.0) / expected_resistance, rel=1e-4
    )
    assert result.heat_flow_per_length_w_per_m is None


def test_a_coarse_layer_is_reported_rather_than_silently_accepted():
    model = RadialConductionModel(
        _layers(steel_elements=1, insulation_elements=1), inner_radius_m=0.127
    )
    result = model.solve_steady(
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    assert any("elements" in warning for warning in result.warnings)


def test_temperature_dependent_conductivity_converges():
    layers = [
        ConductionLayer("steel", material("carbon-steel"), 0.0127, 10),
        ConductionLayer("insulation", material("polyurethane-insulation"), 0.05, 20),
    ]
    model = RadialConductionModel(layers, inner_radius_m=0.127)
    result = model.solve_steady(
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    assert result.nonlinear_converged
    assert result.nonlinear_sweeps <= 12


def test_cooldown_with_a_lumped_bore_fluid_matches_the_lumped_time_constant():
    layers = _layers()
    inner_radius = 0.127
    model = RadialConductionModel(layers, inner_radius_m=inner_radius)

    # A dead-oil bore inventory: rho cp A.
    capacity = 800.0 * 2100.0 * pi * inner_radius**2
    result = model.solve_transient(
        initial_temperature_c=45.0,
        duration_s=30.0 * 3600.0,
        time_step_s=60.0,
        inner_film_coefficient_w_per_m2k=50.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
        inner_fluid_capacity=capacity,
        sample_count=120,
    )
    assert result.inner_fluid_history_c[0] == pytest.approx(45.0)
    assert result.inner_fluid_history_c[-1] < 15.0

    time_to_25 = result.time_to_reach(25.0)
    assert time_to_25 is not None
    # A lumped estimate over the fluid plus the wall gives a time constant of order
    # twelve hours, so the crossing sits between six and twelve hours.
    assert 6.0 * 3600.0 < time_to_25 < 12.0 * 3600.0


def test_a_fixed_bulk_temperature_is_flagged_as_not_a_cooldown():
    model = RadialConductionModel(_layers(), inner_radius_m=0.127)
    result = model.solve_transient(
        initial_temperature_c=45.0,
        duration_s=3600.0,
        time_step_s=10.0,
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    assert result.inner_fluid_history_c == ()
    assert any("cooldown" in warning for warning in result.warnings)


def test_transient_relaxes_to_the_steady_solution():
    layers = _layers()
    model = RadialConductionModel(layers, inner_radius_m=0.127)
    steady = model.solve_steady(
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    transient = model.solve_transient(
        initial_temperature_c=4.0,
        duration_s=200.0 * 3600.0,
        time_step_s=600.0,
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    assert transient.inner_surface_history_c[-1] == pytest.approx(
        steady.inner_surface_temperature_c, abs=0.1
    )


def test_geometry_and_layer_inputs_are_validated():
    with pytest.raises(ValueError, match="at least one conduction layer"):
        RadialConductionModel([], inner_radius_m=0.1)
    with pytest.raises(ValueError, match="geometry"):
        RadialConductionModel(_layers(), inner_radius_m=0.1, geometry="toroidal")
    with pytest.raises(ValueError, match="inner_radius_m"):
        RadialConductionModel(_layers())


def test_outer_bulk_temperature_is_calibrated_to_a_known_metal_temperature():
    steel = custom_material(
        "carbon-steel", conductivity_w_per_mk=45.0, conductivity_temp_coeff_w_per_mk2=0.0
    )
    wall = RadialConductionModel(
        [ConductionLayer("tube wall", steel, 0.00356, 12)], inner_radius_m=0.01752
    )
    gas_c = wall.calibrate_outer_bulk_temperature(
        target_inner_surface_temperature_c=165.0,
        inner_film_coefficient_w_per_m2k=10056.0,
        inner_bulk_temperature_c=150.0,
        outer_film_coefficient_w_per_m2k=400.0,
    )
    solved = wall.solve_steady(
        inner_film_coefficient_w_per_m2k=10056.0,
        inner_bulk_temperature_c=150.0,
        outer_film_coefficient_w_per_m2k=400.0,
        outer_bulk_temperature_c=gas_c,
    )
    assert solved.inner_surface_temperature_c == pytest.approx(165.0, abs=1e-4)
    # A waste-heat recovery tube at these coefficients implies a turbine-exhaust
    # gas temperature, which is the sanity check the calibration exists to enable.
    assert 400.0 < gas_c < 600.0


def test_calibration_survives_temperature_dependent_conductivity():
    wall = RadialConductionModel(
        [ConductionLayer("tube wall", material("carbon-steel"), 0.00356, 12)],
        inner_radius_m=0.01752,
    )
    gas_c = wall.calibrate_outer_bulk_temperature(
        target_inner_surface_temperature_c=165.0,
        inner_film_coefficient_w_per_m2k=10056.0,
        inner_bulk_temperature_c=150.0,
        outer_film_coefficient_w_per_m2k=400.0,
    )
    solved = wall.solve_steady(
        inner_film_coefficient_w_per_m2k=10056.0,
        inner_bulk_temperature_c=150.0,
        outer_film_coefficient_w_per_m2k=400.0,
        outer_bulk_temperature_c=gas_c,
    )
    assert solved.inner_surface_temperature_c == pytest.approx(165.0, abs=1e-3)
