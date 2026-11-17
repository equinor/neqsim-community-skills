import math

import pytest

from psc_bid_economics_screening import (
    ProfitOilTable,
    adjustment_pp,
    effective_share,
    load_annex_xx,
)


def test_grid_dimensions_and_open_top_band() -> None:
    table = load_annex_xx()
    bands = table.price_bands
    assert len(bands) == 41 and table.rate_bands == 101
    assert (
        bands[0] == (0.0, 5.0)
        and bands[1] == (5.01, 10.0)
        and bands[-2] == (195.01, 200.0)
    )
    assert bands[-1][0] == 200.01 and math.isinf(bands[-1][1])


def test_reference_cell_is_zero_pp_at_brent_50_and_10000_bbld() -> None:
    assert adjustment_pp(50.0, 10000.0) == 0.0
    assert adjustment_pp(50.0, 9999.0) == adjustment_pp(50.0, 10000.0)
    assert adjustment_pp(50.0, 10000.5) != 0.0
    assert effective_share(0.1552, 50.0, 10000.0) == pytest.approx(0.1552)


def test_price_band_upper_bound_is_inclusive() -> None:
    assert adjustment_pp(50.0, 20000.0) == adjustment_pp(45.5, 20000.0)
    assert adjustment_pp(50.005, 20000.0) == adjustment_pp(52.0, 20000.0)
    assert adjustment_pp(50.0, 20000.0) != adjustment_pp(50.01, 20000.0)


def test_adjustment_saturates_near_13_4_pp_at_pre_salt_rates() -> None:
    assert adjustment_pp(70.0, 28000.0) == pytest.approx(13.4, abs=0.1)
    for price in (60.5, 70.0, 90.0, 125.0):
        for rate in (25000.0, 30000.0, 40000.0, 50000.0):
            assert 13.0 < adjustment_pp(price, rate) < 13.6
    # a flat offered share would overstate contractor value by about 13 pp of profit oil
    assert effective_share(0.2502, 70.0, 28000.0) == pytest.approx(
        0.2502 + 0.134, abs=0.002
    )


def test_rate_band_edges_and_clamps() -> None:
    assert adjustment_pp(70.0, 0.0) == adjustment_pp(70.0, 250.0)
    assert adjustment_pp(70.0, -5.0) == adjustment_pp(70.0, 250.0)
    assert adjustment_pp(70.0, 60000.0) == adjustment_pp(70.0, 50250.0)
    assert adjustment_pp(500.0, 28000.0) == adjustment_pp(250.0, 28000.0)


def test_one_percent_cells_are_share_floor_not_plus_one_pp() -> None:
    assert adjustment_pp(3.0, 100.0) == -100.0
    assert effective_share(0.20, 3.0, 100.0) == pytest.approx(0.01)
    assert effective_share(0.20, 3.0, 1700.0) == pytest.approx(
        0.01
    )  # -93.6 pp also floors


def test_share_cap_at_100_percent() -> None:
    assert effective_share(0.95, 250.0, 50000.0) == 1.0


def test_constant_table_adds_nothing_or_a_fixed_pp() -> None:
    flat = ProfitOilTable.constant(0.0)
    assert flat.effective_share(0.25, 90.0, 1234.0) == 0.25
    assert ProfitOilTable.constant(5.0).effective_share(
        0.25, 90.0, 1234.0
    ) == pytest.approx(0.30)


def test_nan_inputs_rejected_and_incomplete_grid_rejected() -> None:
    with pytest.raises(ValueError):
        adjustment_pp(float("nan"), 10000.0)
    with pytest.raises(ValueError):
        ProfitOilTable(
            [(0.0, 5.0, 0.0, 1.0), (0.0, 5.0, 500.0, 1.0), (5.01, None, 0.0, 2.0)]
        )
