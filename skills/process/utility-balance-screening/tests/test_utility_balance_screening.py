import pytest

from utility_balance_screening import UtilityBalanceModel


def test_instrument_air_demand_includes_margin():
    model = UtilityBalanceModel()
    result = model.evaluate(instrument_air_consumers=100, air_per_consumer_nm3_h=0.3)
    # 100 * 0.3 * 1.3 = 39.0
    assert result.instrument_air_demand_nm3_h == pytest.approx(39.0, rel=1e-6)


def test_cooling_water_flow_from_duty():
    model = UtilityBalanceModel()
    result = model.evaluate(
        instrument_air_consumers=0,
        cooling_duty_kw=2500.0,
        cooling_water_delta_t_c=10.0,
    )
    # 2500 * 3600 / (1000 * 4.18 * 10) ~= 215.31 m3/h
    assert result.cooling_water_flow_m3_h == pytest.approx(215.311, rel=1e-3)


def test_wobbe_index_and_band_check():
    model = UtilityBalanceModel()
    result = model.evaluate(
        instrument_air_consumers=10,
        fuel_gas_lhv_mj_sm3=39.0,
        fuel_gas_relative_density=0.62,
    )
    assert result.wobbe_index_mj_sm3 == pytest.approx(39.0 / (0.62 ** 0.5), rel=1e-3)
    assert result.wobbe_in_band is True
    assert result.wobbe_warning == "ok"


def test_wobbe_out_of_range_flag():
    model = UtilityBalanceModel()
    result = model.evaluate(
        instrument_air_consumers=10,
        fuel_gas_lhv_mj_sm3=30.0,
        fuel_gas_relative_density=0.62,
    )
    assert result.wobbe_in_band is False
    assert result.wobbe_warning == "wobbe-out-of-range"


def test_capacity_utilisation_and_undersized_warning():
    model = UtilityBalanceModel()
    result = model.evaluate(
        instrument_air_consumers=300,
        air_per_consumer_nm3_h=0.3,
        instrument_air_capacity_nm3_h=60.0,
    )
    # demand 300*0.3*1.3 = 117 > 60 capacity
    assert result.air_utilisation > 1.0
    assert result.utility_warning == "air-undersized"


def test_no_fuel_data_warning():
    model = UtilityBalanceModel()
    result = model.evaluate(instrument_air_consumers=10)
    assert result.wobbe_index_mj_sm3 is None
    assert result.wobbe_warning == "no-fuel-data"


def test_assumptions_present():
    model = UtilityBalanceModel()
    result = model.evaluate(instrument_air_consumers=5)
    assert result.assumptions
    assert any("screening" in line.lower() for line in result.assumptions)


def test_invalid_partial_fuel_data_raises():
    model = UtilityBalanceModel()
    with pytest.raises(ValueError, match="supplied together"):
        model.evaluate(
            instrument_air_consumers=10,
            fuel_gas_lhv_mj_sm3=39.0,
        )


def test_invalid_negative_consumers_raises():
    model = UtilityBalanceModel()
    with pytest.raises(ValueError, match="non-negative"):
        model.evaluate(instrument_air_consumers=-1)
