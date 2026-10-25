"""Concept long-list generation, screening and short-listing (educational).

The method follows the decision-quality sequence used in early field-development
work: frame the decision, generate a wide long list of genuinely different
concepts from a matrix of decision elements, remove what cannot work with
evidence (non-compensatory must-pass screens), rank what remains with a
transparent weighted decision matrix, test whether the ranking survives the
weights, and select a short list that is robust, diverse and includes a
reference concept. Every elimination is logged with its reason.

Everything is deterministic for a given seed and uses only the standard library.
"""

from __future__ import annotations

import itertools
import random
from typing import Any, Iterable, Mapping, Sequence

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"
ASSESSMENT_RESULTS = (PASS, FAIL, UNKNOWN)

BENEFIT = "benefit"
COST = "cost"

READINESS_LABEL = "SCREENING"

# A generic offshore field-development option matrix. Callers should replace or
# trim it to the decision frame of their own opportunity.
DEFAULT_DECISION_ELEMENTS: dict[str, list[str]] = {
    "host": [
        "subsea_tieback",
        "fpso",
        "semi_submersible",
        "tlp",
        "spar",
        "fixed_jacket",
        "subsea_to_shore",
    ],
    "wells": ["subsea", "dry_tree"],
    "oil_export": ["shuttle_tanker", "pipeline", "via_host"],
    "gas_disposal": ["export_pipeline", "reinjection", "via_host"],
    "drive": ["depletion", "water_injection", "gas_injection"],
    "power": ["gas_turbine", "power_from_shore", "power_from_host"],
}

# Compatibility rules: if a concept matches every element in ``if`` it must not
# take any option listed in ``then_not``. Rules are generic physics/logistics.
DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "if": {"host": ["subsea_tieback", "subsea_to_shore"]},
        "then_not": {"wells": ["dry_tree"]},
        "reason": "Dry-tree wells need a surface wellhead platform.",
    },
    {
        "if": {"host": ["fpso", "semi_submersible"]},
        "then_not": {"wells": ["dry_tree"]},
        "reason": "Large-motion floaters are normally subsea-well hosts.",
    },
    {
        "if": {"host": ["subsea_tieback"]},
        "then_not": {
            "oil_export": ["shuttle_tanker", "pipeline"],
            "gas_disposal": ["export_pipeline", "reinjection"],
            "power": ["gas_turbine", "power_from_shore"],
        },
        "reason": "A tieback exports, disposes and takes power through its host.",
    },
    {
        "if": {"host": ["fpso", "semi_submersible", "tlp", "spar", "fixed_jacket"]},
        "then_not": {
            "oil_export": ["via_host"],
            "gas_disposal": ["via_host"],
            "power": ["power_from_host"],
        },
        "reason": "A standalone host has no other host to route through.",
    },
    {
        "if": {"host": ["subsea_to_shore"]},
        "then_not": {
            "oil_export": ["shuttle_tanker", "via_host"],
            "gas_disposal": ["reinjection", "via_host"],
            "power": ["gas_turbine", "power_from_host"],
        },
        "reason": "Subsea-to-shore exports by pipeline and is powered from shore.",
    },
    {
        "if": {"drive": ["gas_injection"]},
        "then_not": {"gas_disposal": ["export_pipeline"]},
        "reason": "Gas injection drive consumes the gas otherwise exported.",
    },
]


def _matches(
    choices: Mapping[str, str], condition: Mapping[str, Sequence[str]]
) -> bool:
    """Return True when every element in ``condition`` takes one of its options.

    Args:
        choices: concept choices keyed by decision element.
        condition: element to allowed options.

    Returns:
        True when the concept matches the condition.
    """
    return all(
        choices.get(element) in options for element, options in condition.items()
    )


def _violations(
    choices: Mapping[str, str], rules: Iterable[Mapping[str, Any]]
) -> list[str]:
    """List the reasons of every rule a concept breaks.

    Args:
        choices: concept choices keyed by decision element.
        rules: compatibility rules.

    Returns:
        Reasons of the violated rules (empty when compatible).
    """
    reasons = []
    for rule in rules:
        if _matches(choices, rule.get("if", {})) and any(
            choices.get(element) in options
            for element, options in rule.get("then_not", {}).items()
        ):
            reasons.append(str(rule.get("reason", "incompatible combination")))
    return reasons


