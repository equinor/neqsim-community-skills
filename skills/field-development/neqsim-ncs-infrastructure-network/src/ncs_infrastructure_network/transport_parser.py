"""Extract export routes from the Sodir field 'Transport' description text.

The Sodir field description (DataService layer 7102, heading ``Transport``)
states in prose where each field sends its gas and liquids, e.g.

    "The oil is offloaded from the Norne FPSO and the gas is transported via the
    Norne pipeline to the Asgard Transport System (ATS) and further to the
    Karsto terminal for export."

The parser splits the text into clauses, assigns each clause a commodity
(gas / liquid / both for "well stream"), finds gazetteer mentions in reading
order (longest alias wins) and turns consecutive mentions into directed arcs.
Every route carries a confidence and a ``needs_review`` flag: this is text
mining of public prose, not an as-built line list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .topology import ALIASES, norm

_GAS = re.compile(r"\b(rich gas|dry gas|gas)\b", re.I)
_LIQ = re.compile(r"\b(oil|condensate|ngl|liquids?|crude)\b", re.I)
_BOTH = re.compile(r"\b(well ?stream|oil and gas|gas and oil|hydrocarbons|production)\b", re.I)
_HISTORIC = re.compile(r"\b(was|were|had been)\b", re.I)
_END_NODES = {"TANKER_EXPORT", "GAS_REINJECTION"}
# Proper names that contain commodity words ("Shell-Esso Gas and Liquid", "Troll Oil
# Pipeline"); masked before a clause is classified as gas or liquid.
_NAME_MASK = re.compile(
    r"gas and liquids?|liquids and (associated )?gas( system)?|\b(gas|oil|condensate) (transport|pipeline|export|"
    r"evacuation|system|terminal|pipe)s?\b|scottish area gas|rich gas pipeline",
    re.I,
)
_CLAUSE_SPLIT = re.compile(
    # never split "oil and condensate" / "Gas and Liquid": no commodity word right before
    r"(?<!oil)(?<!gas)(?<!condensate)(?<!ngl)(?<!liquid)"
    r"(?:,|;)?\s+(?=(?:and|while|whereas)\s+(?:the\s+)?(?:excess\s+|processed\s+|rich\s+|dry\s+)?"
    r"(?:oil|gas|condensate|ngl|liquids?|well ?stream)\b)",
    re.I,
)


@dataclass
class ParsedRoute:
    field: str
    medium: str  # "gas" | "liquid"
    nodes: List[str]
    sentence: str
    confidence: str
    needs_review: bool
    historic: bool = False

    def arcs(self) -> List[Tuple[str, str]]:
        return [(a, b) for a, b in zip(self.nodes, self.nodes[1:]) if a != b]


@dataclass
class Gazetteer:
    """Alias -> node id, matched on normalised text, longest alias first."""

    aliases: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, extra: Optional[Dict[str, str]] = None) -> "Gazetteer":
        table: Dict[str, str] = {}
        for alias, node in {**ALIASES, **(extra or {})}.items():
            key = norm(alias)
            if key and len(key) >= 3:
                table.setdefault(key, node)
        return cls(table)

    def find(self, text: str) -> List[Tuple[int, str, str]]:
        """Return (position, alias, node) mentions in reading order without overlaps."""
        hay = " " + norm(text) + " "
        taken = [False] * len(hay)
        hits: List[Tuple[int, str, str]] = []
        for alias in sorted(self.aliases, key=len, reverse=True):
            needle = " " + alias + " "
            start = 0
            while True:
                pos = hay.find(needle, start)
                if pos < 0:
                    break
                span = range(pos + 1, pos + 1 + len(alias))
                if not any(taken[i] for i in span):
                    for i in span:
                        taken[i] = True
                    hits.append((pos, alias, self.aliases[alias]))
                start = pos + 1
        hits.sort()
        return hits


def split_clauses(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").replace("\n", " ").strip())
    clauses: List[str] = []
    for sentence in sentences:
        clauses.extend(part.strip() for part in _CLAUSE_SPLIT.split(sentence) if part.strip())
    return clauses


def _medium(clause: str) -> Optional[str]:
    clause = _NAME_MASK.sub(" ", clause)
    gas, liq, both = bool(_GAS.search(clause)), bool(_LIQ.search(clause)), bool(_BOTH.search(clause))
    if both or (gas and liq):
        return "both"
    if gas:
        return "gas"
    if liq:
        return "liquid"
    return None


def parse_transport_text(field_id: str, text: str, gazetteer: Gazetteer) -> List[ParsedRoute]:
    """Parse one field's Transport text into gas and liquid routes."""
    routes: Dict[str, List[str]] = {"gas": [field_id], "liquid": [field_id]}
    evidence: Dict[str, List[str]] = {"gas": [], "liquid": []}
    unresolved: Dict[str, bool] = {"gas": False, "liquid": False}
    historic = bool(_HISTORIC.search(text or "")) and not re.search(r"\b(is|are|will be)\b", text or "")
    current: Optional[str] = None
    for clause in split_clauses(text):
        medium = _medium(clause) or current
        current = medium if medium != "both" else current
        if medium is None:
            continue
        mentions = [node for _pos, _alias, node in gazetteer.find(clause)]
        # "offloaded from the Norne FPSO": tanker/reinjection end a clause's route
        mentions.sort(key=lambda node: 1 if node in _END_NODES else 0)
        targets = ["gas", "liquid"] if medium == "both" else [medium]
        for target in targets:
            for node in mentions:
                if node == "TANKER_EXPORT" and target == "gas":
                    continue
                if node == "GAS_REINJECTION" and target == "liquid":
                    continue
                if routes[target][-1] != node:
                    routes[target].append(node)
            evidence[target].append(clause)
            if not mentions and re.search(r"\b(to|via|through)\b", clause, re.I):
                unresolved[target] = True
    out: List[ParsedRoute] = []
    for medium, nodes in routes.items():
        # collapse revisits of the field itself (e.g. "Troll A" inside the Troll text)
        cleaned = [nodes[0]] + [n for n in nodes[1:] if n != nodes[0]]
        if len(cleaned) < 2:
            continue
        long_route = len(cleaned) > 4
        confidence = "high" if not (unresolved[medium] or long_route) else "medium"
        out.append(ParsedRoute(field_id, medium, cleaned, " ".join(evidence[medium]), confidence,
                               needs_review=confidence != "high" or historic, historic=historic))
    return out


def parse_many(texts: Iterable[Tuple[str, str]], gazetteer: Gazetteer) -> List[ParsedRoute]:
    routes: List[ParsedRoute] = []
    for field_id, text in texts:
        routes.extend(parse_transport_text(field_id, text, gazetteer))
    return routes
