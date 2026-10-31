"""Charts for a well plan: Gantt with uncertainty whiskers, risk matrix, contingency decision tree, S-curves, time-depth chart with a
P10/P50/P90 band, cost breakdown, location map with distance rings and an offset comparison chart (matplotlib, Agg backend).

All functions take plain Python data, save a PNG (200 dpi) and return its path. Nothing here invents numbers.
"""

from __future__ import annotations

import datetime as _dt
import math
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402

DPI = 200
NAVY = "#1f3a5f"
KIND_COLOURS = {"productive": "#2f6fa8", "npt": "#c0392b", "wait": "#e0a030", "evaluation": "#2e8b57", "abandon": "#7d3c98"}
RISK_COLOURS = {1: "#9bd49b", 2: "#f2e394", 3: "#f5b970", 4: "#ee8a6a"}


def _save(fig, path: Path) -> Path:
    path = Path(path)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return path


def gantt_chart(activities: Sequence[Dict[str, object]], path: Path, spud_date: Optional[_dt.date] = None, title: str = "Operations plan (P50 durations)",
                total: Optional[Dict[str, float]] = None) -> Path:
    """Operations Gantt: sequential bars of P50 duration with P10-P90 whiskers on each activity end.

    Args:
        activities: list of dicts with ``name``, ``p50`` (days), optional ``p10``, ``p90`` (days), ``kind`` (``productive``, ``npt``, ``wait``,
            ``evaluation``, ``abandon``) and optional ``group`` text printed before the name.
        path: output PNG path.
        spud_date: optional start date; adds a calendar axis on top.
        title: chart title.
        total: optional dict with ``p10``, ``p50``, ``p90`` of the whole well (drawn as a bracket under the bars).

    Returns:
        The PNG path.
    """
    n = len(activities)
    fig, ax = plt.subplots(figsize=(10.4, 0.46 * n + 2.6))
    t = 0.0
    ends = []
    for i, a in enumerate(activities):
        d = float(a["p50"])
        kind = str(a.get("kind", "productive"))
        ax.barh(i, d, left=t, height=0.56, color=KIND_COLOURS.get(kind, "#2f6fa8"), edgecolor="k", lw=0.5, hatch="//" if kind in ("npt", "wait") else None, alpha=0.9)
        p10, p90 = a.get("p10"), a.get("p90")
        if p10 is not None and p90 is not None:
            lo, hi = t + float(p10), t + float(p90)
            ax.plot([lo, hi], [i, i], color="k", lw=1.0)
            ax.plot([lo, lo], [i - 0.17, i + 0.17], color="k", lw=1.0)
            ax.plot([hi, hi], [i - 0.17, i + 0.17], color="k", lw=1.0)
        ax.text(t + d + (float(p90) - d if p90 is not None else 0.0) + 0.6, i, f"{d:.1f} d", fontsize=7.2, va="center", ha="left")
        t += d
        ends.append(t)
    ax.set_yticks(range(n))
    ax.set_yticklabels([str(a["name"]) for a in activities], fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlabel("Days from spud (P50 sum; whiskers = P10-P90 of the activity duration, drawn from the bar start)")
    ax.grid(axis="x", alpha=0.3)
    xmax = max(ends) * 1.14
    if total:
        ax.axvline(total["p50"], color="k", lw=1.0, ls="--")
        ax.axvspan(total["p10"], total["p90"], color="0.85", alpha=0.6, zorder=0)
        ax.text(total["p50"], n - 0.2, f" well total P10/P50/P90 = {total['p10']:.0f} / {total['p50']:.0f} / {total['p90']:.0f} d", fontsize=7.6, va="bottom", ha="left")
        xmax = max(xmax, total["p90"] * 1.08)
    ax.set_xlim(0, xmax)
    ax.set_ylim(n - 0.3 + 0.9, -0.7)
    handles = [Rectangle((0, 0), 1, 1, fc=c, ec="k", label=k) for k, c in KIND_COLOURS.items() if any(str(a.get("kind", "productive")) == k for a in activities)]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=len(handles), fontsize=7.5, frameon=False)
    if spud_date is not None:
        top = ax.secondary_xaxis("top", functions=(lambda x: x, lambda x: x))
        ticks = np.arange(0, xmax, 10.0)
        top.set_xticks(ticks)
        top.set_xticklabels([(spud_date + _dt.timedelta(days=float(x))).strftime("%d %b") for x in ticks], fontsize=6.4, rotation=45, ha="left")
    ax.set_title(title, fontsize=10, pad=26 if spud_date else 8, loc="left")
    return _save(fig, path)


