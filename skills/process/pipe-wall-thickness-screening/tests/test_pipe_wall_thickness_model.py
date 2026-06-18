import pytest

from pipe_wall_thickness_screening import PipeWallThicknessModel


def test_wall_thickness_model_ok_with_adequate_nominal() -> None:
    result = PipeWallThicknessModel().evaluate(
        design_pressure=50.0,
        outer_diameter=323.9,
        allowable_stress=138.0,
        nominal_thickness=12.7,
    )

    assert result.wall_thickness_warning == "ok"
    assert result.required_thickness_mm > result.pressure_design_thickness_mm
    assert result.thickness_margin_ratio >= 1.1
    assert result.assumptions


def test_wall_thickness_model_inadequate_when_thin() -> None:
    result = PipeWallThicknessModel().evaluate(
        design_pressure=250.0,
        outer_diameter=323.9,
        allowable_stress=138.0,
        nominal_thickness=4.0,
    )

    assert result.wall_thickness_warning == "inadequate"
    assert result.thickness_margin_ratio < 1.0


def test_wall_thickness_model_design_thickness_matches_formula() -> None:
    result = PipeWallThicknessModel().evaluate(
        design_pressure=100.0,
        outer_diameter=300.0,
        allowable_stress=138.0,
        weld_joint_factor=1.0,
        coefficient_y=0.4,
        corrosion_allowance=0.0,
        nominal_thickness=10.0,
    )

    p = 100.0 * 0.1
    expected = p * 300.0 / (2.0 * (138.0 * 1.0 + p * 0.4))
    assert result.pressure_design_thickness_mm == pytest.approx(expected, rel=1e-4)


def test_wall_thickness_model_rejects_negative_pressure() -> None:
    with pytest.raises(ValueError, match="design_pressure"):
        PipeWallThicknessModel().evaluate(
            design_pressure=-100.0,
            outer_diameter=323.9,
            allowable_stress=138.0,
            nominal_thickness=12.7,
        )
