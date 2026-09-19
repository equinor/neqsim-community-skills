import json

import pytest

from fem_coupling import (
    BoundaryCondition,
    ConductionProblem,
    FemCase,
    FemMeshSpec,
    MaterialAssignment,
    MeshLayer,
    MeshSegment,
    TransientSettings,
    detect_backends,
    detect_gmsh,
    read_case_results,
    recommend_backend,
)
from fem_coupling.solver import _FENICSX_SCRIPT, _SKFEM_SCRIPT


def _spec():
    return FemMeshSpec(
        kind="axisymmetric_section",
        inner_radius_m=0.127,
        layers=[
            MeshLayer("steel", "carbon-steel", 0.0127, 6),
            MeshLayer("insulation", "polyurethane-insulation", 0.05, 16),
        ],
        segments=[MeshSegment("run", 2.0, 20)],
        name="20-P-001",
    )


def _problem(mesh_file, spec, transient=None):
    return ConductionProblem.from_mesh_spec(
        spec,
        name="20-P-001",
        mesh_file=str(mesh_file),
        materials=[
            MaterialAssignment("carbon-steel", 50.0, 7850.0 * 490.0),
            MaterialAssignment("polyurethane-insulation", 0.17, 700.0 * 1500.0),
        ],
        boundaries=[
            BoundaryCondition("inner", "robin", 1000.0, 45.0),
            BoundaryCondition("outer", "robin", 300.0, 4.0),
            BoundaryCondition("west", "adiabatic"),
            BoundaryCondition("east", "adiabatic"),
        ],
        transient=transient,
    )


def test_generated_scripts_are_valid_python():
    compile(_SKFEM_SCRIPT, "case.py", "exec")
    compile(_FENICSX_SCRIPT, "case.py", "exec")


def test_a_one_dimensional_conduction_problem_is_sent_back_to_the_builtin_solver():
    recommendation = recommend_backend(dimension=1, physics="conduction")
    assert "RadialConductionModel" in recommendation.rationale
    assert any("built-in" in warning for warning in recommendation.warnings)


def test_two_dimensional_scalar_problems_go_to_scikit_fem():
    assert recommend_backend(dimension=2, physics="conduction").backend == "scikit-fem"
    assert recommend_backend(dimension=2, physics="diffusion").backend == "scikit-fem"


def test_coupled_and_nonlinear_problems_go_to_fenicsx():
    assert (
        recommend_backend(dimension=2, physics="thermo_mechanical", coupled=True).backend
        == "fenicsx"
    )
    assert (
        recommend_backend(dimension=3, physics="elasticity", nonlinear=True).backend
        == "fenicsx"
    )


def test_a_very_large_problem_goes_to_a_compiled_backend():
    recommendation = recommend_backend(
        dimension=3, physics="conduction", estimated_dof=8_000_000
    )
    assert recommendation.backend == "mfem"
    assert not recommendation.generated
    assert any("by hand" in warning for warning in recommendation.warnings)


def test_a_frame_idealisation_goes_to_a_structural_package():
    assert recommend_backend(dimension=3, structural_frame=True).backend == "pynite"
    assert (
        recommend_backend(dimension=3, structural_frame=True, dynamic=True).backend
        == "openseespy"
    )


def test_detect_backends_reports_every_known_backend():
    available = detect_backends()
    assert set(available) >= {"scikit-fem", "fenicsx", "mfem", "openseespy", "pynite"}
    assert all(isinstance(value, bool) for value in available.values())


def test_a_robin_boundary_needs_a_film_coefficient_and_a_bulk_temperature():
    with pytest.raises(ValueError, match="film_coefficient"):
        BoundaryCondition("inner", "robin", temperature_c=45.0)
    with pytest.raises(ValueError, match="temperature_c"):
        BoundaryCondition("inner", "robin", film_coefficient_w_per_m2k=100.0)


def test_a_transient_problem_needs_a_heat_capacity_for_every_material():
    with pytest.raises(ValueError, match="volumetric heat capacity"):
        ConductionProblem(
            name="x",
            mesh_file="mesh.msh",
            materials=[MaterialAssignment("carbon-steel", 50.0)],
            boundaries=[BoundaryCondition("inner", "robin", 100.0, 45.0)],
            transient=TransientSettings(45.0, 3600.0, 60.0),
        )


