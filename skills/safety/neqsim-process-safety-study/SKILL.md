---
name: neqsim-process-safety-study
calculation_basis: "advisory"
version: "0.3.0"
description: "Vendor-neutral workflow for a full process safety study of a tie-in, modification or new facility: scoping, evidence gates and document register, HAZID, consequence, relief/blowdown/flare, transient and OLGA verification, SIL/LOPA/SRS, explosion CFD, QRA, HAZOP preparation, barriers, ESD cause and effect, reporting. USE WHEN: a safety study needs the order of work, the skill or agent per step, acceptance gates, and the traps found in earlier studies."
last_verified: "2026-11-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Process Safety Study

This skill is the orchestration layer of a process safety study. It does not calculate safety results. It tells you which step comes next, which skill or agent does the work, what evidence the step needs, what makes the step acceptable and which mistakes earlier studies made. It also ships small gate helpers (`process_safety_study`) that turn the rules into tests: an unread document becomes a data gap, a number without a hand calculation is not a basis, a drawing item without a tag is an orphan.

Company-specific document systems, criteria and data sources are added by an enterprise overlay agent that extends `process-safety-study-agent`. Nothing company-specific belongs in this skill.

## When to Use

- A tie-in of a new field or line to an existing installation, a modification, or a new facility needs HAZID, HAZOP, LOPA/SIL, QRA, relief and flare, transient and explosion work that must hold together.
- A rev A study exists and a rev B must close the open items (data gaps, screening-only results, unverified documents).
- A reviewer asks "which evidence supports this safety statement".

Not for: a single screening number (call the step skill directly), approving a design, deciding that a risk is tolerable, or replacing a facilitated HAZID/HAZOP.

## Inputs

- Scope: what is tied in or changed, host installation, project phase, jurisdiction.
- Source drawings (P&IDs, line list, valve and instrument list) and the process basis (rates, pressures, temperatures, fluid) with their revisions.
- The documents that govern the study (criteria, methods, standards) with a read status.
- Earlier study results with their assumptions.

## Outputs

- A step plan with the skill and agent per step and the evidence each needs (`workflow()`).
- A document register and an evidence gate: status `READY_FOR_REVIEW` or `UNVERIFIED_SCREENING`, with data gaps (gap, source, status, assumed, effect).
- Gate results per step: profile match, hand-calculation match, conservatism of screening against transient results, tag anchoring, reconciliation of carried values.
- A hand-off with the human review list. Nothing in the output is a safety case or a compliance statement.

## Engineering Method

Order can iterate (a SIL result can change a HAZOP node), but do not skip a gate.

