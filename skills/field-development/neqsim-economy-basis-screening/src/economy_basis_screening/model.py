from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

# Public, indicative screening ranges only — not investment guidance.
_TYPICAL_DISCOUNT_RANGE = (0.06, 0.12)
_KNOWN_TAX_REGIMES = ("generic", "norwegian-ncs", "uk", "us", "none")


@dataclass(frozen=True)
class EconomyBasisResult:
    currency: str
    gas_price_per_sm3: float
    oil_price_per_bbl: float
    discount_rate: float
    real_terms: bool
    inflation_rate: float
    tax_regime: str
    discount_rate_flag: str
    tax_regime_recognized: bool
    basis_warning: str
    flags: tuple[str, ...]
    neqsim_available: bool
    assumptions: tuple[str, ...]


class EconomyBasisModel:
    """Educational economy-basis assembly and screening placeholder.

    Collects and range-checks the economic assumptions (prices, discount rate,
    currency, inflation, tax regime) that feed a downstream asset-value (NPV)
    screening. It is a transparent placeholder only: real fiscal and economic
    evaluation must come from a validated NeqSim field-economics workflow
    (``neqsim.process.util.fielddevelopment``) or the NeqSim MCP
    ``runFieldEconomics`` tool and qualified commercial review.
    """

    def __init__(
        self,
        *,
        typical_discount_range: tuple[float, float] = _TYPICAL_DISCOUNT_RANGE,
    ) -> None:
        low, high = typical_discount_range
        if not (0.0 < low < high < 1.0):
            raise ValueError("typical_discount_range must be 0 < low < high < 1")
        self.typical_discount_range = typical_discount_range

    def evaluate(
        self,
        *,
        gas_price_per_sm3: float,
        oil_price_per_bbl: float,
        discount_rate: float,
        currency: str = "USD",
        inflation_rate: float = 0.0,
        real_terms: bool = True,
        tax_regime: str = "generic",
    ) -> EconomyBasisResult:
        self._require_non_negative("gas_price_per_sm3", gas_price_per_sm3)
        self._require_non_negative("oil_price_per_bbl", oil_price_per_bbl)
        self._require_finite("discount_rate", discount_rate)
        if not (0.0 <= discount_rate < 1.0):
            raise ValueError("discount_rate must be between 0 and 1")
        self._require_finite("inflation_rate", inflation_rate)
        if inflation_rate < 0.0:
            raise ValueError("inflation_rate must be non-negative")

        currency_norm = str(currency).strip().upper() or "USD"
        tax_norm = str(tax_regime).strip().lower()
        tax_recognized = tax_norm in _KNOWN_TAX_REGIMES

        low, high = self.typical_discount_range
        if discount_rate < low:
            discount_flag = "low"
        elif discount_rate > high:
            discount_flag = "high"
        else:
            discount_flag = "ok"

        flags: list[str] = []
        if discount_flag != "ok":
            flags.append(
                f"discount_rate {discount_rate:.3f} is {discount_flag} "
                f"vs typical {low:.2f}-{high:.2f}"
            )
        if not tax_recognized:
            flags.append(
                f"tax_regime {tax_regime!r} is not in the public screening set "
                f"{_KNOWN_TAX_REGIMES}"
            )
        if gas_price_per_sm3 == 0.0 and oil_price_per_bbl == 0.0:
            flags.append("both gas and oil prices are zero — no revenue basis")
        if not real_terms and inflation_rate == 0.0:
            flags.append(
                "nominal terms selected but inflation_rate is zero — check consistency"
            )

        basis_warning = self._basis_warning(discount_flag, tax_recognized, flags)

        return EconomyBasisResult(
            currency=currency_norm,
            gas_price_per_sm3=round(gas_price_per_sm3, 6),
            oil_price_per_bbl=round(oil_price_per_bbl, 4),
            discount_rate=round(discount_rate, 6),
            real_terms=bool(real_terms),
            inflation_rate=round(inflation_rate, 6),
            tax_regime=tax_norm,
            discount_rate_flag=discount_flag,
            tax_regime_recognized=tax_recognized,
            basis_warning=basis_warning,
            flags=tuple(flags),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational economy-basis assembly and screening placeholder only.",
                "Prices, discount rate, and tax regime are user inputs, not market data.",
                "Discount-rate range check is indicative, not investment guidance.",
                "Tax regime is only checked against a small public name set.",
                "No fiscal, financing, currency-forward, or escalation modelling is performed.",
                "Use NeqSim field-economics or MCP runFieldEconomics for real evaluation.",
            ),
        )

    @staticmethod
    def _basis_warning(
        discount_flag: str, tax_recognized: bool, flags: list[str]
    ) -> str:
        if not flags:
            return "ok"
        if discount_flag != "ok" or not tax_recognized:
            return "watch"
        return "watch" if flags else "ok"

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")
