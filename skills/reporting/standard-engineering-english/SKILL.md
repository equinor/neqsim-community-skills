---
name: neqsim-standard-engineering-english
calculation_basis: "advisory"
version: "0.1.0"
description: "Apply a concise controlled-language house style inspired by ASD-STE100 to final engineering documents and generated summaries. USE WHEN: the final reporting step produces procedures, equipment descriptions, technical requirements, warnings, cautions, checklists, method summaries, or other text that readers must interpret consistently, or when the user requests standard_engineering_english. Do not claim ASD-STE100 compliance."
last_verified: "2026-09-11"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Standard Engineering English

`standard_engineering_english` is the short alias for this style. It is a compact house style
inspired by ASD-STE100. It does not reproduce the ASD-STE100 dictionary and does not establish
ASD-STE100 compliance.

## When to Use

- Use during the final reporting step for procedures, operating steps, equipment descriptions,
  technical requirements, warnings, cautions, limits, checklists, and method summaries.
- Use for generated summaries whose main purpose is repeatable action or unambiguous technical
  interpretation.
- Use whenever the user explicitly requests `standard_engineering_english`.
- Do not activate for analysis notes, ordinary chat, source extraction, or code.

## Inputs

- Verified technical content, actions, conditions, limits, hazards, units, and terminology.
- The project glossary, approved component names, abbreviations, and spelling convention.
- The document type: procedure, description, requirement, safety instruction, or summary.
- Mandatory regulatory wording and an optional explicit user style choice.

## Outputs

- Short, complete sentences with stable terminology and explicit logical relations.
- Procedures with conditions before commands and normally one instruction per sentence.
- Descriptions organized around one subject per sentence and one topic per paragraph.
- A style record of `standard_engineering_english` when the reporting workflow records provenance.

## Engineering Method

1. Build or use the project glossary. Use one preferred term for each concept and one meaning for
   each term. Do not vary synonyms merely to improve rhythm.
2. Use a word in its approved meaning and grammatical role. If a familiar word is ambiguous,
   rewrite the sentence instead of relying on context.
3. Use the project spelling convention consistently. If none exists, use American spelling.
   Preserve spelling in quotations and official names.
4. Keep sentences complete. State the subject and verb, and include articles where normal English
   requires them. Do not use contractions.
5. Prefer active voice. In descriptive text, use passive voice when the agent is unknown or
   unimportant. Never invent an agent to avoid passive voice.
6. Keep noun clusters short. Aim for no more than three consecutive nouns. Expand longer clusters
   with a preposition, relative clause, or defined short form.
7. Put conditions before actions. In a procedure, begin the action with an imperative verb and
   normally give one instruction per sentence. Combine actions only when they occur at the same
   time.
8. Keep procedural sentences at 20 words or fewer where practical. Keep descriptive sentences and
   notes at 25 words or fewer where practical. Split a sentence before deleting necessary meaning.
9. Give one subject per descriptive sentence, one topic per paragraph, and no more than six
   sentences per paragraph where practical.
10. Use notes only for information. Do not hide actions, requirements, limits, or safety controls
    in a note.
11. For safety text, state the condition or command, the hazard, and the consequence. Use
    `warning` for risk of injury or death and `caution` for equipment damage only when that
    distinction matches the governing domain standard.
12. Use vertical lists when they make complex alternatives or sequences easier to scan. Keep all
    items grammatically parallel and do not mix procedures with descriptions in one list.
13. Follow the project rules for units, numbers, symbols, abbreviations, and typography. This style
    does not define those conventions.

For executive summaries, retain stable terminology, explicit actors, short sentences, and
consistent units. Do not force every sentence below 25 words or restrict vocabulary so sharply
that the decision, uncertainty, or consequence becomes less clear.

## Python Usage Pattern

This is a writing guidance skill and has no Python API. Apply it after calculations, validation,
and evidence review are complete, when the reporting workflow renders final technical content.

## Validation Checklist

- [ ] Each concept has one preferred term throughout the document.
- [ ] Words are used with a clear meaning and consistent grammatical role.
- [ ] Sentences are complete, articles are present, and contractions are absent.
- [ ] Active voice is used unless passive voice has a clear descriptive purpose.
- [ ] Noun clusters are short or expanded.
- [ ] Conditions precede commands in procedures.
- [ ] Each procedural sentence normally contains one instruction.
- [ ] Sentence and paragraph lengths meet the targets without losing necessary meaning.
- [ ] Notes contain information only.
- [ ] Safety instructions state the condition or command, hazard, and consequence.
- [ ] Terminology, spelling, units, numbers, and abbreviations follow project rules.
- [ ] The document does not claim ASD-STE100 compliance from this condensed style alone.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Replacing repeated technical terms with synonyms | Repeat the preferred term |
| Forcing active voice by inventing an actor | Use passive voice when the actor is unknown |
| Packing many nouns into one label | Expand the relation with a preposition or clause |
| Combining sequential actions in one sentence | Give each action its own imperative sentence |
| Putting an instruction in a note | Move it into the procedure or requirement |
| Treating the 20-word or 25-word target as absolute | Preserve necessary technical meaning, then split cleanly |
| Calling condensed guidance ASD-STE100 compliant | State that it is inspired by ASD-STE100 |

## Limitations

- Exact ASD-STE100 compliance requires the complete current specification, approved dictionary,
  applicable domain glossary, authoring rules, and a compliance review.
- This skill does not supply or reproduce the ASD-STE100 dictionary, tables, or examples.
- This style does not define typography, numbering, abbreviations, symbols, or units.
- Mandatory regulatory, contractual, and safety wording takes precedence.
- The style can sound repetitive by design. Use `neqsim-prose-english` when interpretation,
  argument, or narrative clarity is the primary need.

## Related NeqSim Functionality

This skill performs no NeqSim calculation. It consumes validated outputs from NeqSim task and
reporting workflows, especially `neqsim-professional-reporting`, after numerical work is complete.
Use `neqsim-final-report-writing-style` to select this style automatically at the final reporting
step.

## References

- ASD Simplified Technical English Maintenance Group. (2025). *ASD-STE100 Simplified Technical
  English: Standard for Technical Documentation*, Issue 9, 15 January 2025.

ASD-STE100 is a registered trademark, and the source standard is copyrighted. This skill contains
independently worded, condensed guidance and does not reproduce its dictionary, tables, or
substantial rule text.