def concept_id(choices: Mapping[str, str], elements: Sequence[str]) -> str:
    """Build a readable concept identifier from its choices.

    Args:
        choices: concept choices keyed by decision element.
        elements: element order.

    Returns:
        Identifier such as ``fpso|subsea|shuttle_tanker``.
    """
    return "|".join(str(choices[e]) for e in elements if e in choices)


def generate_long_list(
    elements: Mapping[str, Sequence[str]] | None = None,
    rules: Sequence[Mapping[str, Any]] | None = None,
    givens: Mapping[str, str] | None = None,
    max_concepts: int | None = None,
) -> dict[str, Any]:
    """Enumerate the compatible combinations of the decision elements.

    Givens are decisions already taken (policy decisions in the decision
    hierarchy); they are fixed, not varied. Incompatible combinations are kept
    in ``excluded`` with their reasons so the screening stays auditable.

    Args:
        elements: decision element to options (defaults to
            :data:`DEFAULT_DECISION_ELEMENTS`).
        rules: compatibility rules (defaults to :data:`DEFAULT_RULES`).
        givens: elements fixed by the decision frame.
        max_concepts: optional cap; a warning is raised when it truncates.

    Returns:
        Dictionary with ``concepts``, ``excluded``, ``n_combinations``,
        ``elements`` and ``warnings``.

    Raises:
        ValueError: when a given is not an option of its element.
    """
    elements = {k: list(v) for k, v in (elements or DEFAULT_DECISION_ELEMENTS).items()}
    rules = list(DEFAULT_RULES if rules is None else rules)
    givens = dict(givens or {})
    warnings: list[str] = []
    for element, option in givens.items():
        if element in elements and option not in elements[element]:
            raise ValueError(f"given {element}={option} is not an option of {element}")
        elements[element] = [option]
    order = list(elements)
    concepts, excluded = [], []
    n = 0
    for combo in itertools.product(*(elements[e] for e in order)):
        n += 1
        choices = dict(zip(order, combo))
        cid = concept_id(choices, order)
        reasons = _violations(choices, rules)
        if reasons:
            excluded.append({"id": cid, "choices": choices, "reasons": reasons})
        else:
            concepts.append({"id": cid, "choices": choices})
    if max_concepts is not None and len(concepts) > max_concepts:
        warnings.append(
            f"Long list truncated from {len(concepts)} to {max_concepts} concepts; "
            "tighten the decision frame instead of truncating silently."
        )
        concepts = concepts[:max_concepts]
    return {
        "concepts": concepts,
        "excluded": excluded,
        "n_combinations": n,
        "elements": order,
        "warnings": warnings,
    }


def _topology_key(concept: Mapping[str, Any]) -> tuple:
    """Return the topology key of a concept (its choices, sizing ignored).

    Args:
        concept: concept with ``choices``.

    Returns:
        Sorted tuple of (element, option) pairs.
    """
    return tuple(
        sorted((str(k), str(v)) for k, v in concept.get("choices", {}).items())
    )


