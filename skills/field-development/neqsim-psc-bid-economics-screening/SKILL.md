---
name: neqsim-psc-bid-economics-screening
calculation_basis: "screening"
version: "1.0.0"
description: "Educational PSC exploration-block bid screening: royalty, capped cost oil, profit-oil split (optionally the Brazilian ANP Annex XX Brent and rate-per-well adjustment table), tax, bonus and exploration programme, with EMV, break-even offered share, break-even chance of discovery and volume. USE WHEN: judging a bid-round offer or how much State profit-oil share a block can bear, or comparing a tie-back with stand-alone."
last_verified: "2026-10-14"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# PSC Bid Economics Screening

Use this skill to put a number on a Production Sharing Contract bid before there is a discovery. The bid variable is the offered State share of profit oil, so the useful answer is the break-even share at which the expected monetary value (EMV) is zero, and the headroom between that and the offer.

## When to Use

- A bid-round block must be judged on value, not volume.
- A near-field tie-back and a stand-alone concept need the same fiscal wrapper.
- An agent needs a quick "can the block bear this offer" answer to scope a deeper study.

## Inputs

- `production_mmbbl`, `capex_musd`, `opex_musd`: yearly development profile starting the year after discovery, at 100%.
- `profit_oil_share_offered`: State share of profit oil, the bid variable.
- `chance_of_discovery`: probability of a developable discovery.
- `working_interest`, `signature_bonus_musd`, `exploration_program_musd`, `discovery_delay_years`.
- `volume_scales` and `volume_weights`: optional P90/P50/P10 outcomes given a discovery, for example scales 0.6/1.0/1.5 with weights 0.3/0.4/0.3.
- Model terms: `oil_price`, `discount_rate`, `royalty_rate`, `cost_oil_cap`, `tax_rate`, `depreciation_years`, `loss_offset_cap`, optional price-linked share step.
- Optional share table: `share_table` (for example `load_annex_xx()`), `realisation_discount_usd` (Brent minus realised price) and `rate_per_producer_bbld` (number or one value per year).

## Outputs

- `emv_musd`, `pv_development_given_discovery_musd`, `pv_pre_discovery_cost_musd`.
- `break_even_profit_oil_share`, `share_headroom`, `government_take`, `effective_profit_oil_share` (production-weighted share actually paid).
- `bid_verdict`: `value_creating`, `thin_headroom` (headroom below 0.05) or `negative_emv`.
- With `what_you_need_to_believe`: break-even chance of discovery and the P50 volume for EMV = 0; with `minimum_economic_volume`, `breakeven_oil_price` and `find_crossover`: zero-NPV volume, Brent and tie-back versus stand-alone crossover.
- `assumptions`.

## Engineering Method

Per development year: royalty on gross revenue; cost oil is the lower of the cap times net revenue and the unrecovered cost pool; profit oil is split by the offered share; contractor income tax applies to contractor revenue less OPEX and straight-line CAPEX depreciation, with losses offset up to a cap. The signature bonus is not cost recoverable. The bonus and exploration programme are paid in every outcome; development only on discovery. EMV equals the pre-discovery cost plus the chance of discovery times the expected development value.

The default terms are generic public placeholders. Replace them with the terms of the actual bid-round contract before reading the numbers as anything but a screen. The model does not represent a contract-compliant calculation, per-well productivity tables, local-content obligations or partner carry.

## Python Usage Pattern

```python
from psc_bid_economics_screening import PscBidModel

model = PscBidModel(oil_price=70.0, discount_rate=0.10,
                    price_share_steps=[(60.0, 0.05)])   # optional contract price-band table, from the contract only
result = model.evaluate(
    production, capex, opex,
    profit_oil_share_offered=0.25, chance_of_discovery=0.30,
    working_interest=0.70, signature_bonus_musd=20.0, exploration_program_musd=60.0,
)
print(result.bid_verdict, result.break_even_profit_oil_share)
rows = model.tornado(0.20, production_mmbbl=production, capex_musd=capex, opex_musd=opex,
                     profit_oil_share_offered=0.25, chance_of_discovery=0.30)   # largest swing first
```

