---
name: neqsim-final-report-writing-style
calculation_basis: "advisory"
version: "0.1.0"
description: "Select and apply prose_english or standard_engineering_english only when generating a final engineering report or summary. USE WHEN: the reporting step is ready to compose final narrative content, or the user explicitly requests either writing style for a generated document. Do not activate during analysis, working notes, ordinary chat, code generation, or source extraction."
last_verified: "2026-09-11"
required_skills:
  - neqsim-prose-english
  - neqsim-standard-engineering-english
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Final Report Writing Style

Choose a writing style only after the calculations, evidence review, and technical conclusions are
complete. The selected style controls expression, not facts, scope, uncertainty, or validation.

## When to Use

- Activate at the final reporting step when generating an HTML, Word, PDF, Markdown, or notebook
  report, or a durable generated summary.
- Activate when revising an existing final document for style.
- Activate when the user explicitly requests `prose_english` or
  `standard_engineering_english` for a generated document.
- Do not activate during research, analysis, calculation, source extraction, ordinary chat,
  interim status messages, code generation, or working notes.

## Inputs

- `document_purpose`: `interpret`, `decide`, `instruct`, `specify`, `describe`, or `mixed`.
- `document_sections`: the final sections that will be generated.
- `audience`: decision-maker, engineer, operator, maintainer, regulator, student, or general reader.
- `user_requested_style`: optional `prose_english` or `standard_engineering_english`.
- Mandatory templates, controlled terminology, safety wording, and accessibility constraints.

## Outputs

- `primary_style`: `prose_english` or `standard_engineering_english`.
- `section_overrides`: sections that require the other style, with a short reason.
- `selection_reason`: one sentence tied to reader purpose and document type.
- Final narrative revised under the selected rules without changing technical content.

When the task uses `results.json`, record the choice as:

```json
{
  "writing_style": {
    "primary": "prose_english",
    "selection": "automatic",
    "reason": "The report interprets evidence for an engineering decision.",
    "section_overrides": {
      "Operating procedure": "standard_engineering_english"
    }
  }
}
```

## Engineering Method

1. Check for a user request. A valid explicit request sets the primary style.
2. If there is no override, select by the reader's task:
   - Choose `prose_english` when the reader must understand evidence, compare alternatives,
     interpret uncertainty, or make a decision.
   - Choose `standard_engineering_english` when the reader must perform an action, reproduce a
     method, identify equipment, follow a limit, or interpret a requirement consistently.
3. For a mixed engineering report, use `prose_english` as the primary style. Apply
   `standard_engineering_english` to procedures, requirements, equipment descriptions, warnings,
   cautions, checklists, and tightly controlled method steps.
4. Mandatory safety, regulatory, contractual, accessibility, and template rules take precedence
   over either style.
5. Apply the selected style only to narrative expression. Do not alter numbers, units, citations,
   uncertainty, technical terminology, findings, or the direction of a recommendation.
6. Record the selection and any section overrides so a reviewer can see which rules were applied.

Selection guide:

| Final content | Default style |
|---|---|
| Executive summary and conclusion | `prose_english` |
| Results discussion and uncertainty interpretation | `prose_english` |
| Root-cause narrative and decision rationale | `prose_english` |
| Method steps and reproducibility instructions | `standard_engineering_english` |
| Equipment descriptions and technical requirements | `standard_engineering_english` |
| Procedures, checklists, warnings, cautions, and limits | `standard_engineering_english` |
| Mixed final report | `prose_english` primary, controlled section overrides |
| Explicit ASD-STE100 deliverable | Full ASD-STE100 workflow, not these condensed skills |

## Python Usage Pattern

This is an agent routing skill and has no Python API. The final report generator or reporting agent
performs the selection immediately before it writes final narrative sections.

## Validation Checklist

- [ ] Selection occurred only at the final reporting or document-revision step.
- [ ] A valid user request took precedence over automatic selection.
- [ ] The automatic choice reflects what the reader must do with the document.
- [ ] Mixed reports use section overrides only where the content type requires them.
- [ ] Safety, regulatory, contractual, template, and accessibility rules take precedence.
- [ ] Style revision did not change facts, values, units, citations, uncertainty, or conclusions.
- [ ] The selected style and reason are recorded in `results.json` when that file exists.
- [ ] No document claims ASD-STE100 compliance from the condensed style.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Selecting a style during analysis | Wait until the final narrative is generated |
| Choosing by personal taste alone | Choose by the reader's task and document type |
| Ignoring an explicit user request | Apply the requested primary style |
| Applying one style mechanically to every section | Use controlled overrides in mixed reports |
| Rewriting values while improving prose | Preserve all technical content exactly |
| Calling the controlled style ASD-STE100 compliant | Use the full standard and compliance workflow |

## Limitations

- The selector does not validate calculations, evidence, standards compliance, or citations.
- Automatic selection cannot override legally required wording or an approved document template.
- A single primary style does not remove the need for controlled safety and procedural language in
  otherwise interpretive reports.
- The two styles cover engineering reports and summaries, not fiction, marketing, legal drafting,
  or ordinary conversation.

## Related NeqSim Functionality

This skill performs no NeqSim calculation. It belongs at the rendering boundary of
`neqsim-professional-reporting` and task Step 3, after `results.json` and validation artifacts are
complete. It routes final content to `neqsim-prose-english` or
`neqsim-standard-engineering-english`.

## References

- Orwell, G. (1946). "Politics and the English Language." *Horizon*, April 1946.
- ASD Simplified Technical English Maintenance Group. (2025). *ASD-STE100 Simplified Technical
  English: Standard for Technical Documentation*, Issue 9.

The selector uses independently worded guidance and does not reproduce either source.
