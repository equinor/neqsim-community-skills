---
name: neqsim-psc-bid-economics-screening
calculation_basis: "screening"
version: "0.1.0"
description: "Educational PSC exploration-block bid screening: royalty, capped cost oil, profit-oil split, income tax, signature bonus and exploration programme, with EMV and the break-even offered profit-oil share. USE WHEN: judging a bid-round offer, asking how much State profit-oil share a block can bear, or comparing a near-field tie-back with a stand-alone case before any discovery exists."
last_verified: "2026-10-09"
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

## Outputs

- `emv_musd`, `pv_development_given_discovery_musd`, `pv_pre_discovery_cost_musd`.
- `break_even_profit_oil_share`, `share_headroom`, `government_take`.
- `bid_verdict`: `value_creating`, `thin_headroom` (headroom below 0.05) or `negative_emv`.
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

## Related NeqSim Functionality

- `neqsim.process.fielddevelopment.economics.PscBidEconomics` — the validated Java class with the same mechanics, plus Monte Carlo and tornado; prefer it inside NeqSim studies.
- `neqsim.process.fielddevelopment.tieback.HostSynergyScreening` — host ullage cover and tie-back synergy value, credited only when the demand fits the host.
- `neqsim.process.fielddevelopment.economics.TaxModelRegistry` (`BR-PSA`) and `CashFlowEngine` — full-life fiscal cash flow once a concept exists.
- Chain with `neqsim-reservoir-model-builder`, `neqsim-brazil-presalt-analogue-basis`, `neqsim-asset-value-npv-screening` and the `frontier-block-bid-agent`.
