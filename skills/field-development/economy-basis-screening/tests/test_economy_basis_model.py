import pytest

from economy_basis_screening import EconomyBasisModel, EconomyBasisResult


def test_typical_basis_is_ok():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.08,
        tax_regime="norwegian-ncs",
    )
    assert isinstance(result, EconomyBasisResult)
    assert result.discount_rate_flag == "ok"
    assert result.tax_regime_recognized is True
    assert result.basis_warning == "ok"
    assert result.flags == ()


def test_low_discount_rate_flagged():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.03,
    )
    assert result.discount_rate_flag == "low"
    assert result.basis_warning == "watch"
    assert any("discount_rate" in f for f in result.flags)


def test_high_discount_rate_flagged():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.20,
    )
    assert result.discount_rate_flag == "high"
    assert result.basis_warning == "watch"


def test_unknown_tax_regime_flagged():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.08,
        tax_regime="atlantis",
    )
    assert result.tax_regime_recognized is False
    assert result.basis_warning == "watch"
    assert any("tax_regime" in f for f in result.flags)


def test_zero_revenue_flagged():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.0,
        oil_price_per_bbl=0.0,
        discount_rate=0.08,
    )
    assert any("no revenue basis" in f for f in result.flags)


def test_nominal_terms_zero_inflation_flagged():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.08,
        real_terms=False,
        inflation_rate=0.0,
    )
    assert any("nominal terms" in f for f in result.flags)


def test_currency_normalized():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=2.5,
        oil_price_per_bbl=600.0,
        discount_rate=0.08,
        currency="nok",
    )
    assert result.currency == "NOK"


def test_neqsim_flag_is_boolean():
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.08,
    )
    assert isinstance(result.neqsim_available, bool)
    assert len(result.assumptions) >= 5


def test_invalid_discount_rate_rejected():
    model = EconomyBasisModel()
    with pytest.raises(ValueError):
        model.evaluate(
            gas_price_per_sm3=0.30,
            oil_price_per_bbl=70.0,
            discount_rate=1.5,
        )


def test_negative_price_rejected():
    model = EconomyBasisModel()
    with pytest.raises(ValueError):
        model.evaluate(
            gas_price_per_sm3=-0.1,
            oil_price_per_bbl=70.0,
            discount_rate=0.08,
        )


def test_invalid_typical_range_rejected():
    with pytest.raises(ValueError):
        EconomyBasisModel(typical_discount_range=(0.5, 0.2))
