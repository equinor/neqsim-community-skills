"""Data model of a one-line conceptual P&ID."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

KINDS = (
    "equipment", "pump", "gate_valve", "ball_valve", "esdv", "check_valve", "control_valve", "psv",
    "pig_launcher", "pig_receiver", "spec_break", "transmitter", "flow_meter", "sampler", "tie_in", "riser",
    "note_box",
)


@dataclass
class Element:
    """One symbol on the main process line, left to right.

    Attributes:
        kind: one of :data:`KINDS`.
        tag: proposed tag, shown with a trailing ``*`` when ``proposed`` (a tag is never an existing controlled-P&ID tag
            unless the caller read it from the controlled P&ID).
        label: short description under the symbol.
        existing: ``True`` for existing plant (solid), ``False`` for new scope (bold, cloud-marked).
        proposed: tag has been invented for the sketch.
        measure: for transmitters, the measured variable letter (``P``, ``T``, ``F``, ``L``, ``A``).
    """

    kind: str
    tag: str = ""
    label: str = ""
    existing: bool = False
    proposed: bool = True
    measure: str = "P"

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown element kind {self.kind!r}; use one of {KINDS}")


@dataclass
class TieInEndSketch:
    """A sketch of one end of the line."""

    title: str
    subtitle: str
    side: str  # "source" (line leaves) or "landing" (line arrives)
    elements: List[Element] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    options: List[str] = field(default_factory=list)
    line_label: str = ""
    source_ref: Optional[str] = None

    def validate(self) -> List[str]:
        """Return a list of completeness findings (empty when the sketch is internally consistent)."""
        findings: List[str] = []
        kinds = [e.kind for e in self.elements]
        if "esdv" not in kinds:
            findings.append("no ESD valve at the platform boundary")
        if "tie_in" not in kinds:
            findings.append("no tie-in point marked")
        if self.side == "source" and "pig_launcher" not in kinds:
            findings.append("no pig launcher: line cannot be pigged")
        if self.side == "landing" and "pig_receiver" not in kinds:
            findings.append("no pig receiver: line cannot be pigged")
        if "check_valve" not in kinds:
            findings.append("no check valve against back flow")
        if self.side == "landing" and "spec_break" not in kinds:
            findings.append("no spectacle blind / spec break at the tie-in")
        return findings
