"""Data-driven P&ID safeguard placement rules and a layout checker.

``RULES`` lists the placement conventions; :func:`check_layout` applies them to a
``neqsim.pfd_layout.v1`` dictionary (``nodes`` with ``id``/``kind``/``tag``/``bbox`` and
``edges`` with ``from``/``to``/``fluid``) and returns :class:`Finding` objects.

Evidence status - read this before using a result:

* The rules are *conventions* paraphrased from public practice (API RP 14C / ISO 10418
  safety-analysis tables, API STD 521 thermal relief, IEC 61511 independence and voting,
  NORSOK S-001 style layout expectations). They are not verified quotations of any
  standard and no compliance is claimed.
* A finding is a prompt for the HAZOP team. It is derived from node kinds, tags, texts and
  edge fluids on one drawing and can be a false alarm (for example a relief device drawn
  on another sheet).
* An empty finding list does **not** prove the design adequate: the checker only sees what
  is drawn, only the listed rules run, and graph heuristics (hop limits, tag tokens) miss
  unusual drawings.
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NOTICE = (
    "Conventions, not verified standard text; no compliance claim. A finding is a prompt for "
    "the HAZOP team and an empty list does not prove the design adequate."
)
SEVERITIES = ("ERROR", "WARN", "INFO")

BASIS_14C = (
    "API RP 14C / ISO 10418 safety analysis table convention "
    "(convention, not verified text; no compliance claim)"
)
BASIS_521 = (
    "API STD 521 trapped-liquid thermal relief convention "
    "(convention, not verified text; no compliance claim)"
)
BASIS_61511 = (
    "IEC 61511 independence/voting convention "
    "(convention, not verified text; no compliance claim)"
)
BASIS_S001 = (
    "NORSOK S-001 convention (convention, not verified text; no compliance claim)"
)
BASIS_GENERAL = (
    "General good-practice drafting convention "
    "(convention, not verified text; no compliance claim)"
)


def _rule(
    rule_id: str,
    title: str,
    applies_to: str,
    check: str,
    rationale: str,
    severity: str,
    basis: str,
) -> dict[str, str]:
    return {
        "id": rule_id,
        "title": title,
        "applies_to": applies_to,
        "check": check,
        "rationale": rationale,
        "severity": severity,
        "basis": basis,
    }


RULES: list[dict[str, str]] = [
    _rule(
        "PR-01",
        "Isolatable liquid or mixed segment has thermal relief",
        "Segments between two closable valves carrying liquid or mixed-phase fluid",
        "A relief device (psv/relief_valve) is connected to the segment, or the segment "
        "is listed as exempt",
        "Trapped liquid heated by the sun, fire or process heat can exceed design pressure",
        "ERROR",
        BASIS_521,
    ),
    _rule(
        "PR-02",
        "Pig receiver has vent, drain, relief and isolation",
        "Pig receivers and launchers (kind pig_receiver / pig_launcher)",
        "Vent, drain and relief connections are drawn near the trap, with an inlet and an "
        "outlet isolation valve",
        "Depressurising, draining and protecting the trap before opening the closure",
        "ERROR",
        BASIS_14C,
    ),
    _rule(
        "PR-03",
        "ESD valve at the platform boundary of an import line",
        "Riser nodes and boundaries marked as riser/import/subsea/platform with outgoing "
        "hydrocarbon flow",
        "An ESD valve (esdv/ssiv/sdv) is found downstream before the first process equipment",
        "The inventory of an import line must be isolable at the platform limit",
        "ERROR",
        BASIS_14C,
    ),
    _rule(
        "PR-04",
        "HIPPS-like function has series isolation, 2oo3 voting and a logic solver",
        "Nodes marked HIPPS (kind hipps or HIPPS in tag/text) and pressure class breaks",
        "At least two isolation valves, at least three pressure transmitters on separate "
        "taps and a logic solver are drawn; a class break with no HIPPS-like function is "
        "reported as INFO",
        "A high-integrity pressure protection function needs redundancy and independence "
        "to reach its integrity level",
        "ERROR",
        BASIS_61511,
    ),
    _rule(
        "PR-05",
        "Pump discharge is protected against overpressure",
        "Pumps (kind pump)",
        "A relief device or at least two pressure transmitters (trip pair) are drawn on the "
        "discharge side",
        "A pump can dead-head against a closed discharge valve",
        "WARN",
        BASIS_14C,
    ),
    _rule(
        "PR-06",
        "Chemical injection has a back-flow barrier",
        "Injection points where a chemical line meets a hydrocarbon line",
        "Two check valves in series, or a check valve plus an isolation valve, on the "
        "chemical supply",
        "Prevents hydrocarbon back-flow into the chemical system",
        "ERROR",
        BASIS_14C,
    ),
    _rule(
        "PR-07",
        "Depressurisation line has a restriction orifice and a destination",
        "Blowdown / emergency depressurisation valves (bdv, edp, tags BDV/EDV)",
        "A restriction orifice is drawn in the line and the line ends in a flare or closed "
        "boundary",
        "Limits the flow to what the flare system can take and keeps the release closed",
        "ERROR",
        BASIS_14C,
    ),
    _rule(
        "PR-08",
        "Hydrocarbon equipment module has gas and flame detection",
        "Equipment connected to hydrocarbon lines, grouped by module/area attribute",
        "At least two gas detectors and a flame detector are drawn in the module (detectors "
        "without a module count for every module)",
        "Detection of leaks and fire in hydrocarbon areas",
        "WARN",
        BASIS_S001,
    ),
    _rule(
        "PR-09",
        "Voted SIF initiator is not a single transmitter",
        "Initiating functions such as PAHH, LAHH, PSHH",
        "A declared voting other than 1oo1, or at least two transmitters of the same "
        "variable near the function",
        "A single transmitter limits the achievable integrity and is a single point of failure",
        "ERROR",
        BASIS_61511,
    ),
    _rule(
        "PR-10",
        "Vents and drains go to a closed system",
        "Vent and drain valves/lines",
        "The line ends in a boundary, header or vessel (or a blind/cap), not in an open end "
        "or atmosphere",
        "Hydrocarbon releases must go to a safe, closed destination",
        "WARN",
        BASIS_S001,
    ),
    _rule(
        "PR-11",
        "Choke/control valve at a pressure class break has a closing provision",
        "Choke and control valves within three hops of a pressure class break",
        "An interlock, travel-stop note or closed-on-demand/fail-closed provision is recorded",
        "A valve that fails open can expose the downstream class to full upstream pressure",
        "WARN",
        BASIS_61511,
    ),
    _rule(
        "PR-12",
        "Tags are unique on a sheet",
        "All nodes with a tag",
        "No two nodes share one tag (asterisk and case ignored)",
        "Duplicate tags make lists, cause-and-effect and the HAZOP record ambiguous",
        "ERROR",
        BASIS_GENERAL,
    ),
]
RULE_IDS = tuple(rule["id"] for rule in RULES)
_SEVERITY = {rule["id"]: rule["severity"] for rule in RULES}

# --------------------------------------------------------------------------- vocabulary
CLOSABLE_KINDS = frozenset(
    {
        "gate_valve",
        "ball_valve",
        "esdv",
        "hydraulic_valve",
        "check_valve",
        "choke",
        "control_valve",
        "ssiv",
        "blind",
        "valve",
        "sdv",
        "bdv",
        "blowdown_valve",
        "edp_valve",
        "globe_valve",
        "plug_valve",
        "butterfly_valve",
        "needle_valve",
        "spectacle_blind",
    }
)
# Closable kinds that act as an isolation valve (not a check valve, throttle or blind).
ISOLATION_KINDS = CLOSABLE_KINDS - {
    "check_valve",
    "choke",
    "control_valve",
    "blind",
    "spectacle_blind",
    "bdv",
    "blowdown_valve",
    "edp_valve",
}
RELIEF_KINDS = frozenset(
    {
        "psv",
        "relief_valve",
        "pzv",
        "prv",
        "safety_valve",
        "thermal_relief",
        "tsv",
        "rupture_disc",
        "bursting_disc",
    }
)
ESD_KINDS = frozenset({"esdv", "ssiv", "sdv"})
BDV_KINDS = frozenset(
    {
        "bdv",
        "blowdown_valve",
        "edp_valve",
        "edv",
        "depressurisation_valve",
        "depressurization_valve",
    }
)
JUNCTION_KINDS = frozenset(
    {"junction", "tee", "spec_break", "pressure_class_break", "class_break", "tie_in"}
)
BOUNDARY_KINDS = frozenset(
    {
        "boundary",
        "flare",
        "flare_header",
        "closed_drain",
        "drain_header",
        "header",
        "atmosphere",
        "vent_stack",
        "open_end",
        "vent_outlet",
        "cold_vent",
        "battery_limit",
    }
)
OPEN_KINDS = frozenset(
    {"atmosphere", "vent_stack", "open_end", "vent_outlet", "cold_vent"}
)
INSTRUMENT_KINDS = frozenset(
    {
        "instrument",
        "transmitter",
        "detector",
        "gas_detector",
        "flame_detector",
        "logic_solver",
        "logic",
        "plc",
        "sis",
        "controller",
        "switch",
        "sensor",
        "analyser",
        "analyzer",
        "indicator",
        "pressure_transmitter",
        "level_transmitter",
        "temperature_transmitter",
        "flow_transmitter",
        "hipps_logic",
        "voter",
    }
)
LOGIC_KINDS = frozenset({"logic_solver", "logic", "plc", "sis", "hipps_logic", "voter"})
FITTING_KINDS = frozenset(
    {
        "restriction_orifice",
        "orifice",
        "ro",
        "hipps",
        "strainer",
        "reducer",
        "flange",
        "spool",
    }
)
ORIFICE_KINDS = frozenset({"restriction_orifice", "orifice", "ro"})
INJECTION_KINDS = frozenset(
    {
        "injection_point",
        "chemical_injection",
        "chemical_injection_point",
        "injection",
        "dosing_point",
        "injection_quill",
    }
)
CLOSED_STUB_KINDS = frozenset({"blind", "cap", "plug", "spectacle_blind"})
BREAK_KINDS = frozenset({"spec_break", "pressure_class_break", "class_break"})
PIG_KINDS = frozenset({"pig_receiver", "pig_launcher"})

HYDROCARBON_FLUIDS = frozenset(
    {
        "gas",
        "oil",
        "mixed",
        "multiphase",
        "hc",
        "hydrocarbon",
        "condensate",
        "production",
        "prod",
        "well",
        "crude",
        "flare",
        "lean_gas",
        "rich_gas",
        "fuel_gas",
        "export",
        "vent",
        "liquid",
    }
)
LIQUID_FLUIDS = frozenset(
    {
        "oil",
        "liquid",
        "condensate",
        "mixed",
        "multiphase",
        "water",
        "produced_water",
        "glycol",
        "meg",
        "methanol",
        "chemical",
        "crude",
        "seawater",
        "inhibitor",
    }
)
CHEMICAL_FLUIDS = frozenset(
    {
        "chemical",
        "meg",
        "glycol",
        "methanol",
        "inhibitor",
        "corrosion_inhibitor",
        "scale_inhibitor",
        "hydrate_inhibitor",
        "demulsifier",
        "antifoam",
    }
)
SIGNAL_FLUIDS = frozenset({"signal", "electrical", "electric", "control", "e", "i"})

_PASS_CATEGORIES = frozenset({"junction", "valve", "instrument", "fitting"})
_TOKEN_SPLIT = re.compile(r"[-_\s/.:,;()]+")
_PT_TOKEN = re.compile(r"^P(?!D)[A-Z]{0,3}T\d*$")
_GAS_TOKEN = re.compile(r"^(?:AT|AIT|AE|GD|GT)\d*$")
_HH_TOKEN = re.compile(r"^[A-Z]{1,3}(?:AHH|SHH|ALL|SLL)\d*$")
_VOTING = re.compile(r"(\d+)\s*oo\s*(\d+)", re.IGNORECASE)
_CLOSING_NOTE = re.compile(
    r"travel[ _-]?stop|interlock|closed on demand|close on demand|fail[ _-]?closed|"
    r"\bfc\b|mechanical stop|stroke limit",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- findings
@dataclass(frozen=True)
class Finding:
    """One prompt for the HAZOP team raised by a placement rule."""

    rule_id: str
    severity: str
    message: str
    objects: tuple[str, ...]
    fix: str

    def to_dict(self) -> dict[str, Any]:
        """Return the finding as a JSON-serialisable dictionary."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "objects": list(self.objects),
            "fix": self.fix,
        }


