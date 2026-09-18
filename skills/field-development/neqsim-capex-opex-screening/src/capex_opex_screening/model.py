from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class CapexOpexResult:
    bare_equipment_cost_musd: float
    installation_factor: float
    contingency_fraction: float
    installed_capex_musd: float
    total_capex_musd: float
    annual_opex_musd: float
    annual_energy_cost_musd: float
    total_annual_opex_musd: float
    project_life_years: float
    lifecycle_opex_musd: float
    total_cost_of_ownership_musd: float
    capex_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class CapexOpexModel:
    """Educational factored CAPEX/OPEX screening placeholder.

    Estimates a total installed CAPEX from a bare equipment cost using a public
    installation (Lang/Hand-style) factor and a contingency allowance, then adds
    a simple OPEX (a fraction of CAPEX per year plus an annual energy cost). It is
    a transparent placeholder only: real cost estimates must come from the
    validated NeqSim ``CostEstimationCalculator`` (Turton/Peters/Ulrich/Seider
    correlations with CEPCI escalation) and the NeqSim MCP ``runFieldEconomics``
    workflow, with a qualified cost-engineering review.
    """

    def __init__(self, *, watch_capex_musd: float = 1000.0) -> None:
        if watch_capex_musd <= 0.0:
            raise ValueError("watch_capex_musd must be positive")
        self.watch_capex_musd = watch_capex_musd

    def evaluate(
        self,
        *,
        bare_equipment_cost_musd: float,
        installation_factor: float = 3.5,
        contingency_fraction: float = 0.2,
        opex_fraction_of_capex_per_year: float = 0.04,
        annual_energy_use_mwh: float = 0.0,
        energy_price_usd_per_mwh: float = 0.0,
        project_life_years: float = 20.0,
    ) -> CapexOpexResult:
        self._require_positive("bare_equipment_cost_musd", bare_equipment_cost_musd)
        self._require_at_least("installation_factor", installation_factor, 1.0)
        self._require_fraction("contingency_fraction", contingency_fraction)
        self._require_fraction(
            "opex_fraction_of_capex_per_year", opex_fraction_of_capex_per_year
        )
        self._require_non_negative("annual_energy_use_mwh", annual_energy_use_mwh)
        self._require_non_negative("energy_price_usd_per_mwh", energy_price_usd_per_mwh)
        self._require_positive("project_life_years", project_life_years)

        installed_capex = bare_equipment_cost_musd * installation_factor
        total_capex = installed_capex * (1.0 + contingency_fraction)

        annual_opex = total_capex * opex_fraction_of_capex_per_year
        # Energy cost: MWh/year * USD/MWh -> USD/year -> MUSD/year (1e6 USD).
        annual_energy_cost = (annual_energy_use_mwh * energy_price_usd_per_mwh) / 1.0e6
        total_annual_opex = annual_opex + annual_energy_cost

        lifecycle_opex = total_annual_opex * project_life_years
        total_cost_of_ownership = total_capex + lifecycle_opex

        warning = self._capex_warning(total_capex)

        return CapexOpexResult(
            bare_equipment_cost_musd=round(bare_equipment_cost_musd, 3),
            installation_factor=round(installation_factor, 4),
            contingency_fraction=round(contingency_fraction, 4),
            installed_capex_musd=round(installed_capex, 3),
            total_capex_musd=round(total_capex, 3),
            annual_opex_musd=round(annual_opex, 3),
            annual_energy_cost_musd=round(annual_energy_cost, 3),
            total_annual_opex_musd=round(total_annual_opex, 3),
            project_life_years=round(project_life_years, 3),
            lifecycle_opex_musd=round(lifecycle_opex, 3),
            total_cost_of_ownership_musd=round(total_cost_of_ownership, 3),
            capex_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational factored CAPEX/OPEX screening placeholder only.",
                "Total installed CAPEX = bare equipment cost * installation factor.",
                "A public Lang/Hand-style installation factor and contingency are user inputs, not a quote.",
                "OPEX is a fixed fraction of CAPEX per year plus a simple annual energy cost.",
                "No CEPCI escalation, material/pressure factors, location factor, or currency conversion is applied.",
                "No phasing, financing, depreciation, or abandonment cost is modelled.",
                "Use NeqSim CostEstimationCalculator and MCP runFieldEconomics for real cost estimates.",
            ),
        )

    def _capex_warning(self, total_capex_musd: float) -> str:
        if total_capex_musd >= self.watch_capex_musd:
            return "high"
        if total_capex_musd >= 0.5 * self.watch_capex_musd:
            return "watch"
        return "ok"

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    @classmethod
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")

    @classmethod
    def _require_at_least(cls, name: str, value: float, minimum: float) -> None:
        cls._require_finite(name, value)
        if value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")

    @classmethod
    def _require_fraction(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be between 0 and 1")
