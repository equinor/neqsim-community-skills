"""Stage-gate project timelines for field-development and host-modification screening.

Educational, dependency-free. Every value-bearing item is scheduled through its stage gates before it can earn or
cost anything:

* prospect: exploration well -> appraisal -> DG1/DG2 concept -> DG3 FEED -> execution -> first production at the
  next turnaround (templates per maturity: undrilled / discovered / appraised / sanctioned);
* host project (modification, debottleneck): DG0 study -> DG1-DG3 -> execution with a shutdown tie-in aligned to
  the turnaround calendar, scheduled ASAP or just in time for the year the capacity is first needed;
* life extension: a pool of lifetime-extension actions by required year that must be sanctioned ``lead_years``
  before the technical-lifetime programme ends.

Costs are placed in the years of the phases that incur them (study cost in the study phase, capex over execution,
opex from availability to the horizon). ``portfolio_plan`` combines items into Gantt rows, a capex calendar and
milestones; ``plot_gantt`` renders it (matplotlib optional).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from typing import Any

DECISION_YEAR = 2026
MATURATION: dict[str, list[tuple[str, int]]] = {
    "undrilled": [
        ("exploration well", 1),
        ("appraisal", 1),
        ("DG1-DG2 concept", 1),
        ("DG3 FEED", 1),
        ("execution", 2),
    ],
    "discovered": [
        ("appraisal", 1),
        ("DG1-DG2 concept", 1),
        ("DG3 FEED", 1),
        ("execution", 2),
    ],
    "appraised": [("DG1-DG2 concept", 1), ("DG3 FEED", 1), ("execution", 2)],
    "sanctioned": [("execution", 2)],
}
HOST_PROJECT_PHASES: list[tuple[str, str, int]] = [
    ("DG0 study", "study_years", 1),
    ("DG1-DG3", "concept_years", 1),
    ("execution", "execution_years", 2),
]
DEFAULT_TURNAROUNDS: list[int] = list(range(2027, 2061, 2))
EXTENSION_LEAD_YEARS = 5
STUDY_COST_FRACTION = 0.05
PHASE_COLOURS = {
    "exploration well": "#8c564b",
    "appraisal": "#e377c2",
    "DG1-DG2 concept": "#bcbd22",
    "DG3 FEED": "#ff7f0e",
    "execution": "#d62728",
    "production": "#2ca02c",
    "DG0 study": "#bcbd22",
    "DG1-DG3": "#ff7f0e",
    "programme revision / DG": "#ff7f0e",
    "execution (life-extension actions)": "#d62728",
}


def _phases(
    template: Sequence[tuple[str, int]], start_year: int
) -> tuple[list[dict[str, Any]], int]:
    out, y = [], start_year
    for name, dur in template:
        if dur <= 0:
            continue
        out.append({"phase": name, "start": y, "end": y + dur - 1})
        y += dur
    return out, y


def next_turnaround(year: int, turnarounds: Iterable[int] | None = None) -> int:
    """First turnaround year at or after ``year`` (the year itself when the calendar has none)."""
    cal = sorted(turnarounds) if turnarounds is not None else DEFAULT_TURNAROUNDS
    return next((t for t in cal if t >= year), year)


def prospect_timeline(
    prospect: dict[str, Any],
    decision_year: int = DECISION_YEAR,
    requires_turnaround: bool = True,
    turnarounds: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Stage-gate plan for one prospect.

    ``prospect`` needs ``name``; optional ``status`` (undrilled/discovered/appraised/sanctioned), ``phase_years``
    ({phase: years} overrides), ``decision_year``, ``earliest_start_year`` (hard floor, e.g. licence or rig slot).
    Returns phases, ``first_production_year`` (year after execution ends, moved to the next turnaround if required),
    ``exploration_year`` and ``sanction_year`` (DG3).
    """
    status = str(prospect.get("status", "undrilled"))
    template = MATURATION.get(status, MATURATION["undrilled"])
    overrides = prospect.get("phase_years") or {}
    template = [(n, int(overrides.get(n, d))) for n, d in template]
    start = int(prospect.get("decision_year", decision_year)) + 1
    phases, first = _phases(template, start)
    if requires_turnaround:
        first = next_turnaround(first, turnarounds)
    first = max(first, int(prospect.get("earliest_start_year", 0) or 0))
    return {
        "item": prospect["name"],
        "kind": "prospect",
        "status": status,
        "phases": phases,
        "first_production_year": first,
        "exploration_year": next(
            (p["start"] for p in phases if p["phase"] == "exploration well"), None
        ),
        "sanction_year": next(
            (p["end"] for p in phases if p["phase"] == "DG3 FEED"), start
        ),
    }


