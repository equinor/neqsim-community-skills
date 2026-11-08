"""Standards and acceptance-basis register.

The register records *what must be checked*, not what the standards say. It never carries design
factors, material ratings or acceptance limits: those must be taken from the verified edition of the
governing document (or the operator/regulator) and entered as supplied limits with a source. Every
seeded entry starts as ``TO_VERIFY`` - edition, amendments, applicability and exclusions are not
verified by this skill.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

STANDARD_STATUS = ("TO_VERIFY", "VERIFIED_APPLICABLE", "VERIFIED_NOT_APPLICABLE", "COMPLIANT_EVIDENCE_REVIEWED", "NON_COMPLIANT", "NOT_ASSESSED")
ASSESSMENT_AREAS = ("well_integrity", "well_control", "borehole_stability", "flow_assurance", "materials", "operations", "reservoir", "facility")


@dataclass
class StandardEntry:
    """One row of the standards register."""

    id: str
    requirement_topic: str
    source_document: str
    edition_checked: str = "NOT_VERIFIED"
    applicability: str = "TO_VERIFY"
    verification_method: str = ""
    assessment_area: str = "well_integrity"
    status: str = "TO_VERIFY"
    evidence: str = ""
    notes: str = ""


_SEED = [
    ("STD-001", "Well barrier philosophy, barrier elements, acceptance criteria and verification (drilling, completion, production, abandonment)",
     "NORSOK D-010 (or the jurisdiction's equivalent well-integrity standard)", "Barrier schematics per well state; verification evidence per element; "
     "independent review of element acceptance tables", "well_integrity"),
    ("STD-002", "Well integrity management in the operational phase", "ISO 16530-1 (or successor)", "Operating-envelope table, monitoring plan, "
     "annulus pressure limits supplied by the operator", "well_integrity"),
    ("STD-003", "Casing, tubing and connection performance properties and design-formula basis", "ISO/TR 10400 / API TR 5C3 and API 5CT/5C2 product data",
     "Rating calculation against the manufacturer's datasheet; design factors from the operator's casing-design standard", "well_integrity"),
    ("STD-004", "Materials for H2S-containing and CO2/chloride environments (sour service, cracking resistance)", "ISO 15156 (NACE MR0175) parts 1-3",
     "Partial-pressure and pH screening, then materials engineer selection against the verified edition", "materials"),
    ("STD-005", "Erosional-velocity and flow-line sizing practice", "API RP 14E (screening) / operator velocity criteria",
     "Erosional ratio from the hydraulics model against the operator-approved C-factor", "flow_assurance"),
    ("STD-006", "Wellhead, tree and subsea equipment design and testing", "API 6A / API 17D / ISO 13628 series as applicable",
     "Equipment datasheets and pressure-class selection by the equipment engineer", "well_integrity"),
    ("STD-007", "Well control, kick tolerance and BOP requirements", "Operator well-control standard / regulator regulations / API Std 53",
     "Kick-tolerance and BOP assessment by the drilling engineer (separate from integrity)", "well_control"),
    ("STD-008", "Borehole stability and pore/fracture-pressure window", "Operator geomechanics procedure",
     "Geomechanics model by a specialist; this skill only specifies the interface", "borehole_stability"),
    ("STD-009", "Regulatory and operator well requirements for the jurisdiction (permits, DPR/well programme, abandonment)",
     "Jurisdiction regulations and company requirements (to be identified at study start)", "Requirements lookup by the study lead; record the "
     "document and the edition", "operations"),
    ("STD-010", "Subsea well and tree interface, intervention and workover system requirements", "ISO 13628 series / company requirements as applicable",
     "Subsea engineer review", "operations"),
    ("STD-011", "Corrosion rate prediction and inhibition basis", "NORSOK M-506 (CO2 corrosion model) / ISO 21457 as applicable",
     "NeqSim screening class plus corrosion-engineer review", "materials"),
    ("STD-012", "Hydrate, wax and scale management basis", "Operator flow-assurance guideline / laboratory data",
     "Phase-behaviour calculation plus laboratory confirmation", "flow_assurance"),
]


def _jurisdiction_rows(jurisdiction: str) -> List[StandardEntry]:
    """Return TO_VERIFY rows for the laws, regulations and contract terms of a known jurisdiction.

    Uses ``jurisdiction_basis.activity_basis`` when that skill is installed; returns no rows when it is
    missing or the jurisdiction is unknown. Rows name what to check; they carry no limits.
    """
    try:
        from jurisdiction_basis import activity_basis
    except ImportError:
        return []
    block = activity_basis(jurisdiction, ("well",))
    area_by_topic = {"well_control_bop": "well_control", "materials_sour_chemicals": "materials"}
    rows: List[StandardEntry] = []
    seen = set()
    for topic, item in block.get("activities", {}).get("well", {}).items():
        for r in item["instruments"]:
            if r["layer"] == "standard-referenced" or r["instrument"] in seen:
                continue
            seen.add(r["instrument"])
            rows.append(StandardEntry(
                "STD-J{:02d}".format(len(rows) + 1), item["title"], r["instrument"],
                applicability="TO_VERIFY (jurisdiction: {}; {}; registry status {})".format(jurisdiction, r["authority"], r["status"]),
                verification_method="Fetch the current text at the authority; record edition and clause; {}".format(r["note"]),
                assessment_area=area_by_topic.get(topic, "operations")))
    return rows


def seed_register(jurisdiction: str = "TO_BE_IDENTIFIED") -> List[StandardEntry]:
    """Return the default register (all rows TO_VERIFY) for the study.

    A recognised jurisdiction (for example ``Norway`` or ``US``) adds ``STD-J`` rows for its laws and
    regulations from the optional ``jurisdiction_basis`` skill.
    """
    rows = []
    for sid, topic, doc, method, area in _SEED:
        rows.append(StandardEntry(sid, topic, doc, applicability="TO_VERIFY (jurisdiction: {})".format(jurisdiction), verification_method=method,
                                  assessment_area=area))
    rows.extend(_jurisdiction_rows(jurisdiction))
    return rows


def update_entry(register: List[StandardEntry], entry_id: str, **changes: Any) -> StandardEntry:
    """Update fields of one entry (validates the status value).

    Raises:
        KeyError: when the id is unknown.
        ValueError: when ``status`` is not allowed or a compliant status carries no evidence.
    """
    for e in register:
        if e.id == entry_id:
            for k, v in changes.items():
                setattr(e, k, v)
            if e.status not in STANDARD_STATUS:
                raise ValueError("status must be one of {}".format(STANDARD_STATUS))
            if e.status == "COMPLIANT_EVIDENCE_REVIEWED" and (not e.evidence or e.edition_checked == "NOT_VERIFIED"):
                raise ValueError("a compliance statement needs evidence and a verified edition")
            return e
    raise KeyError(entry_id)


def validate_register(register: List[StandardEntry]) -> List[str]:
    """Return problems: unverified editions behind compliance claims, unknown statuses, duplicate ids."""
    problems: List[str] = []
    seen = set()
    for e in register:
        if e.id in seen:
            problems.append("duplicate id " + e.id)
        seen.add(e.id)
        if e.status not in STANDARD_STATUS:
            problems.append("{}: unknown status {}".format(e.id, e.status))
        if e.status == "COMPLIANT_EVIDENCE_REVIEWED" and (not e.evidence or e.edition_checked == "NOT_VERIFIED"):
            problems.append("{}: compliance claimed without evidence/edition".format(e.id))
    return problems


def summarise(register: List[StandardEntry]) -> Dict[str, int]:
    """Count entries per status."""
    out: Dict[str, int] = {}
    for e in register:
        out[e.status] = out.get(e.status, 0) + 1
    return out


def to_rows(register: List[StandardEntry]) -> List[Dict[str, Any]]:
    """Return rows as dictionaries."""
    return [asdict(e) for e in register]


def ready_for_compliance_statement(register: List[StandardEntry]) -> bool:
    """True only when no entry is still TO_VERIFY/NOT_ASSESSED (otherwise reports must say so)."""
    return all(e.status not in ("TO_VERIFY", "NOT_ASSESSED") for e in register)
