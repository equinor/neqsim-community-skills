"""Educational technology-assessment model.

Implements the screening steps of a technology assessment as described in the
public technology-qualification literature (DNV-RP-A203, ISO 20815 Annex I):
decomposition, novelty categorisation, technology readiness level (TRL)
roll-up, enabling/enhancing classification, step-out definition, benefits and
risks, standardisation potential and a preliminary outline of qualification
activities.

The module is dependency-free. It structures and sanity-checks engineering
judgement; it does not replace an expert-panel assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "technology_assessment.v1"

TECHNOLOGY_NOVELTY = ("proven", "limited_history", "new")
APPLICATION_AREA = ("known", "limited_knowledge", "new")
QUALIFIED_BY = ("none", "company", "others")
ROLES = ("enabling", "enhancing")
STEP_OUT_DIRECTIONS = ("max", "min")

STEP_OUT_DIMENSIONS = (
    "design",
    "manufacturing",
    "installation",
    "operability",
    "fluids",
    "operating_conditions",
    "lifetime",
)

# Novelty categorisation (technology novelty x application area).
_CATEGORY_MATRIX = {
    ("proven", "known"): 1,
    ("limited_history", "known"): 2,
    ("new", "known"): 3,
    ("proven", "limited_knowledge"): 2,
    ("limited_history", "limited_knowledge"): 3,
    ("new", "limited_knowledge"): 4,
    ("proven", "new"): 3,
    ("limited_history", "new"): 4,
    ("new", "new"): 4,
}

CATEGORY_DESCRIPTIONS = {
    "1": "Proven: no new technical uncertainty.",
    "2a": "Limited novelty, qualified by the user company: no qualification required.",
    "2b": "Limited novelty, qualified by others: verify that the third-party evidence applies.",
    "2c": "Limited novelty, unqualified: qualification required, low-to-medium risk.",
    "3": "New technical challenges: qualification required, medium risk.",
    "4": "Demanding new technical challenges: qualification required, high risk.",
}

TRL_SCALE = {
    0: ("Unproven idea", "Paper concept; no analysis or testing."),
    1: ("Concept demonstrated", "Basic functionality shown by analysis, analogy or sub-component tests."),
    2: ("Concept validated", "Novel features validated by models or small-scale laboratory tests."),
    3: ("New technology tested", "First version built and tested over a limited range of conditions."),
    4: ("Qualified for first use", "Large-scale version tested in the intended environment; scale effects understood."),
    5: ("Integration tested", "Full-scale unit integrated in its environment with interface and function tests."),
    6: ("In operation", "Operated to predefined performance criteria for a limited period."),
    7: ("Proven", "Operated to performance and reliability criteria long enough to reveal time effects."),
}

_QUALIFICATION_ACTIVITIES = {
    "1": [
        "Confirm the applicable industry standard or specification and comply with it.",
        "Verify with ordinary design review and QA/QC; no technology qualification needed.",
    ],
    "2a": [
        "Confirm the existing company qualification covers the intended operating envelope.",
        "Record the qualification evidence in the technology qualification basis.",
    ],
    "2b": [
        "Gap-analyse the third-party qualification evidence against the intended application.",
        "Verify TRL 4 independently before first use; close gaps with targeted analysis or tests.",
    ],
    "2c": [
        "Define acceptance criteria and qualify by analysis, component tests or documented experience.",
        "Rank failure modes and cover critical ones in the qualification plan.",
    ],
    "3": [
        "Validate models and critical parameters with representative tests.",
        "Test a large-scale version in the intended environment to reach TRL 4.",
        "Hold independent review at qualification milestones.",
    ],
    "4": [
        "Stage the qualification: concept validation, small-scale tests, then large-scale tests.",
        "Reduce the largest uncertainties first and review at each decision gate.",
        "Appoint independent expert review and plan for fallback options.",
    ],
}

_QUALIFICATION_RISK = {
    "1": "none",
    "2a": "none",
    "2b": "low",
    "2c": "low-to-medium",
    "3": "medium",
    "4": "high",
}

_REQUIRED_STEP_OUT_NOTE = "No step-out defined for {}; state whether it is within existing experience."


@dataclass(frozen=True)
class NoveltyCategory:
    """Result of a novelty categorisation."""

    category: int
    label: str
    description: str
    qualification_required: bool
    qualification_risk: str


@dataclass(frozen=True)
class TechnologyElement:
    """One element of the technology decomposition."""

    element_id: str
    name: str
    parent_id: str | None = None
    function: str = ""
    kind: str = "component"
    technology_novelty: str = "proven"
    application_area: str = "known"
    qualified_by: str = "none"
    trl: int = 0
    evidence: tuple[str, ...] = ()
    lifecycle_phases: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class StepOutItem:
    """Step-out from existing experience along one dimension."""

    dimension: str
    experience_basis: str = ""
    proposed: str = ""
    reference_value: float | None = None
    proposed_value: float | None = None
    unit: str = ""
    direction: str = "max"
    note: str = ""


@dataclass(frozen=True)
class BenefitRisk:
    """A benefit or risk of using the technology."""

    text: str
    kind: str = ""
    mitigation: str = ""


def _require_choice(name: str, value: str, choices: Sequence[str]) -> None:
    if value not in choices:
        raise ValueError("{} must be one of {}, got {!r}".format(name, list(choices), value))


def categorize(
    technology_novelty: str, application_area: str, qualified_by: str = "none"
) -> NoveltyCategory:
    """Return the novelty category for a technology element.

    Args:
        technology_novelty: ``proven``, ``limited_history`` or ``new``.
        application_area: ``known``, ``limited_knowledge`` or ``new``.
        qualified_by: Who qualified a category-2 element: ``company``, ``others`` or ``none``.

    Returns:
        The category (1-4), a label (``1``, ``2a``, ``2b``, ``2c``, ``3`` or ``4``) and the way forward.

    Raises:
        ValueError: If an argument is not one of the accepted values.
    """
    _require_choice("technology_novelty", technology_novelty, TECHNOLOGY_NOVELTY)
    _require_choice("application_area", application_area, APPLICATION_AREA)
    _require_choice("qualified_by", qualified_by, QUALIFIED_BY)
    category = _CATEGORY_MATRIX[(technology_novelty, application_area)]
    if category == 2:
        label = {"company": "2a", "others": "2b", "none": "2c"}[qualified_by]
    else:
        label = str(category)
    return NoveltyCategory(
        category=category,
        label=label,
        description=CATEGORY_DESCRIPTIONS[label],
        qualification_required=label not in ("1", "2a"),
        qualification_risk=_QUALIFICATION_RISK[label],
    )


def classify_role(critical_to_business_case: bool, qualified_fallback_available: bool) -> dict[str, Any]:
    """Classify a technology as enabling or enhancing.

    Args:
        critical_to_business_case: True when the business case cannot be realised without it.
        qualified_fallback_available: True when a qualified or proven fallback exists.

    Returns:
        A mapping with ``role`` and a ``rationale`` sentence.
    """
    if critical_to_business_case and not qualified_fallback_available:
        return {
            "role": "enabling",
            "rationale": "Critical to the business case with no qualified fallback; the project "
            "critical path may run through the qualification.",
        }
    return {
        "role": "enhancing",
        "rationale": "The project is not fully dependent on it, or a qualified fallback exists; "
        "it improves the concept or the business case.",
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class TechnologyAssessment:
    """Builds and evaluates a technology assessment.

    Example:
        >>> ta = TechnologyAssessment("Demo technology")
        >>> ta.add_element(TechnologyElement("S1", "System", technology_novelty="new", trl=2))
        >>> ta.assess()["summary"]["system_trl"]
        2
    """

    def __init__(
        self,
        technology_name: str,
        *,
        description: str = "",
        intended_use: str = "",
        environment: str = "",
        functions: Sequence[str] = (),
        performance_expectations: Sequence[str] = (),
        regulatory_requirements: Sequence[str] = (),
        critical_to_business_case: bool = False,
        qualified_fallback_available: bool = True,
        interfaces_untested: bool = False,
        system_trl_override: int | None = None,
        system_trl_override_rationale: str = "",
    ) -> None:
        if not technology_name or not technology_name.strip():
            raise ValueError("technology_name must be a non-empty string")
        self.technology_name = technology_name.strip()
        self.description = description
        self.intended_use = intended_use
        self.environment = environment
        self.functions = tuple(functions)
        self.performance_expectations = tuple(performance_expectations)
        self.regulatory_requirements = tuple(regulatory_requirements)
        self.critical_to_business_case = critical_to_business_case
        self.qualified_fallback_available = qualified_fallback_available
        self.interfaces_untested = interfaces_untested
        if system_trl_override is not None:
            if not 0 <= system_trl_override <= 7:
                raise ValueError("system_trl_override must be between 0 and 7")
            if not system_trl_override_rationale.strip():
                raise ValueError("system_trl_override requires a rationale")
        self.system_trl_override = system_trl_override
        self.system_trl_override_rationale = system_trl_override_rationale
        self._elements: dict[str, TechnologyElement] = {}
        self._step_out: list[StepOutItem] = []
        self._benefits: list[BenefitRisk] = []
        self._risks: list[BenefitRisk] = []
        self.standardisation: list[str] = []
        self.multi_implementation: list[str] = []

    @property
    def elements(self) -> tuple[TechnologyElement, ...]:
        """Return the elements in insertion order."""
        return tuple(self._elements.values())

    def add_element(self, element: TechnologyElement) -> None:
        """Add a validated element to the decomposition.

        Args:
            element: The element to add.

        Raises:
            ValueError: On a duplicate id, unknown choice value or TRL outside 0-7.
        """
        if not element.element_id.strip():
            raise ValueError("element_id must be non-empty")
        if element.element_id in self._elements:
            raise ValueError("duplicate element_id {!r}".format(element.element_id))
        _require_choice("technology_novelty", element.technology_novelty, TECHNOLOGY_NOVELTY)
        _require_choice("application_area", element.application_area, APPLICATION_AREA)
        _require_choice("qualified_by", element.qualified_by, QUALIFIED_BY)
        if not isinstance(element.trl, int) or isinstance(element.trl, bool) or not 0 <= element.trl <= 7:
            raise ValueError("trl of {!r} must be an integer 0-7".format(element.element_id))
        self._elements[element.element_id] = element

    def add_step_out(self, item: StepOutItem) -> None:
        """Add a step-out item.

        Args:
            item: The step-out item.

        Raises:
            ValueError: If the dimension is empty or the direction is invalid.
        """
        if not item.dimension.strip():
            raise ValueError("dimension must be non-empty")
        _require_choice("direction", item.direction, STEP_OUT_DIRECTIONS)
        for value in (item.reference_value, item.proposed_value):
            if value is not None and not _is_number(value):
                raise ValueError("step-out values must be numbers or None")
        self._step_out.append(item)

    def add_benefit(self, text: str, kind: str = "") -> None:
        """Add a benefit.

        Args:
            text: Description of the benefit.
            kind: Optional category such as ``cost``, ``schedule``, ``emissions`` or ``HSE``.
        """
        self._benefits.append(BenefitRisk(text=text, kind=kind))

    def add_risk(self, text: str, kind: str = "", mitigation: str = "") -> None:
        """Add a risk of using the technology.

        Args:
            text: Description of the risk.
            kind: Optional category.
            mitigation: Optional mitigation.
        """
        self._risks.append(BenefitRisk(text=text, kind=kind, mitigation=mitigation))

    def _validate_tree(self) -> None:
        for element in self._elements.values():
            parent = element.parent_id
            if parent is None:
                continue
            if parent not in self._elements:
                raise ValueError(
                    "element {!r} has unknown parent {!r}".format(element.element_id, parent)
                )
            seen = {element.element_id}
            while parent is not None:
                if parent in seen:
                    raise ValueError("cycle in decomposition at {!r}".format(parent))
                seen.add(parent)
                parent = self._elements[parent].parent_id

    def _element_result(self, element: TechnologyElement) -> dict[str, Any]:
        cat = categorize(element.technology_novelty, element.application_area, element.qualified_by)
        flags: list[str] = []
        if cat.label == "1" and element.trl < 7:
            flags.append("Category 1 (proven) but TRL < 7: proven status requires TRL 7 evidence.")
        if cat.category >= 2 and element.trl == 7:
            flags.append("TRL 7 but novelty category >= 2: reconcile the claimed maturity.")
        if cat.qualification_required and not element.evidence:
            flags.append("Novel element without documented evidence; record the supporting sources.")
        if cat.label == "2b" and element.trl < 4:
            flags.append("Qualified by others (2b) but TRL < 4: third-party qualification is not verified.")
        return {
            "id": element.element_id,
            "name": element.name,
            "parent_id": element.parent_id,
            "kind": element.kind,
            "function": element.function,
            "technology_novelty": element.technology_novelty,
            "application_area": element.application_area,
            "qualified_by": element.qualified_by,
            "category": cat.category,
            "category_label": cat.label,
            "category_description": cat.description,
            "qualification_required": cat.qualification_required,
            "qualification_risk": cat.qualification_risk,
            "trl": element.trl,
            "trl_name": TRL_SCALE[element.trl][0],
            "evidence": list(element.evidence),
            "lifecycle_phases": list(element.lifecycle_phases),
            "notes": element.notes,
            "flags": flags,
        }

    def _step_out_result(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        for item in self._step_out:
            status = "qualitative: assess against experience"
            ratio = None
            if item.reference_value is not None and item.proposed_value is not None:
                if item.reference_value != 0:
                    ratio = item.proposed_value / item.reference_value
                beyond = (
                    item.proposed_value > item.reference_value
                    if item.direction == "max"
                    else item.proposed_value < item.reference_value
                )
                status = "step-out beyond experience" if beyond else "within experience"
            rows.append(
                {
                    "dimension": item.dimension,
                    "experience_basis": item.experience_basis,
                    "proposed": item.proposed,
                    "reference_value": item.reference_value,
                    "proposed_value": item.proposed_value,
                    "unit": item.unit,
                    "direction": item.direction,
                    "ratio": ratio,
                    "status": status,
                    "note": item.note,
                }
            )
        covered = {item.dimension for item in self._step_out}
        gaps = [_REQUIRED_STEP_OUT_NOTE.format(dim) for dim in STEP_OUT_DIMENSIONS if dim not in covered]
        return rows, gaps

    def _qualification_outline(self, results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        outline = []
        for res in results:
            label = res["category_label"]
            if label == "1":
                continue
            outline.append(
                {
                    "element_id": res["id"],
                    "element": res["name"],
                    "category": label,
                    "current_trl": res["trl"],
                    "target_trl": 4,
                    "activities": list(_QUALIFICATION_ACTIVITIES[label]),
                }
            )
        return outline

    def assess(self) -> dict[str, Any]:
        """Evaluate the assessment and return a ``technology_assessment.v1`` mapping.

        Returns:
            A JSON-serialisable mapping with element results, summary, step-out,
            benefits, risks, qualification outline, flags, data gaps and assumptions.

        Raises:
            ValueError: If there are no elements or the decomposition is inconsistent.
        """
        if not self._elements:
            raise ValueError("add at least one technology element before assessing")
        self._validate_tree()
        results = [self._element_result(e) for e in self._elements.values()]
        min_trl = min(r["trl"] for r in results)
        system_trl = min_trl
        system_note = "Minimum TRL over all elements."
        if self.interfaces_untested and min_trl > 0:
            system_trl = min_trl - 1
            system_note = (
                "Minimum element TRL reduced by one level because interfaces between elements "
                "are untested; replace with a documented system-level evaluation."
            )
        if self.system_trl_override is not None:
            if self.system_trl_override > min_trl:
                raise ValueError("system_trl_override may not exceed the lowest element TRL")
            system_trl = self.system_trl_override
            system_note = "Override: " + self.system_trl_override_rationale
        novel = [r for r in results if r["qualification_required"]]
        highest = max(r["category"] for r in results)
        step_out, step_gaps = self._step_out_result()
        role = classify_role(self.critical_to_business_case, self.qualified_fallback_available)
        flags = [
            "{}: {}".format(r["id"], flag) for r in results for flag in r["flags"]
        ]
        for row in step_out:
            if row["status"] == "step-out beyond experience":
                flags.append("Step-out in {}: {} (reference {} {}).".format(
                    row["dimension"], row["proposed"] or row["proposed_value"],
                    row["reference_value"], row["unit"]).strip())
        data_gaps = list(step_gaps)
        if not self._benefits:
            data_gaps.append("No benefits recorded.")
        if not self._risks:
            data_gaps.append("No risks recorded.")
        if not self.standardisation and not self.multi_implementation:
            data_gaps.append("Standardisation / multi-implementation potential not assessed.")
        for field_name, value in (
            ("technology description", self.description),
            ("intended use", self.intended_use),
            ("environment", self.environment),
        ):
            if not value:
                data_gaps.append("Qualification basis: {} missing.".format(field_name))
        if not self.functions:
            data_gaps.append("Qualification basis: functions missing.")
        if not self.performance_expectations:
            data_gaps.append("Qualification basis: performance expectations missing.")
        if not self.regulatory_requirements:
            data_gaps.append("Qualification basis: applicable regulatory requirements not stated.")
        return {
            "schema_version": SCHEMA_VERSION,
            "technology": self.technology_name,
            "qualification_basis": {
                "description": self.description,
                "intended_use": self.intended_use,
                "environment": self.environment,
                "functions": list(self.functions),
                "performance_expectations": list(self.performance_expectations),
                "regulatory_requirements": list(self.regulatory_requirements),
            },
            "elements": results,
            "summary": {
                "element_count": len(results),
                "novel_element_count": len(novel),
                "highest_category": highest,
                "system_trl": system_trl,
                "system_trl_name": TRL_SCALE[system_trl][0],
                "system_trl_basis": system_note,
                "qualification_required": bool(novel),
                "role": role["role"],
                "role_rationale": role["rationale"],
            },
            "step_out": step_out,
            "benefits": [vars(b) for b in self._benefits],
            "risks": [vars(r) for r in self._risks],
            "standardisation": list(self.standardisation),
            "multi_implementation": list(self.multi_implementation),
            "qualification_outline": self._qualification_outline(results),
            "flags": flags,
            "data_gaps": data_gaps,
            "assumptions": [
                "Novelty categories and TRLs are expert judgement; only documented, traceable and "
                "accessible evidence may reduce novelty.",
                "Novelty categorisation ignores consequence of failure; use the FMIRR to rank risk.",
                "Proven (category 1) elements still need verification to the applicable standard.",
                "Educational screening; human review by a qualified technology-qualification panel "
                "is required.",
            ],
        }


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def from_dict(spec: Mapping[str, Any]) -> TechnologyAssessment:
    """Build a :class:`TechnologyAssessment` from a JSON-style mapping.

    Args:
        spec: Mapping with ``technology`` plus optional ``qualification_basis``,
            ``role``, ``elements``, ``step_out``, ``benefits``, ``risks``,
            ``standardisation`` and ``multi_implementation`` keys.

    Returns:
        The populated assessment, ready for :meth:`TechnologyAssessment.assess`.

    Raises:
        ValueError: If required keys are missing or values are invalid.
    """
    if "technology" not in spec:
        raise ValueError("spec requires a 'technology' name")
    basis = spec.get("qualification_basis", {}) or {}
    role = spec.get("role", {}) or {}
    ta = TechnologyAssessment(
        spec["technology"],
        description=basis.get("description", ""),
        intended_use=basis.get("intended_use", ""),
        environment=basis.get("environment", ""),
        functions=_tuple(basis.get("functions")),
        performance_expectations=_tuple(basis.get("performance_expectations")),
        regulatory_requirements=_tuple(basis.get("regulatory_requirements")),
        critical_to_business_case=bool(role.get("critical_to_business_case", False)),
        qualified_fallback_available=bool(role.get("qualified_fallback_available", True)),
        interfaces_untested=bool(spec.get("interfaces_untested", False)),
        system_trl_override=spec.get("system_trl_override"),
        system_trl_override_rationale=spec.get("system_trl_override_rationale", ""),
    )
    for raw in spec.get("elements", []):
        ta.add_element(
            TechnologyElement(
                element_id=str(raw["id"]),
                name=raw.get("name", str(raw["id"])),
                parent_id=raw.get("parent_id"),
                function=raw.get("function", ""),
                kind=raw.get("kind", "component"),
                technology_novelty=raw.get("technology_novelty", "proven"),
                application_area=raw.get("application_area", "known"),
                qualified_by=raw.get("qualified_by", "none"),
                trl=raw.get("trl", 0),
                evidence=_tuple(raw.get("evidence")),
                lifecycle_phases=_tuple(raw.get("lifecycle_phases")),
                notes=raw.get("notes", ""),
            )
        )
    for raw in spec.get("step_out", []):
        ta.add_step_out(
            StepOutItem(
                dimension=raw["dimension"],
                experience_basis=raw.get("experience_basis", ""),
                proposed=raw.get("proposed", ""),
                reference_value=raw.get("reference_value"),
                proposed_value=raw.get("proposed_value"),
                unit=raw.get("unit", ""),
                direction=raw.get("direction", "max"),
                note=raw.get("note", ""),
            )
        )
    for raw in spec.get("benefits", []):
        ta.add_benefit(raw["text"], raw.get("kind", ""))
    for raw in spec.get("risks", []):
        ta.add_risk(raw["text"], raw.get("kind", ""), raw.get("mitigation", ""))
    ta.standardisation.extend(_tuple(spec.get("standardisation")))
    ta.multi_implementation.extend(_tuple(spec.get("multi_implementation")))
    return ta
