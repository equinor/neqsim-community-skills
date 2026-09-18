import pytest

from asset_value_npv_screening import AssetValueModel


def _base(**overrides):
    kwargs = dict(
        annual_revenue_musd=[0.0, 300.0, 320.0, 280.0, 230.0, 180.0],
        annual_opex_musd=40.0,
        capex_schedule_musd=[600.0, 200.0, 0.0, 0.0, 0.0, 0.0],
        discount_rate_fraction=0.08,
        tax_rate_fraction=0.0,
    )
    kwargs.update(overrides)
    return AssetValueModel().evaluate(**kwargs)


def test_net_cash_flow_matches_definition() -> None:
    result = _base(tax_rate_fraction=0.0)
    # Year 1 (index 0): 0 revenue - 40 opex - 0 tax - 600 capex = -640.
    assert result.net_cash_flow_musd[0] == pytest.approx(-640.0)
    # Year 2 (index 1): 300 - 40 - 200 = 60.
    assert result.net_cash_flow_musd[1] == pytest.approx(60.0)


def test_flat_capex_goes_to_year_zero() -> None:
    result = _base(capex_schedule_musd=800.0)
    assert result.total_capex_musd == pytest.approx(800.0)
    assert result.net_cash_flow_musd[0] == pytest.approx(0.0 - 40.0 - 800.0)


def test_higher_discount_rate_lowers_npv() -> None:
    low = _base(discount_rate_fraction=0.05).npv_musd
    high = _base(discount_rate_fraction=0.15).npv_musd
    assert high < low


def test_tax_reduces_npv() -> None:
    no_tax = _base(tax_rate_fraction=0.0).npv_musd
    taxed = _base(tax_rate_fraction=0.5).npv_musd
    assert taxed < no_tax


def test_value_warning_ok_for_positive_npv() -> None:
    result = _base()
    assert result.value_warning == "ok"
    assert result.npv_musd > 0.0


def test_value_warning_high_for_negative_npv() -> None:
    result = _base(annual_revenue_musd=[0.0, 50.0, 40.0, 30.0, 20.0, 10.0])
    assert result.value_warning == "high"
    assert result.npv_musd < 0.0


def test_irr_is_identified_for_conventional_profile() -> None:
    result = _base()
    assert result.irr_fraction is not None
    assert result.irr_fraction > 0.0


def test_payback_year_is_reported() -> None:
    result = _base()
    assert result.payback_year is not None
    assert 1 <= result.payback_year <= result.years


def test_opex_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        _base(annual_opex_musd=[40.0, 40.0])


def test_empty_revenue_raises() -> None:
    with pytest.raises(ValueError):
        _base(annual_revenue_musd=[])


def test_discount_rate_above_one_raises() -> None:
    with pytest.raises(ValueError):
        _base(discount_rate_fraction=1.5)
