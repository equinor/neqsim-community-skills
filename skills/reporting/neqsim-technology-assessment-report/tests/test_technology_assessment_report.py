import json
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[3]
for sibling in (
    SKILLS / "field-development" / "neqsim-technology-assessment" / "src",
    SKILLS / "safety" / "neqsim-technology-fmirr" / "src",
):
    sys.path.insert(0, str(sibling))

from technology_assessment import from_dict as assessment_from_dict  # noqa: E402
from technology_fmirr import from_dict as fmirr_from_dict  # noqa: E402

from technology_assessment_report import ReportMeta, build_report, check_report_inputs  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def assessment():
    path = SKILLS / "field-development" / "neqsim-technology-assessment" / "examples" / "example_novel_technology.json"
    return assessment_from_dict(_load(path)).assess()


@pytest.fixture(scope="module")
def fmirr():
    path = SKILLS / "safety" / "neqsim-technology-fmirr" / "examples" / "example_fmirr.json"
    return fmirr_from_dict(_load(path)).evaluate()


def test_report_has_expected_chapters(assessment, fmirr):
    report = build_report(assessment, fmirr)
    ids = [s.section_id for s in report.sections]
    assert ids == [
        "executive_summary", "introduction", "qualification_basis", "composition", "maturity", "role",
        "step_out", "benefits_risks", "standardisation", "fmirr", "qualification_outline", "conclusions",
        "open_points", "references", "appendix_definitions",
    ]
    assert next(s for s in report.sections if s.section_id == "fmirr").landscape


def test_report_without_fmirr_omits_chapter_and_reports_issue(assessment):
    report = build_report(assessment)
    assert "fmirr" not in [s.section_id for s in report.sections]
    assert any("No FMIRR supplied" in i for i in report.issues)


def test_markdown_contains_key_results(assessment, fmirr):
    md = build_report(assessment, fmirr, ReportMeta(title="Test report", author="A")).to_markdown()
    assert md.startswith("# Test report")
    assert "enabling" in md
    assert "Internal separation device" in md
    assert "1.1.1" in md
    assert "## 10. Failure mode identification" in md
    assert md.count("| --- |") >= 5


def test_narrative_is_appended(assessment, fmirr):
    report = build_report(assessment, fmirr, narrative={"conclusions": ["Author conclusion text."]})
    conclusions = next(s for s in report.sections if s.section_id == "conclusions")
    assert conclusions.blocks[-1].text == "Author conclusion text."


def test_extra_references_listed(assessment):
    report = build_report(assessment, references=["Internal test report TR-1."])
    refs = next(s for s in report.sections if s.section_id == "references")
    assert "Internal test report TR-1." in refs.blocks[0].items


def test_check_inputs_flags_missing_failure_modes(assessment, fmirr):
    trimmed = dict(fmirr)
    trimmed["rows"] = [r for r in fmirr["rows"] if r["item"] != "Internal separation device"]
    issues = check_report_inputs(assessment, trimmed)
    assert any("S.2" in i and "no failure mode" in i for i in issues)


def test_check_inputs_flags_name_mismatch(assessment, fmirr):
    other = dict(fmirr, technology="Another technology")
    assert any("technology name differs" in i for i in check_report_inputs(assessment, other))


def test_check_inputs_rejects_wrong_schema(assessment, fmirr):
    with pytest.raises(ValueError):
        check_report_inputs({"schema_version": "x"}, None)
    with pytest.raises(ValueError):
        check_report_inputs(assessment, {"schema_version": "x"})


def test_to_dict_is_json_serialisable(assessment, fmirr):
    json.dumps(build_report(assessment, fmirr).to_dict())


def test_proven_only_technology_needs_no_qualification():
    spec = {
        "technology": "Standard pump",
        "elements": [{"id": "P", "name": "Pump", "technology_novelty": "proven",
                      "application_area": "known", "trl": 7, "evidence": ["standard"]}],
    }
    result = assessment_from_dict(spec).assess()
    md = build_report(result).to_markdown()
    assert "No qualification is required" in md
    assert "No element requires technology qualification" in md


def test_save_markdown(tmp_path, assessment, fmirr):
    path = build_report(assessment, fmirr).save_markdown(tmp_path / "r.md")
    assert path.read_text(encoding="utf-8").startswith("# Technology Assessment Report")


def test_save_docx(tmp_path, assessment, fmirr):
    docx = pytest.importorskip("docx")
    meta = ReportMeta(title="Doc test", classification="Restricted", status="Draft")
    path = build_report(assessment, fmirr, meta).save_docx(tmp_path / "r.docx")
    document = docx.Document(str(path))
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert any("Executive summary" in h for h in headings)
    assert any("Failure mode identification" in h for h in headings)
    assert len(document.tables) >= 10
    assert "Restricted" in document.sections[0].footer.paragraphs[0].text
    assert any(s.orientation == 1 for s in document.sections)
