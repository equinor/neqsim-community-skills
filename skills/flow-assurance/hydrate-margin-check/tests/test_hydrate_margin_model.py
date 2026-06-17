import pytest

from hydrate_margin_check import HydrateMarginModel


def test_hydrate_margin_model_returns_ok_with_adequate_margin() -> None:
    result = HydrateMarginModel().evaluate(
        operating_temperature=15.0,
        hydrate_equilibrium_temperature=8.0,
    )

    assert result.margin_warning == "ok"
    assert result.hydrate_margin_c == pytest.approx(7.0, abs=1e-6)
    assert result.subcooling_c == pytest.approx(0.0, abs=1e-6)
    assert result.assumptions


def test_hydrate_margin_model_flags_watch_near_boundary() -> None:
    result = HydrateMarginModel().evaluate(
        operating_temperature=10.0,
        hydrate_equilibrium_temperature=8.0,
    )

    assert result.margin_warning == "watch"
    assert 0.0 < result.hydrate_margin_c < 3.0


def test_hydrate_margin_model_flags_high_inside_hydrate_region() -> None:
    result = HydrateMarginModel().evaluate(
        operating_temperature=4.0,
        hydrate_equilibrium_temperature=8.0,
    )

    assert result.margin_warning == "high"
    assert result.hydrate_margin_c < 0.0
    assert result.subcooling_c == pytest.approx(4.0, abs=1e-6)


def test_hydrate_margin_model_rejects_non_positive_min_margin() -> None:
    with pytest.raises(ValueError, match="min_margin"):
        HydrateMarginModel(min_margin=-3.0)
