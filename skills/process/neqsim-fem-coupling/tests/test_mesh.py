import pytest

from fem_coupling import FemMeshSpec, MeshLayer, MeshSegment, detect_gmsh


def _spec(**overrides):
    defaults = dict(
        kind="axisymmetric_section",
        inner_radius_m=0.127,
        layers=[
            MeshLayer("steel", "carbon-steel", 0.0127, 6),
            MeshLayer("insulation", "polyurethane-insulation", 0.05, 16),
        ],
        segments=[
            MeshSegment("upstream", 0.8, 16),
            MeshSegment("defect", 0.4, 10, {"insulation": "seawater-flooded"}),
            MeshSegment("downstream", 0.8, 16),
        ],
        name="20-P-001",
    )
    defaults.update(overrides)
    return FemMeshSpec(**defaults)


def test_stations_stack_layers_and_segments():
    spec = _spec()
    assert spec.axial_stations_m == (0.0, 0.8, pytest.approx(1.2), pytest.approx(2.0))
    assert spec.radial_stations_m[0] == pytest.approx(0.127)
    assert spec.radial_stations_m[-1] == pytest.approx(0.127 + 0.0127 + 0.05)
    assert spec.element_count == (16 + 10 + 16) * (6 + 16)


def test_a_segment_override_creates_a_separate_material_group():
    spec = _spec()
    assert "seawater-flooded" in spec.materials()
    script = spec.geo_script()
    assert 'Physical Surface("seawater-flooded", 3)' in script
    assert 'Physical Surface("carbon-steel", 1)' in script


def test_boundary_groups_are_named_and_tagged_deterministically():
    spec = _spec()
    assert spec.boundary_names() == ("inner", "outer", "west", "east")
    assert spec.boundary_ids() == {"inner": 101, "outer": 102, "west": 103, "east": 104}
    script = spec.geo_script()
    for name, tag in spec.boundary_ids().items():
        assert f'Physical Curve("{name}", {tag})' in script


def test_every_layer_interface_lands_on_an_element_boundary():
    spec = _spec()
    script = spec.geo_script()
    interface = spec.radial_stations_m[1]
    assert f"{interface:.10g}" in script


def test_a_thin_layer_with_too_few_linear_elements_is_flagged():
    spec = _spec(
        layers=[
            MeshLayer("steel", "carbon-steel", 0.0127, 1),
            MeshLayer("insulation", "polyurethane-insulation", 0.05, 16),
        ]
    )
    warnings = spec.mesh_warnings()
    assert any("steel" in warning for warning in warnings)


def test_quadratic_elements_relax_the_element_count_requirement():
    spec = _spec(
        element_order=2,
        layers=[
            MeshLayer("steel", "carbon-steel", 0.0127, 2),
            MeshLayer("insulation", "polyurethane-insulation", 0.05, 16),
        ],
    )
    assert not any("steel" in warning for warning in spec.mesh_warnings())


def test_an_element_size_target_from_the_physics_is_enforced():
    spec = _spec()
    warnings = spec.mesh_warnings(max_element_size_m=0.0005)
    assert any("penetration depth" in warning for warning in warnings)


def test_a_stretched_grid_is_reported():
    spec = _spec(segments=[MeshSegment("run", 20.0, 4)])
    assert spec.max_aspect_ratio() > 20.0
    assert any("aspect ratio" in warning for warning in spec.mesh_warnings())


def test_overriding_an_unknown_layer_is_rejected():
    with pytest.raises(ValueError, match="overrides unknown layer"):
        _spec(segments=[MeshSegment("run", 1.0, 10, {"coating": "concrete"})])


def test_an_axisymmetric_mesh_needs_an_inner_radius():
    with pytest.raises(ValueError, match="inner_radius_m"):
        FemMeshSpec(
            kind="axisymmetric_section",
            layers=[MeshLayer("steel", "carbon-steel", 0.01, 4)],
            segments=[MeshSegment("run", 1.0, 10)],
        )


def test_the_geometry_is_written_even_without_gmsh(tmp_path):
    spec = _spec()
    outcome = spec.generate(tmp_path)
    assert outcome.geo_path.exists()
    assert outcome.status in {"completed", "not_executed", "failed"}
    assert "gmsh" in outcome.command
    if detect_gmsh() is None:
        assert outcome.status == "not_executed"
        assert outcome.mesh_path is None
    elif outcome.status == "completed":
        assert outcome.meshed
        assert outcome.mesh_path.exists()
