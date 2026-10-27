"""Educational failure-mode identification and risk-ranking (FMIRR) register.

Registers failure modes of novel technology elements, keeps the failed item,
failure mode, failure mechanism and failure cause in separate fields (ISO 14224
terminology), ranks risk from consequence and probability classes on a 5x5 matrix
and links critical failure modes to qualification activities.

The scales and matrix are illustrative defaults based on the public
technology-qualification literature; adapt them to the case and keep the adapted
version under version control. The module is dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "technology_fmirr.v1"

RISK_LEVELS = ("Low", "Medium", "High")

# Rows are probability class 1..5, columns are consequence class 1..5.
DEFAULT_MATRIX = {
    1: ("Low", "Low", "Low", "Low", "Low"),
    2: ("Low", "Low", "Low", "Medium", "Medium"),
    3: ("Low", "Low", "Medium", "Medium", "High"),
    4: ("Low", "Medium", "Medium", "High", "High"),
    5: ("Low", "Medium", "High", "High", "High"),
}

CONSEQUENCE_CLASSES = {
    1: "Insignificant: no or superficial injury, negligible environmental effect, short delay.",
    2: "Minor: slight injury, minor local effect, delay of up to about a day.",
    3: "Moderate: major injury, localised effect needing response, delay of days.",
    4: "Major: single fatality, major environmental effect, delay of weeks.",
    5: "Severe: multiple fatalities, massive effect, loss of main function and damage to interfaces.",
}

PROBABILITY_CLASSES = {
    1: "Failure not expected (below about 1e-4 within the reference period).",
    2: "Has occurred in the industry or a related industry (about 1e-4 to 1e-3).",
    3: "Experienced by most operators (about 1e-3 to 1e-2).",
    4: "Occurs several times per year per operator (about 1e-2 to 1e-1).",
    5: "Occurs several times per year per facility (above about 1e-1).",
}

FAILURE_MECHANISM_CLASSES = (
    "Mechanical failure",
    "Material failure",
    "Instrumentation failure",
    "Electrical failure",
    "External influence",
    "Miscellaneous",
)

FAILURE_CAUSE_CLASSES = (
    "Design-related",
    "Fabrication/installation-related",
    "Operation/maintenance-related",
    "Management-related",
    "Miscellaneous",
)

LIFECYCLE_PHASES = (
    "design",
    "fabrication and testing",
    "transportation and storage",
    "installation",
    "commissioning",
    "operation and maintenance",
    "decommissioning",
)

_MIXED_TEXT_MARKERS = (" due to ", " caused by ", " because of ", " as a result of ")


@dataclass(frozen=True)
class FailureModeEntry:
    """One row of the FMIRR register."""

    entry_id: str
    item: str
    function: str
    failure_mode: str
    failure_mechanism: str
    failure_mechanism_class: str = ""
    failure_cause: str = ""
    failure_cause_class: str = ""
    detection: str = ""
    consequence_text: str = ""
    consequence_class: int = 1
    probability_class: int = 1
    comments: str = ""
    qualification_test: str = ""
    lifecycle_phase: str = ""
    novelty_category: str = ""


def _check_class(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise ValueError("{} must be an integer 1-5, got {!r}".format(name, value))


def risk_level(
    consequence_class: int,
    probability_class: int,
    *,
    matrix: Mapping[int, Sequence[str]] | None = None,
    high_consequence_floor: bool = True,
) -> str:
    """Return ``Low``, ``Medium`` or ``High`` for a consequence and probability class.

    Args:
        consequence_class: Consequence class 1-5.
        probability_class: Probability class 1-5.
        matrix: Optional 5x5 matrix keyed by probability class; defaults to the illustrative matrix.
        high_consequence_floor: When true, consequence class 5 is never rated below ``Medium`` so
            that high-consequence, low-probability failure modes are not dismissed.

    Returns:
        The risk level.

    Raises:
        ValueError: If a class is outside 1-5 or the matrix is malformed.
    """
    _check_class("consequence_class", consequence_class)
    _check_class("probability_class", probability_class)
    grid = matrix if matrix is not None else DEFAULT_MATRIX
    try:
        level = grid[probability_class][consequence_class - 1]
    except (KeyError, IndexError) as exc:
        raise ValueError("risk matrix must cover probability and consequence classes 1-5") from exc
    if level not in RISK_LEVELS:
        raise ValueError("risk matrix entries must be one of {}".format(list(RISK_LEVELS)))
    if high_consequence_floor and consequence_class == 5 and level == "Low":
        return "Medium"
    return level


class FmirrRegister:
    """Failure-mode register with risk ranking and re-rating history.

    Example:
        >>> reg = FmirrRegister("Demo")
        >>> reg.add(FailureModeEntry("1.1", "Seal", "Contain gas", "External leakage",
        ...     "Material fatigue", consequence_class=4, probability_class=3))
        >>> reg.evaluate()["summary"]["critical_count"]
        1
    """

    def __init__(
        self,
        technology: str,
        *,
        matrix: Mapping[int, Sequence[str]] | None = None,
        high_consequence_floor: bool = True,
    ) -> None:
        if not technology or not technology.strip():
            raise ValueError("technology must be a non-empty string")
        self.technology = technology.strip()
        self.matrix = dict(matrix) if matrix is not None else None
        self.high_consequence_floor = high_consequence_floor
        self._entries: dict[str, FailureModeEntry] = {}
        self._history: list[dict[str, Any]] = []
        self.iteration = 1

    @property
    def entries(self) -> tuple[FailureModeEntry, ...]:
        """Return the entries in insertion order."""
        return tuple(self._entries.values())

    def _risk(self, entry: FailureModeEntry) -> str:
        return risk_level(
            entry.consequence_class,
            entry.probability_class,
            matrix=self.matrix,
            high_consequence_floor=self.high_consequence_floor,
        )

    def add(self, entry: FailureModeEntry) -> None:
        """Add a failure mode.

        Args:
            entry: The failure mode entry.

        Raises:
            ValueError: On a duplicate id, an empty mandatory field or a class outside 1-5.
        """
        if not entry.entry_id.strip():
            raise ValueError("entry_id must be non-empty")
        if entry.entry_id in self._entries:
            raise ValueError("duplicate entry_id {!r}".format(entry.entry_id))
        for name in ("item", "failure_mode"):
            if not getattr(entry, name).strip():
                raise ValueError("{} must be non-empty for entry {!r}".format(name, entry.entry_id))
        _check_class("consequence_class", entry.consequence_class)
        _check_class("probability_class", entry.probability_class)
        self._entries[entry.entry_id] = entry

    def rerate(
        self,
        entry_id: str,
        *,
        consequence_class: int | None = None,
        probability_class: int | None = None,
        basis: str,
    ) -> None:
        """Re-rate a failure mode after new evidence and keep the previous rating.

        Args:
            entry_id: Id of an existing entry.
            consequence_class: New consequence class, or None to keep.
            probability_class: New probability class, or None to keep.
            basis: Evidence or mitigation that justifies the change (mandatory).

        Raises:
            KeyError: If the entry does not exist.
            ValueError: If the basis is empty or a class is outside 1-5.
        """
        if not basis.strip():
            raise ValueError("a re-rating requires a basis")
        old = self._entries[entry_id]
        new = replace(
            old,
            consequence_class=old.consequence_class if consequence_class is None else consequence_class,
            probability_class=old.probability_class if probability_class is None else probability_class,
        )
        _check_class("consequence_class", new.consequence_class)
        _check_class("probability_class", new.probability_class)
        self._history.append(
            {
                "entry_id": entry_id,
                "iteration": self.iteration,
                "consequence_class": old.consequence_class,
                "probability_class": old.probability_class,
                "risk": self._risk(old),
                "basis": basis,
            }
        )
        self._entries[entry_id] = new

    def next_iteration(self) -> int:
        """Start a new FMIRR iteration; the FMIRR is repeated as qualification progresses.

        Returns:
            The new iteration number.
        """
        self.iteration += 1
        return self.iteration

    def _findings(self, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []

        def add(level: str, entry_id: str, text: str) -> None:
            findings.append({"level": level, "entry_id": entry_id, "text": text})

        for entry, row in zip(self._entries.values(), rows):
            eid = entry.entry_id
            if entry.failure_mode.strip().lower() == entry.item.strip().lower():
                add("warning", eid, "Failure mode repeats the failed item; keep item and mode separate.")
            lowered = " " + entry.failure_mode.lower() + " "
            if any(marker in lowered for marker in _MIXED_TEXT_MARKERS):
                add("warning", eid, "Failure mode text mixes in a mechanism or cause; use separate columns.")
            if not entry.failure_mechanism.strip():
                add("warning", eid, "Failure mechanism missing.")
            elif entry.failure_mechanism_class and entry.failure_mechanism_class not in FAILURE_MECHANISM_CLASSES:
                add("warning", eid, "Mechanism class {!r} is not a recognised class.".format(
                    entry.failure_mechanism_class))
            if entry.failure_cause_class and entry.failure_cause_class not in FAILURE_CAUSE_CLASSES:
                add("warning", eid, "Cause class {!r} is not a recognised class.".format(
                    entry.failure_cause_class))
            if entry.lifecycle_phase and entry.lifecycle_phase not in LIFECYCLE_PHASES:
                add("info", eid, "Life-cycle phase {!r} is not in the standard list.".format(
                    entry.lifecycle_phase))
            if row["critical"]:
                if not entry.qualification_test.strip():
                    add("gap", eid, "Critical failure mode has no qualification activity (TEST) linked.")
                if not entry.detection.strip():
                    add("gap", eid, "Critical failure mode has no detection method stated.")
            if entry.novelty_category == "1" and row["critical"]:
                add("info", eid, "Critical mode on a proven element: verify to the applicable standard.")
        return findings

    def evaluate(self) -> dict[str, Any]:
        """Rank the register and return a ``technology_fmirr.v1`` mapping.

        Returns:
            A JSON-serialisable mapping with rows, summary, risk-matrix counts,
            findings, history and assumptions.

        Raises:
            ValueError: If the register is empty.
        """
        if not self._entries:
            raise ValueError("add at least one failure mode before evaluating")
        rows: list[dict[str, Any]] = []
        for entry in self._entries.values():
            level = self._risk(entry)
            rows.append(
                {
                    "id": entry.entry_id,
                    "item": entry.item,
                    "function": entry.function,
                    "failure_mode": entry.failure_mode,
                    "failure_mechanism": entry.failure_mechanism,
                    "failure_mechanism_class": entry.failure_mechanism_class,
                    "failure_cause": entry.failure_cause,
                    "failure_cause_class": entry.failure_cause_class,
                    "detection": entry.detection,
                    "consequence": entry.consequence_text,
                    "consequence_class": entry.consequence_class,
                    "probability_class": entry.probability_class,
                    "risk": level,
                    "critical": level in ("Medium", "High"),
                    "comments": entry.comments,
                    "test": entry.qualification_test,
                    "lifecycle_phase": entry.lifecycle_phase,
                    "novelty_category": entry.novelty_category,
                }
            )
        counts = {level: sum(1 for r in rows if r["risk"] == level) for level in RISK_LEVELS}
        order = {"High": 0, "Medium": 1, "Low": 2}
        critical = sorted(
            (r for r in rows if r["critical"]),
            key=lambda r: (order[r["risk"]], -r["consequence_class"], -r["probability_class"], r["id"]),
        )
        grid = {
            str(p): [
                sum(1 for r in rows if r["probability_class"] == p and r["consequence_class"] == c)
                for c in range(1, 6)
            ]
            for p in range(5, 0, -1)
        }
        covered = {r["lifecycle_phase"] for r in rows if r["lifecycle_phase"]}
        findings = self._findings(rows)
        for phase in LIFECYCLE_PHASES:
            if phase not in covered:
                findings.append(
                    {"level": "gap", "entry_id": "", "text": "No failure mode registered for life-cycle phase: {}.".format(phase)}
                )
        linked = [r for r in critical if r["test"].strip()]
        return {
            "schema_version": SCHEMA_VERSION,
            "technology": self.technology,
            "iteration": self.iteration,
            "rows": rows,
            "summary": {
                "total": len(rows),
                "counts": counts,
                "critical_count": len(critical),
                "critical_ids": [r["id"] for r in critical],
                "critical_with_test": len(linked),
                "critical_without_test": len(critical) - len(linked),
            },
            "risk_matrix": {
                "rows_probability_5_to_1": grid,
                "columns": "consequence classes 1 to 5",
                "high_consequence_floor": self.high_consequence_floor,
            },
            "scales": {
                "consequence": {str(k): v for k, v in CONSEQUENCE_CLASSES.items()},
                "probability": {str(k): v for k, v in PROBABILITY_CLASSES.items()},
            },
            "findings": findings,
            "history": list(self._history),
            "assumptions": [
                "Consequence is rated for the system as specified, without safeguards not yet adopted.",
                "Probability classes are qualitative until test or experience evidence is available.",
                "Medium and High risk failure modes are critical and must be covered by the "
                "qualification plan; Low risk modes stay in the register.",
                "Scales and matrix are illustrative defaults; adapt them to the case.",
                "The FMIRR is repeated as qualification evidence arrives.",
            ],
        }


def from_dict(spec: Mapping[str, Any]) -> FmirrRegister:
    """Build an :class:`FmirrRegister` from a JSON-style mapping.

    Args:
        spec: Mapping with ``technology`` and ``entries`` (list of mappings using the
            :class:`FailureModeEntry` field names, with ``id`` accepted for ``entry_id``).

    Returns:
        The populated register.

    Raises:
        ValueError: If required keys are missing or entries are invalid.
    """
    if "technology" not in spec:
        raise ValueError("spec requires a 'technology' name")
    reg = FmirrRegister(
        spec["technology"],
        high_consequence_floor=bool(spec.get("high_consequence_floor", True)),
    )
    for raw in spec.get("entries", []):
        data = dict(raw)
        if "id" in data and "entry_id" not in data:
            data["entry_id"] = data.pop("id")
        reg.add(FailureModeEntry(**data))
    return reg
