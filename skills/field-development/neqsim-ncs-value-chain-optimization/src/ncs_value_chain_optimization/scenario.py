"""Scenario schema ``ncs_value_chain_scenario.v1`` and defaults.

A scenario is plain JSON so an enterprise binding skill can emit it from
governed data (PDM actuals, RNB forecasts, Gassled tariffs, gas-quality specs,
UMM outages) without this public skill touching those systems.

Every default below is a stated public screening assumption, overridable.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

SCHEMA = "ncs_value_chain_scenario.v1"

DEFAULT_SCENARIO: Dict[str, Any] = {
    "schema": SCHEMA,
    "name": "public screening base case",
    "years": [2026, 2040],
    "currency": "NOK",
    "discount_rate": 0.08,
    "prices": {
        # aligned with neqsim ...valuechain.EconomicParameters defaults
        "gas_nok_per_sm3": 3.0,
        "liquid_nok_per_sm3": 4500.0,
        # relative gas price by exit market (1.0 = hub parity)
        "gas_exit_factor": {"MARKET_DE": 1.0, "MARKET_BE": 1.0, "MARKET_FR": 1.0, "MARKET_UK": 1.0,
                            "MARKET_DK_PL": 1.0, "MARKET_LNG": 1.0, "MARKET_NO_GAS": 0.9},
    },
    "tariffs": {
        # screening transport + processing cost per unit shipped; Gassled tariffs are
        # governed commercial data - bind them from enterprise-gassled-tariff
        "gas_nok_per_sm3_default": 0.12,
        "gas_nok_per_sm3_by_arc": {},
        "liquid_nok_per_sm3_default": 30.0,
        "liquid_nok_per_sm3_by_arc": {},
    },
    "capacity_overrides": {},     # {element_id: capacity}
    "outages": [],                # [{"element": id, "years": [y..], "available_fraction": 0.5}]
    "forecast_overrides": {},     # {entity: {"gas_msm3d": {year: v}, "liquid_sm3d": {...}}}
    "field_cost_nok_per_sm3oe": {},  # {entity: NOK per Sm3 oe} e.g. CO2 tax x intensity, or OPEX
    "include_discoveries": True,
    "include_not_evaluated": False,
    "tieback_max_km": 60.0,
    "max_paths_per_entity": 20,
    "provenance": {"prices": "public screening default", "tariffs": "public screening default",
                   "forecast": "Arps decline capped by Sodir remaining reserves"},
}


def make_scenario(**overrides: Any) -> Dict[str, Any]:
    """Deep-merge overrides into the default scenario."""
    scenario = copy.deepcopy(DEFAULT_SCENARIO)
    _merge(scenario, overrides)
    return scenario


def _merge(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def validate_scenario(scenario: Dict[str, Any]) -> List[str]:
    """Return a list of problems; empty means usable."""
    problems = []
    if scenario.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    years = scenario.get("years") or []
    if len(years) != 2 or years[0] > years[1]:
        problems.append("years must be [first, last]")
    if not 0 <= float(scenario.get("discount_rate", 0)) < 1:
        problems.append("discount_rate must be a fraction in [0, 1)")
    for key in ("gas_nok_per_sm3", "liquid_nok_per_sm3"):
        if float(scenario.get("prices", {}).get(key, 0)) <= 0:
            problems.append(f"prices.{key} must be positive")
    for outage in scenario.get("outages", []):
        if not 0 <= float(outage.get("available_fraction", 0)) <= 1:
            problems.append(f"outage {outage.get('element')}: available_fraction must be in [0, 1]")
    return problems
