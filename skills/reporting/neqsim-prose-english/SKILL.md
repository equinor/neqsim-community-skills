---
name: neqsim-prose-english
calculation_basis: "advisory"
version: "0.1.0"
description: "Write direct, concrete, intellectually honest prose for final engineering reports and generated summaries while avoiding canned AI formatting. USE WHEN: the final reporting step needs an executive summary, discussion, conclusion, decision rationale, root-cause narrative, or other interpretive prose, or when the user requests prose_english. Do not activate during analysis, ordinary chat, code generation, or working notes."
last_verified: "2026-09-11"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Prose English

`prose_english` is the short alias for this style. It turns verified engineering content into
clear prose without making the writing sound simplified, promotional, or machine-generated.

## When to Use

- Use during the final reporting step for executive summaries, discussions, conclusions,
  recommendations, decision rationales, and root-cause narratives.
- Use for a generated summary that interprets evidence rather than prescribing a procedure.
- Use whenever the user explicitly requests `prose_english`.
- Do not activate for analysis notes, ordinary chat, source extraction, code, or technical data
  structures.

## Inputs

- Verified findings, evidence, uncertainty, limitations, and recommendations.
- The intended reader and the decision the document must support.
- Mandatory terminology, headings, citations, and template requirements.
- An optional explicit user style choice.

## Outputs

- Final prose that states actors, actions, evidence, consequences, and uncertainty directly.
- Natural paragraph structure shaped by the argument rather than a fixed response template.
- A style record of `prose_english` when the reporting workflow records provenance.

## Engineering Method

1. Decide the meaning before drafting. Identify the claim, evidence, responsible actor, affected
   object, consequence, and uncertainty.
2. Name concrete actors and actions. Prefer "the valve closed in 4 s" to "a rapid closure event
   occurred".
3. Use familiar, precise words. Keep specialized engineering terms when they carry necessary
   meaning, and define them when the audience may not know them.
4. Replace stock phrases, dead metaphors, inflated diction, euphemism, and abstract noun chains
   with the fact or mechanism they conceal.
5. Prefer active voice when the actor matters. Use passive voice when the actor is unknown,
   irrelevant, or less important than the result.
6. Put measured quantities and observed consequences ahead of adjectives. Never make a sentence
   vivid at the cost of technical accuracy.
7. Vary sentence length and cadence deliberately. Let emphasis follow the meaning rather than a
   prefabricated rhythm.
8. State uncertainty, failure, adverse consequence, and responsibility plainly. Do not use style
   to make an unwelcome result disappear.
9. Break a style rule when strict compliance would make the statement misleading, unnatural, or
   technically wrong.

The following presentation rules are house rules added for agent-generated documents. They are
not derived from Orwell's essay:

- Do not use decorative bold text. Use headings, wording, tables, or layout to establish hierarchy.
- Do not use em dashes. Use a full stop, comma, colon, semicolon, or parentheses.
- Do not force every document into the same headings or sequence.
- Do not open with canned framing such as "This comprehensive report explores" or close with a
  generic offer of further help.
- Do not manufacture symmetrical lists, repeated mini-headings, or one-sentence paragraphs merely
  to make the document look polished.

## Python Usage Pattern

This is a writing guidance skill and has no Python API. Apply it after calculations, validation,
and evidence review are complete, when the reporting workflow renders final narrative content.

## Validation Checklist

- [ ] The main claim and engineering decision are explicit.
- [ ] Every quantitative statement retains its value, unit, basis, and uncertainty where needed.
- [ ] Actors and actions are named when responsibility or causality matters.
- [ ] Necessary technical terms remain precise and are not replaced for cosmetic simplicity.
- [ ] Stale phrases, euphemisms, inflated words, and avoidable nominalizations are removed.
- [ ] Passive voice is used deliberately rather than automatically.
- [ ] Paragraph order follows the argument.
- [ ] Decorative bold, em dashes, canned openings, and canned closings are absent.
- [ ] Required report headings and citation conventions are still satisfied.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Treating plain language as loss of precision | Keep the technical term and explain it once |
| Removing all passive voice | Restore it where the actor is unknown or irrelevant |
| Adding vivid imagery to a measured result | State the measured mechanism and consequence |
| Hiding uncertainty to make prose decisive | State the uncertainty and its decision effect |
| Replacing one canned template with another | Let the evidence determine the paragraph structure |
| Using bold labels for every sentence | Use ordinary prose and meaningful headings |

## Limitations

- This style does not validate engineering calculations, evidence, citations, or compliance.
- It is not a controlled language and does not claim ASD-STE100 compliance.
- It should not override mandatory regulatory wording, contractual terminology, report templates,
  or accessibility requirements.
- It is unsuitable as the default for procedures, warnings, equipment instructions, and tightly
  controlled technical descriptions. Use `neqsim-standard-engineering-english` for those forms.

## Related NeqSim Functionality

This skill performs no NeqSim calculation. It consumes validated outputs from NeqSim task and
reporting workflows, especially `neqsim-professional-reporting`, after numerical work is complete.
Use `neqsim-final-report-writing-style` to select this style automatically at the final reporting
step.

## References

- Orwell, G. (1946). "Politics and the English Language." First published in *Horizon*, April
  1946. The source used to derive this guidance was an 11-page reproduction from The Orwell
  Foundation.

This skill paraphrases general writing principles. It does not reproduce substantial source text.
