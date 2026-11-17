"""Candidate tie-in points: distance, existing feeders and an explainable ranking."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass
class TieInCandidate:
    """One possible landing point for a new export line."""

    name: str
    lat: float
    lon: float
    kind: str = "host"
    distance_km: float = 0.0
    feeders: int = 0
    reaches_terminal: bool = False
    spare_capacity_fraction: float | None = None
    score: float = 0.0
    rationale: list[str] = field(default_factory=list)


def rank_candidates(
    source: dict[str, float],
    hosts: Iterable[dict[str, object]],
    feeds_into: dict[str, Sequence[str]] | None = None,
    terminal_hosts: Iterable[str] | None = None,
    spare_capacity_fraction: dict[str, float] | None = None,
    max_km: float = 120.0,
) -> list[TieInCandidate]:
    """Rank hosts as landing points for a new line from ``source``.

    The score is a transparent sum, not an optimum: shorter lines score higher, hosts that already receive
    several feeders (a field centre) get a bonus, hosts with a route to a terminal get a bonus, and spare
    capacity adds up to one point. The rationale of every term is returned so a reviewer can change the weights.

    Args:
        source: mapping with ``lat`` and ``lon`` of the source facility.
        hosts: iterable of mappings with ``name``, ``lat``, ``lon`` and optionally ``kind``.
        feeds_into: mapping ``feeder name -> hosts it feeds`` used to count existing feeders per host.
        terminal_hosts: names of hosts that already have a trunk line to the terminal.
        spare_capacity_fraction: optional mapping ``host -> spare fraction`` in [0, 1].
        max_km: hosts farther away are dropped.

    Returns:
        Candidates sorted from best to worst.
    """
    feeds_into = feeds_into or {}
    terminals = set(terminal_hosts or [])
    spare = spare_capacity_fraction or {}
    feeder_count: dict[str, int] = {}
    for _feeder, targets in feeds_into.items():
        for target in targets:
            feeder_count[target] = feeder_count.get(target, 0) + 1
    out: list[TieInCandidate] = []
    for host in hosts:
        name = str(host["name"])
        dist = haversine_km(float(source["lat"]), float(source["lon"]), float(host["lat"]), float(host["lon"]))
        if dist > max_km or dist < 0.05:
            continue
        cand = TieInCandidate(name=name, lat=float(host["lat"]), lon=float(host["lon"]),
                              kind=str(host.get("kind", "host")), distance_km=round(dist, 1),
                              feeders=feeder_count.get(name, 0), reaches_terminal=name in terminals,
                              spare_capacity_fraction=spare.get(name))
        d_term = 3.0 * (1.0 - dist / max_km)
        score = d_term
        cand.rationale.append(f"distance {dist:.1f} km -> {d_term:.2f}")
        bonus = min(cand.feeders, 4) * 0.5
        if bonus:
            cand.rationale.append(f"{cand.feeders} existing feeders -> +{bonus:.2f}")
        score += bonus
        if cand.reaches_terminal:
            score += 2.0
            cand.rationale.append("existing trunk to terminal -> +2.00")
        if cand.spare_capacity_fraction is not None:
            add = max(0.0, min(1.0, cand.spare_capacity_fraction))
            score += add
            cand.rationale.append(f"spare capacity {add:.0%} -> +{add:.2f}")
        cand.score = round(score, 2)
        out.append(cand)
    out.sort(key=lambda c: c.score, reverse=True)
    return out
