---
name: neqsim-technology-assessment
calculation_basis: "screening"
version: "0.1.0"
description: "Educational technology assessment for new or step-out technology: decomposition, novelty categorisation (1-4), technology readiness level (TRL 0-7) roll-up, enabling vs enhancing, step-out, benefits and risks, standardisation potential and a preliminary qualification outline. USE WHEN: a project study must decide which technology elements need qualification before FMIRR, a qualification programme or a technology assessment report."
last_verified: "2026-10-27"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Technology Assessment

Use this skill to structure the first stage of technology qualification for
**any technology a project may need** (equipment, system, material, process,
software, service or a known technology in a new application): the
**technology assessment**. It answers *which elements of a technology are new,
how mature they are, how far they step outside existing experience, and what
qualification effort is likely to be needed*. The output is a
`technology_assessment.v1` mapping that feeds the failure-mode register
(`neqsim-technology-fmirr`) and the report writer
(`neqsim-technology-assessment-report`).

## When to Use

- A concept study introduces a technology, or an existing technology in a new
  application, and the project must know if qualification is needed.
- A project study deliverable needs a maturity evaluation (novelty category and
  TRL) per system, sub-system and component.
- Before running a failure-mode identification and risk-ranking workshop, to
  focus it on the novel elements.
- Before writing a technology assessment report (see
  `neqsim-technology-assessment-report`).

Do not use it to qualify a technology, approve a design, or replace an expert
panel. It structures judgement; it does not create evidence.

## Inputs

- `technology`: name of the technology.
- `qualification_basis`: description, intended use, environment, functions,
  performance expectations, applicable regulatory requirements. Start with the
  design-basis elements of the project and refine as technologies are selected.
- `role`: `critical_to_business_case` and `qualified_fallback_available`.
- `elements`: the decomposition. Each has `id`, `name`, optional `parent_id`,
  `function`, `kind` (system, subsystem, component, function, interface,
  software, process), `technology_novelty` (`proven`, `limited_history`,
  `new`), `application_area` (`known`, `limited_knowledge`, `new`),
  `qualified_by` (`none`, `company`, `others`), `trl` (0-7), `evidence`,
  `lifecycle_phases`.
- `step_out`: items per dimension (design, manufacturing, installation,
  operability, fluids, operating_conditions, lifetime) with the experience
  basis, the proposed value and optionally numeric `reference_value` /
  `proposed_value` and a `direction` (`max` or `min`).
- `benefits`, `risks` (with optional mitigation), `standardisation`,
  `multi_implementation`.
- `interfaces_untested`, optional `system_trl_override` with a rationale.

## Outputs

- Per element: novelty category (`1`, `2a`, `2b`, `2c`, `3`, `4`), qualification
  need and risk, TRL, consistency flags.
- Summary: element counts, highest category, system TRL with basis, enabling or
  enhancing role.
- Step-out table with status (`within experience`, `step-out beyond experience`,
  `qualitative`), plus missing dimensions as data gaps.
- Benefits and risks, standardisation and multi-implementation notes.
- Preliminary qualification outline per novel element, targeting TRL 4.
- `flags`, `data_gaps` and `assumptions` lists.

## Engineering Method

1. **Qualification basis.** Record what the technology is, how it is used, in
   which environment, which functions it delivers, performance expectations and
   regulatory requirements. This is the yardstick for every later step.
2. **Decomposition.** Top-down from system functions to sub-systems,
   components, software, process sequences and project phases. Cover the whole
   life cycle: design, fabrication, transport, installation, commissioning,
   operation and maintenance, decommissioning. Include interfaces.
3. **Novelty categorisation.** Combine *novelty of the technology* with the
   *application area* (the operating conditions, environment or purpose):

   | Application area \ Technology | Proven | Limited history | New / unproven |
   | --- | --- | --- | --- |
   | Known | 1 | 2 | 3 |
   | Limited knowledge | 2 | 3 | 4 |
   | New | 3 | 4 | 4 |

   Category 2 is split by who qualified it: `2a` by the user company, `2b` by
   others, `2c` unqualified. Only documented, traceable and accessible
   evidence may lower novelty; be conservative. Categorisation ignores
   consequence of failure.
