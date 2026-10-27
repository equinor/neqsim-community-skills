---
name: neqsim-technology-fmirr
calculation_basis: "screening"
version: "0.1.0"
description: "Educational failure-mode identification and risk ranking (FMIRR) register for any new technology: separate failed item, mode, mechanism and cause (ISO 14224 terms), 5x5 consequence-probability ranking, critical modes linked to qualification tests, re-rating history. USE WHEN: a technology assessment has identified novel elements and the project needs a ranked failure-mode register to define the qualification plan."
last_verified: "2026-10-27"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Technology FMIRR (Failure Mode Identification and Risk Ranking)

Use this skill to keep and rank the failure-mode register of a technology that
is being qualified. The register is the basis for defining and prioritising the
qualification activities: every critical failure mode must trace to a
qualification activity (the `TEST` column) and every re-rating must trace to
evidence.

## When to Use

- After `neqsim-technology-assessment` has identified novel elements (category
  2b-4) and before the qualification plan is written.
- To prepare or review the output of an FMIRR workshop with an expert panel.
- To repeat the FMIRR as test results and mitigations change the risk.
- To feed the FMIRR chapter of `neqsim-technology-assessment-report`.

It does not replace the workshop. Failure modes, causes and ratings must come
from a panel covering the needed disciplines.

## Inputs

- `technology` name.
- `entries`: one per failure mode with `id`, `item` (failed item or
  component), `function`, `failure_mode`, `failure_mechanism`,
  `failure_mechanism_class`, `failure_cause`, `failure_cause_class`,
  `detection`, `consequence_text`, `consequence_class` (1-5),
  `probability_class` (1-5), `comments`, `qualification_test` (link to the
  qualification plan), `lifecycle_phase`, `novelty_category`.
- Optional: a custom 5x5 matrix and the high-consequence floor setting.

## Outputs

- `rows` with the computed risk (`Low`, `Medium`, `High`) and a `critical` flag.
- `summary`: counts per risk level, critical ids ranked, critical modes with and
  without a qualification test.
- `risk_matrix`: counts per probability and consequence cell.
- `findings`: warnings and gaps (mixed terminology, missing mechanism,
  critical modes without a test or detection, life-cycle phases not covered).
- `history`: previous ratings with their basis; `iteration` number.

## Engineering Method

1. **Scope.** Take the novel elements from the technology assessment and their
   life-cycle phases (design, fabrication, transport, installation,
   commissioning, operation and maintenance, decommissioning).
2. **Identify failure modes** per element and phase. Keep four separate fields:
   - *Failed item*: the component that fails.
   - *Failure mode*: how it fails (for example external leakage, fails to close).
   - *Failure mechanism*: the physical process (mechanical, material,
     instrumentation, electrical, external influence, miscellaneous).
   - *Failure cause*: why (design, fabrication/installation,
     operation/maintenance, management, miscellaneous; include human error).
   Use the equipment-specific ISO 14224 failure-mode tables where they exist.
3. **Rate consequence** for the system as specified, without safeguards that are
   not yet adopted. Use the highest class across people, environment,
   delay/downtime and reputation. Define the scale for the case.
4. **Rate probability** with qualitative classes early; replace by evidence
   (tests, analysis, documented experience) as it arrives. If evidence is
   lacking, be conservative, more so for higher novelty.
5. **Rank risk** with the matrix. Medium and High are *critical* and must be
   covered by the qualification plan. Low modes stay in the register. The
   high-consequence floor keeps class-5 consequences at Medium or above so
   that low probability does not dismiss them.
6. **Link tests.** Give each critical mode a qualification activity and a
   detection method.
7. **Re-rate and repeat.** Record the basis for every change, start a new
   iteration at each qualification milestone, and never delete a mode.

## Python Usage Pattern

```python
import json
from technology_fmirr import from_dict

spec = json.load(open("examples/example_fmirr.json", encoding="utf-8"))
register = from_dict(spec)
register.rerate("1.1.1", probability_class=3, basis="Full-scale test report TR-12")
result = register.evaluate()
print(result["summary"]["critical_ids"])
```

## Validated NeqSim Path

The register holds judgement, not calculations. Use NeqSim process,
flow-assurance, mechanical-design and dynamic-simulation workflows to produce
the evidence that justifies a probability or consequence class, and cite that
evidence in `comments` or the re-rating basis.

## Escalation

Escalate to a workshop with independent specialists when a critical mode has
consequence class 4-5, when the evidence for a probability class is only
judgement, or when a critical mode lacks a qualification activity.

## Validation Checklist

- [ ] Item, mode, mechanism and cause are in separate fields.
- [ ] Every life-cycle phase is covered or the gap is explained.
- [ ] Consequence is rated without unadopted safeguards.
- [ ] The scales and matrix are documented for the case.
- [ ] Each critical mode has a qualification test and a detection method.
- [ ] Every re-rating has a basis and a document reference.
- [ ] Low risk modes remain in the register.
- [ ] Expert panel members and their competence are recorded.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Leak due to fatigue" as one failure mode | Mode, mechanism and cause mixed | Split into three columns |
| Everything rated Low | Safeguards credited before adoption | Rate the system as specified |
| Rare catastrophic mode dismissed | Probability alone drives ranking | Keep the high-consequence floor |
| Register not updated after tests | Treated as a one-off | Re-rate with basis and new iteration |
| No link from risk to tests | Register separate from the plan | Fill the qualification test field |

## Limitations

- Educational screening; ratings are judgement and the default scales and matrix
  are illustrative.
- No failure-rate database is included; use ISO 14224, OREDA or company data
  under the applicable licence.
- Company-specific templates, scales and approval rules belong in an enterprise
  overlay.

## References

- DNV-RP-A203, *Technology qualification* (threat assessment, failure-mode
  register, risk ranking).
- ISO 14224, *Collection and exchange of reliability and maintenance data for
  equipment* (failure-mode, mechanism and cause terminology, Annex B).
- ISO 20815, *Production assurance and reliability management*.
- NeqSim repository: https://github.com/equinor/neqsim
