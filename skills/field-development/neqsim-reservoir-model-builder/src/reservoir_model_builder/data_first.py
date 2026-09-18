"""Use the best data that exists; simplify only when nothing better is reachable.

A screening reservoir model is allowed to be simple. It is not allowed to be
simple *by accident*. The distinction this module enforces:

* legitimate  -- "the published grid is behind an entitlement we do not have,
                 so we built a play-typical block and the forecast is an upper
                 bound"
* illegitimate -- "we built a play-typical block" (and never looked)

Both produce the same deck. Only the first is a study.

The ladder here mirrors the enterprise OSDU geometry tiers so a task can move
between the open-data and the governed path without changing its vocabulary,
but this module has no OSDU dependency: it works off whatever inventory the
caller assembled.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

#: Ranked data sources for each modelling ingredient, best first. The
#: ``loses`` text is what silently degrades if a study settles for the next
#: rung without saying so.
DATA_LADDER: dict[str, tuple[dict[str, Any], ...]] = {
    "geometry": (
        {"rank": 1, "source": "published_grid",
         "loses": "faults, lateral heterogeneity, true layering and extent"},
        {"rank": 2, "source": "horizons_and_faults",
         "loses": "property distribution"},
        {"rank": 3, "source": "structure_map",
         "loses": "compartmentalisation"},
        {"rank": 4, "source": "well_tops",
         "loses": "areal extent, which must then be solved for"},
        {"rank": 5, "source": "assumed_block",
         "loses": "every structural control on sweep"},
    ),
    "petrophysics": (
        {"rank": 1, "source": "grid_property_arrays", "loses": "heterogeneity"},
        {"rank": 2, "source": "well_logs", "loses": "areal variation"},
        {"rank": 3, "source": "core_measurements", "loses": "upscaling"},
        {"rank": 4, "source": "analogue_field", "loses": "field specificity"},
        {"rank": 5, "source": "play_typical_default", "loses": "everything"},
    ),
    "fluid": (
        {"rank": 1, "source": "pvt_report", "loses": "the measured bubble point"},
        {"rank": 2, "source": "separator_test", "loses": "reservoir-condition data"},
        {"rank": 3, "source": "operator_document_values",
         "loses": "the full composition"},
        {"rank": 4, "source": "analogue_depth_trend", "loses": "field specificity"},
        {"rank": 5, "source": "correlation", "loses": "validity outside its range"},
    ),
    "scal": (
        {"rank": 1, "source": "scal_report", "loses": "measured endpoints"},
        {"rank": 2, "source": "analogue_scal", "loses": "rock specificity"},
        {"rank": 3, "source": "corey_assumed",
         "loses": "the displacement efficiency that sets recovery factor"},
    ),
    "contacts": (
        {"rank": 1, "source": "pressure_gradient_intersection", "loses": "nothing"},
        {"rank": 2, "source": "log_interpreted_contact", "loses": "gradient support"},
        {"rank": 3, "source": "oil_down_to", "loses": "the lower bound on volume"},
        {"rank": 4, "source": "assumed_contact", "loses": "volume control"},
    ),
    "volumes": (
        {"rank": 1, "source": "operator_volumetrics", "loses": "nothing"},
        {"rank": 2, "source": "public_registry", "loses": "segment detail"},
        {"rank": 3, "source": "computed_from_map", "loses": "independent check"},
    ),
}

ATTEMPT_OUTCOMES = ("used", "blocked", "absent")


def _ladder(ingredient: str) -> tuple[dict[str, Any], ...]:
    try:
        return DATA_LADDER[ingredient]
    except KeyError as error:
        raise KeyError(
            f"unknown ingredient {ingredient!r}; expected one of "
            f"{sorted(DATA_LADDER)}") from error


def rank_of(ingredient: str, source: str) -> Optional[int]:
    for rung in _ladder(ingredient):
        if rung["source"] == source:
            return int(rung["rank"])
    return None


def best_available(
    ingredient: str,
    attempts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Highest rung actually used, and what was given up to get there.

    ``attempts`` is the record of what the study tried: one entry per source
    with an outcome of ``used`` / ``blocked`` / ``absent``.
    """
    ladder = _ladder(ingredient)
    by_source = {str(item.get("source")): item for item in attempts}

    used: Optional[dict[str, Any]] = None
    skipped: list[dict[str, Any]] = []
    for rung in ladder:
        record = by_source.get(rung["source"])
        outcome = str(record.get("outcome", "")).lower() if record else ""
        if outcome == "used":
            used = rung
            break
        skipped.append({
            "source": rung["source"],
            "rank": rung["rank"],
            "outcome": outcome or "not_attempted",
            "detail": (record or {}).get("detail", ""),
            "loses": rung["loses"],
        })

    unattempted = [item["source"] for item in skipped
                   if item["outcome"] == "not_attempted"]
    return {
        "ingredient": ingredient,
        "used": used["source"] if used else None,
        "rank": used["rank"] if used else None,
        "bestPossibleRank": ladder[0]["rank"],
        "skipped": skipped,
        "unattempted": unattempted,
        "isDowngraded": bool(used and used["rank"] > ladder[0]["rank"]),
        "lost": [item["loses"] for item in skipped],
    }


def data_first_gate(
    attempts_by_ingredient: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """May the model be built from what was selected?

    Refuses while any rung above the one in use has no recorded outcome. An
    unattempted rung and an absent one give the same model and opposite
    recommendations, so they must not be allowed to look alike.
    """
    summaries = {name: best_available(name, attempts)
                 for name, attempts in attempts_by_ingredient.items()}

    blockers: list[str] = []
    disclosures: list[str] = []
    for name, summary in summaries.items():
        for source in summary["unattempted"]:
            blockers.append(
                f"{name}: '{source}' was never attempted; try it and record "
                f"'used', 'blocked' or 'absent' before settling for a lower rung")
        if summary["used"] is None:
            blockers.append(f"{name}: no source was marked 'used'")
        elif summary["isDowngraded"]:
            disclosures.append(
                f"{name}: built from '{summary['used']}' rather than "
                f"'{_ladder(name)[0]['source']}', which gives up "
                + "; ".join(summary["lost"]))

    missing = [name for name in DATA_LADDER if name not in summaries]
    for name in missing:
        blockers.append(f"{name}: no attempt record supplied at all")

    return {
        "decision": "proceed" if not blockers else "blocked",
        "ingredients": summaries,
        "blockers": blockers,
        "mustDisclose": disclosures,
        "downgraded": [name for name, s in summaries.items() if s["isDowngraded"]],
    }


def acquisition_plan(gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What to obtain next, ordered by how much it would change the answer.

    Ranked by the gap between the rung in use and the best rung, because that
    gap is what the model is currently guessing.
    """
    plan: list[dict[str, Any]] = []
    for name, summary in (gate.get("ingredients") or {}).items():
        if not summary.get("isDowngraded"):
            continue
        blocked = [item for item in summary["skipped"]
                   if item["outcome"] == "blocked"]
        absent = [item for item in summary["skipped"]
                  if item["outcome"] == "absent"]
        target = (blocked or absent or summary["skipped"])[0]
        plan.append({
            "ingredient": name,
            "obtain": target["source"],
            "route": ("access request -- the data exists and is catalogued"
                      if blocked else
                      "acquisition -- nothing of this kind was found"),
            "recovers": target["loses"],
            "gap": summary["rank"] - summary["bestPossibleRank"],
        })
    plan.sort(key=lambda item: -item["gap"])
    for index, item in enumerate(plan, start=1):
        item["priority"] = index
    return plan