For P10/P50/P90 EMV and the probability of loss use the Java `PscBidEconomics.monteCarlo(samples, seed, priceSigma, volumeSigma, capexSigma)`: price, volume and CAPEX get mean-preserving lognormal factors, the dry outcome is counted in the probability of loss, and a fixed seed gives repeatable results. The Python class and the Java class agree on the deterministic EMV, break-even share and price-band results (pinned in the Java tests).

```python
from psc_bid_economics_screening import (PscBidModel, load_annex_xx, net_cost_oil_cap, swanson_emv,
                                         what_you_need_to_believe, minimum_economic_volume, breakeven_oil_price)

model = PscBidModel(oil_price=65.0, realisation_discount_usd=5.0,            # Brent = 70
                    royalty_rate=0.15, cost_oil_cap=net_cost_oil_cap(0.80, 0.15),   # 80 % of GROSS value
                    share_table=load_annex_xx())
kw = dict(profit_oil_share_offered=0.1552, chance_of_discovery=0.35, working_interest=0.70,
          signature_bonus_musd=21.0, exploration_program_musd=140.0, rate_per_producer_bbld=28000.0)
res = swanson_emv(model, production, capex, opex, (100, 350, 1100), **kw)         # 0.3/0.4/0.3 on P90/P50/P10
belief = what_you_need_to_believe(model, production, capex, opex,
                                  volumes_p90_p50_p10=(100, 350, 1100), **kw)   # break-even Pg and P50 volume
vmin = minimum_economic_volume(model, production, capex, opex, **kw)             # MMbbl, development NPV = 0
```

## Brazilian Annex XX share table

The ANP edital ANEXO XX sets the Union profit-oil share as the offered percentage plus a percentage-point adjustment read from a grid of Dated Brent bands (rows, USD/bbl) and average oil rate per producing well (columns of 500 bbl/d from 0 to 50,500). The packaged grid (`annex_xx_profit_oil_adjustment.csv`, 41 price bands x 101 rate bands) was rebuilt from the 2026 OPP edital; check the edital of the round being bid.

- Price band: upper bound inclusive (`0-5, 5.01-10, ... 195.01-200, >200.01`). Rate band: `rate_lo < rate <= rate_hi`, so exactly 10,000 bbl/d is the `OFERTA` cell and is 0 pp at Brent 50.
- Share = offer + adjustment, floored at 1 % and capped at 100 %. Sixteen low-price, low-rate cells print `1%` (the floor, not +1 pp); the packaged CSV marks them `floor_cell=1` with -100 pp.
- At pre-salt rates (25 kbbl/d per producer and up) the adjustment saturates near +13.4 pp for Brent 60 and above, so a flat offered share overstates contractor value by about 13 pp of profit oil. Always pass `rate_per_producer_bbld`; the break-even is the offered share at the reference cell.
- Contract terms to enter: royalty 15 % of gross production (Annex V); cost-oil limit 80 % of gross production value in the edital (the model contract leaves it blank), converted with `net_cost_oil_cap(0.80, 0.15)` because the model applies the cap after royalty; signature bonus fixed in the edital, not a bid variable; only the Union share is bid. The minimum exploration programme is in work units (UT; OPP4 UT = R$ 461,700; 1,000 UT = one well-equivalent; 3D seismic 0.17 UT/km2) and obliges no well.
- Rebuilding the grid from the PDF: the `95.01-100` row starts with a stray `-` token, the reference cell is the word `OFERTA`, and value-only pages follow the price-band order of the first page.

## Reading results