def test_case_is_written_with_a_self_contained_payload(tmp_path):
    spec = _spec()
    geo = spec.write(tmp_path / "mesh")
    problem = _problem(geo.with_suffix(".msh"), spec)
    case = FemCase(problem, backend="scikit-fem")
    target = case.write(tmp_path / "case")

    payload = json.loads((target / "inputs.json").read_text(encoding="utf-8"))
    assert payload["axisymmetric"] is True
    assert payload["mesh_file"] == "mesh.msh"
    assert payload["material_tags"]["carbon-steel"] == 1
    assert payload["boundary_tags"]["inner"] == 101
    assert (target / "case.py").exists()
    assert (target / "README.txt").exists()


def test_a_fenicsx_case_refuses_to_be_written_without_physical_tags(tmp_path):
    problem = ConductionProblem(
        name="x",
        mesh_file="mesh.msh",
        materials=[MaterialAssignment("carbon-steel", 50.0)],
        boundaries=[BoundaryCondition("inner", "robin", 100.0, 45.0)],
    )
    with pytest.raises(ValueError, match="material_tags"):
        FemCase(problem, backend="fenicsx").write(tmp_path)


def test_a_backend_this_skill_cannot_generate_is_rejected():
    problem = ConductionProblem(
        name="x",
        mesh_file="mesh.msh",
        materials=[MaterialAssignment("carbon-steel", 50.0)],
        boundaries=[BoundaryCondition("inner", "robin", 100.0, 45.0)],
    )
    with pytest.raises(ValueError, match="by hand"):
        FemCase(problem, backend="mfem")


def test_a_missing_backend_reports_not_executed_rather_than_raising(tmp_path):
    spec = _spec()
    geo = spec.write(tmp_path / "mesh")
    case = FemCase(_problem(geo.with_suffix(".msh"), spec), backend="fenicsx")
    case.problem.as_dict()  # tags are present, so writing is allowed
    case.write(tmp_path / "case")
    outcome = case.run(tmp_path / "case")
    if not detect_backends()["fenicsx"]:
        assert outcome.status == "not_executed"
        assert "python case.py" in outcome.message


def test_reading_results_before_a_run_is_an_explicit_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="has not been run"):
        read_case_results(tmp_path)


def test_energy_balance_is_derived_when_the_solver_did_not_report_it(tmp_path):
    (tmp_path / "results.json").write_text(
        json.dumps(
            {
                "backend": "scikit-fem",
                "boundary_heat_flow_w": {"inner": 100.0, "outer": -95.0},
            }
        ),
        encoding="utf-8",
    )
    results = read_case_results(tmp_path)
    assert results.energy_balance_error_percent == pytest.approx(5.0)
    assert any("energy balance" in finding for finding in results.findings)


@pytest.mark.skipif(
    detect_gmsh() is None or not detect_backends()["scikit-fem"],
    reason="needs gmsh and scikit-fem",
)
def test_generated_case_reproduces_the_one_dimensional_heat_flow(tmp_path):
    from fem_coupling import (
        ConductionLayer,
        RadialConductionModel,
        custom_material,
    )

    spec = _spec()
    mesh_outcome = spec.generate(tmp_path / "mesh")
    assert mesh_outcome.meshed

    case = FemCase(_problem(mesh_outcome.mesh_path, spec), backend="scikit-fem")
    directory = tmp_path / "case"
    case.write(directory)
    outcome = case.run(directory)
    assert outcome.status == "completed", outcome.steps[0].stderr_tail

    results = read_case_results(directory)
    assert results.energy_balance_error_percent < 0.01

    steel = custom_material(
        "carbon-steel", conductivity_w_per_mk=50.0, conductivity_temp_coeff_w_per_mk2=0.0
    )
    insulation = custom_material(
        "polyurethane-insulation",
        conductivity_w_per_mk=0.17,
        conductivity_temp_coeff_w_per_mk2=0.0,
    )
    reference = RadialConductionModel(
        [
            ConductionLayer("steel", steel, 0.0127, 20),
            ConductionLayer("insulation", insulation, 0.05, 40),
        ],
        inner_radius_m=0.127,
    ).solve_steady(
        inner_film_coefficient_w_per_m2k=1000.0,
        inner_bulk_temperature_c=45.0,
        outer_film_coefficient_w_per_m2k=300.0,
        outer_bulk_temperature_c=4.0,
    )
    expected = reference.heat_flow_per_length_w_per_m * spec.total_length_m
    assert results.boundary_heat_flow_w["inner"] == pytest.approx(expected, rel=1e-3)
