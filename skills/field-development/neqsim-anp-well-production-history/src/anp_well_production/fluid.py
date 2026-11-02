"""Fluid basis for a NeqSim model from the ANP by-well rate files.

The by-well rate files carry, per well and month, the oil API gravity, the gas
composition (percent by volume) and the gross calorific value of the gas. They
are sampled-stream data of the producing installation, not a PVT report. This
module turns them into a declared fluid basis with its warnings so that a fluid
agent can characterise a stream and recombine it, without presenting the data as
a wellstream composition.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from .parse import GAS_COMPOSITION_KEYS

NEQSIM_COMPONENTS = {
    "methane": "methane",
    "ethane": "ethane",
    "propane": "propane",
    "iso_butane": "i-butane",
    "butane": "n-butane",
    "iso_pentane": "i-pentane",
    "n_pentane": "n-pentane",
    "hexanes": "n-hexane",
    "heptanes": "n-heptane",
    "octanes": "n-octane",
    "nonanes": "n-nonane",
    "decanes": "nC10",
    "undecanes": "nC11",
    "oxygen": "oxygen",
    "nitrogen": "nitrogen",
    "carbon_dioxide": "CO2",
}
"""ANP composition key to NeqSim component name (all names exist in the database)."""

WATER_DENSITY_60F = 999.016
"""Water density at 60 degF in kg/m3, the API gravity reference."""


def oil_density_kg_m3(api: float) -> float:
    """Stock-tank oil density at 60 degF from API gravity.

    Args:
        api: API gravity in degrees.

    Returns:
        Density in kg/m3 at 15.56 C and atmospheric pressure.

    Raises:
        ValueError: ``api`` is not above -131.5.
    """
    if api <= -131.5:
        raise ValueError("API gravity must be above -131.5")
    return 141.5 / (131.5 + api) * WATER_DENSITY_60F


def gas_composition(rec: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the normalised gas composition of a record.

    Args:
        rec: Record of the ``well_monthly_rates`` family.

    Returns:
        ``None`` when the record has no composition, else a dict with
        ``mole_fraction`` (NeqSim component name to fraction, normalised to one),
        ``reported_sum_pct`` and ``closure_ok`` (reported sum within 98 to 102).
    """
    comp = rec.get("gas_composition_pct")
    if not comp:
        return None
    total = sum(comp.values())
    if total <= 0:
        return None
    frac = {NEQSIM_COMPONENTS[k]: comp[k] / total for k in GAS_COMPOSITION_KEYS if comp.get(k)}
    return {"mole_fraction": frac, "reported_sum_pct": total, "closure_ok": 98.0 <= total <= 102.0}


def fluid_basis(rec: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a declared fluid basis from one by-well rate record.

    Args:
        rec: Record of the ``well_monthly_rates`` family (see
            :func:`anp_well_production.parse.normalize`).

    Returns:
        A dict for a fluid-characterisation hand-off: identity and period,
        ``api``, ``stock_tank_density_kg_m3``, ``gor_sm3_sm3``, ``gas`` (see
        :func:`gas_composition`), ``gcv_kj_m3`` (gross calorific value, when
        given), ``analysis_period`` and a ``warnings`` list. Fields that the
        record lacks are ``None``.
    """
    api = rec.get("api")
    liquid, gas = rec.get("liquid_m3d"), rec.get("gas_total_km3d")
    gor = gas * 1000.0 / liquid if (liquid and liquid > 0 and gas is not None) else None
    comp = gas_composition(rec)
    warnings: List[str] = [
        "Composition is the gas stream sampled at the installation, not a wellstream or reservoir fluid.",
        "No separator pressure or temperature, no C7+ molecular weight or density and no saturation pressure are published.",
        "API gravity is the stock-tank oil of the installation stream and can blend several wells.",
    ]
    if comp is None:
        warnings.append("No gas composition for this well and month.")
    elif not comp["closure_ok"]:
        warnings.append("Reported composition sums to %.1f %%; it was normalised." % comp["reported_sum_pct"])
    if comp is not None and comp["mole_fraction"].get("oxygen", 0.0) > 0.005:
        warnings.append(
            "Oxygen above 0.5 %% (%.2f %%) is not physical for produced gas: the oxygen, nitrogen and "
            "carbon dioxide columns may be mislabelled in the operator report (seen for Mero in 2023-12); "
            "check against the gross calorific value before use." % (100.0 * comp["mole_fraction"]["oxygen"])
        )
    if api is None:
        warnings.append("No API gravity for this well and month.")
    if gor is None:
        warnings.append("Gas-liquid ratio not computable: no liquid production in the month.")
    return {
        "well": rec.get("well"),
        "field": rec.get("field"),
        "installation": rec.get("installation"),
        "period": rec.get("period"),
        "analysis_period": rec.get("analysis_period"),
        "api": api,
        "stock_tank_density_kg_m3": None if api is None else oil_density_kg_m3(api),
        "gor_sm3_sm3": gor,
        "gas": comp,
        "gcv_kj_m3": rec.get("gcv_kj_m3"),
        "warnings": warnings,
        "source": "ANP open data, Produção por Poço (by-well rate files)",
    }


def latest_fluid_basis(history: Iterable[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Fluid basis of the newest month that has both API gravity and composition.

    Args:
        history: Records of one well or installation sorted by period.

    Returns:
        :func:`fluid_basis` of the newest complete record, or ``None``.
    """
    for rec in sorted(history, key=lambda r: r["period"], reverse=True):
        if rec.get("api") is not None and rec.get("gas_composition_pct"):
            return fluid_basis(rec)
    return None
