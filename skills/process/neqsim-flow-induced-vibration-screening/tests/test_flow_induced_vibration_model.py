import pytest

from flow_induced_vibration_screening import FlowInducedVibrationModel


def test_fiv_model_returns_ok_below_threshold() -> None:
    result = FlowInducedVibrationModel().evaluate(
        fluid_velocity=8.0,
        mixture_density=60.0,
        kinetic_energy_threshold=10000.0,
    )

    assert result.fiv_warning == "ok"
    assert result.likelihood_of_failure_band == "low"
    assert result.kinetic_energy_pa == pytest.approx(60.0 * 8.0 * 8.0, rel=1e-6)
    assert result.assumptions


def test_fiv_model_flags_high_above_threshold() -> None:
    result = FlowInducedVibrationModel().evaluate(
        fluid_velocity=20.0,
        mixture_density=60.0,
        kinetic_energy_threshold=10000.0,
    )

    assert result.fiv_warning == "high"
    assert result.likelihood_of_failure_band == "high"
    assert result.threshold_ratio > 1.0


def test_fiv_model_small_bore_lowers_threshold() -> None:
    base = FlowInducedVibrationModel().evaluate(
        fluid_velocity=11.0,
        mixture_density=60.0,
        kinetic_energy_threshold=10000.0,
        small_bore_present=False,
    )
    small_bore = FlowInducedVibrationModel().evaluate(
        fluid_velocity=11.0,
        mixture_density=60.0,
        kinetic_energy_threshold=10000.0,
        small_bore_present=True,
    )

    assert small_bore.threshold_ratio > base.threshold_ratio
    assert small_bore.small_bore_flag is True


def test_fiv_model_rejects_negative_velocity() -> None:
    with pytest.raises(ValueError, match="fluid_velocity"):
        FlowInducedVibrationModel().evaluate(
            fluid_velocity=-8.0,
            mixture_density=60.0,
        )
