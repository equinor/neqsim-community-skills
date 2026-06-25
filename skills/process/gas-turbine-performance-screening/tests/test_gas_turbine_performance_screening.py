import pytest

from gas_turbine_performance_screening import GasTurbinePerformanceModel


def test_iso_reference_has_unity_derate() -> None:
    result = GasTurbinePerformanceModel().evaluate(
        iso_base_power_kw=30000.0,
        iso_heat_rate_kj_kwh=9500.0,
        inlet_pressure_loss_mbar=0.0,
        exhaust_pressure_loss_mbar=0.0,
    )

    assert result.total_derate_factor == pytest.approx(1.0, abs=1e-6)
    assert result.site_power_kw == pytest.approx(30000.0, abs=1.0)
    assert result.power_warning == "no-rating"
    assert result.assumptions


def test_hot_high_site_derates_power() -> None:
    result = GasTurbinePerformanceModel().evaluate(
        iso_base_power_kw=30000.0,
        iso_heat_rate_kj_kwh=9500.0,
        ambient_temperature_k=313.15,
        site_elevation_m=1000.0,
    )

    assert result.ambient_derate_factor < 1.0
    assert result.altitude_derate_factor < 1.0
    assert result.site_power_kw < 30000.0
    assert result.site_heat_rate_kj_kwh > 9500.0
    assert result.fuel_heat_input_kw > 0.0


def test_insufficient_power_warning() -> None:
    result = GasTurbinePerformanceModel().evaluate(
        iso_base_power_kw=20000.0,
        iso_heat_rate_kj_kwh=9500.0,
        ambient_temperature_k=313.15,
        required_shaft_power_kw=22000.0,
    )

    assert result.power_margin_ratio is not None
    assert result.power_margin_ratio < 1.0
    assert result.power_warning == "insufficient-power"


def test_ok_power_margin_warning() -> None:
    result = GasTurbinePerformanceModel().evaluate(
        iso_base_power_kw=30000.0,
        iso_heat_rate_kj_kwh=9500.0,
        inlet_pressure_loss_mbar=0.0,
        exhaust_pressure_loss_mbar=0.0,
        required_shaft_power_kw=20000.0,
    )

    assert result.power_warning == "ok"
    assert result.thermal_efficiency == pytest.approx(3600.0 / 9500.0, abs=1e-3)


def test_rejects_non_positive_base_power() -> None:
    with pytest.raises(ValueError, match="iso_base_power_kw"):
        GasTurbinePerformanceModel().evaluate(
            iso_base_power_kw=0.0,
            iso_heat_rate_kj_kwh=9500.0,
        )
