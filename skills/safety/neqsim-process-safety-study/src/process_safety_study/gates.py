"""Evidence and consistency gates of a process safety study.

Every gate returns a dictionary with a ``status`` and, where evidence is missing, ``data_gaps`` entries
(gap, source, status, assumed, effect). A missing input is never a pass.
"""

from __future__ import annotations

from itertools import pairwise

READ = "READ"


def _gap(gap: str, source: str, status: str, assumed: str, effect: str) -> dict:
    return {
        "gap": gap,
        "source": source,
        "status": status,
        "assumed": assumed,
        "effect": effect,
    }


def evidence_gate(register: list[dict]) -> dict:
    """Check a governing-document register.

    Args:
        register: rows with ``topic``, ``document`` and ``status`` (READ, PARTLY or NOT_READ).

    Returns:
        ``status`` READY_FOR_REVIEW when every row is READ, else UNVERIFIED_SCREENING, the data gaps,
        and ``compliance_claims_allowed`` (true only when every row is READ and the register is not empty).
    """
    gaps = []
    for row in register:
        status = str(row.get("status", "NOT_READ")).upper()
        if status != READ:
            gaps.append(
                _gap(
                    f"{row.get('document', '?')} not fully read ({status})",
                    str(row.get("topic", "")),
                    "OPEN",
                    "conventions applied",
                    "no statement of compliance for this topic",
                )
            )
    ready = bool(register) and not gaps
    return {
        "status": "READY_FOR_REVIEW" if ready else "UNVERIFIED_SCREENING",
        "compliance_claims_allowed": ready,
        "data_gaps": (
            gaps
            if register
            else [
                _gap(
                    "empty register", "study", "OPEN", "none", "nothing can be claimed"
                )
            ]
        ),
    }


def claim_gate(claims: list[dict], register: list[dict]) -> list[dict]:
    """Allow a compliance statement only when its document and clause were read.

    Args:
        claims: rows with ``claim``, ``document`` and ``clause``.
        register: rows with ``document``, ``status`` and ``clauses`` (list of clause numbers that were read).

    Returns:
        One row per claim with ``decision`` ALLOWED or REJECTED and the ``reason``.
    """
    by_document = {str(row.get("document")): row for row in register}
    decided = []
    for claim in claims:
        row = by_document.get(str(claim.get("document")))
        if row is None:
            decision, reason = "REJECTED", "document is not in the register"
        elif str(row.get("status", "")).upper() != READ:
            decision, reason = "REJECTED", f"document status is {row.get('status')}"
        elif str(claim.get("clause")) not in [str(c) for c in row.get("clauses", [])]:
            decision, reason = "REJECTED", "clause was not read"
        else:
            decision, reason = "ALLOWED", "clause read in a READ document"
        decided.append({**claim, "decision": decision, "reason": reason})
    return decided


def _interpolate(points: list[tuple[float, float]], x: float) -> float | None:
    ordered = sorted(points)
    if not ordered or x < ordered[0][0] or x > ordered[-1][0]:
        return None
    for (x0, y0), (x1, y1) in pairwise(ordered):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ordered[-1][1]


def profile_gate(
    used: list[tuple[float, float]],
    source: list[tuple[float, float]],
    source_label: str,
    rel_tol: float = 0.02,
) -> dict:
    """Compare a profile used in the study (for example pressure against distance) with its source.

    Args:
        used: (x, y) points used in the study.
        source: (x, y) points of the controlled source profile.
        source_label: document and revision of the source; required.
        rel_tol: allowed relative difference.

    Returns:
        ``status`` MATCH, MISMATCH or NO_SOURCE with ``max_rel_diff`` and the point where it occurs.
    """
    if not source or not source_label:
        return {
            "status": "NO_SOURCE",
            "data_gaps": [
                _gap(
                    "source profile",
                    source_label or "missing",
                    "OPEN",
                    "none",
                    "profile cannot be used as basis",
                )
            ],
        }
    worst, worst_x, outside = 0.0, None, []
    for x, y in used:
        ref = _interpolate(source, x)
        if ref is None:
            outside.append(x)
            continue
        diff = abs(y - ref) / max(abs(ref), 1e-12)
        if diff > worst:
            worst, worst_x = diff, x
    ok = worst <= rel_tol and not outside
    return {
        "status": "MATCH" if ok else "MISMATCH",
        "max_rel_diff": worst,
        "worst_x": worst_x,
        "outside_source_range": outside,
        "source": source_label,
    }


