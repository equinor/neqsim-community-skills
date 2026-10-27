"""Build the synthetic example report (Markdown, and Word when python-docx is installed).

Usage: python build_example_report.py [output_directory]
"""

import json
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[3]
for sibling in (
    SKILLS / "field-development" / "neqsim-technology-assessment" / "src",
    SKILLS / "safety" / "neqsim-technology-fmirr" / "src",
):
    sys.path.insert(0, str(sibling))

from technology_assessment import from_dict as assessment_from_dict  # noqa: E402
from technology_fmirr import from_dict as fmirr_from_dict  # noqa: E402

from technology_assessment_report import ReportMeta, build_report  # noqa: E402


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    assessment_spec = json.loads(
        (SKILLS / "field-development" / "neqsim-technology-assessment" / "examples" / "example_novel_technology.json")
        .read_text(encoding="utf-8")
    )
    fmirr_spec = json.loads(
        (SKILLS / "safety" / "neqsim-technology-fmirr" / "examples" / "example_fmirr.json").read_text(encoding="utf-8")
    )
    report = build_report(
        assessment_from_dict(assessment_spec).assess(),
        fmirr_from_dict(fmirr_spec).evaluate(),
        ReportMeta(title="Technology Assessment Report: Compact inline separation system (synthetic)",
                   author="Example author", classification="Public", status="Draft"),
        introduction_context="This synthetic example shows the report structure for an illustrative technology.",
    )
    print("Markdown:", report.save_markdown(out_dir / "technology_assessment_report.md"))
    try:
        print("Word:", report.save_docx(out_dir / "technology_assessment_report.docx"))
    except ImportError as exc:
        print("Word output skipped:", exc)
    print("Open issues:", len(report.issues))


if __name__ == "__main__":
    main()