def risk_matrix(risks: Sequence[Dict[str, object]], path: Path, title: str = "Risk matrix (5 x 5, screening)", show_residual: bool = True) -> Path:
    """5 x 5 likelihood-severity matrix with numbered risks and a legend list.

    Args:
        risks: list of dicts with ``id`` (short, e.g. ``R01``), ``event``, ``likelihood`` (1-5), ``severity`` (1-5) and optional ``res_likelihood``,
            ``res_severity`` (residual position after mitigation, drawn as an open circle with an arrow).
        path: output PNG path.
        title: chart title.
        show_residual: draw the residual positions when present.

    Returns:
        The PNG path.
    """
    fig = plt.figure(figsize=(12.6, 6.4))
    ax = fig.add_axes([0.05, 0.11, 0.36, 0.80])
    for L in range(1, 6):
        for S in range(1, 6):
            score = L * S
            band = 1 if score <= 4 else 2 if score <= 9 else 3 if score <= 15 else 4
            ax.add_patch(Rectangle((S - 0.5, L - 0.5), 1, 1, fc=RISK_COLOURS[band], ec="white", lw=1.5))
            ax.text(S + 0.44, L - 0.44, str(score), fontsize=6, ha="right", va="bottom", color="0.35")
    pos: Dict[Tuple[int, int], List[Tuple[str, str]]] = {}
    for r in risks:
        pos.setdefault((int(r["likelihood"]), int(r["severity"])), []).append(("inh", str(r["id"])))
    seen: Dict[Tuple[int, int], int] = {}

    def slot(cell: Tuple[int, int], k: int) -> Tuple[float, float]:
        sub = [(-0.24, 0.16), (0.0, 0.16), (0.24, 0.16), (-0.24, -0.08), (0.0, -0.08), (0.24, -0.08), (-0.24, -0.30), (0.0, -0.30), (0.24, -0.30)]
        dx, dy = sub[k % len(sub)]
        return cell[1] + dx, cell[0] + dy

    placed: Dict[str, Tuple[float, float]] = {}
    for r in risks:
        cell = (int(r["likelihood"]), int(r["severity"]))
        k = seen.get(cell, 0)
        seen[cell] = k + 1
        x, y = slot(cell, k)
        placed[str(r["id"])] = (x, y)
        ax.add_patch(plt.Circle((x, y), 0.105, fc="#1f3a5f", ec="white", lw=0.8, zorder=4))
        ax.text(x, y, str(r["id"]).lstrip("R").lstrip("0") or "0", fontsize=5.8, ha="center", va="center", color="white", zorder=5, fontweight="bold")
    if show_residual:
        seen2: Dict[Tuple[int, int], int] = {}
        for r in risks:
            if r.get("res_likelihood") is None:
                continue
            cell = (int(r["res_likelihood"]), int(r["res_severity"]))
            k = seen2.get(cell, 0)
            seen2[cell] = k + 1
            x, y = slot(cell, k)
            x0, y0 = placed[str(r["id"])]
            if (x, y) != (x0, y0):
                ax.annotate("", xy=(x, y), xytext=(x0, y0), arrowprops=dict(arrowstyle="->", color="0.25", lw=0.6, alpha=0.7), zorder=3)
            ax.add_patch(plt.Circle((x, y), 0.105, fc="white", ec="#1f3a5f", lw=1.1, zorder=4))
            ax.text(x, y, str(r["id"]).lstrip("R").lstrip("0") or "0", fontsize=5.8, ha="center", va="center", color="#1f3a5f", zorder=5, fontweight="bold")
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xticklabels(["1 minor", "2 moderate", "3 serious", "4 major", "5 critical"], fontsize=7)
    ax.set_yticklabels(["1 remote", "2 unlikely", "3 possible", "4 likely", "5 frequent"], fontsize=7)
    ax.set_xlabel("Severity")
    ax.set_ylabel("Likelihood")
    ax.set_aspect("equal")
    ax.set_title("filled = before mitigation, open = residual (screening judgement)" if show_residual else "before mitigation", fontsize=7.5)
    lg = fig.add_axes([0.44, 0.05, 0.55, 0.88])
    lg.axis("off")
    lg.set_xlim(0, 1)
    lg.set_ylim(0, 1)
    step = min(0.075, 0.9 / max(1, len(risks)))
    y = 0.97
    for r in risks:
        lg.add_patch(plt.Circle((0.02, y), 0.016, fc="#1f3a5f", ec="none"))
        lg.text(0.02, y, str(r["id"]).lstrip("R").lstrip("0") or "0", fontsize=5.6, ha="center", va="center", color="white", fontweight="bold")
        lg.text(0.055, y, textwrap.shorten(f"{r['id']}  {r.get('short', r['event'])}  (L{r['likelihood']}xS{r['severity']}" + (f" to L{r['res_likelihood']}xS{r['res_severity']})" if r.get("res_likelihood") is not None else ")"), 78, placeholder=".."),
                fontsize=8.2, va="center")
        y -= step
    fig.suptitle(title, fontsize=10, x=0.06, ha="left")
    return _save(fig, path)


