import math

import pytest

from psc_bid_economics_screening import PscBidModel

PRODUCTION = [10.0, 25.0, 30.0, 28.0, 24.0, 20.0, 16.0, 13.0, 10.0, 8.0]
CAPEX = [900.0, 900.0, 400.0, 0, 0, 0, 0, 0, 0, 0]
OPEX = [20.0, 60.0, 80.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0]


def evaluate(model=None, **kw):
    args = dict(
        profit_oil_share_offered=0.25,
        chance_of_discovery=0.30,
        signature_bonus_musd=20.0,
        exploration_program_musd=60.0,
    )
    args.update(kw)
    return (model or PscBidModel()).evaluate(PRODUCTION, CAPEX, OPEX, **args)


def test_state_and_contractor_split_pre_tax_net_cash_flow() -> None:
    r = evaluate()
    expected = sum(PRODUCTION) * 70.0 - sum(CAPEX) - sum(OPEX)
    assert r.contractor_cash_undiscounted_musd + r.state_take_undiscounted_musd == pytest.approx(expected)
    assert 0.0 < r.government_take < 1.0


def test_break_even_share_gives_zero_emv() -> None:
    model = PscBidModel()
    r = evaluate(model, chance_of_discovery=0.60)
    assert 0.0 < r.break_even_profit_oil_share < 0.99
    at_be = evaluate(model, chance_of_discovery=0.60, profit_oil_share_offered=r.break_even_profit_oil_share)
    assert at_be.emv_musd == pytest.approx(0.0, abs=1e-3)


def test_zero_chance_loses_pre_discovery_costs() -> None:
    r = evaluate(chance_of_discovery=0.0)
    assert r.emv_musd == pytest.approx(r.pv_pre_discovery_cost_musd)
    assert r.bid_verdict == "negative_emv"
    assert r.break_even_profit_oil_share == 0.0


def test_working_interest_scales_linearly() -> None:
    full = evaluate(working_interest=1.0).emv_musd
    seventy = evaluate(working_interest=0.70).emv_musd
    assert seventy == pytest.approx(0.70 * full)


def test_emv_falls_with_offered_share() -> None:
    low = evaluate(profit_oil_share_offered=0.10).emv_musd
    high = evaluate(profit_oil_share_offered=0.50).emv_musd
    assert low > high


def test_volume_cases_are_weighted() -> None:
    mid = evaluate().pv_development_given_discovery_musd
    low = evaluate(volume_scales=[0.6], volume_weights=[1.0]).pv_development_given_discovery_musd
    high = evaluate(volume_scales=[1.5], volume_weights=[1.0]).pv_development_given_discovery_musd
    mixed = evaluate(
        volume_scales=[0.6, 1.0, 1.5], volume_weights=[3.0, 4.0, 3.0]
    ).pv_development_given_discovery_musd
    assert mixed == pytest.approx(0.3 * low + 0.4 * mid + 0.3 * high)


def test_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        PscBidModel().evaluate([1.0, 2.0], [1.0], [1.0, 2.0], 0.2, 0.3)


def test_assumptions_listed() -> None:
    assert evaluate().assumptions
    assert not math.isnan(evaluate().government_take)


def test_price_share_steps_reduce_value_above_threshold() -> None:
    flat = evaluate().emv_musd
    stepped = evaluate(PscBidModel(price_share_steps=[(60.0, 0.05), (90.0, 0.10)])).emv_musd
    below = evaluate(PscBidModel(oil_price=55.0, price_share_steps=[(60.0, 0.05)])).emv_musd
    assert stepped < flat
    assert below == pytest.approx(evaluate(PscBidModel(oil_price=55.0)).emv_musd)


def test_tornado_is_ordered_and_low_below_high() -> None:
    model = PscBidModel()
    rows = model.tornado(
        0.20,
        production_mmbbl=PRODUCTION,
        capex_musd=CAPEX,
        opex_musd=OPEX,
        profit_oil_share_offered=0.25,
        chance_of_discovery=0.30,
        signature_bonus_musd=20.0,
        exploration_program_musd=60.0,
    )
    assert list(rows) and len(rows) == 5
    swings = [hi - lo for lo, hi in rows.values()]
    assert swings == sorted(swings, reverse=True)
    assert all(lo <= hi for lo, hi in rows.values())
    assert model.oil_price == 70.0 and model.discount_rate == 0.10


def test_near_host_and_stand_alone_regression() -> None:
    """Synthetic near-host block (70 percent) and stand-alone block (100 percent), same fiscal terms."""
    tieback_capex = [500.0, 500.0, 200.0] + [0] * 7
    near = PscBidModel().evaluate(
        PRODUCTION, tieback_capex, OPEX, 0.25, 0.30, working_interest=0.70,
        signature_bonus_musd=20.0, exploration_program_musd=60.0,
    )
    alone = PscBidModel().evaluate(
        PRODUCTION, CAPEX, OPEX, 0.25, 0.30, working_interest=1.0,
        signature_bonus_musd=20.0, exploration_program_musd=60.0,
    )
    assert near.emv_musd > 0.70 * alone.emv_musd
    assert near.break_even_profit_oil_share > alone.break_even_profit_oil_share
    assert near.pv_pre_discovery_cost_musd == pytest.approx(0.70 * alone.pv_pre_discovery_cost_musd)
