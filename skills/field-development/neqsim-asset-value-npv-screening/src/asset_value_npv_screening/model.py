from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class AssetValueResult:
    years: int
    discount_rate_fraction: float
    tax_rate_fraction: float
    net_cash_flow_musd: tuple[float, ...]
    discounted_cash_flow_musd: tuple[float, ...]
    cumulative_cash_flow_musd: tuple[float, ...]
    npv_musd: float
    irr_fraction: float | None
    payback_year: int | None
    discounted_payback_year: int | None
    total_capex_musd: float
    total_revenue_musd: float
    value_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class AssetValueModel:
    """Educational discounted-cash-flow (DCF) asset-value screening placeholder.

    Builds a year-by-year net cash flow from revenue, OPEX, and a CAPEX schedule,
    applies a simple flat tax on positive operating profit, discounts to a net
    present value (NPV), and estimates IRR and payback. It is a transparent
    placeholder only: real asset economics must come from the validated NeqSim
    field-development DCF utilities (``neqsim.process.util.fielddevelopment``) and
    the NeqSim MCP ``runFieldEconomics`` workflow, with a qualified commercial
    review.
    """

    def __init__(self) -> None:
        pass

    def evaluate(
        self,
        *,
        annual_revenue_musd: Sequence[float],
        annual_opex_musd: Sequence[float] | float,
        capex_schedule_musd: Sequence[float] | float,
        discount_rate_fraction: float = 0.08,
        tax_rate_fraction: float = 0.0,
    ) -> AssetValueResult:
        revenue = self._normalize_series("annual_revenue_musd", annual_revenue_musd)
        years = len(revenue)
        if years == 0:
            raise ValueError("annual_revenue_musd must contain at least one year")
        opex = self._broadcast("annual_opex_musd", annual_opex_musd, years)
        capex = self._broadcast_capex("capex_schedule_musd", capex_schedule_musd, years)
        self._require_fraction("discount_rate_fraction", discount_rate_fraction)
        self._require_fraction("tax_rate_fraction", tax_rate_fraction)

        net = []
        for r, o, c in zip(revenue, opex, capex):
            operating_profit = r - o
            tax = tax_rate_fraction * operating_profit if operating_profit > 0.0 else 0.0
            net.append(operating_profit - tax - c)

        discounted = [
            cf / ((1.0 + discount_rate_fraction) ** (t + 1)) for t, cf in enumerate(net)
        ]
        npv = sum(discounted)

        cumulative = []
        running = 0.0
        for cf in net:
            running += cf
            cumulative.append(running)

        payback_year = self._first_non_negative_year(cumulative)
        discounted_payback_year = self._first_non_negative_year(
            self._running_sum(discounted)
        )
        irr = self._irr(net)

        total_capex = sum(capex)
        total_revenue = sum(revenue)
        warning = self._value_warning(npv)

        return AssetValueResult(
            years=years,
            discount_rate_fraction=round(discount_rate_fraction, 4),
            tax_rate_fraction=round(tax_rate_fraction, 4),
            net_cash_flow_musd=tuple(round(v, 3) for v in net),
            discounted_cash_flow_musd=tuple(round(v, 3) for v in discounted),
            cumulative_cash_flow_musd=tuple(round(v, 3) for v in cumulative),
            npv_musd=round(npv, 3),
            irr_fraction=None if irr is None else round(irr, 4),
            payback_year=payback_year,
            discounted_payback_year=discounted_payback_year,
            total_capex_musd=round(total_capex, 3),
            total_revenue_musd=round(total_revenue, 3),
            value_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational discounted-cash-flow (DCF) screening placeholder only.",
                "Net cash flow = revenue - OPEX - tax - CAPEX, evaluated per year.",
                "Tax is a flat rate applied only to positive operating profit (revenue - OPEX).",
                "Cash flows are discounted at year-end; year 1 is the first discounting period.",
                "No inflation, depreciation, uplift, ring-fencing, financing, or working capital is modelled.",
                "IRR is the discount rate that zeroes NPV, found by bisection; it may be undefined.",
                "Use NeqSim field-development DCF and MCP runFieldEconomics for real asset economics.",
            ),
        )

    @staticmethod
    def _value_warning(npv_musd: float) -> str:
        if npv_musd < 0.0:
            return "high"
        if npv_musd == 0.0:
            return "watch"
        return "ok"

    @staticmethod
    def _first_non_negative_year(cumulative: Sequence[float]) -> int | None:
        for t, value in enumerate(cumulative):
            if value >= 0.0:
                return t + 1
        return None

    @staticmethod
    def _running_sum(series: Sequence[float]) -> list[float]:
        out = []
        running = 0.0
        for value in series:
            running += value
            out.append(running)
        return out

    @classmethod
    def _irr(cls, net: Sequence[float], *, lower: float = -0.9, upper: float = 5.0) -> float | None:
        def npv_at(rate: float) -> float:
            return sum(cf / ((1.0 + rate) ** (t + 1)) for t, cf in enumerate(net))

        f_lower = npv_at(lower)
        f_upper = npv_at(upper)
        if not (isfinite(f_lower) and isfinite(f_upper)):
            return None
        if f_lower == 0.0:
            return lower
        if f_upper == 0.0:
            return upper
        if (f_lower > 0.0) == (f_upper > 0.0):
            # No sign change in the bracket; IRR not identifiable.
            return None
        for _ in range(200):
            mid = 0.5 * (lower + upper)
            f_mid = npv_at(mid)
            if abs(f_mid) < 1.0e-9:
                return mid
            if (f_mid > 0.0) == (f_lower > 0.0):
                lower = mid
                f_lower = f_mid
            else:
                upper = mid
        return 0.5 * (lower + upper)

    @classmethod
    def _normalize_series(cls, name: str, series: Sequence[float]) -> list[float]:
        try:
            values = [float(v) for v in series]
        except TypeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"{name} must be a sequence of numbers") from exc
        for v in values:
            if not isfinite(v):
                raise ValueError(f"{name} values must be finite")
        return values

    @classmethod
    def _broadcast(cls, name: str, value: Sequence[float] | float, years: int) -> list[float]:
        if isinstance(value, (int, float)):
            cls._require_non_negative(name, float(value))
            return [float(value)] * years
        series = cls._normalize_series(name, value)
        if len(series) != years:
            raise ValueError(f"{name} length must match annual_revenue_musd length")
        for v in series:
            if v < 0.0:
                raise ValueError(f"{name} values must be non-negative")
        return series

    @classmethod
    def _broadcast_capex(
        cls, name: str, value: Sequence[float] | float, years: int
    ) -> list[float]:
        if isinstance(value, (int, float)):
            cls._require_non_negative(name, float(value))
            schedule = [0.0] * years
            schedule[0] = float(value)
            return schedule
        series = cls._normalize_series(name, value)
        if len(series) != years:
            raise ValueError(f"{name} length must match annual_revenue_musd length")
        for v in series:
            if v < 0.0:
                raise ValueError(f"{name} values must be non-negative")
        return series

    @staticmethod
    def _require_non_negative(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")

    @staticmethod
    def _require_fraction(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be between 0 and 1")
