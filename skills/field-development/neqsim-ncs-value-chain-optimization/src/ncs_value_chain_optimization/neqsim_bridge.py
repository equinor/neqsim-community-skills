"""Hand-offs from the NCS value-chain optimiser to NeqSim Java classes.

* ``economic_parameters(scenario)`` -> ``neqsim.process.optimization.valuechain.EconomicParameters``
* ``value_objective_check(result, year)`` -> ``ValueChainObjective.evaluate`` on the
  optimised NCS export for an independent revenue cross-check.
* ``debottleneck_specs`` + ``run_debottlenecking`` -> ``DebottleneckingAdvisor``:
  the incremental value of each candidate comes from re-solving the LP with the
  element's capacity raised (not from a linearised dual), and calendar years are
  converted to the advisor's year offsets (year 0 = scenario base year).
* ``process_model_targets(result, host)`` -> rate targets and spare capacity that
  the ``optimize-processmodel`` agent can hand to ``ProcessAutomation``
  (``findMaxThroughputJson`` / ``AgenticProcessOptimizer``) on a host's NeqSim model.

Spec functions need no JVM; ``run_*`` functions import ``neqsim`` lazily.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


def _jneqsim():
    try:
        from neqsim import jneqsim  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("the NeqSim Python package is required: pip install neqsim") from exc
    return jneqsim


def economic_parameters(scenario: Dict[str, Any]):
    """NeqSim EconomicParameters from a scenario (NOK/Sm3 gas, NOK/Sm3 liquid, discount rate)."""
    vc = _jneqsim().process.optimization.valuechain
    return (vc.EconomicParameters().setGasPrice(float(scenario["prices"]["gas_nok_per_sm3"]))
            .setOilPrice(float(scenario["prices"]["liquid_nok_per_sm3"]))
            .setDiscountRate(float(scenario["discount_rate"])).setCurrency(scenario.get("currency", "NOK")))


def value_objective_check(result: Dict[str, Any], scenario: Dict[str, Any], year: int) -> Dict[str, Any]:
    """Cross-check one optimised year with NeqSim ValueChainObjective (gross revenue, no tariffs)."""
    yr = next(y for y in result["years"] if y["year"] == year)
    gas = sum(p["gas_msm3d"] for p in yr["produced"].values()) * 1.0e6
    liq = sum(p["liquid_sm3d"] for p in yr["produced"].values())
    vc = _jneqsim().process.optimization.valuechain
    value = vc.ValueChainObjective(economic_parameters(scenario)).evaluate(float(gas), float(liq), 0.0)
    neqsim_mnok_yr = float(value.getRevenueNokPerDay()) * 365.0 / 1.0e6
    lp_gross = (gas / 1.0e6 * scenario["prices"]["gas_nok_per_sm3"] * 365.0
                + liq * scenario["prices"]["liquid_nok_per_sm3"] * 365.0 / 1.0e6)
    return {"year": year, "export_gas_sm3_per_day": gas, "export_liquid_sm3_per_day": liq,
            "neqsim_revenue_mnok_yr": round(neqsim_mnok_yr, 1), "optimizer_gross_mnok_yr": round(lp_gross, 1),
            "optimizer_net_mnok_yr": yr["objective_mnok"],
            "relative_difference": round(abs(neqsim_mnok_yr - lp_gross) / max(lp_gross, 1e-9), 6),
            "neqsim_class": "neqsim.process.optimization.valuechain.ValueChainObjective"}


def debottleneck_specs(optimizer: Any, result: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Incremental annual value of each capacity change, by re-solving the LP.

    ``candidates`` = ``[{"element": id, "added_capacity": 10.0, "capex_mnok": 2500, "name": "..."}]``.
    Returns specs ready for ``run_debottlenecking`` with year offsets from the base year.
    """
    base_year = result["base_year"]
    base = {y["year"]: y["objective_mnok"] for y in result["years"]}
    specs = []
    for cand in candidates:
        element = cand["element"]
        trial = copy.deepcopy(optimizer.scenario)
        current = None
        for medium in ("gas", "liquid"):
            caps = optimizer.capacities(base_year, medium)
            if element in caps:
                current = caps[element]
        if current is None:
            raise KeyError(f"{element!r} is not a capacitated element")
        trial.setdefault("capacity_overrides", {})[element] = current + float(cand["added_capacity"])
        from .optimizer import NcsValueChainOptimizer  # local import avoids a cycle

        rerun = NcsValueChainOptimizer(optimizer.network, trial, profiles=optimizer.profiles).run()
        gains = {y["year"]: y["objective_mnok"] - base[y["year"]] for y in rerun["years"]}
        positive = {y: g for y, g in gains.items() if g > 1e-6}
        first = min(positive) if positive else base_year
        last = max(positive) if positive else base_year
        mean_gain = sum(positive.values()) / len(positive) if positive else 0.0
        specs.append({"name": cand.get("name") or f"+{cand['added_capacity']} {element}", "element": element,
                      "added_capacity": cand["added_capacity"], "capex_mnok": float(cand["capex_mnok"]),
                      "first_year": first, "last_year": last,
                      "first_year_offset": first - base_year, "last_year_offset": last - base_year,
                      "annual_incremental_value_mnok": round(mean_gain, 2),
                      "incremental_value_by_year_mnok": {str(k): round(v, 2) for k, v in gains.items()},
                      "capex_basis": cand.get("capex_basis", "caller supplied")})
    return specs