| Step | Work | Skills | Agents | Evidence needed | Acceptance gate |
| --- | --- | --- | --- | --- | --- |
| S00 | Scope and basis freeze | `neqsim-task-workflow`, `neqsim-jurisdiction-regulatory-basis`, `neqsim-task-grill` | `process-safety-study-agent` | scope, host, phase, jurisdiction | written scope, open questions as data gaps |
| S01 | Source drawings and data verification | `neqsim-tie-in-pid-sketch`, `neqsim-document-intelligence-extraction`, `neqsim-technical-document-reading`, `neqsim-pid-quality-review`, `neqsim-pfd-layout-review` | `technical-document-intelligence-agent`, `subsea-layout-screening-agent` | controlled P&IDs, lists, the pressure profile and its revision | `profile_gate` MATCH, `tag_anchor_gate` ANCHORED |
| S02 | Governing requirements and register | `neqsim-standard-requirement-extraction`, `neqsim-standards-lookup` | `technical-document-intelligence-agent` | document, edition, clause, read status | `evidence_gate`, `claim_gate` |
| S03 | Hazard identification | `neqsim-hazid-fmea-eta-fta`, `neqsim-process-safety` | `process-safety-agent` | guide words per phase, hazard list, SIMOPS | every scenario linked to a node and a calculation |
| S04 | Consequence and source terms | `neqsim-consequence-analysis`, `neqsim-release-source-terms`, `neqsim-jet-fire-radiation-screening`, `neqsim-gas-dispersion-distance-screening`, `neqsim-h2s-safety-impact` | `process-safety-agent`, `flare-helideck-dispersion-agent` | inventory, state, hole sizes, isolation times | `hand_calc_gate` MATCH, validity range stated |
| S05 | Relief, blowdown, flare | `neqsim-relief-flare-network`, `neqsim-depressurization-mdmt`, `neqsim-trapped-liquid-fire-rupture`, `neqsim-relief-load-screening`, `neqsim-depressurization-screening`, `neqsim-psv-orifice-screening`, `neqsim-flare-radiation-screening` | `process-safety-agent`, `firewater-coverage-agent` | flare tip, header, knock-out drum, valve data; existing wells and inputs to the receiving separator or header and the relief basis; current inflow | dynamic header and drum check; verified versus assumed data separated; new source compared with existing wells; blocked outlet against current inflow with a verdict |
| S06 | Transients and OLGA | `neqsim-olga-multiphase-simulator`, `neqsim-multiphase-flow-slug-screening`, `neqsim-water-hammer` | `olga-simulation-agent`, `flow-assurance-study-agent` | route profile, PVT, insulation, host boundary, licence | `conservatism_gate` on every comparison row |
| S07 | SIL, LOPA, SRS | `neqsim-process-safety`, `neqsim-safety-function-coverage-screening` | `process-safety-agent` | demand, tolerable frequency, failure data, test regime, response budget | hazard-rate criterion and SIL band both met |
| S08 | Explosion and dispersion CFD | `neqsim-cfd-coupling` | `cfd-coupling-agent`, `flare-helideck-dispersion-agent` | geometry, source terms, scenarios | verification and mesh study reported |
| S09 | QRA | `neqsim-consequence-analysis` | `process-safety-agent` | agreed basis (criteria, models, frequencies, population, baseline) | basis frozen before numbers |
| S10 | HAZOP preparation | `neqsim-hazop-node-pack` | `process-safety-agent` | tagged P&IDs, node definitions, lists | node pack with `missing_evidence`; placement rules run |
| S11 | Barriers and SCE | `neqsim-safety-function-coverage-screening`, `neqsim-hazop-node-pack` | `process-safety-agent` | barrier elements, performance standards, test regime | each barrier has owner, standard, test |
| S12 | ESD, PSD, F&G cause and effect | `neqsim-hazop-node-pack`, `neqsim-firewater-deluge-design` | `process-safety-agent`, `firewater-coverage-agent` | C&E with tags, SIF list | tags exist on drawings; response chains close |
| S13 | Reconcile carried values | `neqsim-task-workflow` | `process-safety-study-agent` | every quantity used twice | `reconcile_values` has no unexplained conflict |
| S14 | Reporting and hand-off | `neqsim-final-report-writing-style`, `neqsim-standard-engineering-english`, `neqsim-professional-reporting` | `process-safety-study-agent` | results, assumptions, gaps | evidence status on every conclusion |

`workflow()` returns the same table with the traps per step.

### Evidence rules for every step

1. **Status per statement.** VERIFIED (read in a document, with document, revision, clause or page), DERIVED (calculated from verified inputs, formula stated), UNVERIFIED (assumed or convention). A value only seen as an image or only quoted by another document is UNVERIFIED until read.
2. **Missing evidence is a data gap**, never a pass: record gap, source, status, what was assumed and the effect on the result.
3. **No compliance claim without the text read.** A title, an index entry or a citation inside another document is not the text. Use `claim_gate`; say "conventions applied" otherwise.
4. **Screening is labelled screening** until the model is qualified for the state (phase, pressure range, geometry) and compared with an independent result.
5. **Proposed changes to a drawing are mark-ups** with the P&ID tag, never edits of the source drawing; new tags are proposals until the document owner accepts them.

## Lessons from earlier studies (generic)

