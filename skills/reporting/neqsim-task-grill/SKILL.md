---
name: neqsim-task-grill
calculation_basis: "advisory"
version: "0.1.0"
description: "Use when: an engineering task is about to start and its basis is not settled - interview the user one question at a time, each with a recommended answer, on the decision or question, the quality bar, the available data and its sources, access to tools and data, constraints, open decisions and the weakest assumptions, then write a task brief, data requests and a run plan that names which NeqSim, community and enterprise agents produce which reports. Never invents data; unknown stays OPEN."
last_verified: "2026-11-01"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# NeqSim Task Grill ("grill me")

Run this before a study, report or workflow, when the request is a sentence and the result must be a report people will rely on. It settles the basis so the agents can deliver the best possible result without guessing. It asks and records; the calculations stay with the specialist agents.

## Behaviour

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

## Rules

- Read-only on source systems; never edit SharePoint files.
- Mock data is allowed only to test a chain and is labelled mock everywhere.
- Nothing here approves a decision.
