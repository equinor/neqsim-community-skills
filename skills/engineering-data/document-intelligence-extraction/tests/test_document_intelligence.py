import pytest

from document_intelligence_extraction import (
    DocumentIntelligenceExtractor,
    EvidenceFact,
    find_conflicts,
)


def test_scanned_pdf_routes_through_ocr_tables_and_vision():
    plan = DocumentIntelligenceExtractor().plan("drawing.pdf", embedded_text_chars=12)

    assert [step.method for step in plan.steps] == [
        "native_text",
        "ocr",
        "native_tables",
        "render_pages",
        "vision",
    ]
    assert plan.warnings


def test_images_and_workbooks_use_different_extraction_paths():
    extractor = DocumentIntelligenceExtractor()

    image_methods = [step.method for step in extractor.plan("pid.png").steps]
    table_methods = [step.method for step in extractor.plan("line-list.xlsx").steps]

    assert image_methods == ["image_metadata", "ocr", "vision"]
    assert table_methods == ["structured_tables"]


def test_low_confidence_and_safety_critical_facts_require_review():
    low_confidence = EvidenceFact(
        field="design_pressure",
        value=150,
        unit="bara",
        original_text="Design pressure 150 bar(a)",
        page=4,
        method="ocr",
        confidence=0.74,
    )
    safety_critical = EvidenceFact(
        field="psv_set_pressure",
        value=145,
        unit="bara",
        original_text="PSV set 145 bar(a)",
        locator="sheet:PSV!B12",
        method="structured_tables",
        confidence=0.99,
        safety_critical=True,
    )

    assert low_confidence.review_status == "needs_review"
    assert safety_critical.review_status == "needs_review"


def test_fact_rejects_missing_provenance():
    with pytest.raises(ValueError, match="page or locator"):
        EvidenceFact(
            field="temperature",
            value=40,
            unit="C",
            original_text="Operating temperature 40 C",
            method="native_text",
            confidence=0.95,
        )


def test_package_has_stable_schema_and_detects_source_conflict():
    extractor = DocumentIntelligenceExtractor()
    fact_a = EvidenceFact(
        field="design_pressure",
        value=150,
        unit="bara",
        original_text="Design pressure 150 bar(a)",
        page=1,
        method="native_text",
        confidence=0.98,
    )
    fact_b = EvidenceFact(
        field="design_pressure",
        value=160,
        unit="bara",
        original_text="Design pressure 160 bar(a)",
        locator="sheet:Data!C7",
        method="structured_tables",
        confidence=0.99,
    )
    result_a = extractor.package(extractor.plan("datasheet.pdf", embedded_text_chars=200), "datasheet", [fact_a])
    result_b = extractor.package(extractor.plan("register.xlsx"), "equipment_register", [fact_b])

    payload = result_a.to_dict()
    conflicts = find_conflicts([result_a, result_b])

    assert payload["schema_version"] == "1.0"
    assert payload["quality"]["needs_review"] is False
    assert conflicts[0]["field"] == "design_pressure"
    assert conflicts[0]["status"] == "needs_review"
