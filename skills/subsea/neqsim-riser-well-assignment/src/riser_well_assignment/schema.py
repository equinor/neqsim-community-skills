"""Normalise and validate a riser-well assignment problem.

All inputs are plain JSON-style dictionaries. Scalars are broadcast over the
planning periods, so a static case (one period) and a multi-year case use the
same schema. The module carries no field data of its own.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

DEFAULT_CONFIG = {
    "period_days": [365.0],
    "stream_value": {"oil": 1.0},
    "swap_days": 3.0,
    "rov_cost_per_swap": 0.0,
    "manifold_switch_cost": 0.0,
    "max_swaps_total": None,
    "max_swaps_per_period": None,
    "disconnect_cost": 0.0,
    "sibling_shutin": True,
    "lock_manifolds": False,
    "unknown_temp_policy": "exclude",
    "derived_streams": {},
    "allow_choking": True,
    "time_limit_s": 120.0,
    "mip_rel_gap": 1e-4,
}


@dataclass
class Well:
    """One well with per-manifold, per-period stream rates."""

    id: str
    rates: Dict[str, List[Dict[str, float]]]
    temp_c: List[Optional[float]]
    current_riser: Optional[str] = None
    pinned_riser: Optional[str] = None
    swap_cost: Optional[float] = None
    slot: Optional[str] = None
    retired_from: Optional[int] = None
    fixed_riser: Optional[List[Optional[str]]] = None


@dataclass
class Riser:
    """One riser: connection capacity, manifold options and limits."""

    id: str
    capacity: int = 1
    manifolds: List[str] = field(default_factory=lambda: ["HP", "LP"])
    max_temp_c: Optional[float] = None
    limits: Dict[str, List[float]] = field(default_factory=dict)
    limits_by_manifold: Dict[str, Dict[str, List[float]]] = field(default_factory=dict)
    current_manifold: Optional[str] = None
    max_reach_m: Optional[float] = None
    available: bool = True
    capacity_by_period: List[int] = field(default_factory=list)


@dataclass
class Problem:
    """Normalised problem consumed by the optimizer."""

    wells: Dict[str, Well]
    risers: Dict[str, Riser]
    manifolds: List[str]
    reach: Dict[str, Set[str]]
    manifold_limits: Dict[str, Dict[str, List[float]]]
    total_limits: Dict[str, List[float]]
    config: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    linked_lineups: List[List[str]] = field(default_factory=list)

    @property
    def n_periods(self) -> int:
        """Number of planning periods."""
        return len(self.config["period_days"])


def _series(value: Any, n: int, what: str) -> List[Any]:
    """Broadcast a scalar or validate a list against the period count."""
    if isinstance(value, (list, tuple)):
        if len(value) != n:
            raise ValueError("%s has %d entries, expected %d periods" % (what, len(value), n))
        return list(value)
    return [value] * n


def _limit(value: Any, n: int, what: str) -> List[float]:
    """A capacity limit as one value per period (a scalar applies to every period)."""
    return [float(v) for v in _series(value, n, what)]


def _stream_rates(raw: Dict[str, Any], n: int, what: str) -> List[Dict[str, float]]:
    """Turn {stream: scalar|list} into one {stream: rate} dict per period."""
    per_stream = {s: _series(v, n, "%s.%s" % (what, s)) for s, v in raw.items()}
    return [{s: float(per_stream[s][t]) for s in per_stream} for t in range(n)]


def load_problem(data: Dict[str, Any]) -> Problem:
    """Build a validated :class:`Problem` from a JSON-style dictionary.

    Args:
        data: dictionary with ``wells``, ``risers``, optional ``reach`` or
            ``distance_m``, ``manifold_limits``, ``total_limits`` and ``config``.

    Returns:
        The normalised problem; data issues that do not stop the run are in
        ``warnings``.

    Raises:
        ValueError: if identifiers, rates or references are inconsistent.
    """
    data = copy.deepcopy(data)
    config = dict(DEFAULT_CONFIG)
    config.update(data.get("config", {}))
    n = len(config["period_days"])
    warnings: List[str] = []

    risers: Dict[str, Riser] = {}
    for r in data.get("risers", []):
        if r["id"] in risers:
            raise ValueError("duplicate riser id %s" % r["id"])
        caps = [int(c) for c in _series(r.get("capacity", 1), n, "riser %s capacity" % r["id"])]
        risers[r["id"]] = Riser(
            id=r["id"],
            capacity=max(caps),
            capacity_by_period=caps,
            manifolds=list(r.get("manifolds", ["HP", "LP"])),
            max_temp_c=r.get("max_temp_c"),
            limits={k: _limit(v, n, "riser %s limit %s" % (r["id"], k)) for k, v in r.get("limits", {}).items()},
            limits_by_manifold={m: {k: _limit(v, n, "riser %s limit %s %s" % (r["id"], m, k)) for k, v in d.items()}
                                for m, d in r.get("limits_by_manifold", {}).items()},
            current_manifold=r.get("current_manifold"),
            max_reach_m=r.get("max_reach_m"),
            available=bool(r.get("available", True)),
        )
    if not risers:
        raise ValueError("no risers given")

    manifolds: List[str] = []
    wells: Dict[str, Well] = {}
    for w in data.get("wells", []):
        if w["id"] in wells:
            raise ValueError("duplicate well id %s" % w["id"])
        rates = {m: _stream_rates(v, n, "well %s rates %s" % (w["id"], m)) for m, v in w["rates"].items()}
        for per_period in rates.values():
            for q in per_period:
                for name, parts in config["derived_streams"].items():
                    missing = [p for p in parts if p not in q]
                    if missing:
                        raise ValueError("well %s: derived stream %s needs %s" % (w["id"], name, missing))
                    q[name] = sum(q[p] for p in parts)
        for m in rates:
            if m not in manifolds:
                manifolds.append(m)
        temp = _series(w.get("temp_c"), n, "well %s temp_c" % w["id"])
        retired = w.get("retired_from")
        if retired is not None and not 0 <= int(retired) <= n:
            raise ValueError("well %s retired_from %s outside the %d periods" % (w["id"], retired, n))
        fixed = w.get("fixed_riser")
        fixed = None if fixed is None else list(_series(fixed, n, "well %s fixed_riser" % w["id"]))
        wells[w["id"]] = Well(
            id=w["id"],
            rates=rates,
            temp_c=[None if x is None else float(x) for x in temp],
            current_riser=w.get("current_riser"),
            pinned_riser=w.get("pinned_riser"),
            swap_cost=w.get("swap_cost"),
            slot=w.get("slot"),
            retired_from=None if retired is None else int(retired),
            fixed_riser=fixed,
        )
    if not wells:
        raise ValueError("no wells given")

    for rid, r in risers.items():
        for m in r.manifolds:
            if m not in manifolds:
                manifolds.append(m)
        if r.current_manifold is not None and r.current_manifold not in r.manifolds:
            raise ValueError("riser %s current manifold %s not allowed" % (rid, r.current_manifold))
    for wid, w in wells.items():
        for ref in [w.current_riser, w.pinned_riser] + list(w.fixed_riser or []):
            if ref is not None and ref not in risers:
                raise ValueError("well %s refers to unknown riser %s" % (wid, ref))
    linked = [list(g) for g in data.get("linked_lineups", [])]
    for group in linked:
        for rid in group:
            if rid not in risers:
                raise ValueError("linked_lineups refers to unknown riser %s" % rid)

    reach = _build_reach(data, wells, risers, warnings)
    limited = set(problem_limit_streams(data))
    for wid, w in wells.items():
        for m, per_period in w.rates.items():
            for t, q in enumerate(per_period):
                missing = sorted(limited - set(q))
                if missing:
                    raise ValueError(
                        "well %s manifold %s period %d lacks stream(s) %s used by a limit; supply them or define derived_streams"
                        % (wid, m, t + 1, missing))
    if config["unknown_temp_policy"] not in ("exclude", "allow"):
        raise ValueError("unknown_temp_policy must be 'exclude' or 'allow'")
    counts: Dict[str, int] = {}
    for wid, w in wells.items():
        if w.current_riser:
            counts[w.current_riser] = counts.get(w.current_riser, 0) + 1
            if w.current_riser not in reach.get(wid, set()):
                warnings.append("current state: well %s on riser %s is outside the reach set" % (wid, w.current_riser))
            if not risers[w.current_riser].available:
                warnings.append("current state: well %s on riser %s which is marked unavailable" % (wid, w.current_riser))
        for rid, r in risers.items():
            if r.max_temp_c is not None and any(x is None for x in w.temp_c) and rid in reach.get(wid, set()):
                warnings.append("well %s has unknown temperature on temperature-limited riser %s (policy: %s)"
                                % (wid, rid, config["unknown_temp_policy"]))
    for rid, cnt in counts.items():
        if cnt > risers[rid].capacity:
            warnings.append("current state: riser %s carries %d wells, capacity %d" % (rid, cnt, risers[rid].capacity))

    return Problem(
        wells=wells,
        risers=risers,
        manifolds=manifolds,
        reach=reach,
        manifold_limits={m: {k: _limit(v, n, "manifold %s limit %s" % (m, k)) for k, v in d.items()}
                         for m, d in data.get("manifold_limits", {}).items()},
        total_limits={k: _limit(v, n, "total limit %s" % k) for k, v in data.get("total_limits", {}).items()},
        config=config,
        warnings=warnings,
        linked_lineups=linked,
    )


def problem_limit_streams(data: Dict[str, Any]) -> List[str]:
    """Names of all streams that appear in any capacity limit of the raw input."""
    names: List[str] = []
    for d in data.get("manifold_limits", {}).values():
        names.extend(d)
    names.extend(data.get("total_limits", {}))
    for r in data.get("risers", []):
        names.extend(r.get("limits", {}))
        for d in r.get("limits_by_manifold", {}).values():
            names.extend(d)
    return names


def _build_reach(data, wells, risers, warnings) -> Dict[str, Set[str]]:
    """Return well -> set of risers that can physically reach it."""
    reach: Dict[str, Set[str]] = {}
    if "reach" in data:
        for wid in wells:
            reach[wid] = set()
        for rid, wl in data["reach"].items():
            if rid not in risers:
                raise ValueError("reach refers to unknown riser %s" % rid)
            for wid in wl:
                if wid not in wells:
                    raise ValueError("reach refers to unknown well %s" % wid)
                reach[wid].add(rid)
    elif "distance_m" in data:
        for rid, r in risers.items():
            if r.max_reach_m is None:
                raise ValueError("distance_m given but riser %s has no max_reach_m" % rid)
        for wid in wells:
            reach[wid] = set()
            for rid, d in data["distance_m"].get(wid, {}).items():
                if d <= risers[rid].max_reach_m:
                    reach[wid].add(rid)
    else:
        warnings.append("no reach data: every riser is assumed to reach every well")
        for wid in wells:
            reach[wid] = set(risers)
    return reach


def active(problem: Problem, wid: str, t: int) -> bool:
    """Whether well ``wid`` still exists in period ``t`` (not retired, plugged or removed)."""
    r = problem.wells[wid].retired_from
    return r is None or t < r


def fixed_at(problem: Problem, wid: str, t: int) -> Optional[str]:
    """Riser a planned operation fixes the well to in period ``t``, or ``None``."""
    f = problem.wells[wid].fixed_riser
    return None if f is None else f[t]


def capacity_at(problem: Problem, rid: str, t: int) -> int:
    """Number of wells riser ``rid`` can carry in period ``t``."""
    return problem.risers[rid].capacity_by_period[t]


def connectable(problem: Problem, wid: str, rid: str, t: Optional[int] = None) -> bool:
    """Whether well ``wid`` can be physically connected to riser ``rid`` (reach, pin, availability).

    With a period ``t`` it also honours retirement, planned fixed connections and riser capacity of that period.
    """
    w, r = problem.wells[wid], problem.risers[rid]
    if not r.available or rid not in problem.reach.get(wid, set()):
        return False
    if t is not None:
        if not active(problem, wid, t) or capacity_at(problem, rid, t) <= 0:
            return False
        fixed = fixed_at(problem, wid, t)
        if fixed is not None and fixed != rid:
            return False
    return w.pinned_riser is None or w.pinned_riser == rid


def feasible_options(problem: Problem, wid: str, rid: str, t: int) -> List[str]:
    """Manifolds on which well ``wid`` may flow through riser ``rid`` in period ``t``."""
    if not connectable(problem, wid, rid, t):
        return []
    w, r = problem.wells[wid], problem.risers[rid]
    if r.max_temp_c is not None:
        temp = w.temp_c[t]
        if temp is None:
            if problem.config["unknown_temp_policy"] == "exclude":
                return []
        elif temp > r.max_temp_c:
            return []
    return [m for m in r.manifolds if m in w.rates]


def revenue_rate(problem: Problem, wid: str, manifold: str, t: int) -> float:
    """Value per day of the well on a manifold in period ``t`` at full rate."""
    value = problem.config["stream_value"]
    rates = problem.wells[wid].rates[manifold][t]
    return sum(value.get(s, 0.0) * q for s, q in rates.items())
