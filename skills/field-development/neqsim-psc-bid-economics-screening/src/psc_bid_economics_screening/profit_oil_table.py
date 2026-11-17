"""Brazilian ANP edital ANEXO XX: Union profit-oil share adjustment by Dated Brent and rate per producer.

The edital states the offered Union profit-oil share at the reference cell (Brent
45.01-50 USD/bbl, 10,000 bbl/d per producing well, printed ``OFERTA``). The share
actually paid is the offer plus a percentage-point adjustment read from a grid of
Brent price bands (rows) and average oil rate per producing well (columns of
500 bbl/d), floored at 1 % and capped at 100 %.

Band conventions (verified against the edital grid, 41 price bands x 101 rate bands):

* price band: upper bound inclusive, ``0-5, 5.01-10, ... 195.01-200, >200.01``;
  a price of exactly 50.0 belongs to ``45.01-50``.
* rate band: ``rate_lo < rate <= rate_hi``; exactly 10,000 bbl/d is the
  ``9,500-10,000`` cell, which is the ``OFERTA`` cell (0 pp) at Brent 50.
* rate at or below 0 uses the first band; rate above the last band uses the last.
* 16 cells print ``1%`` (the share floor, not +1 pp); the packaged CSV marks them
  ``floor_cell=1`` with an adjustment of -100 pp so that the same formula floors them.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from functools import lru_cache
from importlib import resources

MIN_SHARE = 0.01
MAX_SHARE = 1.0
RATE_STEP_BBLD = 500.0


class ProfitOilTable:
    """Lookup of the Annex XX adjustment (percentage points) by Brent price and rate per producer."""

    def __init__(
        self, rows: Iterable[tuple[float, float | None, float, float]]
    ) -> None:
        """Build from ``(price_lo, price_hi_or_None, rate_lo, adjustment_pp)`` rows, grid complete."""
        cells: dict[tuple[tuple[float, float], float], float] = {}
        for price_lo, price_hi, rate_lo, pp in rows:
            band = (float(price_lo), math.inf if price_hi is None else float(price_hi))
            cells[(band, float(rate_lo))] = float(pp)
        self._bands: list[tuple[float, float]] = sorted({band for band, _ in cells})
        self._rate_lo: list[float] = sorted({rate for _, rate in cells})
        if len(cells) != len(self._bands) * len(self._rate_lo):
            raise ValueError(
                f"profit-oil grid is not complete: {len(cells)} cells for {len(self._bands)} bands x {len(self._rate_lo)} rates"
            )
        self._grid: dict[tuple[int, float], float] = {
            (i, rate): cells[(band, rate)]
            for i, band in enumerate(self._bands)
            for rate in self._rate_lo
        }

    @classmethod
    def from_csv(cls, path) -> ProfitOilTable:
        """Load a CSV with columns price_lo_usd, price_hi_usd (blank = open), rate_lo_bbld, adjustment_pp."""
        with open(path, newline="", encoding="utf-8") as handle:
            rows = [
                (
                    float(r["price_lo_usd"]),
                    float(r["price_hi_usd"]) if r["price_hi_usd"].strip() else None,
                    float(r["rate_lo_bbld"]),
                    float(r["adjustment_pp"]),
                )
                for r in csv.DictReader(handle)
            ]
        return cls(rows)

    @classmethod
    def constant(cls, pp: float = 0.0) -> ProfitOilTable:
        """A one-cell-per-band table with the same adjustment everywhere (for cross-checks)."""
        return cls([(0.0, None, 0.0, pp)])

    @property
    def price_bands(self) -> list[tuple[float, float]]:
        """Price bands as ``(lo, hi)`` in order; the last ``hi`` is infinity."""
        return list(self._bands)

    @property
    def rate_bands(self) -> int:
        """Number of rate bands (columns)."""
        return len(self._rate_lo)

    def _band_of_price(self, price: float) -> int:
        if math.isnan(price):
            raise ValueError("price must not be NaN")
        for i, (_lo, hi) in enumerate(self._bands):
            if price <= hi:
                return i
        return len(self._bands) - 1

    def _rate_index(self, rate_bbld: float) -> int:
        if math.isnan(rate_bbld):
            raise ValueError("rate must not be NaN")
        if len(self._rate_lo) == 1:
            return 0
        idx = math.ceil(rate_bbld / RATE_STEP_BBLD) - 1
        return min(max(idx, 0), len(self._rate_lo) - 1)

    def adjustment_pp(self, price: float, rate_bbld: float) -> float:
        """Adjustment in percentage points at Dated Brent ``price`` (USD/bbl) and ``rate_bbld`` per producer."""
        return self._grid[
            (self._band_of_price(price), self._rate_lo[self._rate_index(rate_bbld)])
        ]

    def effective_share(self, offer: float, price: float, rate_bbld: float) -> float:
        """Union profit-oil share paid: offer plus adjustment, floored at 1 % and capped at 100 %."""
        return min(
            MAX_SHARE,
            max(MIN_SHARE, offer + self.adjustment_pp(price, rate_bbld) / 100.0),
        )


@lru_cache(maxsize=1)
def load_annex_xx() -> ProfitOilTable:
    """Packaged Annex XX grid of the ANP OPP edital (versions 2026; check the edital of the round)."""
    path = resources.files(__package__).joinpath(
        "data", "annex_xx_profit_oil_adjustment.csv"
    )
    with resources.as_file(path) as real_path:
        return ProfitOilTable.from_csv(real_path)


def adjustment_pp(price: float, rate_bbld: float) -> float:
    """Annex XX adjustment (pp) from the packaged grid."""
    return load_annex_xx().adjustment_pp(price, rate_bbld)


def effective_share(offer: float, price: float, rate_bbld: float) -> float:
    """Effective Union share from the packaged Annex XX grid (see the module docstring)."""
    return load_annex_xx().effective_share(offer, price, rate_bbld)
