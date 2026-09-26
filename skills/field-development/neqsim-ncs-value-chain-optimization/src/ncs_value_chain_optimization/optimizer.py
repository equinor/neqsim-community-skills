"""Capacity-constrained value optimisation of the whole NCS export system.

For each year the optimiser solves a linear programme on the
``neqsim-ncs-infrastructure-network`` graph:

    maximise   sum_e,p  netback(e,p) * x[e,p]
    subject to sum_p x_gas[e,p]    = u[e] * G[e]      (field e ships its gas...)
               sum_p x_liquid[e,p] = u[e] * L[e]      (...and liquids together)
               sum_(e,p) through c x[e,p] <= cap[c]   (every trunkline and plant)
               0 <= u[e] <= 1

``u[e]`` is the fraction of field e's available production that is produced,
so oil and gas of one field are curtailed together. ``netback`` = market price
x exit-market factor - path tariff. Duals of the capacity rows are the value of
one more unit of capacity (MNOK/yr per MSm3/d or per Sm3/d), which drives the
debottlenecking and tie-in opportunity lists.

Years are solved independently: curtailed volume is lost within the year, not
deferred (a conservative screening assumption). Solver: SciPy HiGHS; without
SciPy a capacity-aware greedy allocation is used and duals are unavailable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .scenario import make_scenario, validate_scenario
from .supply import EntityProfile, build_supply

MEDIA = ("gas", "liquid")


@dataclass
class RoutedPath:
    medium: str
    arcs: List[str]
    nodes: List[str]
    exit: str
    tariff: float  # NOK per Sm3


@dataclass
class YearResult:
    year: int
    status: str
    objective_mnok: float
    produced: Dict[str, Dict[str, float]] = field(default_factory=dict)      # entity -> {u, gas, liquid}
    curtailed: Dict[str, Dict[str, float]] = field(default_factory=dict)
    element_flow: Dict[str, float] = field(default_factory=dict)
    element_capacity: Dict[str, float] = field(default_factory=dict)
    shadow_price: Dict[str, float] = field(default_factory=dict)             # MNOK/yr per unit capacity
    exits: Dict[str, float] = field(default_factory=dict)                    # market -> rate
    unsold: Dict[str, Dict[str, float]] = field(default_factory=dict)        # no sales route (reinjection etc.)
    unconnected: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        util = {e: round(self.element_flow.get(e, 0.0) / c, 4) for e, c in self.element_capacity.items() if c}
        return {"year": self.year, "status": self.status, "objective_mnok": round(self.objective_mnok, 1),
                "produced": self.produced, "curtailed": self.curtailed,
                "element_flow": {k: round(v, 3) for k, v in self.element_flow.items()},
                "utilization": util, "shadow_price_mnok_per_unit_yr": {k: round(v, 4) for k, v in
                                                                       self.shadow_price.items() if abs(v) > 1e-9},
                "exits": {k: round(v, 3) for k, v in self.exits.items()},
                "unsold": self.unsold, "unconnected": self.unconnected}


class NcsValueChainOptimizer:
    """Multi-year, capacity-constrained allocation of NCS production to markets."""

    def __init__(self, network: Any, scenario: Optional[Dict[str, Any]] = None,
                 profiles: Optional[Dict[str, EntityProfile]] = None) -> None:
        self.network = network
        self.scenario = scenario or make_scenario()
        problems = validate_scenario(self.scenario)
        if problems:
            raise ValueError("invalid scenario: " + "; ".join(problems))
        first = self.scenario["years"][0]
        self.profiles = profiles or build_supply(
            network, reference_year=first - 1, end_year=self.scenario["years"][1],
            include_discoveries=self.scenario.get("include_discoveries", True),
            include_not_evaluated=self.scenario.get("include_not_evaluated", False),
            overrides=self.scenario.get("forecast_overrides"))
        self._paths: Dict[Tuple[str, str], List[RoutedPath]] = {}
        self.tiebacks: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ routing
    def _tariff(self, medium: str, arcs: List[str]) -> float:
        t = self.scenario["tariffs"]
        by_arc = t.get(f"{medium}_nok_per_sm3_by_arc", {})
        hits = [by_arc[a] for a in arcs if a in by_arc]
        return float(sum(hits)) if hits else float(t.get(f"{medium}_nok_per_sm3_default", 0.0))

    def paths(self, entity: str, medium: str) -> List[RoutedPath]:
        key = (entity, medium)
        if key in self._paths:
            return self._paths[key]
        net = self.network
        limit = int(self.scenario.get("max_paths_per_entity", 20))
        prefix_arcs: List[str] = []
        start = entity
        if entity in net.discoveries:
            host = self._tieback_host(entity, medium)
            if host is None:
                self._paths[key] = []
                return []
            start = host["field_id"]
            prefix_arcs = [f"TIEBACK:{entity}->{start}"]
        raw = net.export_paths(start, medium, max_paths=limit)
        out = [RoutedPath(medium, prefix_arcs + p.arcs, ([entity] if prefix_arcs else []) + p.nodes, p.exit,
                          self._tariff(medium, p.arcs)) for p in raw]
        self._paths[key] = out
        return out

    def _tieback_host(self, discovery: str, medium: str) -> Optional[Dict[str, Any]]:
        cache_key = f"{discovery}:{medium}"
        if cache_key in self.tiebacks:
            return self.tiebacks[cache_key]
        max_km = float(self.scenario.get("tieback_max_km", 60.0))
        chosen = None
        try:
            hosts = self.network.nearest_hosts(discovery, n=10, max_km=max_km)
        except ValueError:
            hosts = []
        for host in hosts:
            fid = host.get("field_id")
            if fid and fid in self.network.nodes and self.network.export_paths(fid, medium, max_paths=1):
                chosen = host
                break
        self.tiebacks[cache_key] = chosen
        return chosen

    # ------------------------------------------------------------------ capacities
    def capacities(self, year: int, medium: str) -> Dict[str, float]:
        net = self.network
        caps: Dict[str, float] = {}
        for arc_id, arc in net.arcs.items():
            if arc["medium"] == medium and arc.get("capacity") is not None:
                caps[arc_id] = float(arc["capacity"])
        key = "gas_capacity_msm3d" if medium == "gas" else "liquid_capacity_sm3d"
        for nid, node in net.nodes.items():
            if node.get(key) is not None:
                caps[nid] = float(node[key])
        for element, value in self.scenario.get("capacity_overrides", {}).items():
            if element in caps or element in net.arcs or element in net.nodes:
                arc = net.arcs.get(element)
                if arc is None or arc["medium"] == medium:
                    caps[element] = float(value)
        for outage in self.scenario.get("outages", []):
            if outage["element"] in caps and year in [int(y) for y in outage.get("years", [])]:
                caps[outage["element"]] *= float(outage.get("available_fraction", 0.0))
        return caps

    # ------------------------------------------------------------------ solve
    def solve_year(self, year: int) -> YearResult:
        try:
            import numpy as np
            from scipy.optimize import linprog
            from scipy.sparse import coo_matrix
        except ImportError:  # pragma: no cover - environment dependent
            return self._greedy_year(year)

        prices = self.scenario["prices"]
        exit_factor = prices.get("gas_exit_factor", {})
        # per-entity cost, NOK per Sm3 oil-equivalent (1000 Sm3 gas = 1 Sm3 oe), e.g. CO2 tax or OPEX
        field_cost = self.scenario.get("field_cost_nok_per_sm3oe", {})
        entities, var_meta = [], []  # var_meta: ("u", e) | ("x", e, medium, path_index)
        cost: List[float] = []
        eq_rows, eq_cols, eq_vals, eq_rhs = [], [], [], []
        unsold: Dict[str, Dict[str, float]] = {}
        unconnected: List[str] = []
        elem_users: Dict[Tuple[str, str], List[int]] = defaultdict(list)
        caps = {m: self.capacities(year, m) for m in MEDIA}

        for ent, prof in self.profiles.items():
            rates = {m: prof.rate(year, m) for m in MEDIA}
            if rates["gas"] <= 0 and rates["liquid"] <= 0:
                continue
            routed = {m: self.paths(ent, m) if rates[m] > 0 else [] for m in MEDIA}
            if not any(routed[m] for m in MEDIA):
                unconnected.append(ent)
                continue
            u_idx = len(var_meta)
            var_meta.append(("u", ent))
            cost.append(0.0)
            entities.append(ent)
            for m in MEDIA:
                if rates[m] <= 0:
                    continue
                if not routed[m]:
                    unsold.setdefault(ent, {})[m] = round(rates[m], 4)
                    continue
                row = len(eq_rhs)
                eq_rhs.append(0.0)
                eq_rows.append(row)
                eq_cols.append(u_idx)
                eq_vals.append(-rates[m])
                for k, path in enumerate(routed[m]):
                    idx = len(var_meta)
                    var_meta.append(("x", ent, m, k))
                    cost_oe = float(field_cost.get(ent, 0.0))
                    if m == "gas":
                        value = (prices["gas_nok_per_sm3"] * exit_factor.get(path.exit, 1.0) - path.tariff
                                 - cost_oe / 1000.0) * 365.0
                    else:  # Sm3/d -> Sm3/yr, value in NOK; convert both to MNOK below
                        value = (prices["liquid_nok_per_sm3"] - path.tariff - cost_oe) * 365.0 / 1.0e6
                    cost.append(-value)  # gas: MSm3/d x NOK/Sm3 x 365 = MNOK/yr
                    eq_rows.append(row)
                    eq_cols.append(idx)
                    eq_vals.append(1.0)
                    for element in path.arcs + path.nodes:
                        if element in caps[m]:
                            elem_users[(m, element)].append(idx)

        n = len(var_meta)
        if n == 0:
            return YearResult(year, "empty", 0.0, unconnected=unconnected)
        ub_keys = sorted(elem_users)
        ub_rows, ub_cols = [], []
        for r, key in enumerate(ub_keys):
            for idx in set(elem_users[key]):
                ub_rows.append(r)
                ub_cols.append(idx)
        a_ub = coo_matrix(([1.0] * len(ub_rows), (ub_rows, ub_cols)), shape=(len(ub_keys), n)).tocsr()
        b_ub = [caps[m][e] for m, e in ub_keys]
        a_eq = coo_matrix((eq_vals, (eq_rows, eq_cols)), shape=(len(eq_rhs), n)).tocsr()
        bounds = [(0.0, 1.0) if meta[0] == "u" else (0.0, None) for meta in var_meta]
        res = linprog(np.array(cost), A_ub=a_ub if ub_keys else None, b_ub=b_ub if ub_keys else None,
                      A_eq=a_eq, b_eq=eq_rhs, bounds=bounds, method="highs")
        result = YearResult(year, "optimal" if res.status == 0 else f"solver status {res.status}: {res.message}",
                            -float(res.fun) if res.status == 0 else 0.0, unsold=unsold, unconnected=unconnected)
        if res.status != 0:
            return result
        x = res.x
        u_of: Dict[str, float] = {}
        for idx, meta in enumerate(var_meta):
            if meta[0] == "u":
                u_of[meta[1]] = float(x[idx])
        for idx, meta in enumerate(var_meta):
            if meta[0] != "x" or x[idx] <= 1e-9:
                continue
            _, ent, m, k = meta
            path = self._paths[(ent, m)][k]
            for element in path.arcs + path.nodes:
                if element in caps[m] or element in self.network.arcs:
                    result.element_flow[element] = result.element_flow.get(element, 0.0) + float(x[idx])
            result.exits[path.exit] = result.exits.get(path.exit, 0.0) + float(x[idx])
        for ent in entities:
            prof = self.profiles[ent]
            u = u_of.get(ent, 0.0)
            g, lq = prof.rate(year, "gas"), prof.rate(year, "liquid")
            result.produced[ent] = {"u": round(u, 4), "gas_msm3d": round(u * g, 4), "liquid_sm3d": round(u * lq, 2)}
            if u < 0.999:
                result.curtailed[ent] = {"gas_msm3d": round((1 - u) * g, 4), "liquid_sm3d": round((1 - u) * lq, 2)}
        for (m, element) in ub_keys:
            result.element_capacity[element] = caps[m][element]
        marginals = getattr(res.ineqlin, "marginals", None) if ub_keys else None
        if marginals is not None:
            for r, (m, element) in enumerate(ub_keys):
                result.shadow_price[element] = -float(marginals[r])
        return result

    def _greedy_year(self, year: int) -> YearResult:  # pragma: no cover - fallback without SciPy
        result = YearResult(year, "greedy (scipy unavailable, no duals)", 0.0)
        for m in MEDIA:
            rates = {e: p.rate(year, m) for e, p in self.profiles.items() if e in self.network.fields}
            util = self.network.utilization(year, m, rates=rates)
            for el in util["elements"]:
                result.element_flow[el["element"]] = el["flow"]
                if el.get("capacity"):
                    result.element_capacity[el["element"]] = el["capacity"]
        return result

    def run(self) -> Dict[str, Any]:
        first, last = self.scenario["years"]
        rate = float(self.scenario["discount_rate"])
        years = [self.solve_year(y) for y in range(first, last + 1)]
        npv = sum(y.objective_mnok / (1.0 + rate) ** (y.year - first) for y in years)
        return {"schema": "ncs_value_chain_result.v1", "scenario": self.scenario.get("name"),
                "years": [y.to_dict() for y in years], "npv_mnok": round(npv, 1),
                "discount_rate": rate, "base_year": first,
                "tiebacks": {k.split(":")[0]: v for k, v in self.tiebacks.items() if v},
                "supply": {e: p.to_dict() for e, p in self.profiles.items()},
                "assumptions": [
                    "years solved independently; curtailed volume is lost, not deferred",
                    "field oil and gas curtailed together (one fraction u per field and year)",
                    "nameplate capacities from norskpetroleum/Gassco; no line-pack or pressure effects",
                    f"prices and tariffs: {self.scenario.get('provenance', {})}",
                    "discoveries tie back to the nearest host within tieback_max_km that has an export route",
                ]}