def _tree_layout(node: Dict[str, object], depth: int, counter: List[int], out: List[Dict[str, object]], parent: Optional[int], edge: str) -> int:
    idx = len(out)
    rec = {"label": node["label"], "kind": node.get("kind", "action"), "depth": depth, "parent": parent, "edge": edge, "y": 0.0}
    out.append(rec)
    kids = node.get("children") or []
    if not kids:
        rec["y"] = float(counter[0])
        counter[0] += 1
    else:
        ys = [_tree_layout(c["node"], depth + 1, counter, out, idx, str(c.get("edge", ""))) for c in kids]
        rec["y"] = float(np.mean([out[i]["y"] for i in ys]))
    return idx


def decision_tree(root: Dict[str, object], path: Path, title: str = "Contingency decision tree", wrap: int = 26) -> Path:
    """Left-to-right decision tree. ``root`` = {"label", "kind", "children": [{"edge": "yes", "node": {...}}, ...]}.

    Node kinds: ``question`` (hexagon), ``action`` (rounded box), ``contingency`` (orange box), ``outcome`` (green box), ``stop`` (red box).

    Args:
        root: nested tree specification.
        path: output PNG path.
        title: chart title.
        wrap: characters per label line.

    Returns:
        The PNG path.
    """
    nodes: List[Dict[str, object]] = []
    _tree_layout(root, 0, [0], nodes, None, "")
    nd = max(n["depth"] for n in nodes) + 1
    nl = max(n["y"] for n in nodes) + 1
    colw, boxw, boxh = 4.2, 3.1, 0.95
    fig, ax = plt.subplots(figsize=(min(13.5, 3.2 * nd + 0.8), max(5.0, 1.15 * nl + 1.6)))
    fill = {"question": "#dbe7f7", "action": "#eef2f7", "contingency": "#fbe0bd", "outcome": "#d9f0e1", "stop": "#f6c8c8"}
    for n in nodes:
        x, y = n["depth"] * colw, -n["y"]
        n["xy"] = (x, y)
    for n in nodes:
        if n["parent"] is not None:
            px, py = nodes[n["parent"]]["xy"]
            x, y = n["xy"]
            ax.plot([px + boxw / 2, x - boxw / 2 - 0.0], [py, y], color="0.35", lw=0.9, zorder=1)
            ax.text((px + boxw / 2 + x - boxw / 2) / 2, (py + y) / 2 + 0.08, n["edge"], fontsize=7.6, ha="center", va="bottom", color="#1f3a5f", fontweight="bold",
                    bbox=dict(fc="white", ec="none", pad=0.6))
    for n in nodes:
        x, y = n["xy"]
        lab = "\n".join(textwrap.wrap(str(n["label"]), wrap))
        if n["kind"] == "question":
            pts = [[x - boxw / 2, y], [x - boxw / 2 + 0.25, y + boxh / 2], [x + boxw / 2 - 0.25, y + boxh / 2], [x + boxw / 2, y], [x + boxw / 2 - 0.25, y - boxh / 2],
                   [x - boxw / 2 + 0.25, y - boxh / 2]]
            ax.add_patch(Polygon(pts, closed=True, fc=fill["question"], ec="k", lw=0.9, zorder=2))
        else:
            ax.add_patch(FancyBboxPatch((x - boxw / 2, y - boxh / 2), boxw, boxh, boxstyle="round,pad=0.0,rounding_size=0.10", fc=fill.get(n["kind"], "#eef2f7"), ec="k", lw=0.9, zorder=2))
        ax.text(x, y, lab, fontsize=7.8, ha="center", va="center", zorder=3)
    ax.set_xlim(-boxw / 2 - 0.2, (nd - 1) * colw + boxw / 2 + 0.2)
    ax.set_ylim(-nl + 0.2, 0.9)
    ax.axis("off")
    ax.set_title(title, fontsize=10, loc="left")
    return _save(fig, path)


