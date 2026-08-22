---
name: neqsim-resource-classification-screening
version: "0.2.0"
description: "Educational petroleum resource classification screening using public SODIR RC0-RC9 project maturity and SPE-PRMS categories as independent axes. USE WHEN: a task needs to classify historical production, reserves, contingent resources, or undiscovered/prospective resources without confusing maturity with 1P/2P/3P or 1C/2C/3C uncertainty."
last_verified: "2026-08-22"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Resource Classification Screening

Use this skill for public, educational petroleum resource classification screening. It maps project maturity to the public Norwegian Offshore Directorate (SODIR) resource classes and separately reports the corresponding SPE-PRMS category. It does not infer quantity uncertainty from project maturity.

## When to Use

- When a user asks which resource category a project sits in.
- When an agent needs to distinguish SODIR `RC0`-`RC9` from a PRMS category.
- When a user asks what `F` and `A` mean in a SODIR resource class.
- When a report must keep maturity separate from `1P/2P/3P`, `1C/2C/3C`, or low/best/high estimates.
- When examples must run without confidential volumes, reservoir data, or company estimates.

## Inputs

- `maturity_stage`: an explicit SODIR class (`RC0`, `RC4A`, and so on) or a supported public maturity descriptor such as `on production`, `approved for development`, `development pending`, `recovery unlikely`, `prospect`, `lead`, or `play`.
- `commercial`: optional flag indicating whether the project has been judged commercial.

## Outputs

- `resource_class`: a normalized maturity-stage label.
- `resource_category`: compatibility category used by existing callers.
- `sodir_resource_class`: `RC0`-`RC9`, including `F`/`A` where applicable, or `unclassified` when evidence is insufficient.
- `sodir_resource_category`: `historical-production`, `reserves`, `contingent-resources`, or `undiscovered-resources`.
- `prms_category`: `reserves`, `contingent resources`, `prospective resources`, or `not applicable` for historical production.
- `prms_class_range`: compatibility alias for `prms_category`; it is not a numbered PRMS uncertainty range.
- `uncertainty_basis`: reminder that uncertainty must be reported independently.
- `maturity_warning`: `ok`, `watch`, `sodir-class-needs-evidence`, or `unclassified`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `ResourceClassificationModel` keeps three concepts separate:

1. **SODIR project maturity:** `RC0` is historical production; `RC1`-`RC3` are reserves; `RC4`-`RC7` are contingent resources; `RC8`-`RC9` are undiscovered resources. `F` means first development and `A` means additional/improved recovery.
2. **PRMS category:** reserves, contingent resources, or prospective resources.
3. **Quantity uncertainty:** `1P/2P/3P`, `1C/2C/3C`, or low/best/high, supplied from an estimate rather than inferred from maturity.

Generic PRMS statuses do not always identify one SODIR class. For example, `development on hold` remains a PRMS contingent-resource classification and returns `sodir-class-needs-evidence` unless an authoritative SODIR class is supplied. Unknown stages return `unclassified`; they are not assumed unrecoverable.

This is educational and screening-only logic. It is a rule-based mapping of maturity descriptors, not a volumetric estimate. It does not compute in-place or recoverable volumes, recovery factors, or uncertainty ranges, and it does not apply any company-specific maturity gate. It is not a replacement for a formal resource estimate under SPE-PRMS or the Norwegian Petroleum Directorate scheme and a qualified subsurface review.

## Python Usage Pattern

```python
from resource_classification_screening import ResourceClassificationModel

model = ResourceClassificationModel()
result = model.evaluate(
    maturity_stage="justified for development",
)

print(result.resource_category)
print(result.sodir_resource_class)
print(result.prms_category)
print(result.maturity_warning)
```

## Related NeqSim Functionality

For volumetric resource estimation that feeds a formal classification, redirect to NeqSim field-development functionality:

- `neqsim.process.fielddevelopment.ReservesClassification` — public SPE-PRMS maturity-to-category mapping in Java, mirroring this skill.
- `neqsim.process.util.fielddevelopment` production-profile and recovery utilities — recoverable-volume estimation that supports a classification.
- field-development economics utilities — commercial screening that distinguishes reserves from contingent resources.

This skill is a public maturity-mapping triage layer that decides when to invoke those validated estimation utilities.

## Validation Checklist

- [ ] The maturity stage is a public descriptor, not a confidential project name.
- [ ] No confidential volumes or reservoir data are included.
- [ ] SODIR class and PRMS category are reported as independent fields.
- [ ] Quantity uncertainty is supplied separately and never inferred from resource class.
- [ ] Tests cover historical production, reserves, contingent, undiscovered/prospective, ambiguous, and unclassified cases.
- [ ] Results are described as educational screening indicators.
- [ ] Formal classification is redirected to SPE-PRMS, the NPD scheme, and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| SODIR RC called a PRMS class | Two schemes were conflated | Report SODIR resource class and PRMS category separately |
| `2P` inferred from `RC2` | Maturity mistaken for uncertainty | Obtain an independent probabilistic estimate |
| Reserves labelled too early | Production decision assumed | Confirm the governing production decision evidence |
| Contingent treated as reserves | Sub-commercial volumes counted as reserves | Keep sub-commercial discovered volumes as contingent |
| Prospective over-counted | Undiscovered volumes added to reserves | Keep undiscovered volumes as prospective only |
| Unknown stage called unrecoverable | Missing evidence treated as a technical verdict | Return `unclassified` and request evidence |

## Limitations

- No confidential volumes, reservoir data, or company estimates are included.
- No volumetric, recovery-factor, or uncertainty calculation is performed.
- No company-specific maturity gate is applied.
- Generic PRMS statuses may not resolve to an exact SODIR resource class.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Norwegian Offshore Directorate, Fact box - Resource classification: https://www.sodir.no/en/whats-new/publications/reports/resource-report/resource-report-2022/1-introduction-and-summary/fact-box-resource-classification/
- Norwegian Petroleum, Classification of petroleum resources: https://www.norskpetroleum.no/en/petroleum-resources/resource-classification/
- SPE, Petroleum Resources Management System: https://www.spe.org/en/industry/petroleum-resources-management-system-2018/
