"""Risk register, schedule, time-depth and decision-tree inputs derived from the basis and results.

Risk scores are qualitative presentation values (likelihood and consequence 1-5) assigned from the model findings; they are
ASSUMED by the author, labelled as such, and are not an acceptance criterion. Schedule durations come from ``basis.schedule``
(supplied or synthetic); nothing is inferred from offset-well data here (use the drilling module for that).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .registers import get_path

DEFAULT_SCHEDULE = [
    {"name": "Mobilise and conductor/top hole", "low": 6.0, "base": 8.0, "high": 12.0},
    {"name": "Surface section", "low": 5.0, "base": 7.0, "high": 11.0},
    {"name": "Production section", "low": 8.0, "base": 11.0, "high": 18.0},
    {"name": "Logging and casing", "low": 4.0, "base": 6.0, "high": 9.0},
    {"name": "Completion and tubing", "low": 5.0, "base": 7.0, "high": 12.0},
    {"name": "Clean-up and test", "low": 3.0, "base": 4.0, "high": 8.0},
]


def schedule_tasks(basis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gantt tasks with sequential start days (base durations); durations from ``basis.schedule`` or the labelled synthetic default."""
    tasks = [dict(t) for t in (get_path(basis, "schedule") or DEFAULT_SCHEDULE)]
    start = 0.0
    for t in tasks:
        t["start"] = start
        start += t["base"]
    return tasks


def time_depth(basis: Dict[str, Any]) -> Dict[str, List]:
    """Time-depth curves (low/base/high) built from the schedule and the casing shoe depths (piecewise linear, synthetic when the schedule is)."""
    tasks = schedule_tasks(basis)
    shoes = [0.0] + [c["shoe_md_m"] for c in sorted(get_path(basis, "completion.casing") or [], key=lambda c: c["shoe_md_m"])] + [float(get_path(basis, "trajectory.md_m"))]
    shoes = sorted(set(shoes))
    out = {}
    for case in ("low", "base", "high"):
        t, pts = 0.0, [(0.0, 0.0)]
        drill_tasks = tasks[:3] + tasks[3:4]
        for i, d in enumerate(shoes[1:]):
            dur = drill_tasks[min(i, len(drill_tasks) - 1)][case] / max(1, 1)
            t += dur
            pts.append((t, d))
        out[case] = pts
    return out


def build_risks(basis: Dict[str, Any], res: Dict[str, Any], gaps: List[Any]) -> List[Dict[str, Any]]:
    """Risk register entries from findings (envelope statuses, data gaps, unresolved assessments)."""
    risks: List[Dict[str, Any]] = []

    def add(title: str, lk: int, cq: int, mitigation: str, owner: str = "well planning lead") -> None:
        risks.append({"id": len(risks) + 1, "title": title, "likelihood": lk, "consequence": cq, "mitigation": mitigation, "owner": owner, "scoring": "ASSUMED qualitative"})

    for row in (res.get("envelope") or {}).get("rows", []):
        if row["indicative_status"] == "FAIL":
            add("{} exceeds its (indicative) limit: {}".format(row["parameter"], row["condition"]), 4, 4, row["action"])
        elif row["indicative_status"] == "WARN":
            add("{} close to its limit: {}".format(row["parameter"], row["condition"]), 3, 3, "review margin; consider mitigation")
    prod = (res.get("producer") or {}).get("base")
    if prod and not prod.get("target_met"):
        add("Target rate not deliverable in the base case", 4, 4, "evaluate artificial lift, lower host back pressure or larger tubing")
    low = (res.get("producer") or {}).get("low")
    if low and not low.get("target_met"):
        add("Target rate not deliverable in the pessimistic case", 3, 4, "acquire well-test/pressure data; design flexibility for lift")
    for g in gaps:
        sev = {"BLOCKING": 5, "MAJOR": 3, "MINOR": 2}.get(getattr(g, "severity", "MINOR"), 2)
        add("Data gap: {}".format(g.key), 3, sev, g.consequence[:60], "study lead")
    for spec in res.get("interface_specs", []):
        add("Unresolved specialist assessment: {}".format(spec["assessment"]), 3, 4, "hand off to {}".format(spec["receiver"]), "discipline lead")
    return risks[:14]


def decision_tree_nodes(alt: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Decision tree: select the completion alternative, then the reservoir outcome (low/base/high) and whether the target is met."""
    nodes = [{"id": "root", "parent": None, "label": "Select completion", "kind": "decision"}]
    for r in alt.get("alternatives", []):
        aid = r["id"]
        nodes.append({"id": aid, "parent": "root", "label": r["label"], "kind": "chance", "edge": ""})
        for c in ("low", "base", "high"):
            ok = (r["target_met"][c] if "target_met" in r else r["status"][c] == "OK")
            nodes.append({"id": aid + c, "parent": aid, "label": "{}: {}".format(c, "target met" if ok else "target missed"), "kind": "outcome", "edge": c})
    return nodes
