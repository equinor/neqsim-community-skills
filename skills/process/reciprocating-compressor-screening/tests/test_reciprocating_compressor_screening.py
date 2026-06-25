import pytest

from reciprocating_compressor_screening import ReciprocatingCompressorModel


def test_single_stage_ok() -> None:
    result = ReciprocatingCompressorModel().evaluate(
        suction_pressure=10.0,
        discharge_pressure=30.0,
        suction_temperature=313.15,
        swept_volume_rate_m3_h=500.0,
    )

    assert result.stages == 1
    assert 0.0 < result.volumetric_efficiency < 1.0
    assert result.actual_inlet_capacity_m3_h < 500.0
    assert result.discharge_temperature_k > 313.15
    assert result.capacity_warning in {"ok", "watch", "low-volumetric-efficiency"}
    assert result.assumptions


def test_high_ratio_triggers_staging() -> None:
    result = ReciprocatingCompressorModel().evaluate(
        suction_pressure=2.0,
        discharge_pressure=200.0,
        suction_temperature=313.15,
        swept_volume_rate_m3_h=800.0,
    )

    assert result.stages >= 3
    assert result.stage_pressure_ratio <= 4.0 + 1e-9


def test_rod_load_exceeded() -> None:
    result = ReciprocatingCompressorModel().evaluate(
        suction_pressure=10.0,
        discharge_pressure=40.0,
        suction_temperature=313.15,
        swept_volume_rate_m3_h=500.0,
        rated_rod_load_kn=50.0,
        piston_area_m2=0.05,
    )

    assert result.rod_load_ratio is not None
    assert result.rod_load_warning in {"ok", "watch", "rod-load-exceeded"}


def test_rejects_low_discharge_pressure() -> None:
    with pytest.raises(ValueError, match="discharge_pressure"):
        ReciprocatingCompressorModel().evaluate(
            suction_pressure=40.0,
            discharge_pressure=10.0,
            suction_temperature=313.15,
            swept_volume_rate_m3_h=500.0,
        )


def test_no_rating_returns_none_rod_load() -> None:
    result = ReciprocatingCompressorModel().evaluate(
        suction_pressure=10.0,
        discharge_pressure=30.0,
        suction_temperature=313.15,
        swept_volume_rate_m3_h=500.0,
    )

    assert result.rod_load_ratio is None
    assert result.rod_load_warning == "no-rating"
