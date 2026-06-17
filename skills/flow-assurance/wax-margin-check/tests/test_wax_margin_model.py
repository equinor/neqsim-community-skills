import pytest

from wax_margin_check import WaxMarginModel


def test_wax_margin_model_returns_ok_with_adequate_margin() -> None:
    result = WaxMarginModel().evaluate(
        operating_temperature=40.0,
        wax_appearance_temperature=30.0,
    )

    assert result.margin_warning == "ok"
    assert result.wax_margin_c == pytest.approx(10.0, abs=1e-6)
    assert result.below_wax_appearance is False
    assert result.assumptions


def test_wax_margin_model_flags_watch_near_wat() -> None:
    result = WaxMarginModel().evaluate(
        operating_temperature=33.0,
        wax_appearance_temperature=30.0,
    )

    assert result.margin_warning == "watch"
    assert 0.0 < result.wax_margin_c < 5.0
    assert result.below_wax_appearance is False


def test_wax_margin_model_flags_high_below_wat() -> None:
    result = WaxMarginModel().evaluate(
        operating_temperature=25.0,
        wax_appearance_temperature=30.0,
    )

    assert result.margin_warning == "high"
    assert result.wax_margin_c < 0.0
    assert result.below_wax_appearance is True


def test_wax_margin_model_rejects_non_positive_min_margin() -> None:
    with pytest.raises(ValueError, match="min_margin"):
        WaxMarginModel(min_margin=-5.0)