def hand_calc_gate(
    model_value: float, hand_value: float | None, rel_tol: float = 0.10, label: str = ""
) -> dict:
    """Compare a model result with an independent hand calculation.

    Returns:
        ``status`` MATCH, MISMATCH or NO_HAND_CALC (then ``usable_as_basis`` is false).
    """
    if hand_value is None:
        return {"label": label, "status": "NO_HAND_CALC", "usable_as_basis": False}
    ratio = model_value / hand_value
    ok = abs(ratio - 1.0) <= rel_tol
    return {
        "label": label,
        "status": "MATCH" if ok else "MISMATCH",
        "ratio": ratio,
        "usable_as_basis": ok,
    }


def conservatism_gate(
    screening: float,
    reference: float,
    higher_is_conservative: bool = True,
    tol: float = 0.05,
) -> dict:
    """Classify a screening value against a transient or detailed reference.

    Args:
        screening: value from the screening model.
        reference: value from the detailed model (for example OLGA).
        higher_is_conservative: true when a larger screening value is on the safe side (surge volume,
            peak pressure, blowdown time); false when a smaller value is safe (time to reach a limit
            pressure after a blocked outlet).
        tol: relative band treated as consistent.

    Returns:
        ``verdict`` CONSERVATIVE, NON_CONSERVATIVE or CONSISTENT and the ratio screening/reference.

    Raises:
        ValueError: if the reference is zero.
    """
    if reference == 0:
        raise ValueError("reference must not be zero")
    ratio = screening / reference
    if abs(ratio - 1.0) <= tol:
        verdict = "CONSISTENT"
    elif (ratio > 1.0) == higher_is_conservative:
        verdict = "CONSERVATIVE"
    else:
        verdict = "NON_CONSERVATIVE"
    return {"verdict": verdict, "ratio": ratio}


def tag_anchor_gate(items: list[dict], pid_tags: list[str]) -> dict:
    """Check that every safety item (SIF element, cause, effect, node item) uses a tag on the P&IDs.

    Args:
        items: rows with ``id``, ``tag`` and optionally ``proposed`` (true for a marked-up new tag).
        pid_tags: tags found on the controlled drawings.

    Returns:
        ``status`` ANCHORED or ORPHANS, the orphan rows and the proposed mark-ups.
    """
    known = {str(tag).strip().upper() for tag in pid_tags}
    orphans, proposals = [], []
    for item in items:
        tag = str(item.get("tag", "")).strip().upper()
        if tag in known:
            continue
        (proposals if item.get("proposed") else orphans).append(item)
    return {
        "status": "ANCHORED" if not orphans else "ORPHANS",
        "orphans": orphans,
        "proposed_markups": proposals,
    }


def reconcile_values(values: list[dict], rel_tol: float = 0.02) -> list[dict]:
    """Find quantities that differ between workstreams.

    Args:
        values: rows with ``name``, ``workstream``, ``value`` and ``unit``.
        rel_tol: allowed relative spread between the largest and smallest value.

    Returns:
        One conflict row per name with different units or a spread above the tolerance.
    """
    grouped: dict[str, list[dict]] = {}
    for row in values:
        grouped.setdefault(str(row["name"]), []).append(row)
    conflicts = []
    for name, rows in sorted(grouped.items()):
        units = {str(r.get("unit", "")) for r in rows}
        nums = [float(r["value"]) for r in rows]
        top = max(abs(v) for v in nums) or 1.0
        spread = (max(nums) - min(nums)) / top
        if len(units) > 1 or spread > rel_tol:
            conflicts.append(
                {"name": name, "spread": spread, "units": sorted(units), "rows": rows}
            )
    return conflicts
