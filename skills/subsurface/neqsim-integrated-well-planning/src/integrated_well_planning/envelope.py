"""Operating-envelope table: parameter, condition, limit, source, margin, predicted value, status, action.

Fail-closed rules:

* a limit with no source (or ``limit_basis`` NONE) is ``NEEDS_REVIEW``;
* a limit whose basis is not ``APPROVED`` (SYNTHETIC / ASSUMED) still gets an *indicative* status but the row status
  stays ``NEEDS_REVIEW`` - calculated values are never promoted to verified limits;
* a row without a predicted value is ``NOT_ASSESSED``;
* margins are computed against the effective limit (limit with the supplied design margin applied), not against the raw limit.

The ``warn_utilisation`` threshold is a presentation convention (default 0.9 of the limit), not a design factor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from .registers import get_path

STATUSES = ("PASS", "WARN", "FAIL", "NEEDS_REVIEW", "NOT_ASSESSED")
LIMIT_BASES = ("APPROVED", "SYNTHETIC", "ASSUMED", "NONE")


@dataclass
class EnvelopeRow:
    """One row of the operating-envelope table."""

    id: str
    parameter: str
    condition: str
    unit: str
    min_limit: Optional[float]
    max_limit: Optional[float]
    limit_source: str
    limit_basis: str
    design_margin: str
    predicted: Optional[float]
    predicted_source: str
    margin_to_limit: Optional[float]
    utilisation: Optional[float]
    indicative_status: str
    status: str
    action: str


def evaluate_row(row_id: str, parameter: str, condition: str, unit: str, predicted: Optional[float], predicted_source: str, min_limit: Optional[float] = None,
                 max_limit: Optional[float] = None, limit_source: str = "", limit_basis: str = "NONE", margin_factor: Optional[float] = None, margin_source: str = "",
                 warn_utilisation: float = 0.9) -> EnvelopeRow:
    """Build one envelope row applying the fail-closed rules.

    Args:
        margin_factor: optional design margin; the effective maximum is ``max_limit / margin_factor`` and the effective minimum is
            ``min_limit * margin_factor`` (only applied when a ``margin_source`` is given).
    """
    if limit_basis not in LIMIT_BASES:
        raise ValueError("limit_basis must be one of {}".format(LIMIT_BASES))
    applied = bool(margin_factor and margin_source)
    eff_max = max_limit / margin_factor if (max_limit is not None and applied) else max_limit
    eff_min = min_limit * margin_factor if (min_limit is not None and applied) else min_limit
    margin_txt = ("factor {} ({})".format(margin_factor, margin_source) if applied else ("factor {} given without source - IGNORED".format(margin_factor) if margin_factor else "none supplied"))
    margin: Optional[float] = None
    util: Optional[float] = None
    ind = "NOT_ASSESSED"
    if predicted is not None and predicted == predicted:
        margins = []
        if eff_max is not None:
            margins.append(eff_max - predicted)
            util = predicted / eff_max if eff_max else None
        if eff_min is not None:
            margins.append(predicted - eff_min)
            if eff_max is None:
                util = eff_min / predicted if predicted else None
        if margins:
            margin = min(margins)
            if margin < 0:
                ind = "FAIL"
            elif util is not None and util >= warn_utilisation:
                ind = "WARN"
            else:
                ind = "PASS"
        else:
            ind = "NOT_ASSESSED"
    if predicted is None or predicted != predicted:
        status, action = "NOT_ASSESSED", "calculate or supply the predicted value"
    elif not limit_source or limit_basis == "NONE" or (min_limit is None and max_limit is None):
        status, action = "NEEDS_REVIEW", "supply the approved limit with its source (standard clause, datasheet or operator limit)"
    elif limit_basis != "APPROVED":
        status, action = "NEEDS_REVIEW", "replace the {} limit by an approved limit; indicative result is {}".format(limit_basis, ind)
    else:
        status = ind
        action = {"PASS": "none", "WARN": "review margin; consider mitigation", "FAIL": "limit exceeded: redesign or change operating strategy", "NOT_ASSESSED": "no applicable limit"}[ind]
    return EnvelopeRow(row_id, parameter, condition, unit, min_limit, max_limit, limit_source, limit_basis, margin_txt, predicted, predicted_source,
                       margin, util, ind, status, action)


def _limits(basis: Dict[str, Any], parameter: str) -> Dict[str, Any]:
    for lim in get_path(basis, "limits") or []:
        if lim.get("parameter") == parameter:
            return lim
    return {}


def build_envelope(basis: Dict[str, Any], results: Dict[str, Any], warn_utilisation: float = 0.9) -> List[EnvelopeRow]:
    """Assemble the envelope rows from the model results using limits supplied in ``basis.limits``."""
    rows: List[EnvelopeRow] = []

    def add(parameter: str, condition: str, unit: str, predicted: Optional[float], source: str) -> None:
        lim = _limits(basis, parameter)
        rows.append(evaluate_row("E{:02d}".format(len(rows) + 1), parameter, condition, unit, predicted, source, lim.get("min"), lim.get("max"), lim.get("source", ""),
                                 lim.get("limit_basis", "NONE" if not lim else "ASSUMED"), lim.get("margin_factor"), lim.get("margin_source", ""), warn_utilisation))

    prod = (results.get("producer") or {}).get("base")
    inj = (results.get("injector") or {}).get("base")
    if prod:
        tub = prod.get("tubing", {})
        add("erosional_ratio", "production, base case at diagnostic rate", "-", tub.get("erosional_ratio_max"), "DriftFluxWellboreHydraulics (L02)")
        if results.get("meta", {}).get("gas_well"):
            add("turner_ratio", "production, base case (gas well)", "-", tub.get("turner_min"), "DriftFluxWellboreHydraulics (L02)")
        add("wellhead_flowing_pressure_bara", "production, base case", "bara", (prod.get("wellhead") or {}).get("pressure_bara"), "back-pressure chain (L02/L04)")
        add("wellhead_flowing_temperature_C", "production, base case", "C", (prod.get("wellhead") or {}).get("temperature_C"), "WellboreThermalModel (L01)")
        add("bottomhole_flowing_pressure_bara", "production, base case", "bara", (prod.get("bottomhole") or {}).get("pressure_bara"), "nodal chain (L04)")
        add("drawdown_bar", "production, base case", "bar", prod.get("drawdown_bar"), "nodal chain (L04)")
        hy = (results.get("flow_assurance") or {}).get("hydrate", {})
        add("hydrate_margin_K", "production, wellhead", "K", hy.get("wellhead_margin_K"), "CPA hydrate temperature (L08)")
        si = results.get("integrity", {}).get("load_cases", [])
        for lc in si:
            if lc["state"] == "shut_in":
                add("wellhead_pressure_bara", "shut-in", "bara", lc.get("pi_top_bara"), lc["source"])
        wax = (results.get("flow_assurance") or {}).get("wax", {})
        add("wax_margin_K", "production, coldest tubing point", "K", wax.get("margin_K"), "supplied WAT (L20)")
    if inj:
        add("wellhead_injection_pressure_bara", "injection, base case", "bara", inj.get("whp_required_bara"), "InjectionWellHydraulics (L06)")
        add("fracture_margin_bar", "injection, matrix basis", "bar", inj.get("fracture_margin_bar"), "InjectionWellHydraulics (L06)")
        add("bottomhole_injection_pressure_bara", "injection, base case", "bara", inj.get("bhp_bara"), "InjectionWellHydraulics (L06)")
        if "pump" in inj.get("surface_duty", {}).get("type", ""):
            add("pump_power_kw", "injection, base case", "kW", inj.get("power_kw"), "hydraulic power (L07)")
        else:
            add("compression_power_kw", "injection, base case", "kW", inj.get("power_kw"), "NeqSim isentropic duty (L07)")
    integ = results.get("integrity") or {}
    for ex in results.get("extra_conditions", []):
        add(ex["parameter"], ex["condition"], ex.get("unit", "-"), ex.get("predicted"), ex.get("source", "study calculation"))
    apb = integ.get("apb")
    if apb:
        add("annulus_a_pressure_bara", "heat-up/cool-down, predicted APB (free-standing)", "bara", apb.get("final_pressure_bara"), "AnnularPressureBuildup (L09)")
    for tub in integ.get("tubing", []):
        if tub.get("burst_utilisation") is not None:
            add("tubing_burst_utilisation", tub["state"], "-", tub.get("burst_utilisation") if tub.get("rating_available") else None, "API TR 5C3 formula rating (L11)")
            add("tubing_collapse_utilisation", tub["state"], "-", tub.get("collapse_utilisation") if tub.get("rating_available") else None, "API TR 5C3 formula rating (L11)")
    for mv in integ.get("tubing_movement", []):
        add("tubing_free_movement_m", "{} ({} packer)".format(mv["state"], mv["packer_mode"]), "m", mv.get("free_movement_m") if mv["packer_mode"] == "FREE" else None, "TubingMovementCalculator (L10)") \
            if mv["packer_mode"] == "FREE" else add("packer_axial_force_change_kn", "{} (FIXED packer)".format(mv["state"]), "kN", mv.get("axial_force_change_kn"), "TubingMovementCalculator (L10)")
    return rows


def summarise(rows: List[EnvelopeRow]) -> Dict[str, int]:
    """Count rows per status."""
    out = {s: 0 for s in STATUSES}
    for r in rows:
        out[r.status] += 1
    return out


def to_rows(rows: List[EnvelopeRow]) -> List[Dict[str, Any]]:
    """Rows as dictionaries."""
    return [asdict(r) for r in rows]


def to_markdown(rows: List[EnvelopeRow]) -> str:
    """Render the envelope table as Markdown."""
    head = "| ID | Parameter | Condition | Min | Max | Limit source (basis) | Predicted | Margin | Status | Action |\n|---|---|---|---|---|---|---|---|---|---|\n"
    lines = []
    f = lambda v: "-" if v is None else ("{:.3g}".format(v) if isinstance(v, (int, float)) else str(v))  # noqa: E731
    for r in rows:
        lines.append("| {} | {} | {} | {} | {} | {} ({}) | {} | {} | {} | {} |".format(r.id, r.parameter, r.condition, f(r.min_limit), f(r.max_limit), r.limit_source or "-", r.limit_basis,
                                                                                          f(r.predicted), f(r.margin_to_limit), r.status + (" [{}]".format(r.indicative_status) if r.status == "NEEDS_REVIEW" else ""), r.action))
    return head + "\n".join(lines)