def _finding(
    rule_id: str,
    message: str,
    objects: Iterable[str],
    fix: str,
    severity: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity or _SEVERITY[rule_id],
        message=message,
        objects=tuple(sorted({str(o) for o in objects})),
        fix=fix,
    )


# --------------------------------------------------------------------------- graph model
def _kind(raw: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(raw or "").strip().lower())


def _clean_tag(tag: Any) -> str:
    return str(tag or "").strip().rstrip("*").strip()


class _Node:
    """A drawing node with normalised kind, tag, free text and attributes."""

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.id = str(raw["id"])
        self.raw = raw
        self.kind = _kind(raw.get("kind"))
        self.tag = _clean_tag(raw.get("tag"))
        texts = []
        for item in raw.get("texts", []) or []:
            texts.append(
                str(item.get("text", "")) if isinstance(item, Mapping) else str(item)
            )
        for key in ("desc", "description", "label", "note", "notes", "function"):
            value = raw.get(key)
            if isinstance(value, (list, tuple)):
                texts.extend(str(v) for v in value)
            elif value:
                texts.append(str(value))
        self.text = " ".join(texts)
        attrs: dict[str, Any] = {}
        for key in ("attrs", "props", "attributes"):
            if isinstance(raw.get(key), Mapping):
                attrs.update(raw[key])
        self.attrs = attrs
        self.category = self._category()

    def _category(self) -> str:
        if self.kind in JUNCTION_KINDS:
            return "junction"
        if self.kind in BOUNDARY_KINDS:
            return "boundary"
        if self.kind in CLOSABLE_KINDS or self.kind in RELIEF_KINDS:
            return "valve"
        if self.kind in INSTRUMENT_KINDS:
            return "instrument"
        if self.kind in FITTING_KINDS:
            return "fitting"
        return "equipment"

    def attr(self, key: str, default: Any = None) -> Any:
        """Attribute from the node itself or its ``attrs``/``props`` mapping."""
        if key in self.raw:
            return self.raw[key]
        return self.attrs.get(key, default)

    @property
    def label(self) -> str:
        """Lower-case searchable text: kind, tag and texts."""
        return f"{self.kind} {self.tag} {self.text}".replace("_", " ").lower()

    @property
    def tokens(self) -> set[str]:
        """Upper-case tokens of the tag and the text."""
        return {t for t in _TOKEN_SPLIT.split(f"{self.tag} {self.text}".upper()) if t}

    @property
    def tag_tokens(self) -> set[str]:
        """Upper-case tokens of the tag only."""
        return {t for t in _TOKEN_SPLIT.split(self.tag.upper()) if t}

    def has_word(self, *words: str) -> bool:
        """True when any word appears as a whole word in the label."""
        return any(re.search(rf"\b{re.escape(w)}", self.label) for w in words)


