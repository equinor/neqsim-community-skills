"""Screening helpers for Brazilian offshore gas export and host capacity.

All functions are arithmetic on caller-supplied numbers. No tariff is public in
Brazil, so the net-back uses the MME share of the delivered price, not a tariff.
"""

from __future__ import annotations

from typing import Dict, Optional

BBL_TO_SM3 = 0.158987
DEFAULT_HEATING_VALUE_MMBTU_PER_SM3 = 0.036
ANP_CO2_SPEC_MOL_PCT = 3.0
MME_MIDSTREAM_SHARE = 0.46


def co2_removal_fraction(
    co2_mol_pct: float, spec_mol_pct: float = ANP_CO2_SPEC_MOL_PCT
) -> float:
    """Fraction of the feed-gas moles that must be removed as CO2 to reach the CO2 spec.

    Pure CO2 removal: x = (y - s) / (1 - s) with y and s as mole fractions. A
    declared 19.5 mol % gas needs about 17 % of its moles removed for a 3 mol % spec.
    """
    if not 0.0 <= co2_mol_pct <= 100.0 or not 0.0 <= spec_mol_pct < 100.0:
        raise ValueError("CO2 content and spec must be mol % between 0 and 100")
    y, s = co2_mol_pct / 100.0, spec_mol_pct / 100.0
    return 0.0 if y <= s else (y - s) / (1.0 - s)


def wellhead_netback(
    city_gate_usd_mmbtu: float, midstream_share: float = MME_MIDSTREAM_SHARE
) -> float:
    """Wellhead gas net-back (USD/MMBtu) after escoamento plus processing.

    ``midstream_share`` defaults to the MME estimate (46 % of the delivered price),
    which is the only public number; it is not an offshore tariff.
    """
    if city_gate_usd_mmbtu < 0.0 or not 0.0 <= midstream_share <= 1.0:
        raise ValueError("city-gate price must be >= 0 and midstream share within 0..1")
    return city_gate_usd_mmbtu * (1.0 - midstream_share)


def gas_export_upside(
    volume_mmbbl: float,
    gor_sm3_sm3: float,
    export_fraction: float,
    netback: float,
    heating_value_mmbtu_per_sm3: float = DEFAULT_HEATING_VALUE_MMBTU_PER_SM3,
    oil_net_price_usd_bbl: Optional[float] = None,
) -> Dict[str, float]:
    """Undiscounted gas export revenue from the recoverable oil volume and a GOR.

    ``export_fraction`` is the share of produced gas that can be exported after
    fuel, flare and re-injection. With ``oil_net_price_usd_bbl`` the result also
    reports the gas revenue as a percentage of oil revenue (about 8 % in the
    2026-10-14 evaluation at 5.9 USD/MMBtu and 50 % exportable gas).
    """
    if volume_mmbbl < 0.0 or gor_sm3_sm3 < 0.0 or netback < 0.0:
        raise ValueError("volume, GOR and net-back must be >= 0")
    if not 0.0 <= export_fraction <= 1.0:
        raise ValueError("export_fraction must be within 0..1")
    gas_sm3 = volume_mmbbl * 1.0e6 * BBL_TO_SM3 * gor_sm3_sm3
    exportable_mmbtu = gas_sm3 * heating_value_mmbtu_per_sm3 * export_fraction
    revenue_musd = exportable_mmbtu * netback / 1.0e6
    out = {
        "gas_produced_gsm3": gas_sm3 / 1.0e9,
        "exportable_mmmbtu": exportable_mmbtu / 1.0e6,
        "gross_gas_revenue_musd": revenue_musd,
    }
    if oil_net_price_usd_bbl is not None:
        oil_revenue = volume_mmbbl * oil_net_price_usd_bbl
        out["oil_revenue_musd"] = oil_revenue
        out["gas_pct_of_oil_revenue"] = (
            100.0 * revenue_musd / oil_revenue if oil_revenue > 0.0 else float("nan")
        )
    return out


def host_capacity_check(
    host_nameplate_kbd: float,
    host_demand_kbd: float,
    compression_limit_kbd: Optional[float] = None,
    additional_demand_kbd: float = 0.0,
) -> Dict[str, object]:
    """Host oil ullage when gas handling or compression can bind before oil nameplate.

    ``compression_limit_kbd`` is the oil rate at which the host gas train limits
    (from a process model or the host owner). A tie-back competes for gas
    handling, so the effective limit is the lower of nameplate and that limit.
    """
    for label, val in (
        ("nameplate", host_nameplate_kbd),
        ("demand", host_demand_kbd),
        ("additional", additional_demand_kbd),
    ):
        if val < 0.0:
            raise ValueError("{} must be >= 0".format(label))
    if compression_limit_kbd is not None and compression_limit_kbd < 0.0:
        raise ValueError("compression_limit_kbd must be >= 0")
    limit = host_nameplate_kbd
    binding = "oil_nameplate"
    if compression_limit_kbd is not None and compression_limit_kbd < host_nameplate_kbd:
        limit = compression_limit_kbd
        binding = "gas_compression"
    ullage = max(0.0, limit - host_demand_kbd)
    return {
        "effective_limit_kbd": limit,
        "binding_constraint": binding,
        "ullage_kbd": ullage,
        "nameplate_ullage_kbd": max(0.0, host_nameplate_kbd - host_demand_kbd),
        "ullage_overstatement_kbd": max(0.0, host_nameplate_kbd - host_demand_kbd)
        - ullage,
        "additional_demand_kbd": additional_demand_kbd,
        "fits": additional_demand_kbd <= ullage,
    }
