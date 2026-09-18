import pytest

from acoustic_induced_vibration_screening import AcousticInducedVibrationModel


def test_computes_sound_power_level() -> None:
    result = AcousticInducedVibrationModel().evaluate(
        mass_flow_kg_s=12.0,
        upstream_pressure_bar=90.0,
        downstream_pressure_bar=20.0,
        pipe_outside_diameter_mm=323.9,
        wall_thickness_mm=9.5,
    )

    assert result.sound_power_level_db > 0.0
    assert 0.0 < result.pressure_drop_ratio < 1.0
    assert result.diameter_thickness_ratio == pytest.approx(323.9 / 9.5, abs=1e-2)
    assert result.likelihood_of_failure >= 0.0
    assert result.risk_warning in {"low-risk", "medium-risk", "high-risk"}
    assert result.assumptions


def test_supplied_sound_power_level_is_used() -> None:
    result = AcousticInducedVibrationModel().evaluate(
        mass_flow_kg_s=12.0,
        upstream_pressure_bar=90.0,
        downstream_pressure_bar=20.0,
        pipe_outside_diameter_mm=323.9,
        wall_thickness_mm=9.5,
        sound_power_level_db=155.0,
    )

    assert result.sound_power_level_db == 155.0


def test_thin_wall_increases_likelihood() -> None:
    thick = AcousticInducedVibrationModel().evaluate(
        mass_flow_kg_s=15.0,
        upstream_pressure_bar=100.0,
        downstream_pressure_bar=15.0,
        pipe_outside_diameter_mm=323.9,
        wall_thickness_mm=12.7,
    )
    thin = AcousticInducedVibrationModel().evaluate(
        mass_flow_kg_s=15.0,
        upstream_pressure_bar=100.0,
        downstream_pressure_bar=15.0,
        pipe_outside_diameter_mm=323.9,
        wall_thickness_mm=4.0,
    )

    assert thin.diameter_thickness_ratio > thick.diameter_thickness_ratio
    assert thin.likelihood_of_failure > thick.likelihood_of_failure


def test_high_energy_case_flags_high_risk() -> None:
    result = AcousticInducedVibrationModel().evaluate(
        mass_flow_kg_s=60.0,
        upstream_pressure_bar=150.0,
        downstream_pressure_bar=5.0,
        pipe_outside_diameter_mm=508.0,
        wall_thickness_mm=4.0,
    )

    assert result.likelihood_of_failure > 1.0
    assert result.risk_warning == "high-risk"


def test_rejects_non_decreasing_pressure() -> None:
    with pytest.raises(ValueError, match="downstream_pressure_bar"):
        AcousticInducedVibrationModel().evaluate(
            mass_flow_kg_s=12.0,
            upstream_pressure_bar=20.0,
            downstream_pressure_bar=90.0,
            pipe_outside_diameter_mm=323.9,
            wall_thickness_mm=9.5,
        )


def test_rejects_thin_pipe_geometry() -> None:
    with pytest.raises(ValueError, match="pipe_outside_diameter_mm"):
        AcousticInducedVibrationModel().evaluate(
            mass_flow_kg_s=12.0,
            upstream_pressure_bar=90.0,
            downstream_pressure_bar=20.0,
            pipe_outside_diameter_mm=10.0,
            wall_thickness_mm=9.5,
        )