class _Edge:
    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.id = str(raw.get("id", ""))
        self.raw = raw
        self.a = str(raw.get("from", raw.get("from_", "")))
        self.b = str(raw.get("to", ""))
        self.fluid = _kind(raw.get("fluid"))
        self.role = _kind(raw.get("role"))
        self.is_signal = self.fluid in SIGNAL_FLUIDS or self.role == "signal"


class _Graph:
    """Process and signal adjacency of one layout."""

    def __init__(self, layout: Mapping[str, Any]) -> None:
        nodes = layout.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("layout has no nodes")
        self.layout = layout
        self.nodes: dict[str, _Node] = {}
        for raw in nodes:
            if isinstance(raw, Mapping) and "id" in raw:
                self.nodes[str(raw["id"])] = _Node(raw)
        self.edges: list[_Edge] = []
        self.proc: dict[str, list[tuple[str, _Edge]]] = {}
        self.fwd: dict[str, list[tuple[str, _Edge]]] = {}
        self.bwd: dict[str, list[tuple[str, _Edge]]] = {}
        self.full: dict[str, list[tuple[str, _Edge]]] = {}
        for raw in layout.get("edges", []) or []:
            edge = _Edge(raw)
            if edge.a not in self.nodes or edge.b not in self.nodes or edge.a == edge.b:
                continue
            self.edges.append(edge)
            self.full.setdefault(edge.a, []).append((edge.b, edge))
            self.full.setdefault(edge.b, []).append((edge.a, edge))
            if edge.is_signal:
                continue
            self.proc.setdefault(edge.a, []).append((edge.b, edge))
            self.proc.setdefault(edge.b, []).append((edge.a, edge))
            self.fwd.setdefault(edge.a, []).append((edge.b, edge))
            self.bwd.setdefault(edge.b, []).append((edge.a, edge))
        self.exemptions = _exemption_table(layout)

    def reach(
        self,
        start: str,
        adj: Mapping[str, list[tuple[str, _Edge]]],
        depth: int,
    ) -> dict[str, int]:
        """Nodes reachable within ``depth`` hops; walks pass through fittings only."""
        seen = {start: 0}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            hops = seen[current]
            if hops >= depth:
                continue
            if (
                current != start
                and self.nodes[current].category not in _PASS_CATEGORIES
            ):
                continue
            for nxt, _edge in adj.get(current, ()):
                if nxt not in seen:
                    seen[nxt] = hops + 1
                    queue.append(nxt)
        seen.pop(start)
        return seen

    def exempt(
        self, rule_id: str, ids: Iterable[str], edges: Iterable[_Edge] = ()
    ) -> bool:
        """True when a node, edge or layout-level entry exempts ``ids`` from the rule."""
        id_set = {str(i) for i in ids}
        for entry in self.exemptions:
            if _exempt_matches(entry["rule"], rule_id) and (
                not entry["objects"] or entry["objects"] & id_set
            ):
                return True
        for node_id in id_set:
            node = self.nodes.get(node_id)
            if node is not None and _exempt_matches(
                _exempt_set(node.attr("exempt")), rule_id
            ):
                return True
        return any(
            _exempt_matches(_exempt_set(e.raw.get("exempt")), rule_id) for e in edges
        )


