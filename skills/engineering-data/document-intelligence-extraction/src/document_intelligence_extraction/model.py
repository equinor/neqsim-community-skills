"""Source-aware planning and evidence contracts for engineering document extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


_NATIVE_TEXT_EXTENSIONS = {".txt", ".md", ".rtf", ".html", ".xml", ".json"}
_TABLE_EXTENSIONS = {".csv", ".tsv", ".xls", ".xlsx", ".xlsm", ".ods"}
_WORD_EXTENSIONS = {".doc", ".docx", ".odt"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic"}
_PRESENTATION_EXTENSIONS = {".ppt", ".pptx", ".odp"}


@dataclass(frozen=True)
class ExtractionStep:
    """One ordered extraction operation and its purpose."""

    method: str
    purpose: str
    required: bool = True


@dataclass(frozen=True)
class ExtractionPlan:
    """A source classification and ordered extraction strategy."""

    source_path: str
    source_format: str
    source_kind: str
    steps: tuple[ExtractionStep, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class EvidenceFact:
    """A normalized fact with enough provenance for independent review."""

    field: str
    value: Any
    unit: str | None
    original_text: str
    method: str
    confidence: float
    page: int | None = None
    locator: str | None = None
    normalized_value: Any | None = None
    normalized_unit: str | None = None
    safety_critical: bool = False
    ambiguous: bool = False
    review_status: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate evidence and assign its review gate."""
        if not self.field.strip():
            raise ValueError("field must not be empty")
        if not self.original_text.strip():
            raise ValueError("original_text is required for traceability")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.page is None and not self.locator:
            raise ValueError("page or locator is required for traceability")
        self.review_status = (
            "needs_review"
            if self.safety_critical or self.ambiguous or self.confidence < 0.85
            else "accepted"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class ExtractionResult:
    """Facts, quality gates, and gaps extracted from one source."""

    source_path: str
    source_format: str
    document_type: str
    facts: list[EvidenceFact]
    extraction_methods: list[str]
    warnings: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        """Return whether any evidence requires human review."""
        return any(fact.review_status == "needs_review" for fact in self.facts)

    @property
    def quality_score(self) -> float:
        """Return a transparent confidence-and-completeness score from 0 to 100."""
        if not self.facts:
            return 0.0
        confidence = sum(fact.confidence for fact in self.facts) / len(self.facts)
        accepted = sum(fact.review_status == "accepted" for fact in self.facts) / len(self.facts)
        gap_penalty = min(0.4, 0.05 * len(self.gaps))
        return round(max(0.0, 100.0 * (0.7 * confidence + 0.3 * accepted - gap_penalty)), 1)

    def to_dict(self) -> dict[str, Any]:
        """Return the stable evidence-package shape used by downstream agents."""
        return {
            "schema_version": "1.0",
            "source": {
                "path": self.source_path,
                "format": self.source_format,
                "document_type": self.document_type,
            },
            "facts": [fact.to_dict() for fact in self.facts],
            "extraction_methods": list(self.extraction_methods),
            "quality": {
                "score": self.quality_score,
                "needs_review": self.needs_review,
                "fact_count": len(self.facts),
            },
            "warnings": list(self.warnings),
            "gaps": list(self.gaps),
        }


class DocumentIntelligenceExtractor:
    """Build extraction plans and governed evidence packages for mixed sources."""

    def __init__(self, minimum_embedded_text_chars: int = 80) -> None:
        """Create an extractor planner.

        Args:
            minimum_embedded_text_chars: Minimum PDF text yield before OCR is optional.
        """
        if minimum_embedded_text_chars < 0:
            raise ValueError("minimum_embedded_text_chars must be non-negative")
        self.minimum_embedded_text_chars = minimum_embedded_text_chars

    def plan(
        self,
        source_path: str | Path,
        *,
        embedded_text_chars: int | None = None,
        contains_visuals: bool | None = None,
    ) -> ExtractionPlan:
        """Classify a source and select native, OCR, table, and vision operations."""
        path = Path(source_path)
        extension = path.suffix.lower()
        warnings: list[str] = []

        if extension == ".pdf":
            steps = [ExtractionStep("native_text", "Extract the embedded text layer")]
            if embedded_text_chars is None or embedded_text_chars < self.minimum_embedded_text_chars:
                steps.append(ExtractionStep("ocr", "Recover text from scanned or low-yield pages"))
                warnings.append("PDF has unknown or low embedded-text yield; OCR is required.")
            steps.append(ExtractionStep("native_tables", "Recover table cells and reading order"))
            steps.append(ExtractionStep("render_pages", "Render pages for layout-preserving review"))
            steps.append(ExtractionStep("vision", "Interpret drawings, charts, symbols, and annotations"))
            return ExtractionPlan(str(path), "pdf", "mixed_document", tuple(steps), tuple(warnings))

        if extension in _IMAGE_EXTENSIONS:
            return ExtractionPlan(
                str(path),
                extension.lstrip("."),
                "image",
                (
                    ExtractionStep("image_metadata", "Read dimensions, orientation, and metadata"),
                    ExtractionStep("ocr", "Recover visible text with coordinates"),
                    ExtractionStep("vision", "Interpret layout, symbols, charts, and relationships"),
                ),
            )

        if extension in _TABLE_EXTENSIONS:
            return ExtractionPlan(
                str(path),
                extension.lstrip("."),
                "table",
                (ExtractionStep("structured_tables", "Read sheets, cells, formulas, and headers"),),
            )

        if extension in _WORD_EXTENSIONS or extension in _PRESENTATION_EXTENSIONS:
            steps = [ExtractionStep("native_document", "Read paragraphs, tables, and metadata")]
            if contains_visuals is not False:
                steps.extend(
                    (
                        ExtractionStep("extract_media", "Extract embedded images and charts"),
                        ExtractionStep("vision", "Interpret extracted visual content"),
                    )
                )
            return ExtractionPlan(str(path), extension.lstrip("."), "office_document", tuple(steps))

        if extension in _NATIVE_TEXT_EXTENSIONS:
            return ExtractionPlan(
                str(path),
                extension.lstrip("."),
                "text",
                (ExtractionStep("native_text", "Read structured text without OCR"),),
            )

        return ExtractionPlan(
            str(path),
            extension.lstrip(".") or "unknown",
            "unknown",
            (ExtractionStep("manual_triage", "Identify a safe parser or conversion route"),),
            ("Unsupported source format; do not infer content before manual triage.",),
        )

    def package(
        self,
        plan: ExtractionPlan,
        document_type: str,
        facts: Iterable[EvidenceFact],
        *,
        warnings: Iterable[str] = (),
        gaps: Iterable[str] = (),
    ) -> ExtractionResult:
        """Create a validated evidence package from adapter-produced facts."""
        fact_list = list(facts)
        methods = list(dict.fromkeys(fact.method for fact in fact_list))
        return ExtractionResult(
            source_path=plan.source_path,
            source_format=plan.source_format,
            document_type=document_type,
            facts=fact_list,
            extraction_methods=methods,
            warnings=list(plan.warnings) + list(warnings),
            gaps=list(gaps),
        )


def find_conflicts(results: Iterable[ExtractionResult]) -> list[dict[str, Any]]:
    """Find fields with differing normalized values across source documents."""
    seen: dict[str, list[tuple[str, Any, str | None]]] = {}
    for result in results:
        for fact in result.facts:
            value = fact.normalized_value if fact.normalized_value is not None else fact.value
            unit = fact.normalized_unit if fact.normalized_unit is not None else fact.unit
            seen.setdefault(fact.field, []).append((result.source_path, value, unit))

    conflicts: list[dict[str, Any]] = []
    for field_name, observations in seen.items():
        distinct = {(repr(value), unit) for _, value, unit in observations}
        if len(distinct) > 1:
            conflicts.append(
                {
                    "field": field_name,
                    "status": "needs_review",
                    "observations": [
                        {"source_path": source, "value": value, "unit": unit}
                        for source, value, unit in observations
                    ],
                }
            )
    return conflicts
