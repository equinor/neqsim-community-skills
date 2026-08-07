import pytest

from fem_coupling import (
    FemMeshSpec,
    MeshLayer,
    MeshSegment,
    detect_pyvista,
    render_field,
    render_mesh,
)


def _spec(**overrides):
    defaults = dict(
        kind="axisymmetric_section",
        inner_radius_m=0.01752,
        layers=[
            MeshLayer("steel", "carbon-steel", 0.00356, 4),
            MeshLayer("insulation", "mineral-wool", 0.05, 8),
        ],
        segments=[MeshSegment("run", 0.5, 20)],
        name="tube",
    )
    defaults.update(overrides)
    return FemMeshSpec(**defaults)


def test_a_plain_section_is_two_dimensional():
    spec = _spec()
    assert not spec.is_three_dimensional
    assert spec.dimension == 2
    assert spec.boundary_names() == ("inner", "outer", "west", "east")


def test_revolving_makes_it_three_dimensional_and_adds_symmetry_planes():
    spec = _spec(revolve_deg=30.0, circumferential_cells=6)
    assert spec.is_three_dimensional
    assert spec.dimension == 3
    assert spec.element_count == 20 * 12 * 6
    assert spec.boundary_names() == (
        "inner",
        "outer",
        "west",
        "east",
        "symmetry_start",
        "symmetry_end",
    )
    assert spec.boundary_ids()["symmetry_end"] == 106


def test_a_full_revolve_has_no_cut_planes():
    spec = _spec(revolve_deg=360.0, circumferential_cells=24)
    assert spec.boundary_names() == ("inner", "outer", "west", "east")


def test_the_swept_script_declares_volumes_and_lateral_faces():
    script = _spec(revolve_deg=90.0, circumferential_cells=8).geo_script()
    assert "Extrude { {1, 0, 0}, {0, 0, 0}" in script
    assert 'Physical Volume("carbon-steel", 1)' in script
    assert 'Physical Volume("mineral-wool", 2)' in script
    # Lateral faces are addressed by their position in the sweep return, which is
    # the curve-loop order (inner, east, outer, west).
    assert "sweep_0_0[2]" in script
    assert "sweep_0_1[4]" in script
    assert 'Physical Surface("symmetry_end", 106)' in script


def test_an_extruded_section_sweeps_out_of_plane():
    spec = FemMeshSpec(
        kind="plane_section",
        layers=[MeshLayer("plate", "carbon-steel", 0.02, 8)],
        segments=[MeshSegment("run", 0.5, 20)],
        extrude_m=0.3,
        circumferential_cells=10,
    )
    assert spec.dimension == 3
    assert "Extrude {0, 0, 0.3}" in spec.geo_script()


def test_a_section_cannot_be_both_revolved_and_extruded():
    with pytest.raises(ValueError, match="not both"):
        _spec(revolve_deg=90.0, extrude_m=0.3)


def test_only_an_axisymmetric_section_can_be_revolved():
    with pytest.raises(ValueError, match="only applies to an axisymmetric_section"):
        FemMeshSpec(
            kind="block",
            layers=[MeshLayer("rock", "sandstone", 1.0, 8)],
            segments=[MeshSegment("run", 2.0, 20)],
            revolve_deg=90.0,
        )


def test_a_revolve_angle_must_be_a_real_angle():
    with pytest.raises(ValueError, match="revolve_deg"):
        _spec(revolve_deg=0.0)
    with pytest.raises(ValueError, match="revolve_deg"):
        _spec(revolve_deg=400.0)


def test_rendering_without_a_field_file_is_reported_not_executed(tmp_path):
    outcome = render_field(tmp_path)
    assert outcome.status == "not_executed"
    assert "has not been run" in outcome.message or "no field file" in outcome.message
    assert outcome.images == ()


def test_rendering_a_missing_mesh_is_reported_not_executed(tmp_path):
    outcome = render_mesh(tmp_path / "mesh.msh")
    assert outcome.status == "not_executed"
    assert "does not exist" in outcome.message


@pytest.mark.skipif(not detect_pyvista(), reason="needs pyvista")
def test_an_unreadable_field_file_fails_rather_than_raising(tmp_path):
    (tmp_path / "field.vtu").write_text("not a vtu", encoding="utf-8")
    outcome = render_field(tmp_path)
    assert outcome.status == "failed"
    assert outcome.images == ()


def test_a_bad_view_or_camera_is_rejected_before_any_file_is_read(tmp_path):
    with pytest.raises(ValueError, match="view must be one of"):
        render_field(tmp_path, views=["hologram"])
    with pytest.raises(ValueError, match="camera must be one of"):
        render_field(tmp_path, camera="overhead")
    with pytest.raises(ValueError, match="scale must be three positive factors"):
        render_field(tmp_path, scale=(1.0, 0.0, 1.0))
