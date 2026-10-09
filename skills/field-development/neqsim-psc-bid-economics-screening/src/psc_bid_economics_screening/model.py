"""Screening economics for a bid on a Production Sharing Contract (PSC) exploration block.

Mirrors the validated NeqSim Java class
``neqsim.process.fielddevelopment.economics.PscBidEconomics`` with the same
conventions so the two can be cross-checked. Units: volumes in million barrels
per year, money in million USD, prices in USD per barrel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

MAX_SHARE = 0.99


@dataclass
class PscBidResult:
    """Result of a PSC bid evaluation. Money is net to the working interest."""

    profit_oil_share_offered: float
    chance_of_discovery: float
    pv_development_given_discovery_musd: float
    pv_pre_discovery_cost_musd: float
    emv_musd: float
    break_even_profit_oil_share: float
    share_headroom: float
    government_take: float
    contractor_cash_undiscounted_musd: float
    state_take_undiscounted_musd: float
    bid_verdict: str
    assumptions: List[str] = field(default_factory=list)


class PscBidModel:
    """Educational PSC bid screening with a break-even offered profit-oil share."""

    def __init__(
        self,
        oil_price: float = 70.0,
        discount_rate: float = 0.10,
        royalty_rate: float = 0.15,
        cost_oil_cap: float = 0.50,
        tax_rate: float = 0.34,
        depreciation_years: int = 5,
        loss_offset_cap: float = 0.30,
        share_per_usd_above_reference: float = 0.0,
        reference_price: float = 40.0,
    ) -> None:
        self.oil_price = oil_price
        self.discount_rate = discount_rate
        self.royalty_rate = royalty_rate
        self.cost_oil_cap = cost_oil_cap
        self.tax_rate = tax_rate
        self.depreciation_years = max(1, int(depreciation_years))
        self.loss_offset_cap = loss_offset_cap
        self.share_per_usd = share_per_usd_above_reference
        self.reference_price = reference_price

    def evaluate(
        self,
        production_mmbbl: Sequence[float],
        capex_musd: Sequence[float],
        opex_musd: Sequence[float],
        profit_oil_share_offered: float,
        chance_of_discovery: float,
        working_interest: float = 1.0,
        signature_bonus_musd: float = 0.0,
        exploration_program_musd: float = 0.0,
        discovery_delay_years: int = 4,
        volume_scales: Sequence[float] = (1.0,),
        volume_weights: Sequence[float] = (1.0,),
    ) -> PscBidResult:
        """Evaluate the bid at the offered share and solve the break-even share."""
        if not (len(production_mmbbl) == len(capex_musd) == len(opex_musd)):
            raise ValueError("production, capex and opex must have the same length")
        if len(volume_scales) != len(volume_weights) or not volume_scales:
            raise ValueError("volume_scales and volume_weights must have the same non-zero length")
        total_w = sum(volume_weights)
        if total_w <= 0.0:
            raise ValueError("volume_weights must sum to a positive number")
        weights = [w / total_w for w in volume_weights]
        delay = max(1, int(discovery_delay_years))

        def at_share(share: float):
            pv_dev = 0.0
            pv_state = 0.0
            base = None
            for scale, w in zip(volume_scales, weights):
                pv_c, pv_s, sums = self._waterfall(
                    production_mmbbl, capex_musd, opex_musd, share, scale, exploration_program_musd, delay
                )
                pv_dev += w * pv_c
                pv_state += w * pv_s
                if base is None:
                    base = sums
            pv_pem = sum(
                (exploration_program_musd / delay) / (1.0 + self.discount_rate) ** y
                for y in range(1, delay + 1)
            )
            pre = -working_interest * (signature_bonus_musd + pv_pem)
            dev = working_interest * pv_dev
            return pre + chance_of_discovery * dev, dev, pre, base

        emv, dev, pre, base = at_share(profit_oil_share_offered)
        break_even = self._break_even(lambda s: at_share(s)[0])
        contractor_sum, state_sum, net_pre_tax = base
        gov_take = state_sum / net_pre_tax if net_pre_tax > 0.0 else float("nan")
        headroom = break_even - profit_oil_share_offered
        if emv <= 0.0:
            verdict = "negative_emv"
        elif headroom < 0.05:
            verdict = "thin_headroom"
        else:
            verdict = "value_creating"
        return PscBidResult(
            profit_oil_share_offered=profit_oil_share_offered,
            chance_of_discovery=chance_of_discovery,
            pv_development_given_discovery_musd=dev,
            pv_pre_discovery_cost_musd=pre,
            emv_musd=emv,
            break_even_profit_oil_share=break_even,
            share_headroom=headroom,
            government_take=gov_take,
            contractor_cash_undiscounted_musd=working_interest * contractor_sum,
            state_take_undiscounted_musd=working_interest * state_sum,
            bid_verdict=verdict,
            assumptions=[
                "Royalty on gross revenue; cost oil capped on net revenue after royalty.",
                "Signature bonus is not cost recoverable; exploration programme is recoverable on discovery.",
                "Flat oil price; generic public fiscal defaults that must be replaced by the bid-round contract terms.",
                "Exploration programme and bonus are paid in every outcome; development only on discovery.",
            ],
        )

    def _waterfall(self, production, capex, opex, share, scale, pem, delay):
        pool = pem
        loss_pool = 0.0
        pv_c = 0.0
        pv_s = 0.0
        contractor_sum = 0.0
        state_sum = 0.0
        net_pre_tax = 0.0
        state_share = min(
            MAX_SHARE, share + self.share_per_usd * max(0.0, self.oil_price - self.reference_price)
        )
        for t in range(len(production)):
            revenue = production[t] * scale * self.oil_price
            royalty = self.royalty_rate * revenue
            net = revenue - royalty
            pool += capex[t] + opex[t]
            cost_oil = min(self.cost_oil_cap * net, pool)
            pool -= cost_oil
            profit_oil = net - cost_oil
            state_profit = state_share * profit_oil
            contractor_rev = cost_oil + profit_oil - state_profit
            depreciation = sum(
                capex[k] / self.depreciation_years
                for k in range(t + 1)
                if t - k < self.depreciation_years
            )
            taxable = contractor_rev - opex[t] - depreciation
            tax = 0.0
            if taxable < 0.0:
                loss_pool += -taxable
            else:
                offset = min(loss_pool, self.loss_offset_cap * taxable)
                loss_pool -= offset
                tax = self.tax_rate * (taxable - offset)
            cash = contractor_rev - capex[t] - opex[t] - tax
            state = royalty + state_profit + tax
            df = (1.0 + self.discount_rate) ** -(delay + t + 1)
            pv_c += cash * df
            pv_s += state * df
            contractor_sum += cash
            state_sum += state
            net_pre_tax += revenue - capex[t] - opex[t]
        return pv_c, pv_s, (contractor_sum, state_sum, net_pre_tax)

    @staticmethod
    def _break_even(emv_at) -> float:
        if emv_at(0.0) <= 0.0:
            return 0.0
        if emv_at(MAX_SHARE) >= 0.0:
            return MAX_SHARE
        lo, hi = 0.0, MAX_SHARE
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if emv_at(mid) > 0.0:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)