- **Verify the source profile before use.** A study carried a superseded proxy pressure profile (shut-in pressure 392 bara) while the design case gave 260.5 bara; the error was found only by a late cross-check. Run `profile_gate` against the controlled source and record its revision.
- **Do not trust a NeqSim number without a hand calculation.** A control-valve failure load came out 2.5 times the IEC 60534-2-1 value, and a specific-heat ratio was taken from the wrong property. Two checks caught it: a hand calculation and a round trip through the standard gas-sizing class. Run `hand_calc_gate` on every release, relief and wave-speed number. A rev A diagnosis ("discharge coefficient applied twice") was wrong; test the diagnosis too.
- **Models have validity ranges.** A homogeneous-equilibrium release model was valid for a hot dense gas but failed for cold dense and two-oil-phase states; a factor applied by hand to cover this was a two-phase correction that did not apply. State the range and the fallback.
- **Transient verification changes the answer.** OLGA runs showed the screening to be non-conservative for severe-slugging onset and surge volume, restart peak flow, blocked-outlet pack-up time and pigging surge, and conservative for steady-state pressure drop, holdup and cooldown. Do not write "screening is conservative" as a blanket statement; run `conservatism_gate` per row and carry the non-conservative groups to the report.
- **Know what the transient model assumes.** Wells as a constant-rate source make pack-up pressures upper bounds; a host as a pressure node hides vessel dynamics; a PVT table limit can stop a cold blowdown run (decode the exit status).
- **Compare with what the receiving system has already seen.** A new higher-pressure source on a separator or header with existing producers needs a table of the existing wells and inputs (riser or inlet pressure, shut-in pressure, rates, choke dP, what the relief valves were sized for), the ratio new to historical, and the effect on the failed-open or choke-collapse relief load. Check blocked outlet against the current inflow, not the design inflow, and say whether it governs: lower production today reduces blocked outlet but not failed-open or choke collapse, which usually governs when the new source pressure exceeds earlier wells. Both belong in the report as their own sections (`neqsim-hp-lp-interface-overpressure`, section 2b).
- **Show the scenario and the valve Cv behind every relief rate.** A reviewer of a failed-open study could not tell which scenario (failed-open or blocked outlet) a relief figure belonged to, and found no installed choke Cv, although the rates depend on it. Open the relief chapter with a scenario register (study status calculated, simple estimate or qualitative; valve states; limiting mechanism; relief rate; governing or not) and an installed-Cv input table (chokes intact and collapsed and their opening, riser EV and stroke time, PV and its maximum opening, PSV orifice and set pressure, volumes, flare backpressure) with document, revision, page or ASSUMED and a quality grade. Add a Cv sensitivity for failed-open and for blocked outlet and state what the relief rate depends on and what it does not: in a reference screening case the failed-open rate followed the PV Cv and stored gas and ignored the choke Cv once a choke had collapsed, while blocked outlet was capped by the well and the choke limited it only at low Cv. End with a short statement of what the report can and cannot be used for (`neqsim-hp-lp-interface-overpressure`, section 2c).
- **Read the host flare data.** An assumed knock-out drum volume was twice the real one; values often sit only in images (datasheet pages, valve schedules) and file ids returned by a search can be stale.
- **SIL needs two criteria.** A SIF reached the SIL 3 PFDavg band and still missed the tolerable hazard rate until the test interval of a second layer was shortened; a layer that only works if the first closes in time is not independent. Failure data without a certificate stays a gap.
- **CFD peaks are screening** without validation against congested-rig data; the class decides, not one run. Verification (closed vessel) and a mesh study are the minimum evidence.
- **Keep drawings tag-anchored.** Every SIF element, node item and cause-and-effect cell must cite a tag on the controlled P&ID; run `tag_anchor_gate` and list new tags as proposals. Drawing differences between the SURF and process sets (order of HIPPS, choke and receiver) are findings.
- **Reconcile before reporting.** A follow-up changed a flare statement, a segment volume and a test interval after later work had quoted the old numbers; run `reconcile_values` on every quantity used by more than one workstream.
- **An AI pre-review is not a facilitated session.** Pre-populated worksheets and persona reviews are prompts for the team; label them so.