def s_curve_plot(samples: Dict[str, np.ndarray], path: Path, units: Dict[str, str], title: str = "Cumulative distributions (S-curves)") -> Path:
    """S-curves (cumulative probability) with P10/P50/P90 markers, one panel per quantity.

    Args:
        samples: name -> 1-D array of Monte Carlo samples.
        path: output PNG path.
        units: name -> axis unit text.
        title: figure title.

    Returns:
        The PNG path.
    """
    fig, axes = plt.subplots(1, len(samples), figsize=(5.4 * len(samples), 4.3), squeeze=False)
    for ax, (name, a) in zip(axes[0], samples.items()):
        a = np.sort(np.asarray(a, dtype=float))
        p = (np.arange(1, a.size + 1) - 0.5) / a.size
        ax.plot(a, p * 100.0, color=NAVY, lw=2.0)
        for q, c, dy in ((10, "#2e8b57", 0.05), (50, "k", 0.0), (90, "#c0392b", -0.05)):
            v = float(np.percentile(a, q))
            ax.plot([a.min(), v], [q, q], color=c, lw=0.8, ls=":")
            ax.plot([v, v], [0, q], color=c, lw=0.8, ls=":")
            ax.plot(v, q, "o", color=c, ms=5)
            ax.text(v, q - 7, f"P{q} = {v:.0f}", fontsize=7.4, ha="left" if q < 90 else "right", va="top", color=c, bbox=dict(fc="white", ec="none", pad=0.6))
        ax.set_xlabel(f"{name} ({units.get(name, '')})")
        ax.set_xlim(float(a.min()) * 0.9, float(np.percentile(a, 99.5)))
        ax.set_ylabel("Cumulative probability (%)")
        ax.set_ylim(0, 100)
        ax.grid(alpha=0.3)
        ax.set_title(name, fontsize=9)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    return _save(fig, path)