def run_debottlenecking(specs: List[Dict[str, Any]], scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rank capacity investments with NeqSim DebottleneckingAdvisor (NPV, B/C, payback)."""
    vc = _jneqsim().process.optimization.valuechain
    advisor = vc.DebottleneckingAdvisor(economic_parameters(scenario))
    for s in specs:
        advisor.addCandidate(vc.DebottleneckingAdvisor.DebottleneckCandidate(
            s["name"], s["element"], s["capex_mnok"] * 1.0e6, int(s["first_year_offset"]),
            int(s["last_year_offset"]), s["annual_incremental_value_mnok"] * 1.0e6, None))
    out = []
    for rec in advisor.evaluate():
        c = rec.getCandidate()
        out.append({"name": str(c.getName()), "element": str(c.getTargetEquipment()),
                    "npv_mnok": round(float(rec.getNpvNok()) / 1.0e6, 1),
                    "pv_benefits_mnok": round(float(rec.getPvBenefitsNok()) / 1.0e6, 1),
                    "benefit_cost_ratio": round(float(rec.getBenefitCostRatio()), 3),
                    "payback_years": float(rec.getPaybackYears()), "attractive": bool(rec.isAttractive()),
                    "neqsim_class": "neqsim.process.optimization.valuechain.DebottleneckingAdvisor"})
    return out


def process_model_targets(result: Dict[str, Any], network: Any, host_field: str,
                          years: Optional[List[int]] = None) -> Dict[str, Any]:
    """Rates a host's NeqSim ProcessModel must handle, and its export-route headroom, per year.

    Output is the input contract for the ``optimize-processmodel`` agent: feed
    rates of the host plus every entity routed through it, and the spare
    capacity on its export route (the rate it could grow to before the network
    binds).
    """
    host = network.resolve(host_field)
    rows = []
    for yr in result["years"]:
        if years and yr["year"] not in years:
            continue
        own = yr["produced"].get(host, {})
        tied = {e: p for e, p in yr["produced"].items()
                if e != host and ((result.get("tiebacks", {}).get(e) or {}).get("field_id") == host)}
        path = network.preferred_path(host, "gas")
        caps = [(e, yr["utilization"].get(e)) for e in (path.arcs + path.nodes if path else [])
                if e in yr["utilization"]]
        spare = []
        for e, util in caps:
            flow = yr["element_flow"].get(e, 0.0)
            if util:
                spare.append((e, flow / util - flow))
        tightest = min(spare, key=lambda s: s[1]) if spare else (None, None)
        rows.append({"year": yr["year"],
                     "host_gas_msm3d": own.get("gas_msm3d", 0.0), "host_liquid_sm3d": own.get("liquid_sm3d", 0.0),
                     "tieback_gas_msm3d": round(sum(p["gas_msm3d"] for p in tied.values()), 4),
                     "tieback_liquid_sm3d": round(sum(p["liquid_sm3d"] for p in tied.values()), 2),
                     "tiebacks": sorted(tied), "export_route_tightest_element": tightest[0],
                     "export_route_spare_msm3d": None if tightest[1] is None else round(tightest[1], 3)})
    return {"host": host, "schema": "ncs_process_model_targets.v1", "years": rows,
            "handoff": {"agent": "optimize-processmodel",
                        "neqsim_api": ["ProcessAutomation.findMaxThroughputJson", "ProcessAutomation.evaluate",
                                       "AgenticProcessOptimizer", "ProcessModel.getUtilizationSnapshotJson"],
                        "use": "set feed rates to host + tie-back rates; check the host process can take them "
                               "and whether its own bottleneck is tighter than the export-route spare"}}
