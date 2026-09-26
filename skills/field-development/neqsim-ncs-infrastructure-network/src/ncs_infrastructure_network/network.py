"""Graph view of the NCS export system: fields -> hubs -> plants -> terminals -> markets.

``NcsNetwork`` answers the connectivity questions an agent needs before any
optimisation: where does a field's gas and liquid go, which fields share a
pipeline or plant, what happens if a node or pipeline is lost, which elements
are single points of failure, and how loaded is each capacitated element in a
given year when every field ships along its preferred route.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .topology import norm

TERMINAL_KINDS = {"market", "sink"}
SALES_KINDS = {"market"}
GSM3_PER_YEAR_TO_MSM3_PER_DAY = 1000.0 / 365.0
MSM3_PER_YEAR_TO_SM3_PER_DAY = 1.0e6 / 365.0


def load_snapshot(path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load the bundled snapshot, or a snapshot file rebuilt by ``scripts/build_snapshot.py``."""
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    text = resources.files("ncs_infrastructure_network").joinpath("data/ncs_network_snapshot.json").read_text(
        encoding="utf-8")
    return json.loads(text)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Path_:
    nodes: List[str]
    arcs: List[str]

    @property
    def exit(self) -> str:
        return self.nodes[-1]


class NcsNetwork:
    """Directed multi-commodity graph built from an ``ncs_network_snapshot.v1``."""

    def __init__(self, snapshot: Dict[str, Any]) -> None:
        if snapshot.get("schema") != "ncs_network_snapshot.v1":
            raise ValueError("expected an ncs_network_snapshot.v1 document")
        self.snapshot = snapshot
        self.nodes: Dict[str, Dict[str, Any]] = snapshot["nodes"]
        self.arcs: Dict[str, Dict[str, Any]] = {a["id"]: a for a in snapshot["arcs"]}
        self.fields: Dict[str, Dict[str, Any]] = snapshot.get("fields", {})
        self.discoveries: Dict[str, Dict[str, Any]] = snapshot.get("discoveries", {})
        self.hosts: List[Dict[str, Any]] = snapshot.get("hosts", [])
        self._out: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        self._in: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for arc in snapshot["arcs"]:
            self._out[(arc["from"], arc["medium"])].append(arc)
            self._in[(arc["to"], arc["medium"])].append(arc)
        self._by_name = {norm(n.get("name", k)): k for k, n in self.nodes.items()}
        self._by_name.update({norm(k): k for k in self.nodes})
        self._by_name.update({norm(d["name"]): k for k, d in self.discoveries.items() if d.get("name")})

    # ------------------------------------------------------------------ lookup
    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "NcsNetwork":
        return cls(load_snapshot(path))

    def resolve(self, name_or_id: str) -> str:
        if name_or_id in self.nodes or name_or_id in self.discoveries:
            return name_or_id
        key = norm(name_or_id)
        if key in self._by_name:
            return self._by_name[key]
        raise KeyError(f"unknown NCS node, field or discovery: {name_or_id!r}")

    def out_arcs(self, node: str, medium: str) -> List[Dict[str, Any]]:
        """Outgoing arcs, the node's own (primary) arcs first, third-party text arcs after."""
        arcs = self._out.get((node, medium), [])
        return sorted(arcs, key=lambda a: 0 if a.get("primary", True) else 1)

    def secondary_count(self, path: "Path_") -> int:
        return sum(1 for a in path.arcs if not self.arcs[a].get("primary", True))

    # ------------------------------------------------------------------ paths
    def export_paths(self, field: str, medium: str = "gas", *, max_paths: int = 50,
                     max_depth: int = 12, removed: Optional[Set[str]] = None,
                     sales_only: bool = True) -> List[Path_]:
        """All loop-free paths from a field (or node) to a market for one medium.

        ``sales_only`` (default) ends paths only at markets, so gas a hub can
        also send to reinjection is routed to sale; set False to include sinks.
        """
        start = self.resolve(field)
        removed = removed or set()
        results: List[Path_] = []
        ends = SALES_KINDS if sales_only else TERMINAL_KINDS

        def walk(node: str, nodes: List[str], arcs: List[str]) -> None:
            if len(results) >= max_paths or len(nodes) > max_depth:
                return
            kind = self.nodes.get(node, {}).get("kind")
            if kind in TERMINAL_KINDS and len(nodes) > 1:
                if kind in ends:
                    results.append(Path_(list(nodes), list(arcs)))
                return
            options = [a for a in self.out_arcs(node, medium) if a["id"] not in removed and a["to"] not in removed]
            for arc in options:
                if arc["to"] in nodes:
                    continue
                walk(arc["to"], nodes + [arc["to"]], arcs + [arc["id"]])

        if start not in removed:
            walk(start, [start], [])
        results.sort(key=lambda p: (self.secondary_count(p), len(p.arcs)))
        return results

    def preferred_path(self, field: str, medium: str = "gas", removed: Optional[Set[str]] = None) -> Optional[Path_]:
        paths = self.export_paths(field, medium, removed=removed)
        return paths[0] if paths else None

    def export_routes(self, field: str) -> Dict[str, Any]:
        """Human-readable routes for a field, both media, with exits and bottleneck capacities."""
        fid = self.resolve(field)
        out: Dict[str, Any] = {"field": fid, "name": self.nodes.get(fid, {}).get("name", fid), "routes": {}}
        for medium in ("gas", "liquid"):
            routes = []
            for path in self.export_paths(fid, medium):
                caps = [(a, self.arcs[a].get("capacity")) for a in path.arcs if self.arcs[a].get("capacity")]
                bottleneck = min(caps, key=lambda c: c[1]) if caps else None
                routes.append({"nodes": path.nodes, "exit": path.exit,
                               "via": [self.arcs[a].get("name") or a for a in path.arcs],
                               "bottleneck_arc": bottleneck[0] if bottleneck else None,
                               "bottleneck_capacity": bottleneck[1] if bottleneck else None,
                               "unit": "MSm3/d" if medium == "gas" else "Sm3/d"})
            out["routes"][medium] = routes
        return out

    def downstream(self, node: str, medium: str = "gas") -> Set[str]:
        start = self.resolve(node)
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            for arc in self.out_arcs(cur, medium):
                if arc["to"] not in seen:
                    seen.add(arc["to"])
                    stack.append(arc["to"])
        return seen

    def upstream_fields(self, element: str, medium: str = "gas") -> List[str]:
        """Fields whose preferred route passes through a node or arc id."""
        target = element if element in self.arcs else self.resolve(element)
        users = []
        for fid in self.fields:
            path = self.preferred_path(fid, medium)
            if path and (target in path.nodes or target in path.arcs):
                users.append(fid)
        return users

    # ------------------------------------------------------------------ volumes
    def field_rate(self, field: str, year: int, medium: str = "gas") -> float:
        """Net production in MSm3/d (gas) or Sm3/d (oil + condensate) for a year."""
        rec = self.fields.get(field, {}).get("production", {}).get(str(year))
        if not rec:
            return 0.0
        if medium == "gas":
            return rec.get("gas_bsm3", 0.0) * GSM3_PER_YEAR_TO_MSM3_PER_DAY
        return (rec.get("oil_msm3", 0.0) + rec.get("condensate_msm3", 0.0)) * MSM3_PER_YEAR_TO_SM3_PER_DAY

    def utilization(self, year: int, medium: str = "gas",
                    rates: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Load each capacitated arc/plant for a year.

        Fields are routed largest first; each takes the path with the most
        remaining headroom and splits across further paths when that fills
        (capacity-aware greedy). A feasibility screen, not the commercial
        nomination - use the value-chain optimiser for that. ``rates``
        overrides historical rates (MSm3/d gas, Sm3/d liquid).
        """
        field_rates = rates if rates is not None else {f: self.field_rate(f, year, medium) for f in self.fields}
        cap_key = "gas_capacity_msm3d" if medium == "gas" else "liquid_capacity_sm3d"
        remaining: Dict[str, float] = {}
        for arc_id, arc in self.arcs.items():
            if arc["medium"] == medium and arc.get("capacity") is not None:
                remaining[arc_id] = float(arc["capacity"])
        for nid, node in self.nodes.items():
            if node.get(cap_key) is not None:
                remaining[nid] = float(node[cap_key])
        flows: Dict[str, float] = defaultdict(float)
        unrouted: Dict[str, float] = {}
        over: Dict[str, float] = {}

        def headroom(path: Path_) -> float:
            elems = [e for e in path.arcs + path.nodes[1:] if e in remaining]
            return min((remaining[e] for e in elems), default=float("inf"))

        for fid, rate in sorted(field_rates.items(), key=lambda kv: -kv[1]):
            if rate <= 0:
                continue
            paths = self.export_paths(fid, medium, max_paths=20)
            if not paths:
                unrouted[fid] = rate
                continue
            left = rate
            for path in sorted(paths, key=lambda p: (self.secondary_count(p), -headroom(p), len(p.arcs))):
                take = min(left, max(headroom(path), 0.0))
                if take <= 1e-9:
                    continue
                self._load(path, take, flows, remaining)
                left -= take
                if left <= 1e-9:
                    break
            if left > 1e-9:  # no headroom left: book on the preferred path and report it
                self._load(paths[0], left, flows, remaining)
                over[fid] = round(left, 3)
        elements = []
        for element, flow in flows.items():
            if element in self.arcs:
                cap = self.arcs[element].get("capacity")
                name, typ = self.arcs[element].get("name") or element, "arc"
            else:
                cap = self.nodes.get(element, {}).get(cap_key)
                name, typ = self.nodes.get(element, {}).get("name", element), "node"
            elements.append({"element": element, "type": typ, "name": name, "flow": round(flow, 3),
                             "capacity": cap, "utilization": round(flow / cap, 3) if cap else None})
        elements.sort(key=lambda e: -(e["utilization"] or 0))
        total = sum(r for r in field_rates.values() if r > 0)
        return {"year": year, "medium": medium, "unit": "MSm3/d" if medium == "gas" else "Sm3/d",
                "method": "capacity-aware greedy (largest field first)",
                "total_rate": round(total, 3), "routed_rate": round(total - sum(unrouted.values()), 3),
                "elements": elements, "unrouted_fields": unrouted, "fields_without_headroom": over,
                "overloaded": [e for e in elements if (e["utilization"] or 0) > 1.0 + 1e-6]}

    @staticmethod
    def _load(path: Path_, rate: float, flows: Dict[str, float], remaining: Dict[str, float]) -> None:
        for element in path.arcs:
            flows[element] += rate
            if element in remaining:
                remaining[element] -= rate
        for node in path.nodes[1:]:
            if node in remaining:
                flows[node] += rate
                remaining[node] -= rate

    # ------------------------------------------------------------------ resilience
    def outage_impact(self, element: str, year: int, medium: str = "gas") -> Dict[str, Any]:
        """Which fields are stranded or rerouted if a node or arc is unavailable."""
        target = element if element in self.arcs else self.resolve(element)
        removed = {target}
        stranded, rerouted = {}, {}
        for fid in self.fields:
            rate = self.field_rate(fid, year, medium)
            base = self.preferred_path(fid, medium)
            if not base or rate <= 0 or (target not in base.nodes and target not in base.arcs):
                continue
            alt = self.preferred_path(fid, medium, removed=removed)
            if alt is None:
                stranded[fid] = round(rate, 3)
            else:
                rerouted[fid] = {"rate": round(rate, 3), "new_exit": alt.exit, "via": alt.nodes}
        return {"element": target, "year": year, "medium": medium,
                "stranded_rate": round(sum(stranded.values()), 3), "stranded_fields": stranded,
                "rerouted_fields": rerouted}

    def single_points_of_failure(self, year: int, medium: str = "gas", top: int = 15) -> List[Dict[str, Any]]:
        """Elements whose loss strands the most production (no alternative route)."""
        candidates: Set[str] = set()
        for fid in self.fields:
            path = self.preferred_path(fid, medium)
            if path and self.field_rate(fid, year, medium) > 0:
                candidates.update(a for a in path.arcs)
                candidates.update(n for n in path.nodes[1:] if self.nodes.get(n, {}).get("kind") not in TERMINAL_KINDS)
        ranked = []
        for element in candidates:
            impact = self.outage_impact(element, year, medium)
            if impact["stranded_rate"] > 0:
                ranked.append({"element": element, "stranded_rate": impact["stranded_rate"],
                               "fields": sorted(impact["stranded_fields"], key=impact["stranded_fields"].get,
                                                reverse=True)[:8]})
        ranked.sort(key=lambda r: -r["stranded_rate"])
        return ranked[:top]

    # ------------------------------------------------------------------ tie-backs
    def nearest_hosts(self, discovery_or_point: Any, n: int = 5,
                      max_km: Optional[float] = None) -> List[Dict[str, Any]]:
        """Nearest in-service processing hosts to a discovery id/name or a (lat, lon) tuple."""
        if isinstance(discovery_or_point, (tuple, list)):
            lat, lon = discovery_or_point
        else:
            item = self.discoveries.get(self.resolve(discovery_or_point)) or self.fields.get(
                self.resolve(discovery_or_point))
            if not item or item.get("lat") is None:
                raise ValueError(f"no coordinates for {discovery_or_point!r}")
            lat, lon = item["lat"], item["lon"]
        ranked = []
        for host in self.hosts:
            d = haversine_km(lat, lon, host["lat"], host["lon"])
            if max_km is None or d <= max_km:
                ranked.append({**host, "distance_km": round(d, 1)})
        ranked.sort(key=lambda h: h["distance_km"])
        return ranked[:n]

    # ------------------------------------------------------------------ summary
    def summary(self) -> Dict[str, Any]:
        kinds: Dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            kinds[node.get("kind", "hub")] += 1
        return {"nodes": dict(kinds), "arcs": len(self.arcs),
                "capacitated_arcs": sum(1 for a in self.arcs.values() if a.get("capacity")),
                "fields": len(self.fields), "candidate_discoveries": len(self.discoveries),
                "hosts": len(self.hosts), "generated_utc": self.snapshot.get("generated_utc")}

    def to_networkx(self, medium: Optional[str] = None):  # pragma: no cover - optional dependency
        import networkx as nx

        g = nx.MultiDiGraph()
        for nid, node in self.nodes.items():
            g.add_node(nid, **{k: v for k, v in node.items() if isinstance(v, (str, int, float, bool))})
        for arc in self.arcs.values():
            if medium is None or arc["medium"] == medium:
                g.add_edge(arc["from"], arc["to"], key=arc["id"], medium=arc["medium"],
                           capacity=arc.get("capacity") or float("inf"))
        return g


def fields_by(network: NcsNetwork, *, status: Optional[str] = None, area: Optional[str] = None,
              operator: Optional[str] = None) -> List[str]:
    out = []
    for fid, f in network.fields.items():
        if status and (f.get("status") or "").lower() != status.lower():
            continue
        if area and area.lower() not in (f.get("area") or "").lower():
            continue
        if operator and operator.lower() not in (f.get("operator") or "").lower():
            continue
        out.append(fid)
    return out


def iter_years(network: NcsNetwork) -> Sequence[int]:
    years: Set[int] = set()
    for f in network.fields.values():
        years.update(int(y) for y in f.get("production", {}))
    return sorted(years)


__all__: Iterable[str] = ("NcsNetwork", "load_snapshot", "haversine_km", "fields_by", "iter_years")
