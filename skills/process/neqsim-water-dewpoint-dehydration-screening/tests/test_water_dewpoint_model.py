import pytest

from water_dewpoint_dehydration_screening import WaterDewpointModel


def test_water_dewpoint_model_dehydration_required_when_warm_and_low_pressure() -> None:
    result = WaterDewpointModel().evaluate(
        pressure=20.0,
        temperature=313.15,
    )

    assert result.dehydration_required is True
    assert result.dehydration_warning == "dehydration-required"
    assert result.saturated_water_content_lb_mmscf > result.water_spec_lb_mmscf
    assert result.assumptions


def test_water_dewpoint_model_in_spec_when_cold_and_high_pressure() -> None:
    result = WaterDewpointModel().evaluate(
        pressure=120.0,
        temperature=275.15,
    )

    assert result.dehydration_required is False
    assert result.dehydration_warning in {"ok", "watch"}
    assert result.spec_ratio <= 1.0


def test_water_dewpoint_model_rejects_negative_pressure() -> None:
    with pytest.raises(ValueError, match="pressure"):
        WaterDewpointModel().evaluate(
            pressure=-20.0,
            temperature=305.15,
        )
