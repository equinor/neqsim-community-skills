import pytest

from cfd_coupling import (
    FluidState,
    MeshSpec,
    OpenFoamCase,
    derive_boundary_conditions,
    read_case_results,
)


@pytest.fixture()
def boundary():
    state = FluidState(
        name="wet gas",
        phase="gas",
        density_kg_per_m3=52.4,
        viscosity_pa_s=1.45e-5,
        speed_of_sound_m_per_s=395.0,
    )
    return derive_boundary_conditions(
        state, hydraulic_diameter_m=0.3048, velocity_m_per_s=12.0
    )


def build_case(boundary, **overrides) -> OpenFoamCase:
    settings = dict(
        boundary=boundary,
        mesh=MeshSpec(kind="pipe", diameter_m=0.3048, length_m=3.0, first_cell_height_m=0.0005),
        name="test-case",
    )
    settings.update(overrides)
    return OpenFoamCase(**settings)


def test_case_writes_a_complete_tree(tmp_path, boundary) -> None:
    case_dir = tmp_path / "case"
    written = build_case(boundary).write(case_dir)

    for expected in (
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/blockMeshDict",
        "constant/physicalProperties",
        "constant/momentumTransport",
        "0/U",
        "0/p",
        "0/k",
        "0/omega",
        "0/nut",
    ):
        assert expected in written
        assert (case_dir / expected).is_file()


def test_viscosity_written_is_the_kinematic_viscosity_of_the_fluid(tmp_path, boundary) -> None:
    case_dir = tmp_path / "case"
    build_case(boundary).write(case_dir)

    text = (case_dir / "constant" / "physicalProperties").read_text()
    expected = boundary.fluid.kinematic_viscosity_m2_per_s
    assert f"{expected:.8g}" in text


def test_turbulence_fields_match_the_derived_inlet_state(tmp_path, boundary) -> None:
    case_dir = tmp_path / "case"
    build_case(boundary).write(case_dir)

    k_text = (case_dir / "0" / "k").read_text()
    omega_text = (case_dir / "0" / "omega").read_text()
    assert f"{boundary.turbulent_kinetic_energy_m2_per_s2:.8g}" in k_text
    assert f"{boundary.specific_dissipation_1_per_s:.8g}" in omega_text


def test_wall_treatment_selects_the_matching_nut_wall_function(tmp_path, boundary) -> None:
    wall_function_dir = tmp_path / "wf"
    resolved_dir = tmp_path / "res"
    build_case(boundary, wall_treatment="wall_function").write(wall_function_dir)
    build_case(boundary, wall_treatment="resolved").write(resolved_dir)

    assert "nutkWallFunction" in (wall_function_dir / "0" / "nut").read_text()
    assert "nutLowReWallFunction" in (resolved_dir / "0" / "nut").read_text()


def test_pipe_block_mesh_has_five_blocks_and_named_patches(tmp_path, boundary) -> None:
    case_dir = tmp_path / "case"
    build_case(boundary).write(case_dir)

    text = (case_dir / "system" / "blockMeshDict").read_text()
    # One core block plus four O-grid ring blocks.
    assert text.count("hex (") == 5
    # Eight arc edges: four per end plane.
    assert text.count("arc ") == 8
    assert "inlet" in text and "outlet" in text and "walls" in text
    assert text.count("(") == text.count(")")


def test_near_wall_grading_is_solved_from_the_requested_first_cell(tmp_path, boundary) -> None:
    fine = build_case(
        boundary,
        mesh=MeshSpec(
            kind="pipe", diameter_m=0.3048, length_m=3.0, radial_cells=14, first_cell_height_m=1e-5
        ),
    )
    uniform = build_case(
        boundary,
        mesh=MeshSpec(kind="pipe", diameter_m=0.3048, length_m=3.0, radial_cells=14),
    )
    fine_dir, uniform_dir = tmp_path / "fine", tmp_path / "uniform"
    fine.write(fine_dir)
    uniform.write(uniform_dir)

    fine_text = (fine_dir / "system" / "blockMeshDict").read_text()
    uniform_text = (uniform_dir / "system" / "blockMeshDict").read_text()
    assert "simpleGrading (1 1 1)" in uniform_text
    assert "Radial grading 1 " not in fine_text


def test_over_stretched_near_wall_mesh_is_warned_about_with_a_cell_count(boundary) -> None:
    case = build_case(
        boundary,
        mesh=MeshSpec(
            kind="pipe", diameter_m=0.3048, length_m=3.0, radial_cells=10, first_cell_height_m=2e-4
        ),
    )

    warnings = case.mesh_warnings()

    assert warnings
    assert "expansion" in warnings[0]
    assert "cell count" in warnings[0]


def test_a_well_proportioned_near_wall_mesh_produces_no_warning(boundary) -> None:
    case = build_case(
        boundary,
        mesh=MeshSpec(
            kind="pipe", diameter_m=0.3048, length_m=3.0, radial_cells=30, first_cell_height_m=2e-4
        ),
    )

    assert case.mesh_warnings() == ()