def time_depth_band_plot(offsets: Dict[str, Sequence[Sequence[float]]], plan: Dict[str, Sequence[Sequence[float]]], path: Path,
                         title: str = "Time-depth: plan P10 / P50 / P90 and offset wells", milestones: Optional[Sequence[Tuple[str, float, float]]] = None) -> Path:
    """Time-depth chart: shaded P10-P90 band, P50 curve, offset lines and optional labelled milestones.

    Args:
        offsets: name -> [(day, depth_m), ...] (grey lines).
        plan: dict with keys ``P10``, ``P50``, ``P90`` -> [(day, depth_m), ...] (same depth nodes).
        path: output PNG path.
        title: chart title.
        milestones: optional (label, day, depth) points on the P50 curve (for example casing shoes).

    Returns:
        The PNG path.
    """
    fig, ax = plt.subplots(figsize=(8.6, 6.0))
    for name, pts in offsets.items():
        a = np.asarray(pts, dtype=float)
        ax.plot(a[:, 0], a[:, 1], color="0.55", lw=0.9, alpha=0.8)
        ax.text(a[-1, 0], a[-1, 1], f" {name}", fontsize=5.8, color="0.35", va="center", clip_on=True)
    p10, p50, p90 = (np.asarray(plan[k], dtype=float) for k in ("P10", "P50", "P90"))
    ax.fill_betweenx(p50[:, 1], p10[:, 0], p90[:, 0], color="#9ecae1", alpha=0.5, lw=0, label="plan P10-P90")
    ax.plot(p50[:, 0], p50[:, 1], color=NAVY, lw=2.4, label="plan P50")
    ax.plot(p10[:, 0], p10[:, 1], color=NAVY, lw=0.8, ls="--")
    ax.plot(p90[:, 0], p90[:, 1], color=NAVY, lw=0.8, ls="--")
    for lab, d, z in milestones or []:
        ax.plot(d, z, "o", color="#c0392b", ms=4)
        ax.annotate(lab, (d, z), xytext=(6, -9), textcoords="offset points", fontsize=6.6, color="#7d1f1f")
    ax.invert_yaxis()
    ax.set_xlim(0, max(float(np.asarray(v)[-1, 0]) for v in list(offsets.values()) + [plan["P90"]]) * 1.12 if offsets else None)
    ax.set_xlabel("Days from spud")
    ax.set_ylabel("Depth (m MD RKB)")
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7.5, loc="upper right")
    return _save(fig, path)


