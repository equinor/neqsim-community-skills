---
name: neqsim-concept-longlist-shortlist-screening
calculation_basis: "screening"
version: "0.1.0"
description: "Educational concept long-list to short-list screening for field development: generates a long list from a decision-element option matrix with compatibility rules and givens, flags capacity variants posing as concepts and undecided elements, applies evidence-based must-pass screens, ranks survivors with a weighted decision matrix and Pareto front, tests the ranking against weight uncertainty (rank acceptability and crossover weights) and selects a robust, diverse short list with a reference concept and an elimination log. USE WHEN: a concept long list must be generated or reduced to a short list before detailed concept comparison."
last_verified: "2026-10-26"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Concept Long-List to Short-List Screening

Early field-development decisions fail most often not in the detailed
comparison but before it: the "alternatives" are three sizes of one concept, an
option nobody wrote down was never evaluated, or a concept was dropped on an
opinion. This skill makes the funnel from a wide long list to a defensible
short list explicit, reproducible and auditable. It produces screening results
for human review; it does not select a concept.

## When to Use

- Building the concept long list for an opportunity (DG0/DG1-type framing).
- Reducing a long list to a short list of two to four concepts that a detailed
  comparison (`concept-selection-agent`) and economics can carry forward.
- Checking that a proposed set of cases is a real choice and not capacity
  variants of one topology.
- Showing why each concept was eliminated, and what evidence would revive it.

## Inputs

| Key | Meaning |
|-----|---------|
| `elements` | Decision element to options (default `DEFAULT_DECISION_ELEMENTS`: host, wells, oil export, gas disposal, drive, power) |
| `rules` | Compatibility rules `{"if": {...}, "then_not": {...}, "reason": ...}` (default `DEFAULT_RULES`) |
| `givens` | Decisions already taken (policy decisions); fixed, not varied |
| `concepts` | Alternatively a hand-made list `{"id", "choices", "sizing"}` instead of generation |
| `must_pass` | Non-compensatory criteria `{"id", "name"}` |
| `assessments` | `{concept: {criterion: {"result": pass/fail/unknown, "evidence": "..."}}}` |
| `criteria` | Weighted ranking criteria `{"id", "weight", "direction": benefit/cost}` |
| `scores` | Raw score per concept and criterion (from screening skills, see below) |
| `confidence` | Optional `{concept: {criterion: high/medium/low}}` |
| `reference` | Concept id(s) carried as reference / benchmark |
| `short_list_size`, `diversity_element`, `robustness` | Selection settings (`n_samples`, `concentration`, `seed`, `acceptability_threshold`) |

## Outputs

`run_screening(study)` returns a JSON-serialisable dictionary with
`readiness` (always `SCREENING`), `long_list`, `excluded_by_rules` (with
reasons), `capacity_variants`, `n_distinct_topologies`, `coverage`,
`must_pass_log`, `decision_matrix` (normalised, 1 = best), `ranking`,
`pareto_front`, `robustness` (`p_first`, `p_top_k`), `crossovers`,
`gap_to_cutoff`, `short_list` (each with a reason), `conditional_short_list`,
`elimination_log`, `open_questions`, `warnings` and
`human_review_required: true`.

## Engineering Method

1. **Frame.** Separate givens (decided), decision elements (decided now) and
   deferred choices (later gates). A strategy table over the elements is the
   long list.
2. **Generate.** Enumerate element combinations, removing incompatible ones by
   explicit rules (for example dry-tree wells need a surface wellhead; a
   tieback exports through its host). Every exclusion keeps its reason.
3. **Check the list.** Concepts with identical choices that differ only in
   `sizing` are one concept (capacity variants); a single topology is a sizing
   study, not a long list. An element with one value in every concept that is
   not a given is an unmade decision.
4. **Must-pass screens** (non-compensatory): technical feasibility, water depth,
   host reach, regulatory or policy limits. Only an *evidenced* fail eliminates;
   an unknown or unevidenced fail stays as pending with an open question.
5. **Rank** survivors with a weighted sum of min-max normalised scores (cost
   criteria inverted) and report the Pareto front, so a concept that wins on
   one axis is not hidden by the weights.
6. **Robustness.** Sample weights from a Dirichlet distribution around the base
   set and report how often each concept ranks first and in the top *k* (rank
   acceptability); scan each weight from 0 to 1 and report where the leader
   changes (crossover weight).
7. **Short list.** Leader, robust contenders, one concept of a different host
   if all agree, the reference concept, then fill by rank. Capacity variants
   take one slot. Concepts ranked out get their score gap and whether their
   low-confidence scores could close it.

Scores come from the other screening skills, computed per concept on the same
basis: `neqsim-capex-opex-screening`, `neqsim-asset-value-npv-screening`,
`neqsim-energy-emissions-screening`, `neqsim-step-out-screening`,
`neqsim-stage-gate-project-timeline` (time to first oil) and qualitative
maturity / risk scores with stated confidence.

## Python Usage Pattern

```python
from concept_longlist_shortlist import generate_long_list, run_screening

ll = generate_long_list(givens={"drive": "water_injection"})
study = {
    "concepts": ll["concepts"][:20],
    "must_pass": [{"id": "depth", "name": "Water depth feasible"}],
    "assessments": {...},
    "criteria": [{"id": "npv", "weight": 0.4},
                 {"id": "capex", "weight": 0.3, "direction": "cost"},
                 {"id": "co2", "weight": 0.3, "direction": "cost"}],
    "scores": {...},
    "reference": [ll["concepts"][0]["id"]],
}
result = run_screening(study)
```

See `examples/basic_screening.py`.

## Validation Checklist

- [ ] Givens are stated and agreed; every other element has more than one option.
- [ ] `n_distinct_topologies` is at least three for a long list, at least two on the short list.
- [ ] Every elimination in `elimination_log` has a reason; every must-pass fail has evidence.
- [ ] Scores were computed on one basis (same resource case, price deck, discount rate).
- [ ] The short list is stable in the robustness check, or the crossovers are reported.
- [ ] A reference concept is carried.
- [ ] Open questions are assigned before the short list is used in a gate.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Three plateau rates on one FPSO called three concepts | `detect_capacity_variants`; vary the topology, size later |
| Dropping a concept because "it won't work" | Record a must-pass fail with evidence, or keep it pending |
| Weights tuned until the favourite wins | Fix weights before scoring; report crossovers and rank acceptability |
| Mixing NPV at 8 % with NPV at 10 % | One economic basis for every concept |
| No reference case | Carry the current best or business-as-usual concept |
| Short list of one host type | Diversity rule; justify explicitly if alternatives are infeasible |

## Limitations

- Weighted-sum ranking is compensatory and linear; it hides threshold effects.
  The Pareto front and must-pass screens are there to counter this.
- Min-max normalisation depends on the set of concepts compared; adding or
  removing a concept can change ranks.
- The default element matrix and rules are generic offshore examples; review
  and adapt them to each opportunity.
- Screening only: it does not replace a concept-selection study, qualified cost
  estimates or company decision-gate governance.

## References

- Bratvold, R. B. and Begg, S. H., *Making Good Decisions*, SPE, 2010 (decision
  hierarchy, strategy tables).
- Belton, V. and Stewart, T. J., *Multiple Criteria Decision Analysis*, Kluwer,
  2002 (weighted sum, sensitivity of weights).
- Lahdelma, R., Hokkanen, J. and Salminen, P., "SMAA - Stochastic multiobjective
  acceptability analysis", *European Journal of Operational Research* 106, 1998
  (rank acceptability indices).
- Pugh, S., *Total Design*, Addison-Wesley, 1991 (concept screening against a datum).