def _exempt_set(raw: Any) -> set[str]:
    if raw is True:
        return {"*"}
    if isinstance(raw, str):
        return {p.strip().upper() for p in re.split(r"[,\s;]+", raw) if p.strip()}
    if isinstance(raw, (list, tuple, set)):
        return {str(p).strip().upper() for p in raw}
    return set()


def _exempt_matches(values: set[str], rule_id: str) -> bool:
    return bool(values & {rule_id.upper(), "*", "ALL"})


def _exemption_table(layout: Mapping[str, Any]) -> list[dict[str, Any]]:
    table = []
    for entry in layout.get("hazop_exemptions", []) or []:
        if not isinstance(entry, Mapping):
            continue
        objects = entry.get("objects", entry.get("object", []))
        if isinstance(objects, str):
            objects = [objects]
        table.append(
            {
                "rule": _exempt_set(entry.get("rule", entry.get("rules", "*"))),
                "objects": {str(o) for o in objects or []},
            }
        )
    return table


def _load(layout: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(layout, (str, Path)):
        layout = json.loads(Path(layout).read_text(encoding="utf-8"))
    if not isinstance(layout, Mapping):
        raise TypeError("layout must be a mapping or a path to a layout JSON file")
    schema = str(layout.get("schema", "neqsim.pfd_layout.v1"))
    if not schema.startswith("neqsim.pfd_layout"):
        raise ValueError(f"unsupported layout schema {schema!r}")
    return layout


# --------------------------------------------------------------------------- predicates
def _is_hc_edge(edge: _Edge) -> bool:
    return edge.fluid == "" or edge.fluid in HYDROCARBON_FLUIDS


def _is_vent(node: _Node) -> bool:
    return node.has_word("vent", "vents", "venting") or bool(
        node.tag_tokens & {"VV", "VNT", "VENT"}
    )


def _is_drain(node: _Node) -> bool:
    return node.has_word("drain", "drains") or bool(
        node.tag_tokens & {"DV", "DRN", "DRAIN"}
    )


def _is_vent_like(node: _Node) -> bool:
    return _is_vent(node) or _is_drain(node) or node.has_word("flare", "atmosphere")


def _is_pressure_transmitter(node: _Node) -> bool:
    if node.category != "instrument":
        return False
    measure = str(node.attr("measure", "") or "").strip().upper()
    if measure.startswith("P") and not measure.startswith("PD"):
        return True
    return any(_PT_TOKEN.match(t) for t in node.tag_tokens)


def _is_transmitter_of(node: _Node, letter: str) -> bool:
    if node.category != "instrument" or node.kind in LOGIC_KINDS:
        return False
    measure = str(node.attr("measure", "") or "").strip().upper()
    if measure.startswith(letter):
        return True
    pattern = re.compile(rf"^{letter}(?!D)[A-Z]{{0,3}}T\d*$")
    return any(pattern.match(t) for t in node.tag_tokens)


def _is_logic_solver(node: _Node) -> bool:
    return node.kind in LOGIC_KINDS or bool(
        node.has_word("logic", "plc") or node.tag_tokens & {"LS", "PLC", "SIS"}
    )


def _is_gas_detector(node: _Node) -> bool:
    if node.kind == "gas_detector" or node.has_word("gas detector"):
        return True
    if node.category != "instrument":
        return False
    measure = str(node.attr("measure", "") or "").strip().upper()
    return measure in {"A", "GAS"} or any(_GAS_TOKEN.match(t) for t in node.tag_tokens)


def _is_flame_detector(node: _Node) -> bool:
    return (
        node.kind == "flame_detector"
        or node.has_word("flame detector", "flame")
        or bool(node.tag_tokens & {"FD", "BE", "UV", "UVD", "IRD"})
    ) and node.category == "instrument"


def _is_esd_valve(node: _Node) -> bool:
    if node.kind in ESD_KINDS or node.tag_tokens & {"ESDV", "SDV", "SSIV"}:
        return True
    return node.kind == "hydraulic_valve" and node.has_word("esd")


def _is_hipps_marked(node: _Node) -> bool:
    fn = str(node.attr("function", "") or "")
    return node.kind in {"hipps", "hipps_valve", "hipps_logic"} or "HIPPS" in (
        f"{node.tag} {node.text} {fn}".upper()
    )


def _module_of(node: _Node) -> str | None:
    for key in ("module", "area", "zone"):
        value = node.attr(key)
        if value:
            return str(value)
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none"}
    return bool(value)


# --------------------------------------------------------------------------- rules
def _isolatable_segments(g: _Graph) -> list[dict[str, Any]]:
    """Segments bounded by closable valves: members, bounding valves and edges."""
    closable = {i for i, n in g.nodes.items() if n.kind in CLOSABLE_KINDS}
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    proc_edges = [e for e in g.edges if not e.is_signal]
    for e in proc_edges:
        if e.a not in closable and e.b not in closable:
            parent[find(e.a)] = find(e.b)
    groups: dict[str, dict[str, Any]] = {}
    standalone: list[dict[str, Any]] = []
    for e in proc_edges:
        a_closable, b_closable = e.a in closable, e.b in closable
        if a_closable and b_closable:
            standalone.append({"members": set(), "valves": {e.a, e.b}, "edges": [e]})
            continue
        anchor = e.b if a_closable else e.a
        group = groups.setdefault(
            find(anchor), {"members": set(), "valves": set(), "edges": []}
        )
        group["edges"].append(e)
        group["members"].update(x for x in (e.a, e.b) if x not in closable)
        group["valves"].update(x for x in (e.a, e.b) if x in closable)
    segments = list(groups.values()) + standalone
    result = []
    for seg in segments:
        valves = set()
        for v in seg["valves"]:
            others = {n for n, _ in g.proc.get(v, ())} - seg["members"] - seg["valves"]
            if others or g.nodes[v].kind in CLOSED_STUB_KINDS:
                valves.add(v)
        seg["valves"] = valves
        result.append(seg)
    return result


def _pr01(g: _Graph) -> list[Finding]:
    findings = []
    for seg in _isolatable_segments(g):
        members = {m for m in seg["members"]}
        if len(seg["valves"]) < 2:
            continue
        if any(g.nodes[m].category == "boundary" for m in members):
            continue
        if not any(e.fluid in LIQUID_FLUIDS for e in seg["edges"]):
            continue
        if any(g.nodes[m].kind in RELIEF_KINDS for m in members):
            continue
        objects = set(seg["valves"]) | {
            m for m in members if g.nodes[m].category == "equipment"
        }
        if g.exempt("PR-01", members | seg["valves"], seg["edges"]):
            continue
        findings.append(
            _finding(
                "PR-01",
                "Liquid or mixed segment between "
                + " and ".join(sorted(seg["valves"]))
                + " can be isolated with no relief device",
                objects,
                "Add a thermal relief valve (psv/relief_valve) to the segment or list the "
                "segment as exempt with the reason (attribute exempt=PR-01 or a "
                "hazop_exemptions entry).",
            )
        )
    return findings


def _isolates(
    g: _Graph, trap_id: str, adj: Mapping[str, list[tuple[str, _Edge]]]
) -> bool:
    """True when a real isolation valve sits within three hops of the trap on one side."""
    for i in g.reach(trap_id, adj, 3):
        valve = g.nodes[i]
        if valve.kind not in ISOLATION_KINDS or _is_vent_like(valve):
            continue
        beyond = [g.nodes[j] for j in g.reach(i, g.fwd, 2) if j != trap_id]
        if any(_is_vent_like(b) for b in beyond):
            continue
        return True
    return False


def _pr02(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        if node.kind not in PIG_KINDS:
            continue
        local = g.reach(node.id, g.proc, 3)
        nearby = [g.nodes[i] for i in local]
        missing = []
        if not any(_is_vent(n) for n in nearby):
            missing.append("vent")
        if not any(_is_drain(n) for n in nearby):
            missing.append("drain")
        if not any(n.kind in RELIEF_KINDS for n in nearby):
            missing.append("relief/PSV connection")
        if not _isolates(g, node.id, g.bwd):
            missing.append("inlet isolation")
        if not _isolates(g, node.id, g.fwd):
            missing.append("outlet isolation")
        if missing and not g.exempt("PR-02", [node.id]):
            findings.append(
                _finding(
                    "PR-02",
                    f"Pig trap {node.tag or node.id} lacks: " + ", ".join(missing),
                    [node.id],
                    "Draw the missing vent, drain, relief connection and inlet/outlet "
                    "isolation valves close to the trap, or note where they are drawn.",
                )
            )
    return findings


def _pr03(g: _Graph) -> list[Finding]:
    hints = (
        "riser",
        "import",
        "subsea",
        "flowline",
        "pipeline",
        "platform",
        "topside",
    )
    skip = ("flare", "vent", "drain", "utility", "chemical", "fuel", "air", "nitrogen")
    findings = []
    for node in g.nodes.values():
        outgoing = [(n, e) for n, e in g.fwd.get(node.id, ()) if _is_hc_edge(e)]
        is_riser = node.kind == "riser"
        is_import = (
            node.category == "boundary"
            and node.has_word(*hints)
            and not node.has_word(*skip)
        )
        if not outgoing or not (is_riser or is_import):
            continue
        downstream = g.reach(node.id, g.fwd, 6)
        if any(_is_esd_valve(g.nodes[i]) for i in downstream):
            continue
        if g.exempt("PR-03", [node.id]):
            continue
        findings.append(
            _finding(
                "PR-03",
                f"No ESD valve between {node.tag or node.id} and the first process equipment",
                [node.id],
                "Add an ESD valve (kind esdv/ssiv/sdv) at the platform boundary of the "
                "import line, or note the sheet where it is drawn.",
            )
        )
    return findings


def _hipps_clusters(g: _Graph) -> list[set[str]]:
    scopes: list[set[str]] = []
    generic: set[str] = set()
    for node in g.nodes.values():
        if not _is_hipps_marked(node):
            continue
        if node.kind == "hipps":
            scopes.append({node.id} | set(g.reach(node.id, g.full, 2)))
        else:
            generic.add(node.id)
    if generic:
        scopes.append(generic)
    clusters: list[set[str]] = []
    for scope in scopes:
        merged = [c for c in clusters if c & scope]
        for c in merged:
            scope = scope | c
            clusters.remove(c)
        clusters.append(scope)
    return clusters


def _pr04(g: _Graph) -> list[Finding]:
    findings = []
    clusters = _hipps_clusters(g)
    for scope in clusters:
        members = [g.nodes[i] for i in scope]
        valves = [
            n for n in members if n.kind in ISOLATION_KINDS and not _is_vent_like(n)
        ]
        transmitters = [n for n in members if _is_pressure_transmitter(n)]
        taps = set()
        for pt in transmitters:
            tap = pt.attr("tap")
            if tap:
                taps.add(str(tap))
                continue
            neighbours = sorted(n for n, _ in g.proc.get(pt.id, ()))
            taps.add(",".join(neighbours) if neighbours else f"own:{pt.id}")
        ids = [n.id for n in members if n.category != "junction"]
        if g.exempt("PR-04", scope):
            continue
        if len(valves) < 2:
            findings.append(
                _finding(
                    "PR-04",
                    f"HIPPS-like function has {len(valves)} isolation valve(s); "
                    "two in series are expected",
                    ids,
                    "Draw two independent isolation valves in series.",
                )
            )
        if len(transmitters) < 3:
            findings.append(
                _finding(
                    "PR-04",
                    f"HIPPS-like function has {len(transmitters)} pressure transmitter(s); "
                    "three are expected for 2oo3 voting",
                    ids,
                    "Add pressure transmitters on separate taps to reach 2oo3 voting.",
                )
            )
        elif len(taps) < 3:
            findings.append(
                _finding(
                    "PR-04",
                    "HIPPS-like pressure transmitters share taps "
                    f"({len(taps)} distinct tap(s) for {len(transmitters)} transmitters)",
                    [t.id for t in transmitters],
                    "Give each transmitter its own process tap so that one blocked tap "
                    "cannot disable the vote.",
                )
            )
        if not any(_is_logic_solver(n) for n in members):
            findings.append(
                _finding(
                    "PR-04",
                    "HIPPS-like function has no logic solver drawn",
                    ids,
                    "Draw the logic solver and connect the transmitters and valves to it.",
                )
            )
    if not clusters:
        for node in g.nodes.values():
            is_break = node.kind in BREAK_KINDS or node.has_word(
                "class break", "spec break", "pressure class"
            )
            if is_break and not g.exempt("PR-04", [node.id]):
                findings.append(
                    _finding(
                        "PR-04",
                        f"Pressure class break {node.tag or node.id} has no HIPPS-like "
                        "function drawn",
                        [node.id],
                        "Confirm how the downstream class is protected (relief, design "
                        "pressure or HIPPS) and record it in the HAZOP.",
                        severity="INFO",
                    )
                )
    return findings


def _pr05(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        if node.kind != "pump":
            continue
        adj = g.fwd if g.fwd.get(node.id) else g.proc
        discharge = [g.nodes[i] for i in g.reach(node.id, adj, 4)]
        if any(n.kind in RELIEF_KINDS for n in discharge):
            continue
        if sum(1 for n in discharge if _is_pressure_transmitter(n)) >= 2:
            continue
        if g.exempt("PR-05", [node.id]):
            continue
        findings.append(
            _finding(
                "PR-05",
                f"Pump {node.tag or node.id} has no relief device or pressure-transmitter "
                "pair on the discharge",
                [node.id],
                "Add a relief device on the discharge or a high-pressure trip with two "
                "transmitters.",
            )
        )
    return findings


def _pr06(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        incident = g.proc.get(node.id, [])
        chemical = [(n, e) for n, e in incident if e.fluid in CHEMICAL_FLUIDS]
        hydrocarbon = [(n, e) for n, e in incident if e.fluid in HYDROCARBON_FLUIDS]
        by_kind = node.kind in INJECTION_KINDS
        if not (by_kind or (chemical and hydrocarbon)):
            continue
        supply = chemical or [
            (n, e)
            for n, e in incident
            if e.b == node.id and e.fluid not in HYDROCARBON_FLUIDS
        ]
        if not supply:
            continue
        checks, isolations = 0, 0
        seen = {node.id}
        queue = deque((n, 1) for n, _ in supply)
        while queue:
            current, hops = queue.popleft()
            if current in seen or hops > 4:
                continue
            seen.add(current)
            cur = g.nodes[current]
            if cur.kind == "check_valve":
                checks += 1
            elif cur.kind in ISOLATION_KINDS:
                isolations += 1
            if cur.category not in _PASS_CATEGORIES:
                continue
            for nxt, edge in g.proc.get(current, ()):
                if nxt not in seen and (
                    edge.fluid in CHEMICAL_FLUIDS or edge.fluid == ""
                ):
                    queue.append((nxt, hops + 1))
        if checks >= 2 or (checks >= 1 and isolations >= 1):
            continue
        if g.exempt("PR-06", [node.id]):
            continue
        findings.append(
            _finding(
                "PR-06",
                f"Chemical injection at {node.tag or node.id} has {checks} check valve(s) "
                f"and {isolations} isolation valve(s) on the supply",
                [node.id],
                "Provide two check valves in series, or a check valve plus an isolation "
                "valve, close to the injection point.",
            )
        )
    return findings


def _pr07(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        if not (node.kind in BDV_KINDS or node.tag_tokens & {"BDV", "EDV", "EDP"}):
            continue
        adj = g.fwd if g.fwd.get(node.id) else g.proc
        downstream = [g.nodes[i] for i in g.reach(node.id, adj, 8)]
        nearby = downstream + [g.nodes[i] for i in g.reach(node.id, g.bwd, 2)]
        missing = []
        if not any(
            n.kind in ORIFICE_KINDS or n.tag_tokens & {"RO", "FO"} for n in nearby
        ):
            missing.append("restriction orifice")
        closed_destination = any(
            (
                n.category == "boundary"
                and n.kind not in OPEN_KINDS
                and not n.has_word("atmosphere")
            )
            or n.has_word("flare")
            for n in downstream
        )
        if not closed_destination:
            missing.append("flare/closed destination")
        if missing and not g.exempt("PR-07", [node.id]):
            findings.append(
                _finding(
                    "PR-07",
                    f"Depressurisation valve {node.tag or node.id} lacks: "
                    + ", ".join(missing),
                    [node.id],
                    "Draw the restriction orifice in the depressurisation line and end the "
                    "line in a flare or other closed boundary.",
                )
            )
    return findings


def _pr08(g: _Graph) -> list[Finding]:
    equipment: dict[str, list[_Node]] = {}
    for node in g.nodes.values():
        if node.category != "equipment":
            continue
        if any(_is_hc_edge(e) for _, e in g.proc.get(node.id, ())):
            equipment.setdefault(_module_of(node) or "(sheet)", []).append(node)
    detectors = [n for n in g.nodes.values() if n.category == "instrument"]
    findings = []
    for module, members in sorted(equipment.items()):
        scoped = [d for d in detectors if _module_of(d) in (None, module)]
        gas = [d for d in scoped if _is_gas_detector(d)]
        flame = [d for d in scoped if _is_flame_detector(d)]
        missing = []
        if len(gas) < 2:
            missing.append(f"gas detectors ({len(gas)} of 2)")
        if not flame:
            missing.append("flame detector")
        if missing and not g.exempt("PR-08", [m.id for m in members]):
            findings.append(
                _finding(
                    "PR-08",
                    f"Hydrocarbon module {module} has no sufficient detection: "
                    + ", ".join(missing),
                    [m.id for m in members],
                    "Draw the gas and flame detectors, or reference the fire-and-gas "
                    "drawing that carries them and record it as exempt.",
                )
            )
    return findings


def _initiator_token(node: _Node) -> str | None:
    if node.category != "instrument" and node.kind not in LOGIC_KINDS:
        return None
    for token in sorted(node.tokens):
        if _HH_TOKEN.match(token):
            return token
    return None


def _pr09(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        token = _initiator_token(node)
        if token is None:
            continue
        voting = _VOTING.search(str(node.attr("voting", "") or ""))
        if voting:
            single = int(voting.group(2)) <= 1
        else:
            letter = token[0]
            group = {node.id} | set(g.reach(node.id, g.full, 3))
            count = sum(1 for i in group if _is_transmitter_of(g.nodes[i], letter))
            single = count < 2
        if single and not g.exempt("PR-09", [node.id]):
            findings.append(
                _finding(
                    "PR-09",
                    f"Initiator function {token} at {node.tag or node.id} rests on a single "
                    "transmitter",
                    [node.id],
                    "Vote the initiator (for example 2oo3) with independent transmitters, or "
                    "justify the single transmitter in the SIF list.",
                )
            )
    return findings


def _pr10(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        is_source = (node.category == "valve" and node.kind in CLOSABLE_KINDS) or (
            node.kind in {"vent", "drain"}
        )
        if not is_source or not (_is_vent(node) or _is_drain(node)):
            continue
        bad: list[tuple[str, str]] = []
        if not g.fwd.get(node.id):
            bad.append((node.id, "ends in an open end"))
        for i in g.reach(node.id, g.fwd, 8):
            term = g.nodes[i]
            if term.category in ("boundary", "equipment"):
                if term.kind in OPEN_KINDS or term.has_word(
                    "atmosphere", "atmospheric"
                ):
                    bad.append((i, "discharges to atmosphere"))
            elif not g.fwd.get(i) and term.kind not in CLOSED_STUB_KINDS:
                bad.append((i, "ends in an open end"))
        if bad and not g.exempt("PR-10", [node.id]):
            reasons = "; ".join(f"{why} at {i}" for i, why in sorted(bad))
            findings.append(
                _finding(
                    "PR-10",
                    f"Vent/drain {node.tag or node.id} {reasons}",
                    [node.id] + [i for i, _ in bad],
                    "Route the vent or drain to a closed system (flare, closed drain or "
                    "vessel) and draw the destination boundary.",
                )
            )
    return findings


def _pr11(g: _Graph) -> list[Finding]:
    findings = []
    for node in g.nodes.values():
        if node.kind not in {"choke", "control_valve"}:
            continue
        incident = [e for _, e in g.proc.get(node.id, ())]
        if incident and not any(_is_hc_edge(e) for e in incident):
            continue
        near = [g.nodes[i] for i in g.reach(node.id, g.proc, 3)]
        change = any(
            n.kind in BREAK_KINDS
            or n.has_word("class break", "spec break", "pressure class")
            for n in near
        ) or (
            node.attr("class_in") is not None
            and node.attr("class_out") is not None
            and str(node.attr("class_in")) != str(node.attr("class_out"))
        )
        if not change:
            continue
        fail = str(node.attr("fail_position", "") or "").strip().lower()
        provided = (
            any(
                _truthy(node.attr(k))
                for k in ("closed_on_demand", "fail_closed", "interlock", "travel_stop")
            )
            or fail in {"closed", "fc", "fail_closed", "fail closed"}
            or bool(_CLOSING_NOTE.search(node.text))
        )
        if provided or g.exempt("PR-11", [node.id]):
            continue
        findings.append(
            _finding(
                "PR-11",
                f"{node.kind.replace('_', ' ').title()} {node.tag or node.id} at a pressure "
                "class break has no interlock, travel-stop or closed-on-demand provision",
                [node.id],
                "Record an interlock or travel stop, or make the valve close on demand "
                "(fail closed), and show it on the drawing.",
            )
        )
    return findings


def _pr12(g: _Graph) -> list[Finding]:
    by_tag: dict[str, list[str]] = {}
    for node in g.nodes.values():
        if node.tag:
            by_tag.setdefault(node.tag.upper(), []).append(node.id)
    findings = []
    for tag, ids in sorted(by_tag.items()):
        if len(ids) > 1 and not g.exempt("PR-12", ids):
            findings.append(
                _finding(
                    "PR-12",
                    f"Tag {tag} is used by {len(ids)} nodes: " + ", ".join(sorted(ids)),
                    ids,
                    "Give every item a unique tag or merge the duplicate symbols.",
                )
            )
    return findings


_CHECKS = {
    "PR-01": _pr01,
    "PR-02": _pr02,
    "PR-03": _pr03,
    "PR-04": _pr04,
    "PR-05": _pr05,
    "PR-06": _pr06,
    "PR-07": _pr07,
    "PR-08": _pr08,
    "PR-09": _pr09,
    "PR-10": _pr10,
    "PR-11": _pr11,
    "PR-12": _pr12,
}


def check_layout(
    layout: Mapping[str, Any] | str | Path, rules: Iterable[str] | None = None
) -> list[Finding]:
    """Apply the placement rules to a ``neqsim.pfd_layout.v1`` layout.

    ``layout`` is the dictionary or the path of a layout JSON file. ``rules`` optionally
    limits the run to rule ids such as ``["PR-01", "PR-02"]``. Findings are sorted by rule
    id and objects. Exemptions come from a node/edge attribute ``exempt`` (``true``, a rule
    id or a list) and from layout-level ``hazop_exemptions`` entries
    ``{"rule": "PR-01", "objects": ["N1"], "reason": "..."}``.

    An empty result does not prove the design adequate; see :data:`NOTICE`.

    Raises:
        TypeError: ``layout`` is neither a mapping nor a path.
        ValueError: the layout has no nodes, an unsupported schema or an unknown rule id.
    """
    data = _load(layout)
    wanted = [r.upper() for r in rules] if rules is not None else list(RULE_IDS)
    unknown = [r for r in wanted if r not in _CHECKS]
    if unknown:
        raise ValueError(f"unknown rule id(s): {', '.join(unknown)}")
    graph = _Graph(data)
    findings: list[Finding] = []
    for rule_id in RULE_IDS:
        if rule_id in wanted:
            findings.extend(_CHECKS[rule_id](graph))
    return sorted(findings, key=lambda f: (f.rule_id, f.objects, f.message))


def format_findings(findings: Iterable[Finding]) -> str:
    """Plain-text report of findings, ending with the evidence notice."""
    lines = [
        f"{f.rule_id} [{f.severity}] {f.message} ({', '.join(f.objects)}) -> {f.fix}"
        for f in findings
    ]
    return "\n".join(lines + [f"Note: {NOTICE}"])
