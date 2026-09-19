import pytest

from hydrate_screening import HydrateScreener


def test_hydrate_screener_flags_high_risk_with_water_and_low_margin() -> None:
    result = HydrateScreener().screen(pressure=80.0, temperature=4.0, water_present=True)

    assert result.risk_level == "high"
    assert result.margin_indicator < 2.0
    assert result.assumptions


def test_hydrate_screener_reports_low_risk_when_water_absent() -> None:
    result = HydrateScreener().screen(pressure=80.0, temperature=4.0, water_present=False)

    assert result.risk_level == "low"
    assert any("Water absent" in assumption for assumption in result.assumptions)


def test_hydrate_screener_reports_low_risk_with_warm_temperature() -> None:
    result = HydrateScreener().screen(pressure=30.0, temperature=30.0, water_present=True)

    assert result.risk_level == "low"
    assert result.margin_indicator > 8.0


def test_hydrate_screener_rejects_non_positive_pressure() -> None:
    with pytest.raises(ValueError, match="pressure"):
        HydrateScreener().screen(pressure=0.0, temperature=5.0, water_present=True)