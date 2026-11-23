"""Mixed-integer optimizer for the well-to-riser pairing problem.

State per planning period ``t``:

* ``z[w,r,t]`` binary: well ``w`` is physically connected to riser ``r`` (persists while shut in).
* ``x[w,r,m,t]`` binary: the connected well flows to manifold ``m``; ``u`` in ``[0, x]`` is the rate fraction.
* ``L[r,m,t]`` binary: riser ``r`` is lined up to manifold ``m`` (persists while idle).

Transitions carry cost and budget: ``mv`` (new connection, an ROV swap), ``dm`` (disconnection),
``ms`` (new line-up) and ``sib`` (production lost by sibling wells on a splitter riser that is
disturbed). :func:`evaluate` recomputes value and violations from a plan with its own code, so the
MILP and the accounting are checked against each other.

Solved with HiGHS through :func:`scipy.optimize.milp`.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

from .schema import Problem, connectable, feasible_options, revenue_rate


@dataclass
class Plan:
    """A multi-period plan: connections, flows and line-ups."""

    connections: List[Dict[str, str]]
    flows: List[Dict[str, Tuple[str, float]]]
    lineups: List[Dict[str, Optional[str]]]


@dataclass
class Evaluation:
    """Value and violations of a plan, computed independently of the MILP."""

    revenue: float = 0.0
    swap_cost: float = 0.0
    disconnect_cost: float = 0.0
    sibling_cost: float = 0.0
    switch_cost: float = 0.0
    moves: List[Dict[str, Any]] = field(default_factory=list)
    stream_totals: List[Dict[str, Dict[str, float]]] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

    @property
    def objective(self) -> float:
        """Net value: revenue minus all transition costs."""
        return self.revenue - self.swap_cost - self.disconnect_cost - self.sibling_cost - self.switch_cost


@dataclass
class Solution:
    """Result of one optimisation."""

    status: str
    plan: Optional[Plan]
    evaluation: Optional[Evaluation]
    milp_objective: float = float("nan")
    mip_gap: Optional[float] = None
    binding_limits: List[str] = field(default_factory=list)
    unproducible_wells: List[str] = field(default_factory=list)

    @property
    def objective(self) -> float:
        """Net value of the plan (nan if no plan was found)."""
        return self.evaluation.objective if self.evaluation else float("nan")

    @property
    def n_swaps(self) -> int:
        """Number of new well-riser connections."""
        return len(self.evaluation.moves) if self.evaluation else 0

    @property
    def moves(self) -> List[Dict[str, Any]]:
        """New connections with period, riser change and cost."""
        return self.evaluation.moves if self.evaluation else []

    @property
    def assignment(self) -> List[Dict[str, Tuple[str, str, float]]]:
        """Flowing wells per period as ``well -> (riser, manifold, rate fraction)``."""
        if not self.plan:
            return []
        return [{w: (self.plan.connections[t][w], m, f) for w, (m, f) in per.items()}
                for t, per in enumerate(self.plan.flows)]


def _best_revenue(problem: Problem, wid: str, t: int) -> float:
    """Non-negative best-case value rate of a well in period ``t``."""
    return max([0.0] + [revenue_rate(problem, wid, m, t) for m in problem.wells[wid].rates])


def swap_cost(problem: Problem, wid: str, t: int) -> float:
    """Cost of one new connection: ROV spread plus shut-in loss; never negative."""
    w = problem.wells[wid]
    if w.swap_cost is not None:
        return max(0.0, float(w.swap_cost))
    cfg = problem.config
    return max(0.0, cfg["rov_cost_per_swap"]) + cfg["swap_days"] * _best_revenue(problem, wid, t)


def _limit_sets(problem: Problem):
    """Yield (label, kind, ref, stream, limit) for every capacity limit."""
    for m, d in problem.manifold_limits.items():
        for s, lim in d.items():
            yield "manifold %s %s" % (m, s), "manifold", m, s, lim
    for s, lim in problem.total_limits.items():
        yield "total %s" % s, "total", None, s, lim
    for rid, r in problem.risers.items():
        for s, lim in r.limits.items():
            yield "riser %s %s" % (rid, s), "riser", rid, s, lim
        for m, d in r.limits_by_manifold.items():
            for s, lim in d.items():
                yield "riser %s on %s %s" % (rid, m, s), "riser_man", (rid, m), s, lim


class _Builder:
    """Collects variables and sparse linear constraints."""

    def __init__(self) -> None:
        self.cost: List[float] = []
        self.lb: List[float] = []
        self.ub: List[float] = []
        self.integer: List[int] = []
        self.rows: List[int] = []
        self.cols: List[int] = []
        self.vals: List[float] = []
        self.rlo: List[float] = []
        self.rhi: List[float] = []

    def var(self, lb: float, ub: float, integer: bool, cost: float = 0.0) -> int:
        """Add a variable and return its index."""
        self.cost.append(cost)
        self.lb.append(lb)
        self.ub.append(ub)
        self.integer.append(1 if integer else 0)
        return len(self.cost) - 1

    def con(self, terms: List[Tuple[int, float]], lo: float, hi: float) -> int:
        """Add ``lo <= sum(coef * var) <= hi`` and return the row index."""
        row = len(self.rlo)
        for idx, coef in terms:
            self.rows.append(row)
            self.cols.append(idx)
            self.vals.append(coef)
        self.rlo.append(lo)
        self.rhi.append(hi)
        return row


def evaluate(problem: Problem, plan: Plan, max_swaps_total: Optional[int] = None,
             lock_manifolds: Optional[bool] = None, tol: float = 1e-6) -> Evaluation:
    """Compute value, transition costs and every constraint violation of a plan.

    This is deliberately separate from the MILP construction. It starts from the
    current connections and line-ups in the problem data.

    Args:
        problem: normalised problem.
        plan: connections, flows and line-ups for every period.
        max_swaps_total: swap budget to check (defaults to the configuration).
        lock_manifolds: whether line-ups must stay as today (defaults to the configuration).
        tol: numerical tolerance.

    Returns:
        The evaluation, with ``violations`` empty for a feasible plan.
    """
    cfg = problem.config
    days = cfg["period_days"]
    n_t = problem.n_periods
    budget = cfg["max_swaps_total"] if max_swaps_total is None else max_swaps_total
    lock = cfg["lock_manifolds"] if lock_manifolds is None else lock_manifolds
    ev = Evaluation()
    bad = ev.violations
    if not (len(plan.connections) == len(plan.flows) == len(plan.lineups) == n_t):
        bad.append("plan has the wrong number of periods")
        return ev

    prev_conn = {wid: w.current_riser for wid, w in problem.wells.items()}
    prev_line = {rid: r.current_manifold for rid, r in problem.risers.items()}
    swaps_total = 0
    for t in range(n_t):
        conn, flows, line = plan.connections[t], plan.flows[t], plan.lineups[t]
        load: Dict[str, int] = {}
        for wid, rid in conn.items():
            if wid not in problem.wells or rid not in problem.risers:
                bad.append("period %d: unknown well or riser in connection %s-%s" % (t + 1, wid, rid))
                continue
            load[rid] = load.get(rid, 0) + 1
            if prev_conn.get(wid) != rid and not connectable(problem, wid, rid):
                bad.append("period %d: new connection %s-%s is not allowed (reach, pin or availability)" % (t + 1, wid, rid))
        for rid, n in load.items():
            if n > problem.risers[rid].capacity:
                bad.append("period %d: riser %s carries %d wells (capacity %d)" % (t + 1, rid, n, problem.risers[rid].capacity))
        for rid, m in line.items():
            if m is not None and m not in problem.risers[rid].manifolds:
                bad.append("period %d: riser %s cannot line up to %s" % (t + 1, rid, m))
            if lock and problem.risers[rid].current_manifold is not None and m != problem.risers[rid].current_manifold:
                bad.append("period %d: riser %s line-up changed while locked" % (t + 1, rid))
            if m is None and problem.risers[rid].current_manifold is not None:
                bad.append("period %d: riser %s has no line-up" % (t + 1, rid))

        totals: Dict[str, Dict[str, float]] = {m: {} for m in problem.manifolds}
        used = {}
        for wid, (m, frac) in flows.items():
            rid = conn.get(wid)
            if rid is None:
                bad.append("period %d: well %s flows without a connection" % (t + 1, wid))
                continue
            if m not in feasible_options(problem, wid, rid, t):
                bad.append("period %d: well %s cannot flow via %s to %s (reach, temperature or manifold)" % (t + 1, wid, rid, m))
                continue
            if line.get(rid) != m:
                bad.append("period %d: riser %s lined up to %s but well %s flows to %s" % (t + 1, rid, line.get(rid), wid, m))
            if not -tol <= frac <= 1 + tol or (not cfg["allow_choking"] and abs(frac - 1.0) > tol):
                bad.append("period %d: well %s rate fraction %.3f not allowed" % (t + 1, wid, frac))
            ev.revenue += days[t] * revenue_rate(problem, wid, m, t) * frac
            for s, q in problem.wells[wid].rates[m][t].items():
                totals[m][s] = totals[m].get(s, 0.0) + q * frac
            used[wid] = (rid, m, frac)
        ev.stream_totals.append(totals)
        for label, kind, ref, stream, lim in _limit_sets(problem):
            tot = 0.0
            for wid, (rid, m, frac) in used.items():
                if (kind == "manifold" and m != ref) or (kind == "riser" and rid != ref) or (kind == "riser_man" and (rid, m) != ref):
                    continue
                tot += problem.wells[wid].rates[m][t].get(stream, 0.0) * frac
            if tot > lim * (1 + 1e-6) + tol:
                bad.append("period %d: %s exceeded (%.4g > %.4g)" % (t + 1, label, tot, lim))

        disturbed = set()
        n_new = 0
        for wid, rid in conn.items():
            if prev_conn.get(wid) != rid:
                cost = swap_cost(problem, wid, t)
                ev.swap_cost += cost
                n_new += 1
                disturbed.add(rid)
                ev.moves.append({"period": t + 1, "well": wid, "from_riser": prev_conn.get(wid), "to_riser": rid, "cost": cost})
        for wid, old in prev_conn.items():
            if old is not None and conn.get(wid) != old:
                ev.disconnect_cost += cfg["disconnect_cost"]
                disturbed.add(old)
        swaps_total += n_new
        if cfg["max_swaps_per_period"] is not None and n_new > cfg["max_swaps_per_period"]:
            bad.append("period %d: %d swaps > %d" % (t + 1, n_new, cfg["max_swaps_per_period"]))
        if cfg["sibling_shutin"]:
            for wid, rid in conn.items():
                if prev_conn.get(wid) == rid and rid in disturbed and problem.risers[rid].capacity > 1:
                    ev.sibling_cost += cfg["swap_days"] * _best_revenue(problem, wid, t)
        for rid, m in line.items():
            if m is not None and prev_line.get(rid) != m:
                ev.switch_cost += cfg["manifold_switch_cost"]
        prev_conn = dict(conn)
        prev_line = {rid: (m if m is not None else prev_line.get(rid)) for rid, m in line.items()}
    if budget is not None and swaps_total > budget:
        bad.append("swap budget exceeded: %d > %d" % (swaps_total, budget))
    return ev


def solve(problem: Problem, max_swaps_total: Optional[int] = None,
          lock_manifolds: Optional[bool] = None) -> Solution:
    """Maximise value over the planning periods.

    Args:
        problem: normalised problem from :func:`riser_well_assignment.load_problem`.
        max_swaps_total: optional override of the total swap budget. ``0`` allows no new
            connection (an unconnected well stays unconnected).
        lock_manifolds: keep every riser lined up as today; with a zero swap budget this
            is the as-is reference.

    Returns:
        The best :class:`Solution`; ``evaluation`` is recomputed independently of the MILP.
    """
    cfg = problem.config
    days = cfg["period_days"]
    n_t = problem.n_periods
    budget = cfg["max_swaps_total"] if max_swaps_total is None else max_swaps_total
    lock = cfg["lock_manifolds"] if lock_manifolds is None else lock_manifolds
    b = _Builder()

    z: Dict[Tuple[str, str, int], int] = {}
    x: Dict[Tuple[str, str, str, int], int] = {}
    u: Dict[Tuple[str, str, str, int], int] = {}
    lv: Dict[Tuple[str, str, int], int] = {}
    mv: Dict[Tuple[str, str, int], int] = {}
    dm: Dict[Tuple[str, str, int], int] = {}

    for t in range(n_t):
        for rid, r in problem.risers.items():
            fixed = lock and r.current_manifold is not None
            for m in r.manifolds:
                if fixed:
                    val = 1.0 if r.current_manifold == m else 0.0
                    lv[(rid, m, t)] = b.var(val, val, True)
                else:
                    lv[(rid, m, t)] = b.var(0, 1, True)
            b.con([(lv[(rid, m, t)], 1.0) for m in r.manifolds],
                  1.0 if r.current_manifold is not None else -np.inf, 1.0)
        for wid in problem.wells:
            for rid in problem.risers:
                if connectable(problem, wid, rid):
                    z[(wid, rid, t)] = b.var(0, 1, True)
        for wid in problem.wells:
            for rid in problem.risers:
                for m in feasible_options(problem, wid, rid, t):
                    key = (wid, rid, m, t)
                    x[key] = b.var(0, 1, True)
                    u[key] = b.var(0, 1, False, -days[t] * revenue_rate(problem, wid, m, t))
                    b.con([(u[key], 1.0), (x[key], -1.0)], -np.inf, 0.0)
                    if not cfg["allow_choking"]:
                        b.con([(u[key], 1.0), (x[key], -1.0)], 0.0, 0.0)
                    b.con([(x[key], 1.0), (z[(wid, rid, t)], -1.0)], -np.inf, 0.0)
                    b.con([(x[key], 1.0), (lv[(rid, m, t)], -1.0)], -np.inf, 0.0)

    prev_z = {(wid, rid): 1.0 if problem.wells[wid].current_riser == rid else 0.0
              for wid in problem.wells for rid in problem.risers}

    def zterm(wid: str, rid: str, t: int, sign: float):
        """Return (terms, constant) for z at period t (t = -1 is the current state)."""
        if t < 0:
            return [], sign * prev_z[(wid, rid)]
        if (wid, rid, t) in z:
            return [(z[(wid, rid, t)], sign)], 0.0
        return [], 0.0

    need_dm = cfg["disconnect_cost"] > 0 or (cfg["sibling_shutin"] and cfg["swap_days"] > 0)
    for t in range(n_t):
        for wid in problem.wells:
            terms = [(z[(wid, r2, t)], 1.0) for r2 in problem.risers if (wid, r2, t) in z]
            if terms:
                b.con(terms, -np.inf, 1.0)
        for rid, r in problem.risers.items():
            terms = [(z[(w2, rid, t)], 1.0) for w2 in problem.wells if (w2, rid, t) in z]
            if terms:
                b.con(terms, -np.inf, float(r.capacity))
        for wid in problem.wells:
            for rid in problem.risers:
                if (wid, rid, t) in z:
                    t_now, c_now = zterm(wid, rid, t, 1.0)
                    t_old, c_old = zterm(wid, rid, t - 1, -1.0)
                    k = b.var(0, 1, False, swap_cost(problem, wid, t))
                    mv[(wid, rid, t)] = k
                    b.con(t_now + t_old + [(k, -1.0)], -np.inf, -(c_now + c_old))
                if need_dm and (prev_z[(wid, rid)] > 0 or (wid, rid, 0) in z):
                    k = b.var(0, 1, False, cfg["disconnect_cost"])
                    dm[(wid, rid, t)] = k
                    t_now, c_now = zterm(wid, rid, t, -1.0)
                    t_old, c_old = zterm(wid, rid, t - 1, 1.0)
                    b.con(t_now + t_old + [(k, -1.0)], -np.inf, -(c_now + c_old))
        if cfg["manifold_switch_cost"] > 0:
            for rid, r in problem.risers.items():
                for m in r.manifolds:
                    k = b.var(0, 1, False, cfg["manifold_switch_cost"])
                    if t == 0:
                        b.con([(k, -1.0), (lv[(rid, m, 0)], 1.0)], -np.inf, 1.0 if r.current_manifold == m else 0.0)
                    else:
                        b.con([(k, -1.0), (lv[(rid, m, t)], 1.0), (lv[(rid, m, t - 1)], -1.0)], -np.inf, 0.0)
        if cfg["sibling_shutin"] and cfg["swap_days"] > 0:
            for rid, r in problem.risers.items():
                if r.capacity <= 1:
                    continue
                k = b.var(0, 1, False)
                for w2 in problem.wells:
                    for table in (mv, dm):
                        if (w2, rid, t) in table:
                            b.con([(table[(w2, rid, t)], 1.0), (k, -1.0)], -np.inf, 0.0)
                for w2 in problem.wells:
                    t_now, c_now = zterm(w2, rid, t, 1.0)
                    t_old, c_old = zterm(w2, rid, t - 1, 1.0)
                    if not t_now:
                        continue
                    s = b.var(0, 1, False, cfg["swap_days"] * _best_revenue(problem, w2, t))
                    b.con(t_now + t_old + [(k, 1.0), (s, -1.0)], -np.inf, 2.0 - (c_now + c_old))

    limit_rows = []
    for t in range(n_t):
        for label, kind, ref, stream, lim in _limit_sets(problem):
            terms = []
            for (wid, rid, m, t2) in x:
                if t2 != t or (kind == "manifold" and m != ref) or (kind == "riser" and rid != ref) \
                        or (kind == "riser_man" and (rid, m) != ref):
                    continue
                q = problem.wells[wid].rates[m][t].get(stream, 0.0)
                if q:
                    terms.append((u[(wid, rid, m, t)], q))
            if terms:
                limit_rows.append((b.con(terms, -np.inf, lim), "%s (period %d)" % (label, t + 1), lim))

    if budget is not None:
        b.con([(i, 1.0) for i in mv.values()], -np.inf, float(budget))
    if cfg["max_swaps_per_period"] is not None:
        for t in range(n_t):
            b.con([(i, 1.0) for (_w, _r, t2), i in mv.items() if t2 == t], -np.inf, float(cfg["max_swaps_per_period"]))

    a = sparse.coo_array((b.vals, (b.rows, b.cols)), shape=(len(b.rlo), len(b.cost))).tocsr()
    res = milp(
        c=np.array(b.cost),
        constraints=LinearConstraint(a, np.array(b.rlo), np.array(b.rhi)),
        integrality=np.array(b.integer),
        bounds=Bounds(np.array(b.lb), np.array(b.ub)),
        options={"time_limit": cfg["time_limit_s"], "mip_rel_gap": cfg["mip_rel_gap"]},
    )
    if res.x is None:
        return Solution("infeasible" if res.status == 2 else "failed", None, None)

    val = res.x
    connections: List[Dict[str, str]] = [dict() for _ in range(n_t)]
    for (wid, rid, t), i in z.items():
        if val[i] > 0.5:
            connections[t][wid] = rid
    flows: List[Dict[str, Tuple[str, float]]] = [dict() for _ in range(n_t)]
    for (wid, rid, m, t), i in x.items():
        if val[i] > 0.5:
            flows[t][wid] = (m, float(min(1.0, max(0.0, val[u[(wid, rid, m, t)]]))))
    lineups = [{rid: next((m for m in r.manifolds if val[lv[(rid, m, t)]] > 0.5), None)
                for rid, r in problem.risers.items()} for t in range(n_t)]
    plan = Plan(connections, flows, lineups)
    ev = evaluate(problem, plan, max_swaps_total=budget, lock_manifolds=lock)
    status = "optimal" if res.status == 0 else "time_limit" if res.status == 1 else "status_%d" % res.status
    sol = Solution(status, plan, ev, milp_objective=-float(res.fun), mip_gap=getattr(res, "mip_gap", None))
    for row, label, lim in limit_rows:
        if float(a[row].dot(val)) >= lim * (1 - 1e-6):
            sol.binding_limits.append(label)
    sol.unproducible_wells = [wid for wid in problem.wells if not any(wid in f for f in flows)]
    return sol


def check_solution(problem: Problem, sol: Solution, max_swaps_total: Optional[int] = None,
                   lock_manifolds: Optional[bool] = None) -> List[str]:
    """Independently verify a solution; an absent plan is reported, never accepted.

    Returns:
        A list of violation messages; empty only for a feasible plan whose reported
        objective equals the recomputed one and the MILP objective.
    """
    if sol.plan is None or sol.evaluation is None:
        return ["no plan to check (solver status: %s)" % sol.status]
    ev = evaluate(problem, sol.plan, max_swaps_total, lock_manifolds)
    issues = list(ev.violations)
    if sol.milp_objective == sol.milp_objective and abs(sol.milp_objective - ev.objective) > 1e-5 * max(1.0, abs(ev.objective)):
        issues.append("MILP objective %.6g differs from recomputed accounting %.6g" % (sol.milp_objective, ev.objective))
    return issues


def pareto_swaps(problem: Problem, budgets: Optional[List[int]] = None,
                 lock_manifolds: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Value versus number of swaps, the basis for choosing a campaign size.

    The comparator is always an explicit zero-swap solve, whatever budgets are requested.

    Args:
        problem: normalised problem.
        budgets: swap budgets to evaluate; defaults to ``0..10``.
        lock_manifolds: keep line-ups as today in every case, the as-is reference.

    Returns:
        One row per budget with value, gain over the zero-swap case and marginal gain.
    """
    base = solve(problem, 0, lock_manifolds).objective
    rows: List[Dict[str, Any]] = []
    prev_value = None
    for k in budgets if budgets is not None else list(range(0, 11)):
        sol = solve(problem, k, lock_manifolds)
        rows.append({
            "swap_budget": k,
            "swaps_used": sol.n_swaps,
            "net_value": sol.objective,
            "gain_vs_no_swap": sol.objective - base,
            "marginal_gain": None if prev_value is None else sol.objective - prev_value,
            "status": sol.status,
        })
        prev_value = sol.objective
    return rows