- Report EMV two ways: forced development (develop on every discovery) and with the development option (develop only if the best concept NPV is positive). Bonus and exploration are paid in every outcome in both.
- Cross-check a deterministic Swanson EMV (0.3/0.4/0.3 on P90/P50/P10) against a Monte Carlo; the 2026-10 Rodocrosita runs gave +167 and +153 MUSD.
- Useful outputs: break-even chance of discovery (`-pre / development`), P50 volume at EMV = 0 ("what you need to believe"), minimum economic volume per concept, Brent for zero development NPV, and the tie-back versus stand-alone crossover volume (`find_crossover` over two concept cash-flow builders).
- Monte Carlo of a portfolio: use a different seed per block. Identical seeds make the blocks comonotonic (P10 = P50 = all-dry).
- Cross-check an independent waterfall against `PscBidModel` at a constant share to 1e-9; the pitfall is the cost-oil cap basis (gross versus after royalty).

## Validation Checklist

- [ ] Contract terms (royalty, cost-oil cap, tax, price-band table) come from the actual bid-round contract, not the defaults.
- [ ] The development profile starts the year after discovery and is at 100 percent, with working interest applied once.
- [ ] The bonus and exploration programme are counted in every outcome, including the dry one.
- [ ] Break-even share reproduces zero EMV when fed back as the offered share.
- [ ] Python and Java `PscBidEconomics` give the same deterministic EMV on the same inputs.
- [ ] For a Brazilian round the Annex XX table is on, `rate_per_producer_bbld` is stated, and the cost-oil cap basis (gross or after royalty) is converted.
- [ ] EMV is reported as forced development and with the development option, plus break-even chance of discovery and P50 volume for EMV = 0.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| EMV looks too high | Exploration programme or bonus charged only on success | Charge both in every outcome |
| Headroom is negative at a sensible offer | Default placeholder terms used as contract terms | Replace with the real contract terms |
| Volume risk looks symmetric | P90/P50/P10 weights do not sum to 1 | Check `volume_weights` |
| Value credited to a tie-back that does not fit | Host ullage ignored | Run `HostSynergyScreening` first |
| EMV too high for a Brazilian block | Flat offered share used; the table adds about +13 pp at pre-salt rates | Use `load_annex_xx()` with the rate per producer |
| Cost oil too small or large vs the edital | 80 % of gross entered as `cost_oil_cap` | Use `net_cost_oil_cap(0.80, 0.15)` |
| Portfolio P10 equals P50 | Same Monte Carlo seed for every block | Different seed per block |

## Limitations

- Generic public placeholder terms unless the Annex XX table and edital terms are entered; not a contract-compliant calculation.
- No per-well productivity model (the rate per producer is an input), local-content obligations or partner carry.
- Not suitable for a bid decision without qualified commercial and fiscal review.

## Related NeqSim Functionality

- `neqsim.process.fielddevelopment.economics.PscBidEconomics` — the validated Java class with the same mechanics, plus Monte Carlo and tornado; prefer it inside NeqSim studies.
- `neqsim.process.fielddevelopment.tieback.HostSynergyScreening` — host ullage cover and tie-back synergy value, credited only when the demand fits the host.
- `neqsim.process.fielddevelopment.economics.TaxModelRegistry` (`BR-PSA`) and `CashFlowEngine` — full-life fiscal cash flow once a concept exists.
- Chain with `neqsim-reservoir-model-builder`, `neqsim-brazil-presalt-analogue-basis`, `neqsim-brazil-offshore-infrastructure-market` (gas export, host capacity, tariff status), `neqsim-anp-open-data` (block and production facts), `neqsim-production-optimization` (rate per producer, plateau), `neqsim-asset-value-npv-screening` and the `frontier-block-bid-agent`.

## References

- Johnston, D. (1994), International Petroleum Fiscal Systems and Production Sharing Contracts, PennWell, for the royalty, cost-oil and profit-oil mechanics.
- ANP edital of the Oferta Permanente de Partilha (Annexes V and XX) and its model PSC; the contract of the round being screened is the only authority for the terms.
