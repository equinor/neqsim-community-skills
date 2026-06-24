import pytest

from capex_opex_screening import CapexOpexModel


def _base(**overrides):
    kwargs = dict(
        bare_equipment_cost_musd=120.0,
        installation_factor=3.5,
        contingency_fraction=0.2,
        opex_fraction_of_capex_per_year=0.04,
        project_life_years=20,
    )
    kwargs.update(overrides)
    return CapexOpexModel().evaluate(**kwargs)


def test_installed_capex_uses_installation_factor() -> None:
    result = _base(installation_factor=3.0, contingency_fraction=0.0)
    assert result.installed_capex_musd == pytest.approx(360.0)
    assert result.total_capex_musd == pytest.approx(360.0)


def test_contingency_is_applied_on_top_of_installed() -> None:
    result = _base(installation_factor=3.0, contingency_fraction=0.25)
    assert result.total_capex_musd == pytest.approx(360.0 * 1.25)


def test_annual_opex_is_fraction_of_total_capex() -> None:
    result = _base(
        installation_factor=3.0,
        contingency_fraction=0.0,
        opex_fraction_of_capex_per_year=0.05,
    )
    assert result.annual_opex_musd == pytest.approx(360.0 * 0.05)


def test_energy_cost_term_converts_to_musd() -> None:
    # 100000 MWh/yr * 50 USD/MWh = 5,000,000 USD/yr = 5 MUSD/yr.
    result = _base(annual_energy_use_mwh=100000.0, energy_price_usd_per_mwh=50.0)
    assert result.annual_energy_cost_musd == pytest.approx(5.0)
    assert result.total_annual_opex_musd == pytest.approx(
        result.annual_opex_musd + 5.0
    )


def test_total_cost_of_ownership_is_capex_plus_lifecycle_opex() -> None:
    result = _base()
    expected = result.total_capex_musd + result.total_annual_opex_musd * 20
    assert result.lifecycle_opex_musd == pytest.approx(
        result.total_annual_opex_musd * 20
    )
    assert result.total_cost_of_ownership_musd == pytest.approx(expected)


def test_capex_warning_flags_high() -> None:
    model = CapexOpexModel(watch_capex_musd=100.0)
    result = model.evaluate(
        bare_equipment_cost_musd=120.0,
        installation_factor=3.5,
        contingency_fraction=0.2,
    )
    assert result.capex_warning == "high"


def test_capex_warning_flags_ok_for_small_project() -> None:
    model = CapexOpexModel(watch_capex_musd=10000.0)
    result = model.evaluate(bare_equipment_cost_musd=10.0)
    assert result.capex_warning == "ok"


def test_installation_factor_below_one_raises() -> None:
    with pytest.raises(ValueError):
        _base(installation_factor=0.5)


def test_negative_equipment_cost_raises() -> None:
    with pytest.raises(ValueError):
        _base(bare_equipment_cost_musd=-1.0)


def test_contingency_above_one_raises() -> None:
    with pytest.raises(ValueError):
        _base(contingency_fraction=1.5)