def cost_breakdown_chart(items: Sequence[Dict[str, object]], path: Path, unit: str = "MNOK", title: str = "Cost breakdown (P50 with P10-P90 range)") -> Path:
    """Horizontal bars of P50 cost per item with P10-P90 whiskers and a total row.

    Args:
        items: list of dicts with ``name``, ``p50`` and optional ``p10``, ``p90``; a row with ``total`` true is drawn in a different colour.
        path: output PNG path.
        unit: cost unit text.
        title: chart title.

    Returns:
        The PNG path.
    """
    n = len(items)
    fig, ax = plt.subplots(figsize=(8.8, 0.42 * n + 2.0))
    for i, it in enumerate(items):
        tot = bool(it.get("total"))
        ax.barh(i, float(it["p50"]), color="#1f3a5f" if tot else "#6fa3d0", edgecolor="k", lw=0.5, height=0.6)
        if it.get("p10") is not None and it.get("p90") is not None:
            ax.plot([float(it["p10"]), float(it["p90"])], [i, i], color="k", lw=1.0)
            ax.plot([float(it["p10"])] * 2, [i - 0.15, i + 0.15], color="k", lw=1.0)
            ax.plot([float(it["p90"])] * 2, [i - 0.15, i + 0.15], color="k", lw=1.0)
        hi = float(it.get("p90") or it["p50"])
        ax.text(hi + 0.01 * max(float(x.get("p90") or x["p50"]) for x in items), i, f"{float(it['p50']):.0f}", fontsize=7.4, va="center")
    ax.set_yticks(range(n))
    ax.set_yticklabels([str(it["name"]) for it in items], fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlabel(unit)
    ax.grid(axis="x", alpha=0.3)
    ax.set_xlim(0, max(float(x.get("p90") or x["p50"]) for x in items) * 1.12)
    ax.set_title(title, fontsize=10, loc="left")
    return _save(fig, path)


def _place_labels(ax, pts: Sequence[Tuple[float, float, str]], fontsize: float = 7.0) -> None:
    """Greedy collision-free label placement around marker points (8 candidate directions, checked against placed labels in display space)."""
    fig = ax.figure
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    placed = []
    markers = [ax.transData.transform((x, y)) for x, y, _ in pts]
    dirs = [(7, 5, "left", "bottom"), (7, -5, "left", "top"), (-7, 5, "right", "bottom"), (-7, -5, "right", "top"), (0, 9, "center", "bottom"), (0, -9, "center", "top"),
            (14, 0, "left", "center"), (-14, 0, "right", "center"), (22, 12, "left", "bottom"), (-22, 12, "right", "bottom"), (22, -12, "left", "top"), (-22, -12, "right", "top")]
    for (x, y, lab), m in zip(pts, markers):
        best = None
        for dx, dy, ha, va in dirs:
            t = ax.annotate(lab, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=fontsize)
            bb = t.get_window_extent(rend).expanded(1.04, 1.12)
            hit = any(bb.overlaps(p) for p in placed) or any(bb.contains(mx, my) for mx, my in markers if (mx, my) != (m[0], m[1]))
            if not hit:
                best = (t, bb)
                break
            t.remove()
        if best is None:
            t = ax.annotate(lab, (x, y), xytext=(7, 5), textcoords="offset points", fontsize=fontsize)
            best = (t, t.get_window_extent(rend))
        placed.append(best[1])


def location_map(points: Sequence[Dict[str, object]], path: Path, centre: Optional[Tuple[float, float]] = None, rings_km: Sequence[float] = (),
                 title: str = "Well location and offset wells", unit_note: str = "Grid coordinates (m) as supplied; distances are straight-line") -> Path:
    """Plan map of a planned well and offset wells with distance rings, scale bar and north arrow.

    Args:
        points: list of dicts with ``name``, ``e``, ``n`` (m) and ``role`` (``planned``, ``offset``, ``host``, ``other``) and optional ``note`` appended to the label.
        path: output PNG path.
        centre: (e, n) of the rings (default the first planned point).
        rings_km: distance rings in km around the centre.
        title: chart title.
        unit_note: sub-title line describing the coordinate basis.

    Returns:
        The PNG path.
    """
    style = {"planned": ("*", "#c0392b", 15), "offset": ("o", "#2f6fa8", 6.5), "host": ("s", "#2e8b57", 8), "other": ("^", "0.5", 6)}
    fig, ax = plt.subplots(figsize=(8.8, 7.6))
    if centre is None:
        pl = [p for p in points if p.get("role") == "planned"]
        centre = (float(pl[0]["e"]), float(pl[0]["n"])) if pl else (float(points[0]["e"]), float(points[0]["n"]))
    for r in rings_km:
        t = np.linspace(0, 2 * math.pi, 241)
        ax.plot(centre[0] + r * 1000 * np.cos(t), centre[1] + r * 1000 * np.sin(t), color="0.65", lw=0.7, ls=":")
    for p in points:
        m, c, s = style.get(str(p.get("role", "offset")), style["offset"])
        ax.plot(float(p["e"]), float(p["n"]), m, color=c, ms=s, mec="k", mew=0.5, zorder=4)
    ax.set_aspect("equal", adjustable="datalim")
    e_all = [float(p["e"]) for p in points]
    n_all = [float(p["n"]) for p in points]
    padx = 0.12 * (max(e_all) - min(e_all) + 1000)
    pady = 0.12 * (max(n_all) - min(n_all) + 1000)
    ax.set_xlim(min(e_all) - padx, max(e_all) + padx)
    ax.set_ylim(min(n_all) - pady, max(n_all) + pady)
    for r in rings_km:
        ax.text(centre[0] + r * 1000 * 0.7071, centre[1] - r * 1000 * 0.7071 - 0.02 * (max(n_all) - min(n_all) + 1000), f"{r:g} km", fontsize=6.6, color="0.45", ha="left", va="top")
    _place_labels(ax, [(float(p["e"]), float(p["n"]), f"{p['name']}" + (f" ({p['note']})" if p.get("note") else "")) for p in points if p.get("label", True)], 6.8)
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.grid(alpha=0.2)
    xlo, xhi = ax.get_xlim()
    ylo, yhi = ax.get_ylim()
    ax.annotate("N", xy=(xhi - 0.05 * (xhi - xlo), yhi - 0.03 * (yhi - ylo)), xytext=(xhi - 0.05 * (xhi - xlo), yhi - 0.14 * (yhi - ylo)), ha="center", fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="k"))
    sb = 5000.0 if (xhi - xlo) > 15000 else 2000.0 if (xhi - xlo) > 6000 else 1000.0
    ax.plot([xlo + 0.04 * (xhi - xlo)] * 2 + [xlo + 0.04 * (xhi - xlo) + sb], [ylo + 0.04 * (yhi - ylo)] * 3, color="k", lw=2.5)
    ax.text(xlo + 0.04 * (xhi - xlo), ylo + 0.055 * (yhi - ylo), f"{sb / 1000:g} km", fontsize=7)
    handles = [plt.Line2D([], [], marker=v[0], color="w", markerfacecolor=v[1], markeredgecolor="k", ms=8, label=k) for k, v in style.items() if any(p.get("role") == k for p in points)]
    ax.legend(handles=handles, loc="lower right", fontsize=7)
    ax.set_title(f"{title}\n{unit_note}", fontsize=9.5, loc="left")
    return _save(fig, path)