def bend_mesh(**overrides) -> MeshSpec:
    settings = dict(
        kind="bend",
        diameter_m=0.03504,
        bend_radius_m=1.5 * 0.03504,
        bend_angle_deg=90.0,
        inlet_length_m=10 * 0.03504,
        outlet_length_m=15 * 0.03504,
        axial_cells=40,
    )
    settings.update(overrides)
    return MeshSpec(**settings)


def test_bend_mesh_sweeps_three_segments_of_the_o_grid(tmp_path, boundary) -> None:
    case_dir = tmp_path / "bend"
    build_case(boundary, mesh=bend_mesh(), axis="x").write(case_dir)

    text = (case_dir / "system" / "blockMeshDict").read_text()
    # Three segments (lead-in, bend, lead-out) of five O-grid blocks each.
    assert text.count("hex (") == 15
    # Four cross-section arcs at each of four stations, plus eight through the bend.
    assert text.count("arc ") == 24
    assert text.count("(") == text.count(")")


def test_bend_inlet_plane_is_normal_to_x_and_outlet_to_z(tmp_path, boundary) -> None:
    case_dir = tmp_path / "bend"
    build_case(boundary, mesh=bend_mesh(), axis="x").write(case_dir)

    text = (case_dir / "system" / "blockMeshDict").read_text()
    vertices = [
        tuple(float(v) for v in line.strip().strip("()").split())
        for line in text.split("vertices")[1].split(");")[0].splitlines()
        if line.startswith("    (")
    ]
    inlet_ring, outlet_ring = vertices[:8], vertices[24:32]
    # The inlet station is a plane at constant x, the outlet at constant z.
    assert len({round(p[0], 9) for p in inlet_ring}) == 1
    assert len({round(p[2], 9) for p in outlet_ring}) == 1


def test_bend_forces_the_inlet_velocity_onto_its_own_axis(boundary) -> None:
    # A bend inlet plane is normal to x; the default z axis would put the inlet
    # velocity in the plane of the inlet and drive essentially no flow.
    with pytest.raises(ValueError, match="inlet normal along x"):
        build_case(boundary, mesh=bend_mesh())

    case = build_case(boundary, mesh=bend_mesh(), axis="x")
    assert case.commands()[0] == "blockMesh"


def test_bend_geometry_is_validated() -> None:
    with pytest.raises(ValueError, match="bend_radius_m"):
        MeshSpec(kind="bend", diameter_m=0.1, inlet_length_m=1.0, outlet_length_m=1.0)
    with pytest.raises(ValueError, match="folds the mesh"):
        bend_mesh(bend_radius_m=0.4 * 0.03504)
    with pytest.raises(ValueError, match="bend_angle_deg"):
        bend_mesh(bend_angle_deg=200.0)


def test_wall_shear_is_reduced_to_a_magnitude_before_it_is_sampled(tmp_path, boundary) -> None:
    # surfaceFieldValue's max on a vector is component-wise, so sampling
    # wallShearStress directly returns a peak that can be below the mean.
    case_dir = tmp_path / "case"
    build_case(boundary).write(case_dir)

    control = (case_dir / "system" / "controlDict").read_text()
    assert "result          magWallShearStress;" in control
    assert "fields          (magWallShearStress);" in control
    assert "fields          (wallShearStress);" not in control
    # The magnitude must be computed after the field it reduces.
    assert control.index("type            wallShearStress;") < control.index(
        "result          magWallShearStress;"
    )


def test_channel_mesh_grades_towards_both_walls(tmp_path, boundary) -> None:
    case_dir = tmp_path / "channel"
    build_case(
        boundary,
        mesh=MeshSpec(
            kind="channel",
            height_m=0.05,
            width_m=0.20,
            length_m=1.0,
            first_cell_height_m=1e-4,
        ),
    ).write(case_dir)

    text = (case_dir / "system" / "blockMeshDict").read_text()
    assert text.count("hex (") == 1
    assert "0.5" in text  # multi-grading halves


def test_legacy_flavour_uses_the_older_dictionary_names(tmp_path, boundary) -> None:
    case_dir = tmp_path / "legacy"
    written = build_case(boundary, flavour="legacy").write(case_dir)

    assert "constant/transportProperties" in written
    assert "constant/turbulenceProperties" in written
    assert "RASModel" in (case_dir / "constant" / "turbulenceProperties").read_text()
    assert "application     simpleFoam;" in (case_dir / "system" / "controlDict").read_text()


