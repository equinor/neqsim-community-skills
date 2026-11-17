import pytest
from psc_bid_economics_screening import (
    ProfitOilTable,
    PscBidModel,
    breakeven_oil_price,
    find_crossover,
    load_annex_xx,
    minimum_economic_volume,
    net_cost_oil_cap,
    swanson_cases,
    swanson_emv,
    what_you_need_to_believe,
)

PRODUCTION = [10.0, 25.0, 30.0, 28.0, 24.0, 20.0, 16.0, 13.0, 10.0, 8.0]
CAPEX = [900.0, 900.0, 400.0, 0, 0, 0, 0, 0, 0, 0]
OPEX = [20.0, 60.0, 80.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0]
KW = dict(chance_of_discovery=0.30, working_interest=0.70, signature_bonus_musd=20.0, exploration_program_musd=60.0)


def independent_waterfall(offer, price, gross_cap, royalty, tax, dep_years, loss_cap, rate, pem, delay, wi):
    """Brazil-style waterfall written from the contract text (cap on gross value), not from the model."""
    pool, loss_pool, pv = pem, 0.0, 0.0
    for t, q in enumerate(PRODUCTION):
        gross = q * price
        roy = royalty * gross
        pool += CAPEX[t] + OPEX[t]
        cost_oil = min(gross_cap * gross, pool)
        pool -= cost_oil
        profit_oil = gross - roy - cost_oil
        contractor = cost_oil + profit_oil * (1.0 - offer)
        dep = sum(CAPEX[k] / dep_years for k in range(t + 1) if t - k < dep_years)
        taxable = contractor - OPEX[t] - dep
        paid = 0.0
        if taxable < 0.0:
            loss_pool += -taxable
        else:
            off = min(loss_pool, loss_cap * taxable)
            loss_pool -= off
            paid = tax * (taxable - off)
        pv += (contractor - CAPEX[t] - OPEX[t] - paid) / (1.0 + rate) ** (delay + t + 1)
    return wi * pv


def run(model, offer=0.25, **kw):
    args = dict(KW)
    args.update(kw)
    return model.evaluate(PRODUCTION, CAPEX, OPEX, offer, **args)


def test_gross_cost_oil_cap_needs_net_conversion_and_matches_independent_waterfall() -> None:
    assert net_cost_oil_cap(0.80, 0.15) == pytest.approx(0.80 / 0.85)
    model = PscBidModel(royalty_rate=0.15, cost_oil_cap=net_cost_oil_cap(0.80, 0.15))
    res = run(model)
    ref = independent_waterfall(0.25, 70.0, 0.80, 0.15, 0.34, 5, 0.30, 0.10, 60.0, 4, 0.70)
    assert res.pv_development_given_discovery_musd == pytest.approx(ref, abs=1e-9)
    # passing 0.80 straight to the model silently applies it after royalty and gives a different answer
    naive = run(PscBidModel(royalty_rate=0.15, cost_oil_cap=0.80)).pv_development_given_discovery_musd
    assert abs(naive - ref) > 1e-3


def test_table_disabled_or_flat_equals_constant_share_result() -> None:
    base = run(PscBidModel())
    flat = run(PscBidModel(share_table=ProfitOilTable.constant(0.0)), rate_per_producer_bbld=20000.0)
    assert flat.emv_musd == pytest.approx(base.emv_musd, abs=1e-9)
    assert flat.break_even_profit_oil_share == pytest.approx(base.break_even_profit_oil_share, abs=1e-9)
    assert base.effective_profit_oil_share == pytest.approx(0.25)
    assert flat.effective_profit_oil_share == pytest.approx(0.25)


def test_annex_xx_table_lowers_value_at_pre_salt_rates() -> None:
    flat = run(PscBidModel())
    table = run(PscBidModel(share_table=load_annex_xx()), rate_per_producer_bbld=28000.0)
    assert table.effective_profit_oil_share == pytest.approx(0.25 + 0.134, abs=0.003)
    assert table.emv_musd < flat.emv_musd
    assert table.break_even_profit_oil_share < flat.break_even_profit_oil_share
    at_be = run(PscBidModel(share_table=load_annex_xx()), offer=table.break_even_profit_oil_share,
                rate_per_producer_bbld=28000.0)
    assert at_be.emv_musd == pytest.approx(0.0, abs=1e-3)