4. **TRL.** Rate each element 0-7 (0 idea, 4 qualified for first use, 7
   proven in operation). The system TRL is the lowest element TRL, or lower when
   interfaces are untested. A proven (category 1) element should be TRL 7.
5. **Enabling or enhancing.** Enabling: critical to the business case with no
   qualified fallback; the critical path may run through qualification.
   Enhancing: the project is not fully dependent on it.
6. **Step-out.** For each of design, manufacturing, installation,
   operability, fluids, operating conditions and lifetime, state the existing
   experience and the proposed value. Flag values beyond experience.
7. **Benefits and risks.** List what the technology adds and what could go
   wrong, so that qualification resources are justified.
8. **Standardisation.** Note potential for standard modules and
   multi-implementation across fields or projects.
9. **Qualification outline.** For each category 2b-4 element, outline the
   activities to reach TRL 4 and preliminary activities to TRL 5-7.
10. **Hand-off.** Pass novel elements to the FMIRR, then to the technology
    qualification plan. Repeat the assessment as evidence arrives.

## Python Usage Pattern

```python
import json
from technology_assessment import from_dict

spec = json.load(open("examples/example_novel_technology.json", encoding="utf-8"))
result = from_dict(spec).assess()

print(result["summary"]["system_trl"], result["summary"]["role"])
for element in result["elements"]:
    print(element["id"], element["category_label"], element["trl"], element["flags"])
```

The programmatic API is `TechnologyAssessment`, `TechnologyElement`,
`StepOutItem`, `categorize` and `classify_role`. `examples/` contains a
synthetic example for a generic novel technology.

## Validated NeqSim Path

This skill holds no engineering calculation. Use it to decide *where* validated
work is needed, then run it: NeqSim process, flow-assurance and
mechanical-design workflows for performance and design evidence, the
qualification tests defined in the qualification plan for TRL evidence, and the
`neqsim-technology-fmirr` skill for risk ranking.

## Escalation

Escalate to a technology-qualification expert panel when any element is
category 3-4, the technology is enabling, system TRL is below 4, or the step-out
is beyond experience in more than one dimension.

## Validation Checklist

- [ ] Qualification basis states description, use, environment, functions,
  performance expectations and regulatory requirements.
- [ ] Decomposition covers the full life cycle and includes interfaces.
- [ ] Every category and TRL cites documented, traceable evidence.
- [ ] Category 1 elements are verified to a named standard or practice.
- [ ] All step-out dimensions are addressed or listed as data gaps.
- [ ] Enabling versus enhancing is justified.
- [ ] Benefits, risks and standardisation are recorded.
- [ ] Every flag and data gap is resolved or carried into the report.
- [ ] A human expert panel has reviewed the result.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Everything rated category 1 | Marketing claims used as evidence | Count only documented, accessible evidence |
| Low system TRL ignored | Component TRLs averaged | Use the lowest TRL, and consider interfaces |
| Qualification skipped for a "proven" element | Category 1 treated as no work | Still verify it to the applicable standard |
| Novelty confused with risk | Category used as a risk rank | Rank failure modes in the FMIRR |
| Third-party TRL 4 accepted blindly | Application area differs | Gap-analyse the evidence against the new application |
| Qualification basis left empty | Started from the solution | Write the basis first, then assess |

## Limitations

- Educational screening; judgement-based and not a substitute for an expert
  panel or a company qualification process.
- The categorisation and TRL scale are summarised in plain wording; consult the
  standards for the authoritative definitions.
- No confidential data or company-specific rules are included. Company
  governance (gates, approvals, TRL verification rules) belongs in an
  enterprise overlay.
- The example is synthetic and illustrative only. The method applies to any technology (equipment, system, material, process, software or service).

## References

- DNV-RP-A203, *Technology qualification* (novelty categorisation, threat
  assessment, qualification plan, TRL guidance).
- ISO 20815, *Production assurance and reliability management*: Annex on
  technology qualification, TRL and novelty categorisation.
- ISO 14224, *Collection and exchange of reliability and maintenance data for
  equipment* (failure-mode terminology).
- API RP 17N, *Recommended practice for subsea production system reliability,
  technical risk, and integrity management*.
- NeqSim repository: https://github.com/equinor/neqsim