def brute_force(problem: Problem, max_swaps_total: Optional[int] = None,
                lock_manifolds: Optional[bool] = None) -> float:
    """Exhaustive optimum for tiny cases without choking (test oracle, any number of periods).

    It enumerates, per period and well, disconnected / connected-and-shut-in / flowing
    options, derives line-ups (an idle riser keeps its line-up) and scores every sequence
    with :func:`evaluate`.
    """
    if problem.config["allow_choking"]:
        raise ValueError("brute_force supports allow_choking=False only")
    wells = list(problem.wells)
    n_t = problem.n_periods
    per_period: List[List[Tuple[Dict[str, str], Dict[str, Tuple[str, float]]]]] = []
    for t in range(n_t):
        opts_per_well = []
        for wid in wells:
            opts: List[Optional[Tuple[str, Optional[str]]]] = [None]
            for rid in problem.risers:
                if connectable(problem, wid, rid):
                    opts.append((rid, None))
                for m in feasible_options(problem, wid, rid, t):
                    opts.append((rid, m))
            opts_per_well.append(opts)
        configs = []
        for combo in itertools.product(*opts_per_well):
            conn = {wid: c[0] for wid, c in zip(wells, combo) if c is not None}
            flows = {wid: (c[1], 1.0) for wid, c in zip(wells, combo) if c is not None and c[1] is not None}
            load: Dict[str, int] = {}
            ok = True
            for rid in conn.values():
                load[rid] = load.get(rid, 0) + 1
                if load[rid] > problem.risers[rid].capacity:
                    ok = False
            if ok:
                configs.append((conn, flows))
        per_period.append(configs)
    best = -np.inf
    for seq in itertools.product(*per_period):
        prev = {rid: r.current_manifold for rid, r in problem.risers.items()}
        lineups, ok = [], True
        for conn, flows in seq:
            line = dict(prev)
            seen: Dict[str, str] = {}
            for wid, (m, _f) in flows.items():
                if seen.setdefault(conn[wid], m) != m:
                    ok = False
            line.update(seen)
            lineups.append(line)
            prev = line
        if not ok:
            continue
        ev = evaluate(problem, Plan([c for c, _f in seq], [f for _c, f in seq], lineups), max_swaps_total, lock_manifolds)
        if not ev.violations:
            best = max(best, ev.objective)
    return float(best)
