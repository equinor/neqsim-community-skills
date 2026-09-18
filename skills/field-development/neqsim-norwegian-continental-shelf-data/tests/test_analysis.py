import pytest

from norwegian_continental_shelf_data import (
    AnnualProduction,
    NcsField,
    aggregate_field_counts,
    fields_started_by_decade,
    production_share,
    production_trend,
    resource_remaining,
)


def test_resource_remaining_basic() -> None:
    result = resource_remaining(
        total_billion_sm3_oe=15.6,
        produced_fraction=0.56,
    )
    assert result.produced_billion_sm3_oe == pytest.approx(8.736, abs=1e-3)
    assert result.remaining_billion_sm3_oe == pytest.approx(6.864, abs=1e-3)
    assert result.remaining_fraction == pytest.approx(0.44, abs=1e-6)
    assert result.reserve_to_production_years is None


def test_resource_remaining_with_rp_horizon() -> None:
    result = resource_remaining(
        total_billion_sm3_oe=15.6,
        produced_fraction=0.56,
        latest_annual_oe_mill_sm3=239.2,
    )
    # remaining 6.864 billion = 6864 million; / 239.2 ~ 28.7 years
    assert result.reserve_to_production_years == pytest.approx(28.7, abs=0.2)


def test_resource_remaining_invalid_fraction() -> None:
    with pytest.raises(ValueError):
        resource_remaining(total_billion_sm3_oe=15.6, produced_fraction=1.5)


def test_production_share_partial_components() -> None:
    record = AnnualProduction(
        year=2020,
        oe_mill_sm3=230.0,
        oil_mill_sm3=100.0,
        gas_bill_sm3=115.0,
    )
    share = production_share(record)
    assert share.oil_share == pytest.approx(100.0 / 230.0, abs=1e-4)
    assert share.gas_share == pytest.approx(115.0 / 230.0, abs=1e-4)
    assert share.ngl_share is None
    assert share.condensate_share is None


def test_production_trend_falling() -> None:
    series = [
        AnnualProduction(year=2005, oe_mill_sm3=250.0),
        AnnualProduction(year=2013, oe_mill_sm3=210.0),
    ]
    trend = production_trend(series)
    assert trend.direction == "falling"
    assert trend.total_change_pct < 0
    assert trend.cagr_pct is not None


def test_production_trend_needs_two_years() -> None:
    with pytest.raises(ValueError):
        production_trend([AnnualProduction(year=2020, oe_mill_sm3=239.0)])


def _fields():
    return [
        NcsField("A", "Op1", "north_sea", "oil", 1979, "producing"),
        NcsField("B", "Op1", "north_sea", "gas", 1995, "producing"),
        NcsField("C", "Op2", "barents_sea", "oil", 2016, "producing"),
    ]


def test_aggregate_field_counts() -> None:
    counts = aggregate_field_counts(_fields())
    assert counts["by_sea_area"]["north_sea"] == 2
    assert counts["by_main_product"]["oil"] == 2
    assert counts["by_status"]["producing"] == 3


def test_fields_started_by_decade() -> None:
    decades = fields_started_by_decade(_fields())
    assert decades[1970] == 1
    assert decades[1990] == 1
    assert decades[2010] == 1
