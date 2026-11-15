# Where Does This Go? — Repository Placement Guide

A single decision rule for **which repository a new capability belongs in**, so the
NeqSim agent/skill ecosystem stays consistent over time.

Use this before opening a PR for any new agent, skill, or engineering method.

## The three placement rules (mandatory)

1. **Equinor- or company-specific → enterprise.** Internal systems and APIs (STID, SMDA,
   SSDL, GeoX, Wellcom, PDM, OTS, WellDB, Diskos access, SAP, ...), internal file shares,
   real asset/facility/well names used as data, company TRs, thresholds and review policy
   go in `neqsim-enterprise-skills` / `neqsim-enterprise-agents` (or a private repo if not
   shareable at all). Community content must stay vendor-neutral and use generic examples
   (`WELL-1`, `Reservoir A`).
2. **Not NeqSim Java functionality → community.** Python methods, file readers and data
   adapters (for example wrappers of open libraries such as dlisio or segyio), screening
   calculations, report helpers and orchestrating agents go in `neqsim-community-skills` /
   `neqsim-community-agents`, even when they are generic and useful in every task.
3. **NeqSim Java functionality → core `equinor/neqsim`.** Only validated Java classes with
   JUnit tests, plus a skill or agent under `.github/` that directly imports and calls those
   classes, evolving in the same PR. Do not add copies of community or enterprise skills, or
   non-Java helpers, to the core repo.

Dependencies stay one-way (`core -> community -> enterprise`): an enterprise skill may
build on a community package (for example an enterprise data provider that uses a
community file reader), never the reverse.

> This guide is the **NeqSim-ecosystem-specific** detail (core vs. community vs.
> enterprise, and screening vs. validated). Any company can follow the same pattern:
> keep the public community repos as the shared base and add company data and policy in
> its own private enterprise repositories.

## The five homes

| Layer | Repository | Visibility | Holds |
| --- | --- | --- | --- |
| NeqSim core | [equinor/neqsim](https://github.com/equinor/neqsim) | Public | Validated, tested Java engineering classes **plus** their co-located `.github/skills` and `.github/agents` that import and call those classes; nothing that is not NeqSim Java functionality |
| Community skills | [equinor/neqsim-community-skills](https://github.com/equinor/neqsim-community-skills) | Public | Educational, **screening-level** methods (placeholders that reference the validated classes) |
| Community agents | [equinor/neqsim-community-agents](https://github.com/equinor/neqsim-community-agents) | Public | Public orchestrators that chain community skills |
| Enterprise skills | [equinor/neqsim-enterprise-skills](https://github.com/equinor/neqsim-enterprise-skills) | Private | Company-policy overlays that wrap a community screening method with a review policy |
| Enterprise agents | [equinor/neqsim-enterprise-agents](https://github.com/equinor/neqsim-enterprise-agents) | Private | Orchestrators that apply enterprise policy; **no engineering method inside the agent** |

Confidential, facility-specific, or asset-specific content that cannot be shared even
inside the enterprise repos belongs in a **private/local workspace repo**, never in
community or core.

## Decision tree

Answer top to bottom; stop at the first match.

1. **Does it embed confidential data, real facility/asset details, internal system
   names, credentials, or non-shareable company thresholds?**
   - Cannot be shared at all → **private/local repo**.
   - It is a company **policy/review overlay** on top of a public screening method
     (e.g. a fixed margin, an acceptance gate, a sign-off rule) →
     **enterprise-skills** (the policy method) / **enterprise-agents** (the orchestration).

2. **Is it a rigorous, validated, testable engineering calculation that drives the
   NeqSim Java API directly?**
   - Yes → implement it as a **Java class in core neqsim** (with JUnit tests).
     If it needs an authoring/code-generation aid, add a **co-located** entry under
     neqsim `.github/skills/` or `.github/agents/` that `import`s and calls the class.
     The Java and its skill/agent evolve in the **same PR**.

3. **Is it a public, educational, screening-level method** — placeholder math, says
   "qualified human review required", and only *references* validated classes in its
   `Related NeqSim Functionality` section?
   - The method/knowledge → **community-skills**.
   - An orchestrator that selects and chains such skills → **community-agents**.

## Skill vs. agent

This axis is independent of the layer:

- **Skill** = a reusable *capability or method* (a calculation pattern, a screening
  rule, a body of domain knowledge). It can run logic.
- **Agent** = an *entry point / orchestrator* for a class of tasks. It selects and
  chains skills, asks for inputs, and routes to human review. In the enterprise and
  community **agents** repos an agent must **not** contain an engineering method
  itself — the method lives in a skill (or in core neqsim).

## Precedence (which one wins when several apply)

When more than one valid option exists, prefer the **most specific** and cite the
lower layers it depends on (from
[neqsim-enterprise-skills/docs/dependency-hierarchy.md](https://github.com/equinor/neqsim-enterprise-skills/blob/main/docs/dependency-hierarchy.md)):

```text
project/facility enterprise skill
enterprise skill
community skill
core NeqSim skill
NeqSim core
```

Dependencies are **one-way**: `core -> community -> enterprise`. Community and core
must never depend on enterprise code, internal package names, or confidential data.

## The decisive test in one line

> **Validated NeqSim Java functionality → core neqsim. Everything else that is public
> (screening methods, readers, adapters, orchestrators) → community.
> Equinor/company-specific or confidential content → enterprise / private.**
> A *skill* is a method; an *agent* is an orchestrator that has no method of its own.

## Worked example — HAZOP deviation → consequence

| Piece | Nature | Home |
| --- | --- | --- |
| `HAZOPTemplate`, `HazopConsequenceAutoPopulator`, `HazopConsequenceMapping`, and the consequence analyzers (`ReliefValveSizing`, `SettleOutPressureAnalyzer`, `GasBlowbyAnalyzer`, `VacuumCollapseAnalyzer`, `PumpDeadheadAnalyzer`, `RunawayReactionAnalyzer`) | Validated, tested Java that drives the NeqSim API | **core neqsim** Java + co-located `.github/skills/neqsim-hazid-fmea-eta-fta` and `.github/agents/consequence.analysis.agent.md` |
| A public "guideword × parameter" screening grid with qualitative hints, pointing to the classes above under `Related NeqSim Functionality` | Educational screening placeholder | **community-skills** (e.g. `neqsim-hazop-deviation-screening`); referenced by the community `process-safety-agent` |
| A company HAZOP procedure, fixed SIL/risk targets, or facility cause-and-effect matrices | Company policy / confidential | **enterprise** (or private if confidential) |

## See also

- [neqsim-community-skills/docs/skill-standard.md](skill-standard.md) — screening-vs-validated boundary, required sections.
- [neqsim-community-skills/docs/governance.md](governance.md) — what is in/out of scope for the public catalog.
- [neqsim-enterprise-skills/docs/dependency-hierarchy.md](https://github.com/equinor/neqsim-enterprise-skills/blob/main/docs/dependency-hierarchy.md) — allowed dependencies, precedence, override rules.
- [equinor/neqsim VISION_AGENTS.md](https://github.com/equinor/neqsim/blob/master/VISION_AGENTS.md) — what belongs in the core repo's agentic layer.
