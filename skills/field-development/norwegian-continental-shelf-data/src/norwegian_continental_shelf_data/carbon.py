"""Public NCS carbon-cost basis and emission-abatement screening.

Deterministic, dependency-free reference data and screening helpers for the
Norwegian carbon-cost regime (CO2 Tax Act on Petroleum Activities, the EU ETS,
and the NOx Fund) and a first-pass economic screening of an emission-reduction
measure (for example power-from-shore, waste-heat recovery, compressor upgrade,
or flaring reduction).

All figures are public and source-attributed to
[norskpetroleum.no](https://www.norskpetroleum.no/en/environment-and-technology/emissions-to-air/)
(run by the Norwegian Ministry of Energy and the Norwegian Offshore
Directorate), which may be reused with attribution and a link to the source.

This is a screening aid to orient a study; it does not replace a validated
NeqSim combustion/energy calculation, a certified emission inventory, or a
qualified commercial evaluation. Human review is required before any decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_SOURCE_URL = (
    "https://www.norskpetroleum.no/en/environment-and-technology/emissions-to-air/"
)
_ATTRIBUTION = (
    "Source: Norwegian Petroleum (www.norskpetroleum.no), Norwegian Ministry of "
    "Energy and Norwegian Offshore Directorate."
)
# Public alias for the source URL, re-exported by the package.
CARBON_COST_BASIS_SOURCE_URL = _SOURCE_URL

# Combustion CO2 emission factor for natural gas, derived from the published tax
# equivalence NOK 2.21/Sm3 gas <-> NOK 944/tonne CO2 (2025): 2.21/944*1000 =
# 2.34 kg CO2 per Sm3 gas. Used only for screening.
GAS_CO2_FACTOR_KG_PER_SM3 = 2.34

# Published carbon-cost rates by year. Each value is a public figure from the
# norskpetroleum.no "Emissions to air" page (see _SOURCE_URL).
_CO2_TAX_NOK_PER_SM3_GAS: Dict[int, float] = {2025: 2.21, 2026: 2.57}
_CO2_TAX_NOK_PER_LITRE_OIL: Dict[int, float] = {2025: 2.51, 2026: 2.92}
_CO2_TAX_NOK_PER_TONNE_CO2: Dict[int, float] = {2025: 944.0, 2026: 1098.0}
_GAS_VENTING_TAX_NOK_PER_SM3: Dict[int, float] = {2025: 20.17, 2026: 23.53}
# EU ETS allowance cost (approximate annual average, converted to NOK).
_EU_ETS_NOK_PER_TONNE_CO2: Dict[int, float] = {2025: 880.0}
# Combined effective CO2 cost (tax + ETS) as reported by norskpetroleum.no.
_COMBINED_CO2_NOK_PER_TONNE: Dict[int, float] = {2025: 1825.0}
# NOx Fund contribution for petroleum-sector participants.
_NOX_FUND_NOK_PER_KG: Dict[int, float] = {2025: 18.0}

# CO2 emissions from NCS petroleum activities in 2024 by source (share of total).
# Source: norskpetroleum.no, "CO2 emissions from petroleum activities in 2024,
# by source" (Norwegian Offshore Directorate).
CO2_SOURCE_SPLIT_2024: Dict[str, float] = {
    "turbines": 0.8355,
    "engines": 0.0652,
    "boilers": 0.0482,
    "flaring": 0.0454,
    "other_sources": 0.0047,
    "well_testing": 0.0009,
}

# Sector greenhouse-gas total (CO2 equivalent), for context only.
SECTOR_GHG_MILL_TONNES_CO2E: Dict[int, float] = {2024: 10.9}

# Fields supplied with power from shore (fully electrified) as reported in 2025.
POWER_FROM_SHORE_FIELDS: Tuple[str, ...] = (
    "Johan Sverdrup",
    "Edvard Grieg",
    "Ivar Aasen",
    "Gina Krog",
    "Ormen Lange",
    "Snohvit",
    "Troll A",
    "Goliat",
    "Valhall",
    "Martin Linge",
)
# Fields partially electrified / with combined-cycle gas turbines / offshore wind.
PARTIALLY_ELECTRIFIED_FIELDS: Tuple[str, ...] = ("Sleipner", "Gjoa")
CCGT_FIELDS: Tuple[str, ...] = ("Oseberg", "Snorre", "Eldfisk")
OFFSHORE_WIND_SUPPLIED_FIELDS: Tuple[str, ...] = ("Gullfaks", "Snorre")
# Power-from-shore projects under development (reported 2025).
POWER_FROM_SHORE_UNDER_DEVELOPMENT: Tuple[str, ...] = (
    "Draugen",
    "Njord",
    "Troll B",
    "Troll C",
    "Oseberg field centre",
    "Oseberg Sor",
)


def _latest_or_year(table: Dict[int, float], year: Optional[int], name: str) -> Tuple[int, float]:
    if not table:
        raise ValueError(f"No published values available for {name}.")
    if year is None:
        chosen = max(table)
        return chosen, table[chosen]
    if year in table:
        return year, table[year]
    # Fall back to the most recent published year not later than the request,
    # otherwise the earliest available; flag via the returned year.
    earlier = [y for y in table if y <= year]
    chosen = max(earlier) if earlier else min(table)
    return chosen, table[chosen]


@dataclass(frozen=True)
class CarbonCostBasis:
    """The public Norwegian carbon-cost basis for a given year."""

    year: int
    co2_tax_nok_per_sm3_gas: float
    co2_tax_nok_per_litre_oil: float
    co2_tax_nok_per_tonne_co2: float
    gas_venting_tax_nok_per_sm3: float
    eu_ets_nok_per_tonne_co2: Optional[float]
    combined_co2_nok_per_tonne: Optional[float]
    nox_fund_nok_per_kg: Optional[float]
    gas_co2_factor_kg_per_sm3: float
    source_url: str
    attribution: str
    note: str


def carbon_cost_basis(year: Optional[int] = None) -> CarbonCostBasis:
    """Return the public carbon-cost basis for ``year`` (default: latest known).

    Values are public figures from norskpetroleum.no (Emissions to air). When a
    requested ``year`` is not published, the most recent earlier published year
    is used and noted; refresh from the source for the current rate.
    """
    tax_year, co2_tax_gas = _latest_or_year(
        _CO2_TAX_NOK_PER_SM3_GAS, year, "CO2 tax per Sm3 gas"
    )
    _, co2_tax_oil = _latest_or_year(_CO2_TAX_NOK_PER_LITRE_OIL, year, "CO2 tax per litre oil")
    _, co2_tax_tonne = _latest_or_year(
        _CO2_TAX_NOK_PER_TONNE_CO2, year, "CO2 tax per tonne"
    )
    _, venting = _latest_or_year(
        _GAS_VENTING_TAX_NOK_PER_SM3, year, "gas venting tax per Sm3"
    )
    _, ets = _latest_or_year(_EU_ETS_NOK_PER_TONNE_CO2, year, "EU ETS per tonne")
    _, combined = _latest_or_year(
        _COMBINED_CO2_NOK_PER_TONNE, year, "combined CO2 cost per tonne"
    )
    _, nox = _latest_or_year(_NOX_FUND_NOK_PER_KG, year, "NOx Fund per kg")
    note = "Figures as published on norskpetroleum.no; verify current rates against the source."
    if year is not None and year != tax_year:
        note = (
            f"No published CO2 tax for {year}; using {tax_year} rates. "
            "Refresh from norskpetroleum.no for the current year."
        )
    return CarbonCostBasis(
        year=tax_year,
        co2_tax_nok_per_sm3_gas=co2_tax_gas,
        co2_tax_nok_per_litre_oil=co2_tax_oil,
        co2_tax_nok_per_tonne_co2=co2_tax_tonne,
        gas_venting_tax_nok_per_sm3=venting,
        eu_ets_nok_per_tonne_co2=ets,
        combined_co2_nok_per_tonne=combined,
        nox_fund_nok_per_kg=nox,
        gas_co2_factor_kg_per_sm3=GAS_CO2_FACTOR_KG_PER_SM3,
        source_url=_SOURCE_URL,
        attribution=_ATTRIBUTION,
        note=note,
    )


def combustion_co2_tonnes(fuel_gas_sm3_per_year: float) -> float:
    """Screening CO2 mass (tonnes/year) from burning ``fuel_gas_sm3_per_year``.

    Uses the public gas combustion factor (2.34 kg CO2/Sm3). This is a
    screening estimate; a validated NeqSim combustion calculation should be used
    for design-grade figures.
    """
    _require_non_negative("fuel_gas_sm3_per_year", fuel_gas_sm3_per_year)
    return fuel_gas_sm3_per_year * GAS_CO2_FACTOR_KG_PER_SM3 / 1000.0


@dataclass(frozen=True)
class CarbonCost:
    year: int
    co2_tonnes_per_year: float
    co2_tax_nok_per_year: float
    eu_ets_nok_per_year: Optional[float]
    combined_co2_nok_per_year: Optional[float]
    nox_cost_nok_per_year: Optional[float]
    total_nok_per_year: float
    source_url: str
    attribution: str


def annual_carbon_cost(
    *,
    co2_tonnes_per_year: float,
    nox_tonnes_per_year: float = 0.0,
    year: Optional[int] = None,
    use_combined_co2_cost: bool = True,
) -> CarbonCost:
    """Screening annual carbon cost (NOK/year) for an emission stream.

    ``use_combined_co2_cost`` applies the reported combined tax+ETS effective
    cost when available; otherwise the CO2 tax and EU ETS allowance costs are
    added separately. NOx is priced with the NOx Fund rate.
    """
    _require_non_negative("co2_tonnes_per_year", co2_tonnes_per_year)
    _require_non_negative("nox_tonnes_per_year", nox_tonnes_per_year)
    basis = carbon_cost_basis(year)
    co2_tax = co2_tonnes_per_year * basis.co2_tax_nok_per_tonne_co2
    ets = (
        co2_tonnes_per_year * basis.eu_ets_nok_per_tonne_co2
        if basis.eu_ets_nok_per_tonne_co2 is not None
        else None
    )
    combined = (
        co2_tonnes_per_year * basis.combined_co2_nok_per_tonne
        if basis.combined_co2_nok_per_tonne is not None
        else None
    )
    if use_combined_co2_cost and combined is not None:
        co2_total = combined
    else:
        co2_total = co2_tax + (ets or 0.0)
    nox_cost = (
        nox_tonnes_per_year * 1000.0 * basis.nox_fund_nok_per_kg
        if basis.nox_fund_nok_per_kg is not None
        else None
    )
    total = co2_total + (nox_cost or 0.0)
    return CarbonCost(
        year=basis.year,
        co2_tonnes_per_year=round(co2_tonnes_per_year, 4),
        co2_tax_nok_per_year=round(co2_tax, 2),
        eu_ets_nok_per_year=None if ets is None else round(ets, 2),
        combined_co2_nok_per_year=None if combined is None else round(combined, 2),
        nox_cost_nok_per_year=None if nox_cost is None else round(nox_cost, 2),
        total_nok_per_year=round(total, 2),
        source_url=basis.source_url,
        attribution=basis.attribution,
    )


@dataclass(frozen=True)
class AbatementScreening:
    """Screening economics of one emission-abatement measure."""

    measure: str
    co2_avoided_tonnes_per_year: float
    nox_avoided_tonnes_per_year: float
    avoided_carbon_cost_nok_per_year: float
    avoided_fuel_value_nok_per_year: float
    added_energy_cost_nok_per_year: float
    net_annual_saving_nok_per_year: float
    capex_nok: float
    simple_payback_years: Optional[float]
    npv_nok: float
    breakeven_co2_price_nok_per_tonne: Optional[float]
    verdict: str
    assumptions: List[str] = field(default_factory=list)
    source_url: str = _SOURCE_URL
    attribution: str = _ATTRIBUTION


def abatement_screening(
    *,
    measure: str,
    fuel_gas_avoided_sm3_per_year: float = 0.0,
    co2_avoided_tonnes_per_year: Optional[float] = None,
    nox_avoided_tonnes_per_year: float = 0.0,
    capex_nok: float,
    added_energy_cost_nok_per_year: float = 0.0,
    gas_price_nok_per_sm3: float = 0.0,
    horizon_years: int = 15,
    discount_rate: float = 0.08,
    year: Optional[int] = None,
    use_combined_co2_cost: bool = True,
) -> AbatementScreening:
    """Screen the economics of an emission-abatement measure on the NCS.

    Combine (a) avoided Norwegian carbon cost (CO2 tax + EU ETS, plus NOx Fund)
    and (b) the value of fuel gas no longer burnt, against the measure CAPEX and
    any added energy cost (for example imported power for electrification). A
    simple payback, a discounted NPV over ``horizon_years`` at ``discount_rate``,
    and the breakeven CO2 price are returned.

    Provide either ``fuel_gas_avoided_sm3_per_year`` (CO2 avoided is derived from
    the public gas combustion factor) or ``co2_avoided_tonnes_per_year``. This is
    a screening result; a validated NeqSim energy/combustion model and a
    qualified commercial review are required before any decision.
    """
    _require_positive("capex_nok", capex_nok)
    _require_non_negative("fuel_gas_avoided_sm3_per_year", fuel_gas_avoided_sm3_per_year)
    _require_non_negative("added_energy_cost_nok_per_year", added_energy_cost_nok_per_year)
    _require_non_negative("gas_price_nok_per_sm3", gas_price_nok_per_sm3)
    _require_non_negative("nox_avoided_tonnes_per_year", nox_avoided_tonnes_per_year)
    _require_positive("horizon_years", horizon_years)
    _require_fraction("discount_rate", discount_rate)

    assumptions: List[str] = []
    if co2_avoided_tonnes_per_year is None:
        co2_avoided = combustion_co2_tonnes(fuel_gas_avoided_sm3_per_year)
        assumptions.append(
            "CO2 avoided derived from avoided fuel gas using the public "
            f"combustion factor {GAS_CO2_FACTOR_KG_PER_SM3} kg CO2/Sm3."
        )
    else:
        _require_non_negative("co2_avoided_tonnes_per_year", co2_avoided_tonnes_per_year)
        co2_avoided = co2_avoided_tonnes_per_year

    carbon = annual_carbon_cost(
        co2_tonnes_per_year=co2_avoided,
        nox_tonnes_per_year=nox_avoided_tonnes_per_year,
        year=year,
        use_combined_co2_cost=use_combined_co2_cost,
    )
    avoided_carbon_cost = carbon.total_nok_per_year
    avoided_fuel_value = fuel_gas_avoided_sm3_per_year * gas_price_nok_per_sm3
    if gas_price_nok_per_sm3 > 0.0 and fuel_gas_avoided_sm3_per_year > 0.0:
        assumptions.append(
            "Avoided fuel gas valued at the supplied gas price; screening only."
        )
    net_annual = avoided_carbon_cost + avoided_fuel_value - added_energy_cost_nok_per_year

    if net_annual > 0.0:
        simple_payback = round(capex_nok / net_annual, 2)
    else:
        simple_payback = None

    # Discounted NPV of the annual net saving less the up-front CAPEX.
    npv = -capex_nok
    for t in range(1, int(horizon_years) + 1):
        npv += net_annual / ((1.0 + discount_rate) ** t)

    # Breakeven CO2 price (NOK/tonne) that makes NPV = 0, holding fuel value and
    # added energy cost fixed. Annuity factor over the horizon.
    breakeven: Optional[float] = None
    if co2_avoided > 0.0:
        annuity = sum(1.0 / ((1.0 + discount_rate) ** t) for t in range(1, int(horizon_years) + 1))
        required_annual = capex_nok / annuity
        needed_from_co2 = required_annual - avoided_fuel_value + added_energy_cost_nok_per_year
        breakeven = round(max(needed_from_co2, 0.0) / co2_avoided, 2)

    verdict = _abatement_verdict(npv, simple_payback)

    return AbatementScreening(
        measure=measure,
        co2_avoided_tonnes_per_year=round(co2_avoided, 4),
        nox_avoided_tonnes_per_year=round(nox_avoided_tonnes_per_year, 4),
        avoided_carbon_cost_nok_per_year=round(avoided_carbon_cost, 2),
        avoided_fuel_value_nok_per_year=round(avoided_fuel_value, 2),
        added_energy_cost_nok_per_year=round(added_energy_cost_nok_per_year, 2),
        net_annual_saving_nok_per_year=round(net_annual, 2),
        capex_nok=round(capex_nok, 2),
        simple_payback_years=simple_payback,
        npv_nok=round(npv, 2),
        breakeven_co2_price_nok_per_tonne=breakeven,
        verdict=verdict,
        assumptions=assumptions,
    )


def _abatement_verdict(npv: float, simple_payback: Optional[float]) -> str:
    """Classify a screening abatement measure by NPV and payback."""
    if npv > 0.0 and simple_payback is not None and simple_payback <= 5.0:
        return "attractive"
    if npv > 0.0:
        return "marginal_positive"
    if simple_payback is not None:
        return "review"
    return "unattractive"


def emission_source_split(year: int = 2024) -> Dict[str, float]:
    """Return the published CO2-by-source split (share of total) for ``year``.

    Only 2024 is bundled; refresh from norskpetroleum.no for other years.
    """
    if year != 2024:
        raise ValueError(
            "Only the 2024 CO2-by-source split is bundled; refresh from "
            "norskpetroleum.no (Emissions to air) for other years."
        )
    return dict(CO2_SOURCE_SPLIT_2024)


def _require_positive(name: str, value: float) -> None:
    if value is None or value <= 0.0:
        raise ValueError(f"{name} must be a positive number, got {value!r}.")


def _require_non_negative(name: str, value: float) -> None:
    if value is None or value < 0.0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}.")


def _require_fraction(name: str, value: float) -> None:
    if value is None or not (0.0 <= value < 1.0):
        raise ValueError(f"{name} must be in [0, 1), got {value!r}.")