def test_brent_follows_realisation_discount_and_reference_cell_is_neutral() -> None:
    # realised 45 + discount 5 = Brent 50, 10,000 bbl/d: the OFERTA cell, so no adjustment
    model = PscBidModel(oil_price=45.0, share_table=load_annex_xx(), realisation_discount_usd=5.0)
    assert run(model, rate_per_producer_bbld=10000.0).effective_profit_oil_share == pytest.approx(0.25)
    flat = run(PscBidModel(oil_price=45.0))
    assert run(model, rate_per_producer_bbld=10000.0).emv_musd == pytest.approx(flat.emv_musd, abs=1e-9)


def test_share_varies_by_year_with_per_year_rate() -> None:
    model = PscBidModel(share_table=load_annex_xx())
    rates = [5000.0, 12000.0, 28000.0] + [28000.0] * 7
    shares = model.effective_share_profile(0.25, PRODUCTION, rates)
    assert shares[0] < shares[1] < shares[2]
    assert shares[2] == pytest.approx(shares[9])
    res = run(model, rate_per_producer_bbld=rates)
    assert 0.25 < res.effective_profit_oil_share < 0.40
    assert any("share-table" in a for a in res.assumptions)


def test_table_input_validation() -> None:
    model = PscBidModel(share_table=load_annex_xx())
    with pytest.raises(ValueError):
        run(model)
    with pytest.raises(ValueError):
        run(model, rate_per_producer_bbld=[1.0, 2.0])


def test_swanson_cases_and_emv_match_manual_weighting() -> None:
    scales, weights = swanson_cases(100.0, 350.0, 1100.0)
    assert scales == pytest.approx([100 / 350, 1.0, 1100 / 350]) and weights == [0.3, 0.4, 0.3]
    with pytest.raises(ValueError):
        swanson_cases(400.0, 350.0, 1100.0)
    model = PscBidModel()
    res = swanson_emv(model, PRODUCTION, CAPEX, OPEX, (100.0, 350.0, 1100.0), profit_oil_share_offered=0.25, **KW)
    manual = run(model, volume_scales=scales, volume_weights=weights)
    assert res.emv_musd == pytest.approx(manual.emv_musd)


def test_what_you_need_to_believe_roots() -> None:
    model = PscBidModel()
    belief = what_you_need_to_believe(model, PRODUCTION, CAPEX, OPEX, profit_oil_share_offered=0.25, **KW)
    assert belief.chance_attainable and 0.0 < belief.break_even_chance_of_discovery < 1.0
    at_pg = dict(KW, chance_of_discovery=belief.break_even_chance_of_discovery)
    assert run(model, **at_pg).emv_musd == pytest.approx(0.0, abs=1e-6)
    m = belief.p50_volume_scale_for_zero_emv
    assert m is not None
    assert run(model, volume_scales=[m]).emv_musd == pytest.approx(0.0, abs=1e-3)
    assert belief.p50_volume_mmbbl_for_zero_emv == pytest.approx(m * sum(PRODUCTION))


def test_what_you_need_to_believe_unreachable_case() -> None:
    huge_capex = [c * 1000.0 for c in CAPEX]
    belief = what_you_need_to_believe(PscBidModel(), PRODUCTION, huge_capex, OPEX, max_volume_scale=3.0,
                                      profit_oil_share_offered=0.25, **KW)
    assert belief.p50_volume_scale_for_zero_emv is None and belief.p50_volume_mmbbl_for_zero_emv is None
    assert not belief.chance_attainable


def test_minimum_economic_volume_and_breakeven_price_are_zero_npv_points() -> None:
    model = PscBidModel()
    vmin = minimum_economic_volume(model, PRODUCTION, CAPEX, OPEX, profit_oil_share_offered=0.25, **KW)
    dev = run(model, volume_scales=[vmin / sum(PRODUCTION)]).pv_development_given_discovery_musd
    assert dev == pytest.approx(0.0, abs=1e-3)
    price = breakeven_oil_price(model, PRODUCTION, CAPEX, OPEX, profit_oil_share_offered=0.25, **KW)
    assert 5.0 < price < 70.0 and model.oil_price == 70.0
    probe = PscBidModel(oil_price=price)
    assert run(probe).pv_development_given_discovery_musd == pytest.approx(0.0, abs=1e-3)


def test_find_crossover_between_concepts() -> None:
    tie_back = lambda v: 1.0 * v - 100.0   # cheap but low slope
    stand_alone = lambda v: 2.0 * v - 400.0
    assert find_crossover(tie_back, stand_alone, 50.0, 1000.0) == pytest.approx(300.0)
    assert find_crossover(tie_back, lambda v: v - 50.0, 50.0, 1000.0) is None