def offset_comparison_chart(rows: Sequence[Dict[str, object]], path: Path, plan: Optional[Dict[str, float]] = None,
                            title: str = "Offset wells: total days from spud to completion") -> Path:
    """Horizontal bars of offset total days (labelled with TD and distance) with the plan P10/P50/P90 band.

    Args:
        rows: list of dicts with ``name``, ``days``, optional ``td_m``, ``distance_km``, ``flag`` (for example sidetrack or HPHT analogue).
        path: output PNG path.
        plan: optional dict with ``p10``, ``p50``, ``p90`` days of the planned well.
        title: chart title.

    Returns:
        The PNG path.
    """
    rows = sorted(rows, key=lambda r: float(r["days"]))
    n = len(rows)
    fig, ax = plt.subplots(figsize=(9.2, 0.38 * n + 2.2))
    for i, r in enumerate(rows):
        flag = str(r.get("flag", ""))
        ax.barh(i, float(r["days"]), color="#c0392b" if "HPHT" in flag else "#9aa9b9" if "sidetrack" in flag else "#6fa3d0", edgecolor="k", lw=0.4, height=0.62)
        lab = f"{float(r['days']):.0f} d" + (f" | TD {float(r['td_m']):.0f} m" if r.get("td_m") else "") + (f" | {float(r['distance_km']):.1f} km" if r.get("distance_km") is not None else "") + (f" | {flag}" if flag else "")
        ax.text(float(r["days"]) + 1.5, i, lab, fontsize=6.8, va="center")
    ax.set_yticks(range(n))
    ax.set_yticklabels([str(r["name"]) for r in rows], fontsize=7.4)
    xmax = max(float(r["days"]) for r in rows) * 1.5
    if plan:
        ax.axvspan(plan["p10"], plan["p90"], color="#fde0a8", alpha=0.6, zorder=0, label=f"plan P10-P90 ({plan['p10']:.0f}-{plan['p90']:.0f} d)")
        ax.axvline(plan["p50"], color="#b36b00", lw=1.5, label=f"plan P50 ({plan['p50']:.0f} d)")
        ax.legend(fontsize=7.5, loc="lower right")
    ax.set_xlim(0, xmax)
    ax.set_xlabel("Days")
    ax.grid(axis="x", alpha=0.3)
    ax.set_title(title, fontsize=10, loc="left")
    return _save(fig, path)
