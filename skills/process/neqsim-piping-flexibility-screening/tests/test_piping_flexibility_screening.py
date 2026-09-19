import pytest

from piping_flexibility_screening import PipingFlexibilityModel


def test_low_stress_ok() -> None:
    result = PipingFlexibilityModel().evaluate(
        outside_diameter_mm=168.3,
        wall_thickness_mm=7.11,
        design_pressure_bar=20.0,
        design_temperature_c=60.0,
        pipe_length_m=20.0,
    )

    assert result.hoop_stress_mpa > 0.0
    assert result.hoop_stress_ratio < 1.0
    assert result.free_thermal_expansion_mm > 0.0
    assert result.stress_warning in {"ok", "watch"}
    assert result.flange_warning == "no-rating"
    assert result.assumptions


def test_high_pressure_hoop_exceeded() -> None:
    result = PipingFlexibilityModel().evaluate(
        outside_diameter_mm=323.9,
        wall_thickness_mm=6.35,
        design_pressure_bar=120.0,
        design_temperature_c=60.0,
        pipe_length_m=20.0,
    )

    assert result.hoop_stress_ratio > 1.0
    assert result.stress_warning == "hoop-stress-exceeded"


def test_restrained_hot_run_expansion_exceeded() -> None:
    result = PipingFlexibilityModel().evaluate(
        outside_diameter_mm=168.3,
        wall_thickness_mm=10.97,
        design_pressure_bar=10.0,
        design_temperature_c=400.0,
        pipe_length_m=30.0,
        anchor_to_anchor=True,
    )

    assert result.delta_temperature_k == pytest.approx(380.0, abs=1e-6)
    assert result.displacement_stress_ratio > 1.0
    assert result.stress_warning in {"expansion-stress-exceeded", "hoop-stress-exceeded"}


def test_routing_relief_lowers_displacement_stress() -> None:
    inputs = dict(
        outside_diameter_mm=168.3,
        wall_thickness_mm=10.97,
        design_pressure_bar=10.0,
        design_temperature_c=400.0,
        pipe_length_m=30.0,
    )
    restrained = PipingFlexibilityModel().evaluate(anchor_to_anchor=True, **inputs)
    routed = PipingFlexibilityModel().evaluate(anchor_to_anchor=False, **inputs)

    assert routed.displacement_stress_mpa < restrained.displacement_stress_mpa


def test_flange_overpressure_warning() -> None:
    result = PipingFlexibilityModel().evaluate(
        outside_diameter_mm=168.3,
        wall_thickness_mm=7.11,
        design_pressure_bar=60.0,
        design_temperature_c=60.0,
        pipe_length_m=20.0,
        flange_rating_class=300,
        flange_allowable_pressure_bar=49.6,
    )

    assert result.flange_pressure_ratio is not None
    assert result.flange_pressure_ratio > 1.0
    assert result.flange_warning == "flange-overpressure"


def test_rejects_thick_wall() -> None:
    with pytest.raises(ValueError, match="wall_thickness_mm"):
        PipingFlexibilityModel().evaluate(
            outside_diameter_mm=100.0,
            wall_thickness_mm=60.0,
            design_pressure_bar=20.0,
            design_temperature_c=60.0,
            pipe_length_m=20.0,
        )
