---
name: neqsim-technology-assessment-report
calculation_basis: "advisory"
version: "0.1.0"
description: "Builds a full technology assessment report (Markdown and Word) for any technology from technology_assessment.v1 and technology_fmirr.v1 results: qualification basis, decomposition, novelty and TRL, step-out, benefits and risks, FMIRR, qualification outline, conclusions, open points. USE WHEN: a project study needs a technology assessment report as a deliverable, or an assessment and FMIRR must be turned into a reviewable document."
last_verified: "2026-10-27"
requires:
  python_packages: ["python-docx (Word output only)"]
  java_packages: []
  env: []
  network: []
---

# Technology Assessment Report

Use this skill to write the **technology assessment report** that a project
study delivers for a technology it may use. The report is generated from the
structured results of `neqsim-technology-assessment` and
`neqsim-technology-fmirr`, plus author-written narrative. It checks the inputs
and lists every open point instead of hiding it.

## When to Use

- A concept or project study needs a technology assessment report for a new or
  step-out technology.
- An assessment and FMIRR exist as data and must become a reviewable Word or
  Markdown document.
- A report is updated after new evidence changes ratings (re-run, compare the
  issues list, issue a new revision).

## Inputs

- `assessment`: a `technology_assessment.v1` mapping (required).
- `fmirr`: a `technology_fmirr.v1` mapping (recommended whenever any element
  needs qualification).
- `ReportMeta`: title, subtitle, document number, revision, author, reviewer,
  date, classification, status, project.
- `narrative`: author-written paragraphs per chapter id, appended to the
  generated text.
- `introduction_context`: why the project considers this technology.
- `references`: project documents, test reports and standards to add.

## Outputs

- A `Report` with chapters, tables and an `issues` list.
- `to_markdown()` / `save_markdown(path)`: Markdown with numbered tables.
- `save_docx(path)`: Word document with title block, contents field, header and
  footer (classification, status, page numbers), landscape FMIRR chapter and
  risk-coloured cells (needs `python-docx`).
- `to_dict()`: JSON view for downstream tools.

## Engineering Method

The report has fixed chapters so that reviewers always find the same content:

1. Executive summary (generated from results).
2. Introduction (purpose, scope, method, context).
3. Technology qualification basis (description, use, environment, functions,
   performance expectations, regulatory requirements). Keep this chapter
   stable; it is reused in the qualification programme and qualification report.
4. Technology description and decomposition.
5. Technology maturity: novelty category and TRL per element and for the system.
6. Enabling or enhancing technology.
7. Step-out from existing experience (design, manufacturing, installation,
   operability, fluids, operating conditions, lifetime).
8. Benefits and risks.
9. Standardisation and multi-implementation.
10. FMIRR, first version (landscape).
11. Preliminary outline of qualification activities, linked to critical modes.
12. Conclusions and recommendations.
13. Assumptions, data gaps and open points.
14. References.
15. Appendix A: definitions (novelty table, TRL scale, consequence and
    probability classes).

Authoring workflow:

1. Run the assessment and FMIRR; resolve flags and gaps where evidence exists.
2. Build the report and read `report.issues`.
3. Write the narrative where judgement is needed: the justification of each
   category and TRL, the reasoning for the role (enabling or enhancing), the
   interpretation of step-out, and the recommendation. Cite the evidence by
   document id.
4. Add project references, set classification and status, build Word output.
5. Review figures and tables in the document (Word: update fields so the
   contents list fills in), then circulate to the expert panel.
6. Re-issue with a new revision when evidence changes ratings.

## Python Usage Pattern

```python
from technology_assessment import from_dict as assess
from technology_fmirr import from_dict as rank
from technology_assessment_report import ReportMeta, build_report

assessment = assess(assessment_spec).assess()
fmirr = rank(fmirr_spec).evaluate()
report = build_report(
    assessment,
    fmirr,
    ReportMeta(title="Technology Assessment Report: <technology>", author="<name>",
               classification="Internal", status="Draft"),
    introduction_context="<why the project considers the technology>",
    narrative={"conclusions": ["<author conclusion>"]},
)
report.save_markdown("technology_assessment_report.md")
report.save_docx("technology_assessment_report.docx")
print(report.issues)
```

`examples/build_example_report.py` builds the report for the synthetic example.

## Validated NeqSim Path

The report presents judgement and evidence; it computes nothing new. Attach
NeqSim study results (process, flow-assurance, mechanical-design, dynamic
simulation) as references and cite them in the narrative and in the FMIRR
re-rating basis.

## Escalation

Do not issue the report for decision-making while `report.issues` contains
open items on novel elements, missing FMIRR coverage, or flags on the ratings.
Have a qualified expert panel review it and record the review.

## Validation Checklist

- [ ] Assessment and FMIRR are current and refer to the same technology.
- [ ] Every novel element has failure modes in the FMIRR.
- [ ] Narrative justifies each category, TRL and the enabling/enhancing role.
- [ ] Evidence is cited by document id; none is invented.
- [ ] Classification, status, revision and document number are set.
- [ ] Open issues are resolved or accepted explicitly.
- [ ] Word contents field updated; tables and landscape chapter checked.
- [ ] Expert panel review recorded.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Generic report without a position | Narrative left empty | Write justification and recommendations |
| Ratings differ between report and workshop | Report not regenerated | Rebuild from the current JSON |
| Contents list empty in Word | Fields not updated | Update fields in Word before issue |
| FMIRR chapter missing | `fmirr` not passed | Supply the FMIRR result |
| Evidence claims without sources | Copy from marketing material | Cite documented, accessible evidence only |

## Limitations

- The chapter structure is a general, public structure; company templates,
  numbering, gates and approval wording belong in an enterprise overlay.
- English output only; figures and drawings are not generated.
- Word output needs `python-docx`; Markdown has no dependency.

## References

- DNV-RP-A203, *Technology qualification*.
- ISO 20815, *Production assurance and reliability management*.
- ISO 14224, *Collection and exchange of reliability and maintenance data for
  equipment*.
- NeqSim repository: https://github.com/equinor/neqsim