def project_timeline(
    project: dict[str, Any],
    decision_year: int = DECISION_YEAR,
    needed_by: int | None = None,
    horizon_year: int = 2055,
    turnarounds: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Plan for a host modification, ASAP or just in time for ``needed_by``.

    ``project`` needs ``id``; optional ``name``, ``capex_musd``, ``study_cost_musd`` (default 5 % of capex),
    ``opex_musd_per_year``, ``study_years``, ``concept_years``, ``execution_years``, ``requires_shutdown`` (default
    True: capacity is available from a turnaround), ``earliest_decision_year``. Returns phases, ``available_year``,
    ``sanction_year``, ``timing`` (asap/just_in_time) and ``cost_by_year_musd``.
    """
    cal = sorted(turnarounds) if turnarounds is not None else DEFAULT_TURNAROUNDS
    durations = [
        (name, int(project.get(key, default)))
        for name, key, default in HOST_PROJECT_PHASES
    ]
    total = sum(d for _, d in durations)
    start = int(project.get("earliest_decision_year", decision_year)) + 1
    available = start + total
    if project.get("requires_shutdown", True):
        available = next_turnaround(available, cal)
    timing = "asap"
    if needed_by is not None and needed_by > available:
        target = (
            max((t for t in cal if t <= needed_by), default=needed_by)
            if project.get("requires_shutdown", True)
            else needed_by
        )
        if target > available:
            start += target - available
            available = target
            timing = "just_in_time"
    phases, _ = _phases(durations, start)
    capex = float(project.get("capex_musd", 0.0))
    study = float(project.get("study_cost_musd", capex * STUDY_COST_FRACTION))
    cost: dict[int, float] = {}
    for ph in phases:
        years = list(range(ph["start"], ph["end"] + 1))
        amount = (
            study
            if ph["phase"] == "DG0 study"
            else (capex - study if ph["phase"] == "execution" else 0.0)
        )
        for y in years:
            cost[y] = cost.get(y, 0.0) + amount / len(years)
    for y in range(available, int(horizon_year) + 1):
        cost[y] = cost.get(y, 0.0) + float(project.get("opex_musd_per_year", 0.0))
    return {
        "item": project.get("name", project["id"]),
        "id": project["id"],
        "kind": "host_project",
        "timing": timing,
        "phases": phases,
        "available_year": available,
        "sanction_year": (phases[-1]["start"] - 1) if phases else start,
        "cost_by_year_musd": cost,
        "capex_musd": capex,
        "needed_by": needed_by,
    }


def life_extension_timeline(
    programme_end_year: int,
    pool_by_year: dict[int, float],
    decision_year: int = DECISION_YEAR,
    lead_years: int = EXTENSION_LEAD_YEARS,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """When a host life extension must be decided and executed.

    ``pool_by_year`` = not-yet-sanctioned life-extension cost (MUSD) by required year. The decision deadline is the
    earlier of ``programme_end_year - lead_years`` and the year before the first action is due.
    """
    end = int(programme_end_year)
    pool = {int(y): float(v) for y, v in (pool_by_year or {}).items()}
    item = f"Host life extension beyond {end}"
    if not pool:
        return {
            "item": item,
            "kind": "life_extension",
            "phases": [],
            "decision_deadline": end - lead_years,
            "cost_by_year_musd": {},
            "programme_end_year": end,
            "actions": actions or [],
        }
    first_exec = min(pool)
    phases = [
        {
            "phase": "programme revision / DG",
            "start": max(decision_year + 1, first_exec - lead_years),
            "end": first_exec - 1,
        },
        {
            "phase": "execution (life-extension actions)",
            "start": first_exec,
            "end": max(pool),
        },
    ]
    phases = [p for p in phases if p["end"] >= p["start"]]
    return {
        "item": item,
        "kind": "life_extension",
        "phases": phases,
        "decision_deadline": min(end - lead_years, first_exec - 1),
        "cost_by_year_musd": dict(sorted(pool.items())),
        "programme_end_year": end,
        "actions": actions or [],
    }


def discounted(
    cost_by_year: dict[int, float], rate: float, base_year: int = DECISION_YEAR
) -> float:
    """Present value at ``base_year`` of a cost calendar."""
    return sum(
        float(v) / (1.0 + rate) ** max(int(y) - base_year, 0)
        for y, v in cost_by_year.items()
    )


def portfolio_plan(
    chosen: list[dict[str, Any]],
    prospects: list[dict[str, Any]],
    project_ids: Iterable[str],
    projects: list[dict[str, Any]],
    life_extension: dict[str, Any] | None = None,
    decision_year: int = DECISION_YEAR,
    horizon_year: int = 2055,
    turnarounds: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Combined timeline for a selected portfolio.

    ``chosen`` rows need ``prospect`` and ``start_year`` (optional ``last_year`` or ``profile`` {year: ...}).
    Development phases of a prospect slide to its chosen first oil; the exploration well stays at its earliest year
    (information first). Host projects are scheduled just in time for the first chosen start year.
    ``life_extension`` is the dict from :func:`life_extension_timeline` (included when given).
    """
    rows: list[dict[str, Any]] = []
    capex_calendar: dict[int, float] = {}
    by_name = {p["name"]: p for p in prospects}
    for c in chosen:
        tl = prospect_timeline(
            by_name.get(c["prospect"], {"name": c["prospect"]}),
            decision_year,
            turnarounds=turnarounds,
        )
        shift = max(0, int(c["start_year"]) - int(tl["first_production_year"]))
        for ph in tl["phases"]:
            if ph["phase"] != "exploration well":
                ph["start"] += shift
                ph["end"] += shift
        tl["sanction_year"] = (tl.get("sanction_year") or 0) + shift
        tl["first_production_year"] = int(c["start_year"])
        tl["deferred_years"] = shift
        last = int(
            c.get("last_year")
            or (
                max(int(y) for y in c["profile"])
                if c.get("profile")
                else c["start_year"]
            )
        )
        tl["phases"].append(
            {"phase": "production", "start": int(c["start_year"]), "end": last}
        )
        rows.append(tl)
    needed_by = min((int(c["start_year"]) for c in chosen), default=None)
    wanted = set(project_ids)
    for p in projects:
        if p["id"] in wanted:
            tl = project_timeline(
                p, decision_year, needed_by, horizon_year, turnarounds
            )
            rows.append(tl)
            for y, v in tl["cost_by_year_musd"].items():
                capex_calendar[y] = capex_calendar.get(y, 0.0) + v
    if life_extension:
        rows.append(life_extension)
        for y, v in life_extension.get("cost_by_year_musd", {}).items():
            capex_calendar[int(y)] = capex_calendar.get(int(y), 0.0) + float(v)
    milestones = sorted(
        {
            (r.get("sanction_year"), "DG3 " + r["item"])
            for r in rows
            if r.get("sanction_year")
        }
        | {
            (r.get("decision_deadline"), "decision deadline " + r["item"])
            for r in rows
            if r.get("decision_deadline")
        }
    )
    return {
        "decision_year": decision_year,
        "rows": rows,
        "capex_calendar_musd": dict(sorted(capex_calendar.items())),
        "milestones": [{"year": y, "milestone": m} for y, m in milestones if y],
    }


def plot_gantt(plan: dict[str, Any], path: str, title: str = "Project plan") -> str:
    """Render the plan as a Gantt chart (needs matplotlib)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = plan["rows"]
    fig, ax = plt.subplots(figsize=(11, 0.55 * max(len(rows), 1) + 2.5))
    for i, r in enumerate(rows):
        for ph in r["phases"]:
            ax.barh(
                i,
                ph["end"] - ph["start"] + 1,
                left=ph["start"],
                color=PHASE_COLOURS.get(ph["phase"], "#7f7f7f"),
                edgecolor="white",
            )
        if r.get("kind") == "prospect" and r.get("first_production_year"):
            ax.plot(r["first_production_year"], i, marker="D", color="black", ms=5)
        if r.get("available_year"):
            ax.plot(r["available_year"], i, marker="^", color="black", ms=6)
        if r.get("decision_deadline"):
            ax.axvline(r["decision_deadline"], color="grey", ls=":", lw=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["item"][:48] for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("year")
    ax.set_title(title)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=c)
        for c in ("#8c564b", "#e377c2", "#bcbd22", "#ff7f0e", "#d62728", "#2ca02c")
    ]
    ax.legend(
        handles,
        [
            "exploration",
            "appraisal",
            "concept / DG0",
            "FEED / DG1-DG3",
            "execution",
            "production",
        ],
        fontsize=7,
        loc="lower right",
    )
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