def test_each_flavour_uses_the_viscosity_keyword_its_solver_accepts(tmp_path, boundary) -> None:
    # simpleFoam rejects a transportProperties without transportModel; foamRun
    # rejects a physicalProperties without viscosityModel.
    legacy_dir = tmp_path / "legacy"
    build_case(boundary, flavour="legacy").write(legacy_dir)
    legacy_text = (legacy_dir / "constant" / "transportProperties").read_text()
    assert "transportModel  Newtonian;" in legacy_text
    assert "viscosityModel" not in legacy_text

    org_dir = tmp_path / "org"
    build_case(boundary, flavour="org").write(org_dir)
    org_text = (org_dir / "constant" / "physicalProperties").read_text()
    assert "viscosityModel  constant;" in org_text
    assert "transportModel" not in org_text


def test_commands_cover_mesh_check_solve_and_export(boundary) -> None:
    assert build_case(boundary).commands() == (
        "blockMesh",
        "checkMesh -constant",
        "foamRun",
        "foamToVTK -latestTime",
    )


def test_external_mesh_selects_the_converter_from_the_file_type(boundary) -> None:
    case = build_case(
        boundary, mesh=MeshSpec(kind="external", mesh_file="/tmp/vessel.msh")
    )

    assert case.commands()[0] == "gmshToFoam vessel.msh"


def test_unknown_external_mesh_type_demands_an_explicit_command(boundary) -> None:
    case = build_case(boundary, mesh=MeshSpec(kind="external", mesh_file="/tmp/vessel.xyz"))

    with pytest.raises(ValueError, match="no converter known"):
        case.commands()


def test_existing_directory_is_not_silently_replaced(tmp_path, boundary) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()

    with pytest.raises(FileExistsError):
        build_case(boundary).write(case_dir)

    assert build_case(boundary).write(case_dir, overwrite=True)


def test_run_reports_not_executed_when_openfoam_is_missing(tmp_path, boundary, monkeypatch) -> None:
    monkeypatch.setattr("cfd_coupling.openfoam.detect_openfoam", lambda **_: None)
    case_dir = tmp_path / "case"
    case = build_case(boundary)
    case.write(case_dir)

    outcome = case.run(case_dir)

    assert outcome.status == "not_executed"
    assert not outcome.executed
    assert "blockMesh" in outcome.message


def _write_surface_field_value(root, name, value):
    path = root / "postProcessing" / name / "1000"
    path.mkdir(parents=True)
    (path / "surfaceFieldValue.dat").write_text(
        "# Region type : patch\n# Time  value\n1000  " + value + "\n"
    )


def test_results_are_read_back_and_converted_to_engineering_units(tmp_path) -> None:
    _write_surface_field_value(tmp_path, "inletFlux", "-0.8760")
    _write_surface_field_value(tmp_path, "outletFlux", "0.8759")
    _write_surface_field_value(tmp_path, "inletPressure", "150.0")
    _write_surface_field_value(tmp_path, "outletPressure", "100.0")
    _write_surface_field_value(tmp_path, "peakWallShear_walls", "(0.03 0.004 0)")
    _write_surface_field_value(tmp_path, "meanWallShear_walls", "(0.01 0.0 0)")
    y_plus_dir = tmp_path / "postProcessing" / "yPlus" / "1000"
    y_plus_dir.mkdir(parents=True)
    (y_plus_dir / "yPlus.dat").write_text(
        "# Time patch min max average\n1000\twalls\t35.0\t180.0\t92.0\n"
    )

    results = read_case_results(tmp_path, density_kg_per_m3=52.4)

    assert results.inlet_volumetric_flow_m3_per_s == pytest.approx(0.876)
    assert results.continuity_error_relative == pytest.approx(0.0001 / 0.876, rel=1e-3)
    assert results.pressure_drop_pa == pytest.approx(50.0 * 52.4)
    assert results.y_plus_max == pytest.approx(180.0)
    # Vector wall shear is reduced to its magnitude, then scaled by density.
    assert results.peak_wall_shear_pa == pytest.approx((0.03**2 + 0.004**2) ** 0.5 * 52.4)
    assert results.wall_shear_enhancement == pytest.approx(
        (0.03**2 + 0.004**2) ** 0.5 / 0.01
    )


def test_results_without_density_stay_kinematic_and_say_so(tmp_path) -> None:
    _write_surface_field_value(tmp_path, "inletPressure", "150.0")
    _write_surface_field_value(tmp_path, "outletPressure", "100.0")

    results = read_case_results(tmp_path)

    assert results.pressure_drop_pa == pytest.approx(50.0)
    assert any("kinematic" in finding for finding in results.findings)


def test_missing_post_processing_is_reported_rather_than_raised(tmp_path) -> None:
    results = read_case_results(tmp_path)

    assert results.pressure_drop_pa is None
    assert any("not produced results" in finding for finding in results.findings)


def test_mesh_spec_validates_its_geometry() -> None:
    with pytest.raises(ValueError, match="diameter_m"):
        MeshSpec(kind="pipe", length_m=1.0)
    with pytest.raises(ValueError, match="mesh_file"):
        MeshSpec(kind="external")
    with pytest.raises(ValueError, match="core_fraction"):
        MeshSpec(kind="pipe", diameter_m=0.3, length_m=1.0, core_fraction=0.95)