def detect_capacity_variants(concepts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Group concepts that differ only in sizing (capacity variants).

    A set of plateau rates or train sizes on one topology is a sizing study of
    one concept, not a set of concepts. Presenting it as a long list hides the
    real decision.

    Args:
        concepts: concepts with ``id``, ``choices`` and optional ``sizing``.

    Returns:
        Dictionary with ``families`` (family id to member ids), ``family_of``
        (concept id to family id), ``variant_groups`` (families with more than
        one member), ``n_distinct_topologies`` and ``warnings``.
    """
    families: dict[tuple, list[str]] = {}
    for c in concepts:
        families.setdefault(_topology_key(c), []).append(str(c["id"]))
    groups = [ids for ids in families.values() if len(ids) > 1]
    warnings = [
        f"Concepts {', '.join(ids)} share one topology and differ only in sizing; "
        "treat them as one concept with a sizing study, not as separate concepts."
        for ids in groups
    ]
    if concepts and len(families) == 1:
        warnings.append(
            "The long list contains a single topology. It is a sizing study, not a "
            "concept long list; generate alternatives on the decision elements."
        )
    family_of = {cid: ids[0] for ids in families.values() for cid in ids}
    return {
        "families": {ids[0]: ids for ids in families.values()},
        "family_of": family_of,
        "variant_groups": groups,
        "n_distinct_topologies": len(families),
        "warnings": warnings,
    }


def coverage_report(
    concepts: Sequence[Mapping[str, Any]],
    elements: Mapping[str, Sequence[str]] | None = None,
    givens: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Report which options of each decision element the long list covers.

    An element that takes only one value across the long list is not being
    decided. That is acceptable only when it is a given in the decision frame.

    Args:
        concepts: concepts with ``choices``.
        elements: decision elements and their options (for missing options).
        givens: elements fixed by the decision frame.

    Returns:
        Dictionary with ``covered``, ``missing`` and ``warnings``.
    """
    givens = dict(givens or {})
    covered: dict[str, list[str]] = {}
    for c in concepts:
        for element, option in c.get("choices", {}).items():
            options = covered.setdefault(element, [])
            if option not in options:
                options.append(option)
    missing = {}
    for element, options in (elements or {}).items():
        if element in givens:
            continue
        gone = [o for o in options if o not in covered.get(element, [])]
        if gone:
            missing[element] = gone
    framed_single = {e for e, o in (elements or {}).items() if len(o) == 1}
    warnings = [
        f"Element '{element}' is '{options[0]}' in every concept but is not a given; "
        "state it as a decided policy or add alternatives."
        for element, options in covered.items()
        if len(options) == 1
        and element not in givens
        and element not in framed_single
        and len(concepts) > 1
    ]
    return {"covered": covered, "missing": missing, "warnings": warnings}


def screen_must_pass(
    concepts: Sequence[Mapping[str, Any]],
    criteria: Sequence[Mapping[str, Any]],
    assessments: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Apply non-compensatory must-pass screens with an evidence rule.

    A concept is eliminated only by an evidenced ``fail``. A ``fail`` without
    evidence, or an ``unknown``, keeps the concept as *pending evidence* with an
    open question, because a long list must not be cut on opinion.

    Args:
        concepts: concepts with ``id``.
        criteria: must-pass criteria with ``id`` and ``name``.
        assessments: ``{concept_id: {criterion_id: {"result", "evidence"}}}``.

    Returns:
        Dictionary with ``passed``, ``pending``, ``eliminated`` and ``log``.

    Raises:
        ValueError: when a result is not pass, fail or unknown.
    """
    passed, pending, eliminated, log = [], [], [], []
    for c in concepts:
        cid = str(c["id"])
        failures, opens = [], []
        for crit in criteria:
            a = assessments.get(cid, {}).get(str(crit["id"]), {})
            result = str(a.get("result", UNKNOWN)).lower()
            if result not in ASSESSMENT_RESULTS:
                raise ValueError(
                    f"{cid}/{crit['id']}: result must be one of {ASSESSMENT_RESULTS}"
                )
            evidence = str(a.get("evidence", "")).strip()
            entry = {
                "concept": cid,
                "criterion": str(crit["id"]),
                "name": str(crit.get("name", crit["id"])),
                "result": result,
                "evidence": evidence,
            }
            if result == FAIL and evidence:
                failures.append(entry)
            elif result != PASS:
                suffix = " (fail asserted without evidence)" if result == FAIL else ""
                entry["open_question"] = f"Provide evidence for '{entry['name']}'{suffix}"
                opens.append(entry)
            log.append(entry)
        if failures:
            eliminated.append(
                {
                    "concept": cid,
                    "stage": "must_pass",
                    "reason": "; ".join(
                        f"{f['name']}: {f['evidence']}" for f in failures
                    ),
                }
            )
        elif opens:
            pending.append({"concept": cid, "open": opens})
        else:
            passed.append(cid)
    return {"passed": passed, "pending": pending, "eliminated": eliminated, "log": log}


def normalise_weights(criteria: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Return criterion weights scaled to sum to one.

    Args:
        criteria: criteria with ``id`` and ``weight``.

    Returns:
        Criterion id to normalised weight.

    Raises:
        ValueError: when a weight is negative or all weights are zero.
    """
    raw = {str(c["id"]): float(c.get("weight", 1.0)) for c in criteria}
    if any(w < 0 for w in raw.values()):
        raise ValueError("criterion weights must be non-negative")
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("at least one criterion weight must be positive")
    return {k: w / total for k, w in raw.items()}


def normalise_scores(
    concept_ids: Sequence[str],
    criteria: Sequence[Mapping[str, Any]],
    scores: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    """Min-max normalise raw scores to 0..1 with 1 always best.

    Args:
        concept_ids: concepts to score.
        criteria: criteria with ``id`` and ``direction`` (``benefit``/``cost``).
        scores: ``{concept_id: {criterion_id: raw value}}``.

    Returns:
        Dictionary with ``normalised`` and ``warnings`` (non-discriminating
        criteria).

    Raises:
        ValueError: when a concept has no score for a criterion.
    """
    norm: dict[str, dict[str, float]] = {cid: {} for cid in concept_ids}
    warnings = []
    for crit in criteria:
        key = str(crit["id"])
        direction = str(crit.get("direction", BENEFIT))
        missing = [cid for cid in concept_ids if key not in scores.get(cid, {})]
        if missing:
            raise ValueError(f"criterion '{key}' has no score for {', '.join(missing)}")
        values = {cid: float(scores[cid][key]) for cid in concept_ids}
        lo, hi = min(values.values()), max(values.values())
        if hi == lo and len(concept_ids) > 1:
            warnings.append(f"Criterion '{key}' does not discriminate between the concepts.")
        for cid, v in values.items():
            x = 0.5 if hi == lo else (v - lo) / (hi - lo)
            norm[cid][key] = 1.0 - x if direction == COST else x
    return {"normalised": norm, "warnings": warnings}


def weighted_ranking(
    normalised: Mapping[str, Mapping[str, float]], weights: Mapping[str, float]
) -> list[dict[str, Any]]:
    """Rank concepts by weighted normalised score.

    Args:
        normalised: ``{concept_id: {criterion_id: 0..1}}``.
        weights: criterion id to weight (summing to one).

    Returns:
        Rows ``{concept, score, rank}`` sorted best first; ties keep input order.
    """
    rows = [
        {
            "concept": cid,
            "score": sum(weights[k] * v for k, v in crit.items() if k in weights),
        }
        for cid, crit in normalised.items()
    ]
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def pareto_front(
    normalised: Mapping[str, Mapping[str, float]],
    criteria_ids: Sequence[str] | None = None,
) -> list[str]:
    """Return the concepts no other concept dominates on the normalised criteria.

    Args:
        normalised: ``{concept_id: {criterion_id: 0..1}}`` (1 is best).
        criteria_ids: criteria to use (default: all).

    Returns:
        Non-dominated concept ids.
    """
    ids = list(normalised)
    keys = list(criteria_ids or next(iter(normalised.values()), {}).keys())
    front = []
    for a in ids:
        dominated = any(
            all(normalised[b][k] >= normalised[a][k] for k in keys)
            and any(normalised[b][k] > normalised[a][k] for k in keys)
            for b in ids
            if b != a
        )
        if not dominated:
            front.append(a)
    return front


def weight_robustness(
    normalised: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    top_k: int = 3,
    n_samples: int = 2000,
    concentration: float = 20.0,
    seed: int = 1,
) -> dict[str, Any]:
    """Sample weights around the base set and report rank acceptability.

    Weights are drawn from a Dirichlet distribution centred on the base weights;
    ``concentration`` sets how far they may move (lower is wider). The result is
    the probability each concept ranks first and within the top ``k``.

    Args:
        normalised: ``{concept_id: {criterion_id: 0..1}}``.
        weights: base weights summing to one.
        top_k: short-list size used for the top-k acceptability.
        n_samples: number of weight samples.
        concentration: Dirichlet concentration (sum of alphas).
        seed: random seed.

    Returns:
        Dictionary with ``p_first``, ``p_top_k``, ``n_samples``, ``top_k`` and
        ``concentration``.
    """
    rng = random.Random(seed)
    keys = list(weights)
    ids = list(normalised)
    first = {cid: 0 for cid in ids}
    topk = {cid: 0 for cid in ids}
    for _ in range(n_samples):
        draw = [
            rng.gammavariate(concentration * weights[k], 1.0) if weights[k] > 0 else 0.0
            for k in keys
        ]
        total = sum(draw) or 1.0
        ranking = weighted_ranking(
            normalised, {k: d / total for k, d in zip(keys, draw)}
        )
        first[ranking[0]["concept"]] += 1
        for r in ranking[:top_k]:
            topk[r["concept"]] += 1
    return {
        "p_first": {cid: first[cid] / n_samples for cid in ids},
        "p_top_k": {cid: topk[cid] / n_samples for cid in ids},
        "n_samples": n_samples,
        "top_k": top_k,
        "concentration": concentration,
    }


def weight_crossovers(
    normalised: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    step: float = 0.01,
) -> list[dict[str, Any]]:
    """Find, per criterion, the weight at which the leading concept changes.

    The weight of one criterion is moved from 0 to 1 while the others keep their
    relative proportions. The crossover closest to the base weight is reported.

    Args:
        normalised: ``{concept_id: {criterion_id: 0..1}}``.
        weights: base weights summing to one.
        step: scan step of the moved weight.

    Returns:
        One row per criterion: ``criterion``, ``base_weight``,
        ``crossover_weight`` (None if the leader never changes), ``new_leader``.
    """
    base_leader = weighted_ranking(normalised, weights)[0]["concept"]
    rows = []
    n = int(round(1.0 / step))
    for key, w0 in weights.items():
        rest = 1.0 - w0
        best = None
        if rest > 0:
            for i in range(n + 1):
                t = i * step
                w = {
                    k: (t if k == key else v * (1.0 - t) / rest)
                    for k, v in weights.items()
                }
                leader = weighted_ranking(normalised, w)[0]["concept"]
                if leader != base_leader and (
                    best is None or abs(t - w0) < abs(best[0] - w0)
                ):
                    best = (t, leader)
        rows.append(
            {
                "criterion": key,
                "base_weight": round(w0, 4),
                "crossover_weight": None if best is None else round(best[0], 4),
                "new_leader": None if best is None else best[1],
            }
        )
    return rows


def gap_to_cutoff(
    ranking: Sequence[Mapping[str, Any]],
    normalised: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    cutoff_score: float,
    confidence: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Bound what would have to change for a ranked-out concept to qualify.

    For each concept below the cut-off, report the score gap and whether moving
    its low-confidence scores to the best observed value could close it.

    Args:
        ranking: weighted ranking rows.
        normalised: normalised scores.
        weights: criterion weights.
        cutoff_score: weighted score of the last short-listed concept.
        confidence: ``{concept_id: {criterion_id: "high"|"medium"|"low"}}``.

    Returns:
        Concept id to ``{gap, low_confidence_criteria, closable_by_low_confidence}``.
    """
    confidence = confidence or {}
    out = {}
    for r in ranking:
        cid = r["concept"]
        if r["score"] >= cutoff_score:
            continue
        gap = cutoff_score - r["score"]
        low = [
            k for k, lvl in confidence.get(cid, {}).items() if str(lvl).lower() == "low"
        ]
        upside = sum(
            weights.get(k, 0.0) * (1.0 - normalised[cid].get(k, 0.0)) for k in low
        )
        out[cid] = {
            "gap": round(gap, 4),
            "low_confidence_criteria": low,
            "closable_by_low_confidence": bool(low) and upside >= gap,
        }
    return out


def select_short_list(
    ranking: Sequence[Mapping[str, Any]],
    robustness: Mapping[str, Any] | None = None,
    size: int = 3,
    acceptability_threshold: float = 0.25,
    concepts: Sequence[Mapping[str, Any]] | None = None,
    diversity_element: str | None = "host",
    reference_ids: Sequence[str] = (),
    family_of: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Select a robust, diverse short list with a reason for every entry.

    Rules, in order: the leader; robust contenders (top-k acceptability at or
    above the threshold) while slots remain after reserving one per reference;
    one concept of a different ``diversity_element`` value when all so far share
    one; the declared reference concept(s); then fill by rank to ``size``.
    Diversity and reference entries may exceed ``size`` (with a warning).
    Capacity variants of one topology fill one slot only.

    Args:
        ranking: weighted ranking rows (best first).
        robustness: output of :func:`weight_robustness`.
        size: target short-list size (mandatory entries may exceed it).
        acceptability_threshold: minimum top-k acceptability for a contender.
        concepts: concepts with ``choices`` (for diversity).
        diversity_element: element whose value should differ across the list.
        reference_ids: concepts that must be carried as reference/benchmark.
        family_of: concept id to capacity-variant family id.

    Returns:
        Dictionary with ``short_list`` (``concept``, ``reason``) and ``warnings``.
    """
    family_of = dict(family_of or {})
    choices = {str(c["id"]): c.get("choices", {}) for c in (concepts or [])}
    robustness = robustness or {}
    p_top = robustness.get("p_top_k", {})
    selected: list[dict[str, str]] = []
    families: set[str] = set()
    warnings: list[str] = []

    def add(cid: str, reason: str) -> bool:
        """Add a concept unless it or its capacity-variant family is listed.

        Args:
            cid: concept id.
            reason: why the concept is short-listed.

        Returns:
            True when the concept was added.
        """
        fam = family_of.get(cid, cid)
        if fam in families:
            return False
        selected.append({"concept": cid, "reason": reason})
        families.add(fam)
        return True

    ranked_ids = [r["concept"] for r in ranking]
    if ranked_ids:
        add(ranked_ids[0], "Highest weighted score")
    n_reserved = len([r for r in reference_ids if r in ranked_ids])
    for cid in ranked_ids[1:]:
        if len(selected) >= max(1, size - n_reserved):
            break
        if p_top and p_top.get(cid, 0.0) >= acceptability_threshold:
            add(
                cid,
                f"Robust contender: top-{robustness['top_k']} in "
                f"{p_top[cid]:.0%} of weight samples",
            )
    if diversity_element and choices and selected:
        values = {
            choices.get(s["concept"], {}).get(diversity_element) for s in selected
        }
        if len(values) <= 1:
            for cid in ranked_ids:
                v = choices.get(cid, {}).get(diversity_element)
                if v is not None and v not in values and add(
                    cid,
                    f"Diversity: best-ranked concept with a different "
                    f"{diversity_element} ({v})",
                ):
                    break
    for ref in reference_ids:
        if ref not in ranked_ids:
            warnings.append(
                f"Reference concept '{ref}' is not among the ranked concepts."
            )
            continue
        if not add(ref, "Reference / benchmark concept carried for comparison"):
            for s in selected:
                if family_of.get(s["concept"], s["concept"]) == family_of.get(ref, ref):
                    s["reason"] += "; also the reference concept family"
    for cid in ranked_ids:
        if len(selected) >= size:
            break
        add(cid, "Next best weighted score")
    if len(selected) > size:
        warnings.append(
            f"Short list has {len(selected)} concepts (more than {size}) because "
            "mandatory entries were added."
        )
    if ranked_ids and len(families) < 2:
        warnings.append(
            "Short list holds a single topology; it cannot support a concept decision."
        )
    return {"short_list": selected, "warnings": warnings}


def run_screening(study: Mapping[str, Any]) -> dict[str, Any]:
    """Run the full long-list to short-list screening from one study dictionary.

    Expected keys: ``concepts`` (or ``elements``/``rules``/``givens`` to generate
    them), ``must_pass`` criteria and ``assessments``, ``criteria`` (weighted,
    with ``direction``), ``scores``, optional ``confidence``, ``reference``
    concept ids, ``short_list_size``, ``diversity_element`` and ``robustness``
    settings (``n_samples``, ``concentration``, ``seed``,
    ``acceptability_threshold``).

    Args:
        study: study definition.

    Returns:
        JSON-serialisable result with long list, eliminations, decision matrix,
        Pareto front, robustness, crossovers, short list, open questions,
        warnings and a ``readiness`` label that is never an approval.
    """
    warnings: list[str] = []
    elements = study.get("elements")
    givens = study.get("givens", {})
    if "concepts" in study:
        concepts = [dict(c) for c in study["concepts"]]
        excluded: list[dict[str, Any]] = []
    else:
        gen = generate_long_list(
            elements, study.get("rules"), givens, study.get("max_concepts")
        )
        concepts, excluded = gen["concepts"], gen["excluded"]
        warnings += gen["warnings"]
    for c in concepts:
        c.setdefault("id", concept_id(c.get("choices", {}), list(c.get("choices", {}))))
    variants = detect_capacity_variants(concepts)
    coverage = coverage_report(concepts, elements, givens)
    warnings += variants["warnings"] + coverage["warnings"]

    screen = screen_must_pass(
        concepts, study.get("must_pass", []), study.get("assessments", {})
    )
    survivors = screen["passed"] + [p["concept"] for p in screen["pending"]]
    criteria = list(study.get("criteria", []))
    ranking: list[dict[str, Any]] = []
    pareto: list[str] = []
    robust: dict[str, Any] = {}
    crossovers: list[dict[str, Any]] = []
    gaps: dict[str, dict[str, Any]] = {}
    normalised: dict[str, dict[str, float]] = {}
    short: dict[str, Any] = {"short_list": [], "warnings": []}
    if survivors and criteria:
        weights = normalise_weights(criteria)
        ns = normalise_scores(survivors, criteria, study.get("scores", {}))
        normalised = ns["normalised"]
        warnings += ns["warnings"]
        ranking = weighted_ranking(normalised, weights)
        pareto = pareto_front(normalised)
        rs = dict(study.get("robustness", {}))
        size = int(study.get("short_list_size", 3))
        robust = weight_robustness(
            normalised,
            weights,
            top_k=size,
            n_samples=int(rs.get("n_samples", 2000)),
            concentration=float(rs.get("concentration", 20.0)),
            seed=int(rs.get("seed", 1)),
        )
        crossovers = weight_crossovers(normalised, weights)
        short = select_short_list(
            ranking,
            robust,
            size=size,
            acceptability_threshold=float(rs.get("acceptability_threshold", 0.25)),
            concepts=concepts,
            diversity_element=study.get("diversity_element", "host"),
            reference_ids=list(study.get("reference", [])),
            family_of=variants["family_of"],
        )
        chosen = {s["concept"] for s in short["short_list"]}
        cutoff = min(r["score"] for r in ranking if r["concept"] in chosen)
        gaps = gap_to_cutoff(
            ranking, normalised, weights, cutoff, study.get("confidence")
        )
    elif survivors:
        warnings.append(
            "No weighted criteria given; concepts were screened but not ranked."
        )
    warnings += short["warnings"]

    selected = {s["concept"] for s in short["short_list"]}
    pending_ids = {p["concept"] for p in screen["pending"]}
    elimination_log = list(screen["eliminated"])
    for r in ranking:
        if r["concept"] in selected:
            continue
        g = gaps.get(r["concept"], {})
        reason = f"Ranked out: weighted score {r['score']:.3f} (rank {r['rank']})"
        if robust:
            reason += (
                f"; top-{robust['top_k']} in {robust['p_top_k'][r['concept']]:.0%} "
                "of weight samples"
            )
        if g.get("closable_by_low_confidence"):
            reason += "; gap closable by its low-confidence scores - revisit with evidence"
        elimination_log.append(
            {"concept": r["concept"], "stage": "ranking", "reason": reason}
        )
    conditional = sorted(selected & pending_ids)
    if conditional:
        warnings.append(
            "Short-listed concepts with open must-pass questions: "
            + ", ".join(conditional)
        )
    return {
        "readiness": READINESS_LABEL,
        "n_combinations": len(concepts) + len(excluded),
        "long_list": [c["id"] for c in concepts],
        "excluded_by_rules": excluded,
        "capacity_variants": variants["variant_groups"],
        "n_distinct_topologies": variants["n_distinct_topologies"],
        "coverage": coverage,
        "must_pass_log": screen["log"],
        "decision_matrix": normalised,
        "ranking": ranking,
        "pareto_front": pareto,
        "robustness": robust,
        "crossovers": crossovers,
        "gap_to_cutoff": gaps,
        "short_list": short["short_list"],
        "conditional_short_list": conditional,
        "elimination_log": elimination_log,
        "open_questions": [o for p in screen["pending"] for o in p["open"]],
        "warnings": warnings,
        "human_review_required": True,
    }
