import pytest

from fem_coupling import FemCouplingModel


@pytest.fixture()
def model():
    return FemCouplingModel()


def _good_gate(**overrides):
    defaults = dict(
        element_order=1,
        elements_across_critical_layer=6,
        mesh_levels=3,
        convergence_percent=0.4,
        max_aspect_ratio=8.0,
        energy_balance_error_percent=0.01,
        far_field_ratio=6.0,
    )
    defaults.update(overrides)
    return defaults


def test_a_well_built_study_is_usable(model):
    result = model.assess_quality(**_good_gate())
    assert result.verdict == "usable"
    assert result.findings == ()


def test_one_mesh_is_not_a_convergence_study(model):
    result = model.assess_quality(**_good_gate(mesh_levels=1, convergence_percent=None))
    assert not result.mesh_independence_ok
    assert result.verdict == "usable_with_caution"
    assert any("mesh independence" in finding for finding in result.findings)


def test_two_linear_elements_across_the_controlling_layer_is_not_enough(model):
    result = model.assess_quality(**_good_gate(elements_across_critical_layer=2))
    assert not result.discretisation_ok
    assert result.verdict == "usable_with_caution"


def test_quadratic_elements_relax_the_element_count(model):
    result = model.assess_quality(
        **_good_gate(element_order=2, elements_across_critical_layer=2)
    )
    assert result.discretisation_ok


def test_an_unreported_energy_balance_is_treated_as_unchecked(model):
    result = model.assess_quality(**_good_gate(energy_balance_error_percent=None))
    assert not result.energy_balance_ok
    assert any("energy balance" in finding for finding in result.findings)


def test_a_broken_energy_balance_and_a_coarse_mesh_is_not_usable(model):
    result = model.assess_quality(
        **_good_gate(energy_balance_error_percent=12.0, elements_across_critical_layer=1)
    )
    assert result.verdict == "not_usable"


def test_a_near_far_field_boundary_becomes_an_input_to_the_answer(model):
    result = model.assess_quality(**_good_gate(far_field_ratio=1.2))
    assert not result.boundary_placement_ok
    assert any("far-field" in finding for finding in result.findings)


def test_a_smeared_transient_is_flagged(model):
    result = model.assess_quality(
        **_good_gate(steady_state=False, time_steps=200, mesh_fourier_number=40.0)
    )
    assert not result.time_resolution_ok
    assert any("Fourier" in finding for finding in result.findings)


def test_a_lumped_problem_is_told_it_did_not_need_a_mesh(model):
    result = model.assess_quality(**_good_gate(biot=0.02))
    assert any("lumped" in finding for finding in result.findings)


def test_resolution_plan_never_falls_below_the_element_minimum(model):
    plan = model.plan_resolution(layer_thickness_m=0.0127, max_element_size_m=0.05)
    assert plan.elements_across_layer == 3
    assert plan.element_size_m == pytest.approx(0.0127 / 3.0)


def test_resolution_plan_follows_the_physics_target(model):
    plan = model.plan_resolution(
        layer_thickness_m=0.05,
        max_element_size_m=0.002,
        thermal_diffusivity_m2_per_s=1.6e-7,
    )
    assert plan.elements_across_layer == 25
    assert plan.time_step_s == pytest.approx(0.5 * plan.element_size_m**2 / 1.6e-7)


def test_thermal_handoff_produces_a_u_value_and_a_multiplier(model):
    handoff = model.evaluate_thermal_handoff(
        location="20-P-001 defect section",
        heat_flow_w=560.0,
        reference_area_m2=1.596,
        inner_bulk_temperature_c=45.0,
        outer_bulk_temperature_c=4.0,
        one_dimensional_heat_flow_w=282.0,
    )
    assert handoff.overall_u_w_per_m2k == pytest.approx(560.0 / (1.596 * 41.0))
    assert handoff.u_multiplier == pytest.approx(560.0 / 282.0, rel=1e-3)
    assert handoff.one_dimensional_u_w_per_m2k is not None


def test_a_large_multiplier_is_questioned_rather_than_accepted(model):
    handoff = model.evaluate_thermal_handoff(
        location="suspect",
        heat_flow_w=3000.0,
        reference_area_m2=1.0,
        inner_bulk_temperature_c=45.0,
        outer_bulk_temperature_c=4.0,
        one_dimensional_heat_flow_w=282.0,
    )
    assert any("large" in text for text in handoff.assumptions)


def test_a_hot_spot_factor_is_reported_against_the_mean_flux(model):
    handoff = model.evaluate_thermal_handoff(
        location="clamp",
        heat_flow_w=282.0,
        reference_area_m2=2.0,
        inner_bulk_temperature_c=45.0,
        outer_bulk_temperature_c=4.0,
        peak_local_flux_w_per_m2=705.0,
    )
    assert handoff.hot_spot_factor == pytest.approx(705.0 / 141.0, rel=1e-3)


def test_a_zero_driving_temperature_has_no_u_value(model):
    with pytest.raises(ValueError, match="no U-value"):
        model.evaluate_thermal_handoff(
            location="isothermal",
            heat_flow_w=1.0,
            reference_area_m2=1.0,
            inner_bulk_temperature_c=20.0,
            outer_bulk_temperature_c=20.0,
        )