## Python Usage Pattern

```python
from process_safety_study import (
    claim_gate, conservatism_gate, evidence_gate, hand_calc_gate,
    profile_gate, reconcile_values, tag_anchor_gate, workflow,
)

plan = workflow()                                    # steps S00..S14 with skills, agents, evidence, gate, traps
register = [{"topic": "criteria", "document": "DOC-A", "status": "READ", "clauses": ["4.1"]},
            {"topic": "rates", "document": "DOC-C", "status": "NOT_READ"}]
print(evidence_gate(register)["status"])             # UNVERIFIED_SCREENING, one data gap
print(claim_gate([{"claim": "tolerable", "document": "DOC-A", "clause": "4.1"}], register)[0]["decision"])
print(hand_calc_gate(464.1, 449.0)["status"])        # MATCH
print(conservatism_gate(9.6, 55.0)["verdict"])       # NON_CONSERVATIVE (screening surge vs transient run)
print(profile_gate([(0, 392.0)], [(0, 260.0), (1, 250.0)], "design case rev 02")["status"])   # MISMATCH
print(tag_anchor_gate([{"id": "SIF-1", "tag": "PT-301"}], ["PT-301"])["status"])              # ANCHORED
```

Tested in `tests/test_process_safety_study.py`, including a worked example from numbers of an earlier study.

## Validation Checklist

- [ ] Scope, host, phase, jurisdiction and acceptance criteria written before any number.
- [ ] Every input profile matches its controlled source revision (`profile_gate`).
- [ ] Document register has status per document; every compliance statement passes `claim_gate`.
- [ ] Release, relief and wave-speed numbers have a hand calculation or an independent model (`hand_calc_gate`).
- [ ] A new source on an existing separator or header is compared with the existing wells and inputs, and blocked outlet is checked against current inflow with a stated verdict.
- [ ] The relief chapter opens with a scenario register and an installed-Cv input table (source and grade, ASSUMED when unsourced), and a Cv sensitivity for failed-open and blocked outlet states what the relief rate depends on.
- [ ] Transient comparisons classified per row; non-conservative rows in the report.
- [ ] SIL verified against both the SIL band and the hazard-rate criterion; data sources named.
- [ ] CFD carries verification, mesh study and an explicit "not validated" label where that applies.
- [ ] HAZOP and cause-and-effect items are tag-anchored; proposals marked.
- [ ] Carried values reconciled; data gaps have an owner; human review list attached.

## Common Mistakes

- Starting the QRA or the HAZOP before the basis and the drawings are frozen.
- Treating "no finding" in an unread document as compliance.
- Presenting a rev A screening number as verified because it was later quoted by another workstream.
- Replacing a failed model by a correction factor without recording the validity range.
- Reading a SIL band without the demand rate, the test regime and the response time.
- Editing a source P&ID instead of proposing a mark-up.

## Limitations

- The gate helpers check structure and arithmetic; they do not judge engineering adequacy.
- The step table is a workflow aid. Project rules, regulations and company procedures override it.
- No licensed standard text is held here; an enterprise overlay supplies document access.
- Placement: vendor-neutral skills, agents and helpers live in `neqsim-community-*`; company-specific content (document systems, criteria, asset data) lives in `neqsim-enterprise-*`; only NeqSim Java functionality goes into the `neqsim` repository.
- Human review by qualified process safety engineers is always required.

## References

- Companion agent: `process-safety-study-agent` (an enterprise overlay agent can extend it).
- Step skills named in the table; core skills `neqsim-process-safety`, `neqsim-consequence-analysis`, `neqsim-relief-flare-network`, `neqsim-water-hammer`.
- IEC 61508 and IEC 61511 (functional safety), API STD 520, 521 and 537 (relief and flare), IEC 60534-2-1 (control valve sizing), IEC 61882 (HAZOP), ISO 10418 (process safety systems).
