"""Build a public synthetic evidence package for a mixed engineering document."""

# pyright: reportMissingImports=false

from document_intelligence_extraction import DocumentIntelligenceExtractor, EvidenceFact

extractor = DocumentIntelligenceExtractor()
plan = extractor.plan("public_equipment_datasheet.pdf", embedded_text_chars=500)
fact = EvidenceFact(
    field="design_pressure",
    value=150.0,
    unit="bara",
    original_text="Design pressure: 150 bar(a)",
    page=2,
    locator="table:Design Conditions,row:Pressure",
    method="native_tables",
    confidence=0.98,
    safety_critical=True,
)
result = extractor.package(plan, "equipment_datasheet", [fact])
print(result.to_dict())
