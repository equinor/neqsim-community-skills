---
name: neqsim-task-grill
calculation_basis: "advisory"
version: "0.1.0"
description: "USE WHEN: an engineering task is about to start and its basis is not settled - interview the user one question at a time, each with a recommended answer, on the decision or question, the quality bar, the available data and its sources, access to tools and data, constraints, open decisions and the weakest assumptions, then write a task brief, data requests and a run plan that names which NeqSim, community and enterprise agents produce which reports. Never invents data; unknown stays OPEN."
last_verified: "2026-11-01"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# NeqSim Task Grill ("grill me")

It settles the basis so the agents can deliver the best possible result without guessing. It asks and records; the calculations stay with the specialist agents.

## When to Use

Run this before a study, report or workflow, when the request is a sentence and the result must be a report people will rely on.

## Inputs

The user's request in their own words, plus whatever the user can name: data, earlier reports, standards, tools and people involved.

## Engineering Method

1. Ask **one question at a time**. Give a recommended answer and say why the question matters. Wait for the answer.
2. If the user does not know, record `OPEN`. Never fill in a plausible value. A value without a source is an assumption and is labelled so.
3. Check each answer against the earlier ones. If two conflict (for example "formal issue" with mock data), say so and ask again.
4. Challenge at the end: which three assumptions would change the result if wrong, and how would each be tested?
5. Test access instead of asking about it: try each named tool or data source and record the real outcome. Use a hand-off only after a real failure.
6. Stop when every question is answered or OPEN, and write the outputs.

## Questions

| Area | Ask |
| --- | --- |
| The decision | What must be decided or answered, by whom, by when? What is the output used for? |
| Quality bar | Screening draft or formal issue? Which earlier report sets the standard? Language, units, templates, who signs? |
| Basis | What data exists (measurements, models, earlier studies, standards)? Where, in what form, how current? |
| Method | Which calculation basis is acceptable (screening, validated, standard-based)? Any required standards? |
| Reports | Which reports are needed (PVT, process, wells, SURF, flow assurance, cost, safety)? Who signs each? |
| Access | Which sources and tools are reachable now? |
| Constraints | Cost, schedule, regulation, host capacity, partner positions. |
| Assumptions | The three that matter most; any with no source. |

## Which agents

Pick the agent per report from the discovery tools (`agent_search`, `skill_search`): NeqSim agents for the calculation (for example PVT, process, flow assurance, mechanical design), community agents for open-data screening, enterprise agents for governed company data. Record each choice with the reason in the run plan.

## Outputs

`task_brief.md` (decision, quality bar, basis, constraints), `data_requests.md` (what each person provides, to which folder), `run_plan.md` (agents in order, the report each delivers, the first command), `intake_answers.json` (all answers, to resume). Put them in the task folder created with `neqsim new-task`.

## Hand-off

A specialist's solved task becomes a report for a larger workflow with `neqsim report-manifest <task> --type <report_type> --person "<name>"`. Project-development work uses `enterprise-project-intake` (energy-project-agents), which adds the gate, the WR2704 register and the company requirements.

## Python Usage Pattern

There is no calculation here; the skill drives the task toolkit from the shell:

```bash
neqsim new-task "<title>" --type <type> --prompt "<verbatim request>"
neqsim report-manifest <task> --type <report_type> --person "<name>"
```

Write the four output files into the task folder. `intake_answers.json` records every answer, including `OPEN`, so the interview can resume.

## Validation Checklist

- Every question is answered or marked `OPEN`.
- No value appears without a source; unsourced values are labelled assumptions.
- Conflicting answers were raised and resolved.
- Access to each named tool or source was tested, not assumed.
- The three weakest assumptions and how to test each are written down.

## Common Mistakes

- Asking several questions at once.
- Filling in a plausible value for an unknown instead of recording `OPEN`.
- Asking whether a tool is reachable instead of trying it.
- Treating mock data as real in a formal issue.

## Limitations

- Nothing here approves a decision.
- It does not run calculations; the chosen agents do.
- Read-only on source systems; never edit SharePoint files.
- Mock data is allowed only to test a chain and is labelled mock everywhere.

## References

- `neqsim-task-workflow` (task folder and report workflow) and `neqsim-professional-reporting`.
- `enterprise-project-intake` (energy-project-agents) for project-development intake.

