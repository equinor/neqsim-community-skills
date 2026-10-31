"""Source and assumptions register, data-gap register and decision/action log.

Every input carries a provenance class so that a reader can tell a supplied or measured value from
a fitted, calculated or assumed one. Missing data become explicit gaps with a stated engineering
consequence. Synthetic assumptions are allowed for demonstrations but are flagged and can never be
promoted to MEASURED.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROVENANCE_CLASSES = ("SUPPLIED", "MEASURED", "FITTED", "CALCULATED", "ASSUMED")
GAP_SEVERITIES = ("BLOCKING", "MAJOR", "MINOR")
DECISION_STATUS = ("PROPOSED", "AGREED", "REJECTED", "SUPERSEDED")
ACTION_STATUS = ("OPEN", "IN_PROGRESS", "CLOSED", "BLOCKED")


def _today() -> str:
    return _dt.date.today().isoformat()


@dataclass
class RegisterItem:
    """One input value with provenance."""

    key: str
    value: Any
    unit: str = ""
    provenance: str = "ASSUMED"
    source: str = ""
    date: str = ""
    synthetic: bool = False
    note: str = ""

    def validate(self) -> List[str]:
        """Return problems with this item (empty list when fine)."""
        problems = []
        if self.provenance not in PROVENANCE_CLASSES:
            problems.append("{}: provenance '{}' not in {}".format(self.key, self.provenance, PROVENANCE_CLASSES))
        if self.provenance in ("SUPPLIED", "MEASURED", "FITTED") and not self.source:
            problems.append("{}: {} value needs a source".format(self.key, self.provenance))
        if self.synthetic and self.provenance == "MEASURED":
            problems.append("{}: synthetic data cannot be MEASURED".format(self.key))
        return problems


@dataclass
class DataGap:
    """A missing or weak input with its engineering consequence."""

    key: str
    description: str
    consequence: str
    severity: str = "MAJOR"
    owner: str = ""
    resolution: str = ""
    status: str = "OPEN"


@dataclass
class Decision:
    """A recorded design decision."""

    id: str
    title: str
    decision: str
    rationale: str
    alternatives_considered: List[str] = field(default_factory=list)
    status: str = "PROPOSED"
    decided_by: str = ""
    date: str = field(default_factory=_today)
    evidence: List[str] = field(default_factory=list)


@dataclass
class Action:
    """An unresolved action."""

    id: str
    description: str
    owner: str = ""
    due: str = ""
    status: str = "OPEN"
    linked_gap: str = ""
    discipline: str = ""


class Registers:
    """Container for the source register, gap register and decision/action log."""

    def __init__(self) -> None:
        self.items: Dict[str, RegisterItem] = {}
        self.gaps: List[DataGap] = []
        self.decisions: List[Decision] = []
        self.actions: List[Action] = []

    def add_item(self, key: str, value: Any, unit: str = "", provenance: str = "ASSUMED", source: str = "", synthetic: bool = False,
                 note: str = "", date: str = "") -> RegisterItem:
        """Add or replace a register item."""
        item = RegisterItem(key, value, unit, provenance, source, date or _today(), synthetic, note)
        self.items[key] = item
        return item

    def add_gap(self, key: str, description: str, consequence: str, severity: str = "MAJOR", owner: str = "", resolution: str = "") -> DataGap:
        """Record a data gap (idempotent by key)."""
        if severity not in GAP_SEVERITIES:
            raise ValueError("severity must be one of {}".format(GAP_SEVERITIES))
        for g in self.gaps:
            if g.key == key:
                return g
        gap = DataGap(key, description, consequence, severity, owner, resolution)
        self.gaps.append(gap)
        return gap

    def add_decision(self, title: str, decision: str, rationale: str, alternatives: Optional[List[str]] = None, status: str = "PROPOSED",
                     decided_by: str = "", evidence: Optional[List[str]] = None) -> Decision:
        """Append a decision with a sequential D-nnn id."""
        if status not in DECISION_STATUS:
            raise ValueError("decision status must be one of {}".format(DECISION_STATUS))
        d = Decision("D-{:03d}".format(len(self.decisions) + 1), title, decision, rationale, list(alternatives or []), status, decided_by,
                     evidence=list(evidence or []))
        self.decisions.append(d)
        return d

    def add_action(self, description: str, owner: str = "", due: str = "", linked_gap: str = "", discipline: str = "") -> Action:
        """Append an action with a sequential A-nnn id."""
        a = Action("A-{:03d}".format(len(self.actions) + 1), description, owner, due, "OPEN", linked_gap, discipline)
        self.actions.append(a)
        return a

    def close_action(self, action_id: str) -> None:
        """Mark an action closed."""
        for a in self.actions:
            if a.id == action_id:
                a.status = "CLOSED"
                return
        raise KeyError(action_id)

    def validate(self) -> List[str]:
        """Return all register problems."""
        problems: List[str] = []
        for item in self.items.values():
            problems.extend(item.validate())
        return problems

    def provenance_counts(self) -> Dict[str, int]:
        """Count items per provenance class."""
        counts = {c: 0 for c in PROVENANCE_CLASSES}
        for item in self.items.values():
            counts[item.provenance] = counts.get(item.provenance, 0) + 1
        return counts

    def open_actions(self) -> List[Action]:
        """Return actions that are not closed."""
        return [a for a in self.actions if a.status != "CLOSED"]

    def blocking_gaps(self) -> List[DataGap]:
        """Return open blocking gaps."""
        return [g for g in self.gaps if g.severity == "BLOCKING" and g.status == "OPEN"]

    def to_dict(self) -> Dict[str, Any]:
        """Return the full register as a JSON-friendly dictionary."""
        return {
            "schema": "iwp_registers.v1",
            "items": [asdict(i) for i in self.items.values()],
            "gaps": [asdict(g) for g in self.gaps],
            "decisions": [asdict(d) for d in self.decisions],
            "actions": [asdict(a) for a in self.actions],
            "provenance_counts": self.provenance_counts(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Registers":
        """Rebuild a register from :meth:`to_dict` output."""
        reg = cls()
        for i in data.get("items", []):
            reg.items[i["key"]] = RegisterItem(**i)
        reg.gaps = [DataGap(**g) for g in data.get("gaps", [])]
        reg.decisions = [Decision(**d) for d in data.get("decisions", [])]
        reg.actions = [Action(**a) for a in data.get("actions", [])]
        return reg

    def save(self, folder: Path) -> None:
        """Write registers.json and CSV views into ``folder``."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "registers.json").write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        _write_csv(folder / "source_register.csv", [asdict(i) for i in self.items.values()],
                   ["key", "value", "unit", "provenance", "source", "date", "synthetic", "note"])
        _write_csv(folder / "data_gaps.csv", [asdict(g) for g in self.gaps],
                   ["key", "description", "consequence", "severity", "owner", "resolution", "status"])
        _write_csv(folder / "decision_log.csv", [asdict(d) | {"alternatives_considered": "; ".join(d.alternatives_considered),
                                                              "evidence": "; ".join(d.evidence)} for d in self.decisions],
                   ["id", "title", "decision", "rationale", "alternatives_considered", "status", "decided_by", "date", "evidence"])
        _write_csv(folder / "action_log.csv", [asdict(a) for a in self.actions],
                   ["id", "description", "owner", "due", "status", "linked_gap", "discipline"])

    @classmethod
    def load(cls, folder: Path) -> "Registers":
        """Load registers.json from ``folder`` (empty register when absent)."""
        p = Path(folder) / "registers.json"
        if not p.exists():
            return cls()
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))


def _write_csv(path: Path, rows: Iterable[Dict[str, Any]], fields: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def registers_from_basis(basis: Dict[str, Any]) -> Registers:
    """Build the source register from the ``provenance`` map of a planning basis.

    The basis carries ``provenance: {dotted.path: {class, source, unit, synthetic, note}}``. Each
    path is resolved against the basis to record its value. Required paths without a provenance
    entry become MAJOR data gaps (see :func:`integrated_well_planning.validation.validate_basis`).
    """
    reg = Registers()
    for path, meta in (basis.get("provenance") or {}).items():
        value = get_path(basis, path)
        reg.add_item(path, value, meta.get("unit", ""), meta.get("class", "ASSUMED"), meta.get("source", ""),
                     bool(meta.get("synthetic", basis.get("study", {}).get("synthetic", False))), meta.get("note", ""))
    return reg


def get_path(data: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """Resolve ``a.b.c`` (dict keys; integer tokens index lists) inside nested data."""
    cur: Any = data
    for token in dotted.split("."):
        if isinstance(cur, dict):
            if token not in cur:
                return default
            cur = cur[token]
        elif isinstance(cur, list):
            try:
                cur = cur[int(token)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return cur
