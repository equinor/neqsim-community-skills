import pytest

from artificial_lift_screening import ArtificialLiftModel


def test_natural_flow_recommended():
    model = ArtificialLiftModel()
    result = model.evaluate(
        reservoir_pressure_bar=250.0,
        bottomhole_flowing_pressure_bar=200.0,
        productivity_index_sm3_d_bar=8.0,
        target_rate_sm3_d=300.0,
    )
    # natural rate = 8 * (250 - 200) = 400 >= 300 target
    assert result.natural_rate_sm3_d == pytest.approx(400.0, rel=1e-6)
    assert result.recommended_method == "natural-flow"
    assert result.required_pressure_reduction_bar == pytest.approx(0.0, abs=1e-9)


def test_gas_lift_recommended():
    model = ArtificialLiftModel()
    result = model.evaluate(
        reservoir_pressure_bar=250.0,
        bottomhole_flowing_pressure_bar=200.0,
        productivity_index_sm3_d_bar=8.0,
        target_rate_sm3_d=600.0,
        gas_lift_available=True,
        well_depth_m=2500.0,
    )
    # target 600 > natural 400, modest reduction achievable by gas lift
    assert result.gas_lift_feasible is True
    assert result.recommended_method == "gas-lift"


def test_esp_recommended_when_gas_lift_unavailable():
    model = ArtificialLiftModel()
    result = model.evaluate(
        reservoir_pressure_bar=250.0,
        bottomhole_flowing_pressure_bar=200.0,
        productivity_index_sm3_d_bar=8.0,
        target_rate_sm3_d=600.0,
        gas_lift_available=False,
        esp_max_head_m=3000.0,
    )
    assert result.gas_lift_feasible is False
    assert result.esp_feasible is True
    assert result.recommended_method == "esp"
    assert result.esp_required_head_m is not None


def test_infeasible_reservoir():
    model = ArtificialLiftModel()
    result = model.evaluate(
        reservoir_pressure_bar=100.0,
        bottomhole_flowing_pressure_bar=90.0,
        productivity_index_sm3_d_bar=2.0,
        target_rate_sm3_d=500.0,
    )
    # required_pwf = 100 - 500/2 = -150 <= 0 -> infeasible
    assert result.required_pwf_bar < 0.0
    assert result.recommended_method == "infeasible"


def test_assumptions_present():
    model = ArtificialLiftModel()
    result = model.evaluate(
        reservoir_pressure_bar=200.0,
        bottomhole_flowing_pressure_bar=150.0,
        productivity_index_sm3_d_bar=5.0,
        target_rate_sm3_d=200.0,
    )
    assert result.assumptions
    assert any("screening" in line.lower() for line in result.assumptions)


def test_invalid_water_cut_raises():
    model = ArtificialLiftModel()
    with pytest.raises(ValueError, match="water_cut"):
        model.evaluate(
            reservoir_pressure_bar=200.0,
            bottomhole_flowing_pressure_bar=150.0,
            productivity_index_sm3_d_bar=5.0,
            target_rate_sm3_d=200.0,
            water_cut=1.0,
        )
