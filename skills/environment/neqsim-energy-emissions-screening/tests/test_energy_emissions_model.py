import pytest

from energy_emissions_screening import EnergyEmissionsModel


def _base(**overrides):
    kwargs = dict(
        annual_energy_use_mwh=[120000.0, 180000.0, 175000.0, 150000.0, 120000.0],
        emission_factor_kg_co2e_per_mwh=450.0,
        annual_production_boe=[3.0e6, 7.0e6, 6.5e6, 5.0e6, 3.5e6],
        co2_tax_usd_per_tonne=0.0,
    )
    kwargs.update(overrides)
    return EnergyEmissionsModel().evaluate(**kwargs)


def test_annual_co2e_matches_factor() -> None:
    # 100000 MWh * 500 kg/MWh / 1000 = 50000 tonnes.
    result = EnergyEmissionsModel().evaluate(
        annual_energy_use_mwh=[100000.0],
        emission_factor_kg_co2e_per_mwh=500.0,
    )
    assert result.annual_co2e_tonnes[0] == pytest.approx(50000.0)
    assert result.total_co2e_tonnes == pytest.approx(50000.0)


def test_carbon_intensity_definition() -> None:
    result = EnergyEmissionsModel().evaluate(
        annual_energy_use_mwh=[100000.0],
        emission_factor_kg_co2e_per_mwh=500.0,
        annual_production_boe=[1.0e6],
    )
    # 50000 tonnes -> 50,000,000 kg / 1,000,000 boe = 50 kg/boe.
    assert result.carbon_intensity_kg_per_boe == pytest.approx(50.0)


def test_carbon_intensity_none_without_production() -> None:
    result = EnergyEmissionsModel().evaluate(
        annual_energy_use_mwh=[100000.0],
        annual_production_boe=0.0,
    )
    assert result.carbon_intensity_kg_per_boe is None
    assert result.intensity_warning == "no-production"


def test_co2_tax_cost_in_musd() -> None:
    result = EnergyEmissionsModel().evaluate(
        annual_energy_use_mwh=[100000.0],
        emission_factor_kg_co2e_per_mwh=500.0,
        co2_tax_usd_per_tonne=100.0,
    )
    # 50000 tonnes * 100 USD/tonne = 5,000,000 USD = 5 MUSD.
    assert result.total_emission_cost_musd == pytest.approx(5.0)


def test_intensity_warning_high() -> None:
    model = EnergyEmissionsModel(watch_intensity_kg_per_boe=10.0)
    result = model.evaluate(
        annual_energy_use_mwh=[100000.0],
        emission_factor_kg_co2e_per_mwh=500.0,
        annual_production_boe=[1.0e6],
    )
    assert result.intensity_warning == "high"


def test_intensity_warning_ok_for_low_intensity() -> None:
    model = EnergyEmissionsModel(watch_intensity_kg_per_boe=100.0)
    result = model.evaluate(
        annual_energy_use_mwh=[100000.0],
        emission_factor_kg_co2e_per_mwh=500.0,
        annual_production_boe=[1.0e9],
    )
    assert result.intensity_warning == "ok"


def test_totals_sum_years() -> None:
    result = _base()
    assert result.total_energy_use_mwh == pytest.approx(745000.0)
    assert result.total_production_boe == pytest.approx(25.0e6)


def test_production_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        _base(annual_production_boe=[1.0e6, 2.0e6])


def test_empty_energy_raises() -> None:
    with pytest.raises(ValueError):
        _base(annual_energy_use_mwh=[])


def test_negative_factor_raises() -> None:
    with pytest.raises(ValueError):
        _base(emission_factor_kg_co2e_per_mwh=-1.0)
