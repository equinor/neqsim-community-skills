import pytest

from two_phase_flow_regime_screening import TwoPhaseRegimeModel


def test_stratified_at_low_velocities():
    model = TwoPhaseRegimeModel()
    result = model.evaluate(
        superficial_gas_velocity=0.3,
        superficial_liquid_velocity=0.05,
    )
    assert result.flow_regime == "stratified-smooth"
    assert result.slug_risk is False
    assert result.regime_warning == "ok"


def test_slug_regime_flagged():
    model = TwoPhaseRegimeModel()
    result = model.evaluate(
        superficial_gas_velocity=3.0,
        superficial_liquid_velocity=0.5,
    )
    assert result.flow_regime == "slug"
    assert result.slug_risk is True
    assert result.regime_warning == "slug-risk"


def test_annular_at_high_gas_velocity():
    model = TwoPhaseRegimeModel()
    result = model.evaluate(
        superficial_gas_velocity=15.0,
        superficial_liquid_velocity=0.2,
    )
    assert result.flow_regime == "annular-mist"


def test_velocities_from_flows():
    model = TwoPhaseRegimeModel()
    result = model.evaluate(
        pipe_inner_diameter=0.2,
        gas_mass_flow=2.0,
        liquid_mass_flow=10.0,
        gas_density=40.0,
        liquid_density=800.0,
    )
    assert result.superficial_gas_velocity_m_s > 0.0
    assert result.superficial_liquid_velocity_m_s > 0.0
    assert result.flow_regime in {
        "stratified-smooth",
        "stratified-wavy",
        "elongated-bubble",
        "slug",
        "dispersed-bubble",
        "annular-mist",
    }


def test_missing_inputs_rejected():
    model = TwoPhaseRegimeModel()
    with pytest.raises(ValueError, match="provide either"):
        model.evaluate(superficial_gas_velocity=3.0)


def test_negative_velocity_rejected():
    model = TwoPhaseRegimeModel()
    with pytest.raises(ValueError, match="superficial_gas_velocity"):
        model.evaluate(
            superficial_gas_velocity=-1.0,
            superficial_liquid_velocity=0.1,
        )
