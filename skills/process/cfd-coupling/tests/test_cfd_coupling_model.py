import pytest

from cfd_coupling import CfdCouplingModel


def test_velocity_only_enhancement_uses_blasius_exponent() -> None:
    result = CfdCouplingModel().evaluate_local_enhancement(
        location="weld at bend tangent",
        bulk_velocity=2.0,
        local_peak_velocity=4.0,
    )

    assert result.shear_source == "estimated_from_velocity"
    assert result.velocity_enhancement == pytest.approx(2.0, abs=1e-6)
    assert result.shear_enhancement == pytest.approx(2.0**1.75, abs=1e-3)
    # Mass transfer scales with the friction velocity, so it is the square root of shear.
    assert result.mass_transfer_enhancement == pytest.approx(
        (2.0**1.75) ** 0.5, abs=1e-3
    )


def test_reported_wall_shear_is_preferred_over_velocity() -> None:
    result = CfdCouplingModel().evaluate_local_enhancement(
        location="header inlet",
        bulk_velocity=2.0,
        local_peak_velocity=4.0,
        bulk_wall_shear=10.0,
        local_peak_wall_shear=25.0,
    )

    assert result.shear_source == "cfd_wall_shear"
    assert result.shear_enhancement == pytest.approx(2.5, abs=1e-6)
    assert result.mass_transfer_enhancement == pytest.approx(2.5**0.5, abs=1e-3)


def test_partial_wall_shear_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        CfdCouplingModel().evaluate_local_enhancement(
            location="bend",
            bulk_velocity=2.0,
            local_peak_velocity=3.0,
            bulk_wall_shear=10.0,
        )


def test_large_enhancement_raises_single_cell_artefact_caution() -> None:
    result = CfdCouplingModel().evaluate_local_enhancement(
        location="model-wide maximum",
        bulk_velocity=2.0,
        local_peak_velocity=30.0,
    )

    assert any("single-cell" in a for a in result.assumptions)


def test_quality_gate_passes_a_well_posed_study() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="k-omega-sst",
        wall_treatment="wall_function",
        y_plus=50.0,
        mesh_levels=3,
        gci_percent=3.0,
    )

    assert gate.verdict == "usable"
    assert gate.wall_treatment_ok
    assert gate.mesh_independence_ok
    assert gate.turbulence_model_class == "rans"


def test_single_mesh_cannot_demonstrate_independence() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="k-omega-sst",
        wall_treatment="wall_function",
        y_plus=50.0,
        mesh_levels=1,
    )

    assert gate.verdict == "usable_with_caution"
    assert not gate.mesh_independence_ok


@pytest.mark.parametrize(
    "spelling", ["kOmegaSST", "k-omega-sst", "k omega SST", "kOmegaSSTLM", "realizable k-epsilon"]
)
def test_model_names_are_recognised_whatever_the_separator_style(spelling: str) -> None:
    # derive_boundary_conditions recommends "kOmegaSST"; the gate must accept the
    # very name the skill itself produces, and the CFD-code spellings around it.
    gate = CfdCouplingModel().assess_quality(
        turbulence_model=spelling,
        wall_treatment="wall_function",
        y_plus=50.0,
        mesh_levels=3,
        gci_percent=1.0,
    )

    assert gate.turbulence_model_class == "rans"
    assert not any("not recognised" in finding for finding in gate.findings)


def test_an_unknown_model_is_still_reported() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="house-blend-v2",
        wall_treatment="wall_function",
        y_plus=50.0,
        mesh_levels=3,
    )

    assert gate.turbulence_model_class == "unknown"
    assert any("not recognised" in finding for finding in gate.findings)


def test_a_des_derivative_is_classified_as_scale_resolving_not_rans() -> None:
    # kOmegaSSTDES contains the SST token but is a DES model; the scale-resolving
    # classification has to win, or a DES study would be wrongly caveated as RANS.
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="kOmegaSSTDES",
        wall_treatment="resolved",
        y_plus=0.9,
        mesh_levels=3,
        steady_state=False,
    )

    assert gate.turbulence_model_class == "scale_resolving"
    assert not any("RANS model" in finding for finding in gate.findings)


def test_wall_function_outside_valid_y_plus_band_is_flagged() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="k-epsilon",
        wall_treatment="wall_function",
        y_plus=3.0,
        mesh_levels=3,
    )

    assert not gate.wall_treatment_ok
    assert any("wall-function band" in f for f in gate.findings)


def test_missing_y_plus_and_single_mesh_is_not_usable() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="k-epsilon",
        wall_treatment="wall_function",
        mesh_levels=1,
    )

    assert gate.verdict == "not_usable"


def test_scale_resolving_model_is_classified() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="SAS",
        wall_treatment="resolved",
        y_plus=0.8,
        mesh_levels=3,
        steady_state=False,
    )

    assert gate.turbulence_model_class == "scale_resolving"
    assert gate.verdict == "usable"


def test_unknown_turbulence_model_cannot_be_fully_trusted() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="proprietary-model-x",
        wall_treatment="wall_function",
        y_plus=50.0,
        mesh_levels=3,
    )

    assert gate.turbulence_model_class == "unknown"
    assert gate.verdict == "usable_with_caution"


def test_poor_grid_convergence_index_fails_mesh_check() -> None:
    gate = CfdCouplingModel().assess_quality(
        turbulence_model="sst",
        wall_treatment="wall_function",
        y_plus=50.0,
        mesh_levels=3,
        gci_percent=14.0,
    )

    assert not gate.mesh_independence_ok
    assert any("not grid converged" in f for f in gate.findings)


def test_wall_resolution_gives_a_finer_cell_for_a_lower_target_y_plus() -> None:
    model = CfdCouplingModel()
    coarse = model.plan_wall_resolution(
        density=931.0, viscosity=0.487e-3, velocity=2.66,
        hydraulic_diameter=0.035, target_y_plus=30.0,
    )
    fine = model.plan_wall_resolution(
        density=931.0, viscosity=0.487e-3, velocity=2.66,
        hydraulic_diameter=0.035, target_y_plus=1.0,
    )

    assert fine.first_cell_height_m < coarse.first_cell_height_m
    assert fine.reynolds == pytest.approx(coarse.reynolds, rel=1e-9)
    assert fine.friction_velocity_ms > 0.0
    # The cell height is twice the centroid distance for a cell-centred solver.
    assert fine.first_cell_height_m == pytest.approx(
        2.0 * fine.first_cell_centroid_height_m, rel=1e-12
    )


def test_laminar_flow_is_flagged_in_wall_resolution() -> None:
    result = CfdCouplingModel().plan_wall_resolution(
        density=1000.0, viscosity=1.0, velocity=0.001,
        hydraulic_diameter=0.01, target_y_plus=1.0,
    )

    assert result.reynolds < 2300.0
    assert any("laminar" in a for a in result.assumptions)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bulk_velocity": -1.0, "local_peak_velocity": 2.0},
        {"bulk_velocity": 2.0, "local_peak_velocity": 0.0},
    ],
)
def test_invalid_velocities_are_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        CfdCouplingModel().evaluate_local_enhancement(location="x", **kwargs)


def test_blank_location_is_rejected() -> None:
    with pytest.raises(ValueError):
        CfdCouplingModel().evaluate_local_enhancement(
            location="   ", bulk_velocity=2.0, local_peak_velocity=3.0
        )


def test_invalid_wall_treatment_is_rejected() -> None:
    with pytest.raises(ValueError):
        CfdCouplingModel().assess_quality(
            turbulence_model="sst", wall_treatment="magic", y_plus=50.0
        )
