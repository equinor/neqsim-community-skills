"""Additional generic charts and the casing-programme sheet of the integrated well planning design system.

Everything draws plain dictionaries/arrays; nothing here calculates engineering values. Styling follows ``iwp_style`` (semantic palette,
direct labels with collision avoidance, units on every axis, shaded bands, no legends where a direct label works).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
import textwrap

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon, Rectangle

from .iwp_style import CATEGORICAL, LW, PALETTE, a3_sheet, band, direct_label, sheet_axes


def _spread_labels(ys: Sequence[float], unit_gap: float, heights: Optional[Sequence[int]] = None) -> List[float]:
    """Push label y-positions apart (sorted order preserved); a label of ``h`` text lines needs ``unit_gap * h`` of room, neighbours share their half heights."""
    hs = list(heights) if heights is not None else [1] * len(ys)
    order = list(np.argsort(ys))
    out = [float(y) for y in ys]
    prev = None
    for i in order:
        if prev is not None:
            out[i] = max(out[i], out[prev] + unit_gap * 0.5 * (hs[prev] + hs[i]) + unit_gap * 0.3)
        prev = i
    return out


def multi_line_chart(series: Sequence[Dict[str, Any]], xlabel: str, ylabel: str, title: str = "", hlines: Optional[Sequence[Dict[str, Any]]] = None,
                     vlines: Optional[Sequence[Dict[str, Any]]] = None, xlim: Optional[Tuple[float, float]] = None, ylim: Optional[Tuple[float, float]] = None,
                     size: Tuple[float, float] = (7.4, 4.6), label_right: bool = True, invert_y: bool = False, annotations: Optional[Sequence[Dict[str, Any]]] = None,
                     shade: Optional[Sequence[Dict[str, Any]]] = None) -> plt.Figure:
    """Line chart with direct labels.

    Args:
        series: dicts with ``x``, ``y``, ``label`` and optional ``color``, ``ls``, ``lw``, ``marker``, ``band`` (``{"low": [...], "high": [...]}``), ``label_dy`` (points).
        hlines: ``[{"y", "label", "color", "ls"}]`` limit lines with a label at the left edge.
        vlines: ``[{"x", "label", "color", "ls"}]`` vertical markers with a label at the top.
        annotations: ``[{"x", "y", "text", "dx", "dy", "color"}]`` point annotations with a leader.
        shade: ``[{"x0", "x1", "color", "label"}]`` shaded x-ranges with a text label at the top.
    """
    fig, ax = plt.subplots(figsize=size)
    ends: List[Tuple[float, float, str, str]] = []
    for i, s in enumerate(series):
        col = s.get("color", CATEGORICAL[i % len(CATEGORICAL)])
        x, y = np.asarray(s["x"], float), np.asarray(s["y"], float)
        if s.get("band"):
            band(ax, x, np.asarray(s["band"]["low"], float), np.asarray(s["band"]["high"], float), col, 0.18)
        ax.plot(x, y, color=col, ls=s.get("ls", "-"), lw=s.get("lw", LW["thick"]), marker=s.get("marker"), ms=s.get("ms", 4), zorder=3)
    if xlim:
        ax.set_xlim(*xlim)
    if ylim:
        ax.set_ylim(*ylim)
    if invert_y:
        ax.invert_yaxis()
    xa, xb = sorted(ax.get_xlim())
    ya, yb = sorted(ax.get_ylim())
    for i, s in enumerate(series):
        if not s.get("label"):
            continue
        col = s.get("color", CATEGORICAL[i % len(CATEGORICAL)])
        x, y = np.asarray(s["x"], float), np.asarray(s["y"], float)
        inside = np.isfinite(y) & (x >= xa) & (x <= xb) & (y >= ya) & (y <= yb)
        if not inside.any():
            continue
        idx = np.where(inside)[0]
        if s.get("label_frac") is not None:
            j = int(idx[int(round(float(s["label_frac"]) * (len(idx) - 1)))])
            ax.annotate(s["label"], (x[j], y[j]), xytext=(s.get("label_dx", 6), s.get("label_dy", 8)), textcoords="offset points", fontsize=7.6, color=col, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85), zorder=6)
            continue
        j = int(idx[-1])
        xe, ye = float(x[j]), float(y[j])
        if j + 1 < len(x) and np.isfinite(y[j + 1]) and not inside[j + 1]:
            # the line leaves the axes between j and j+1: label its exit point instead of the last sample
            ylim_hit = yb if y[j + 1] > yb else (ya if y[j + 1] < ya else None)
            if ylim_hit is not None and y[j + 1] != y[j]:
                f = (ylim_hit - y[j]) / (y[j + 1] - y[j])
                xe, ye = float(x[j] + f * (x[j + 1] - x[j])), float(ylim_hit - 0.02 * (yb - ya) * (1 if ylim_hit == yb else -1))
        ends.append((xe, ye, s["label"], col))
    for h in hlines or []:
        ax.axhline(h["y"], color=h.get("color", PALETTE["limit"]), ls=h.get("ls", "--"), lw=LW["normal"], zorder=2)
        if h.get("label"):
            ax.annotate(h["label"], (ax.get_xlim()[1], h["y"]), xytext=(-4, 3), textcoords="offset points", ha="right", fontsize=7.2, color=h.get("color", PALETTE["limit"]), fontweight="bold", va="bottom")
    for v in vlines or []:
        ax.axvline(v["x"], color=v.get("color", PALETTE["limit"]), ls=v.get("ls", ":"), lw=LW["normal"], zorder=2)
        if v.get("label"):
            ax.annotate(v["label"], (v["x"], ax.get_ylim()[1]), xytext=(3, -3), textcoords="offset points", fontsize=7.2, color=v.get("color", PALETTE["limit"]), fontweight="bold", va="top")
    for sh in shade or []:
        ax.axvspan(sh["x0"], sh["x1"], color=sh.get("color", PALETTE["fail"]), alpha=0.08, lw=0)
        if sh.get("label"):
            ax.annotate(sh["label"], ((sh["x0"] + sh["x1"]) / 2.0, ax.get_ylim()[1]), xytext=(0, -4), textcoords="offset points", fontsize=7, color=sh.get("color", PALETTE["fail"]),
                        ha="center", va="top", fontweight="bold")
    for a in annotations or []:
        ax.annotate(a["text"], (a["x"], a["y"]), xytext=(a.get("dx", 14), a.get("dy", 14)), textcoords="offset points", fontsize=7.4, color=a.get("color", PALETTE["text"]), va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color=a.get("color", PALETTE["text"])), bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9))
    if label_right and ends:
        y0, y1 = ax.get_ylim()
        unit = 0.042 * abs(y1 - y0)
        heights = [textwrap.fill(e[2], 26).count("\n") + 1 for e in ends]
        ys = _spread_labels([e[1] for e in ends], unit, heights)
        xr = ax.get_xlim()[1]
        for (x, y, txt, col), yy in zip(ends, ys):
            ax.annotate(textwrap.fill(txt, 26), (x, y), xytext=(xr + 0.015 * (xr - ax.get_xlim()[0]), yy), textcoords="data", fontsize=7.6, color=col, fontweight="bold", va="center", annotation_clip=False,
                        arrowprops=dict(arrowstyle="-", lw=0.5, color=col, shrinkA=0, shrinkB=2))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, loc="left")
    fig.subplots_adjust(left=0.1, right=0.78 if label_right else 0.96, bottom=0.13, top=0.9 if title else 0.96)
    return fig


def grouped_bar_chart(categories: Sequence[str], groups: Dict[str, Sequence[Optional[float]]], ylabel: str, title: str = "", value_fmt: str = "{:.0f}", colors: Optional[Sequence[str]] = None,
                      hline: Optional[Dict[str, Any]] = None, size: Tuple[float, float] = (7.4, 4.4), note: Optional[Dict[str, str]] = None) -> plt.Figure:
    """Grouped vertical bars with value labels; ``None`` values are drawn as hatched ``n/a`` markers. ``note`` adds a small text below a category."""
    fig, ax = plt.subplots(figsize=size)
    n = len(groups)
    w = 0.8 / n
    x = np.arange(len(categories))
    cols = list(colors or CATEGORICAL)
    top = 0.0
    for gi, (g, vals) in enumerate(groups.items()):
        for ci, v in enumerate(vals):
            xx = x[ci] - 0.4 + w * (gi + 0.5)
            if v is None:
                ax.text(xx, 0.02 * (top if top > 0 else 1.0), "n/a", ha="center", va="bottom", fontsize=7, color=PALETTE["muted"])
                continue
            ax.bar(xx, v, w * 0.92, color=cols[gi % len(cols)], zorder=3)
            ax.text(xx, v, value_fmt.format(v), ha="center", va="bottom", fontsize=7, color=PALETTE["text"])
            top = max(top, v)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=8)
    ax.set_ylim(0, top * 1.22 if top > 0 else 1)
    if hline:
        if hline.get("align") == "margin":
            ax.set_xlim(ax.get_xlim()[0], ax.get_xlim()[1] + 0.9)
        ax.axhline(hline["y"], color=hline.get("color", PALETTE["limit"]), ls="--", lw=LW["normal"], zorder=4)
        if hline.get("align") == "margin":
            ax.annotate(hline["label"], (ax.get_xlim()[1], hline["y"]), xytext=(-4, 4), textcoords="offset points", ha="right", va="bottom", fontsize=7.4, color=hline.get("color", PALETTE["limit"]),
                        fontweight="bold", zorder=6)
        else:
            ax.annotate(hline["label"], (ax.get_xlim()[0], hline["y"]), xytext=(6, 4), textcoords="offset points", ha="left", fontsize=7.4, color=hline.get("color", PALETTE["limit"]), fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9), zorder=6)
    if n > 1:
        handles = [plt.Rectangle((0, 0), 1, 1, color=cols[i % len(cols)]) for i in range(n)]
        ax.legend(handles, list(groups), loc="upper right", ncol=min(n, 3), fontsize=7.5, frameon=False)
    for k, t in (note or {}).items():
        ax.text(categories.index(k), ax.get_ylim()[1] * 0.93, t, ha="center", va="top", fontsize=7, color=PALETTE["muted"], style="italic")
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title, loc="left")
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    fig.subplots_adjust(left=0.1, right=0.97, bottom=0.14, top=0.9 if title else 0.96)
    return fig


def hbar_grouped_chart(categories: Sequence[str], groups: Dict[str, Sequence[Optional[float]]], xlabel: str, title: str = "", value_fmt: str = "{:.2f}", colors: Optional[Sequence[str]] = None,
                       limit: Optional[Dict[str, Any]] = None, size: Tuple[float, float] = (8.0, 4.8), wrap: int = 34) -> plt.Figure:
    """Horizontal grouped bars with wrapped category labels (best for long load-case names). ``None`` values are skipped; ``limit`` draws a vertical limit line ``{"x", "label"}``."""
    fig, ax = plt.subplots(figsize=size)
    n = len(groups)
    h = 0.8 / n
    y = np.arange(len(categories))
    cols = list(colors or CATEGORICAL)
    xmax = 0.0
    for gi, (g, vals) in enumerate(groups.items()):
        for ci, v in enumerate(vals):
            if v is None:
                continue
            yy = y[ci] - 0.4 + h * (gi + 0.5)
            ax.barh(yy, v, h * 0.9, color=cols[gi % len(cols)], zorder=3, label=g if ci == 0 else None)
            ax.text(v, yy, " " + value_fmt.format(v), ha="left", va="center", fontsize=7, color=PALETTE["text"])
            xmax = max(xmax, v)
    ax.set_yticks(y)
    ax.set_yticklabels(["\n".join(textwrap.wrap(c, wrap)) for c in categories], fontsize=7.4)
    ax.invert_yaxis()
    ax.set_xlim(0, max(xmax, (limit or {}).get("x", 0.0)) * 1.18 if xmax > 0 else 1)
    if limit:
        ax.axvline(limit["x"], color=PALETTE["limit"], ls="--", lw=LW["normal"], zorder=4)
        ax.text(limit["x"] + 0.01 * ax.get_xlim()[1], -0.55, limit["label"], ha="left", va="bottom", fontsize=7.4, color=PALETTE["limit"], fontweight="bold")
    if n > 1:
        ax.legend(loc="lower right", fontsize=7.5, frameon=False)
    ax.set_xlabel(xlabel)
    if title:
        ax.set_title(title, loc="left", pad=16)
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    fig.tight_layout()
    return fig


def pressure_window_chart(pore: Dict[str, Sequence[Tuple[float, float]]], frac: Dict[str, Sequence[Tuple[float, float]]], strings: Sequence[Dict[str, Any]],
                          points: Optional[Sequence[Dict[str, Any]]] = None, td_m: Optional[float] = None, title: str = "Pressure window (equivalent mud weight)",
                          mud_floor_ceiling: Optional[Dict[str, Sequence[Tuple[float, float]]]] = None, size: Tuple[float, float] = (6.2, 7.6),
                          xlim: Tuple[float, float] = (0.9, 2.15)) -> plt.Figure:
    """Pore and fracture curves (low/base/high), planned mud weights per hole section, casing shoes and offset measurements against TVD.

    Args:
        pore: ``{"low"|"base"|"high": [(tvd_m, sg), ...]}``.
        frac: same for the fracture / leak-off gradient.
        strings: ``[{"name", "top_m", "shoe_m", "mud_sg", "fit_sg"(optional)}]`` hole sections; mud drawn as a step, FIT as a marker at the shoe.
        points: ``[{"tvd_m", "sg", "kind", "label"(optional)}]`` measurements; kinds ``FIT``, ``LOT``, ``pore_test``, ``pore_record`` get fixed markers.
        mud_floor_ceiling: optional ``{"min": [...], "max": [...]}`` operating window curves from the design check.
    """
    fig, ax = plt.subplots(figsize=size)
    zmax = td_m or max(max(z for z, _ in c) for c in pore.values())
    for name, curve in pore.items():
        z, s = zip(*curve)
        ax.plot(s, z, color=PALETTE["pressure"], lw=LW["thick"] if name == "base" else LW["normal"], ls="-" if name == "base" else "--", zorder=3)
    zl, sl = zip(*pore["low"])
    zh, sh = zip(*pore["high"])
    zz = np.linspace(min(zl), max(zl), 200)
    ax.fill_betweenx(zz, np.interp(zz, zl, sl), np.interp(zz, zh, sh), color=PALETTE["pressure"], alpha=0.13, lw=0)
    for name, curve in frac.items():
        z, s = zip(*curve)
        ax.plot(s, z, color=PALETTE["fail"], lw=LW["thick"] if name == "base" else LW["normal"], ls="-" if name == "base" else "--", zorder=3)
    zl, sl = zip(*frac["low"])
    zh, sh = zip(*frac["high"])
    zz = np.linspace(min(zl), max(zl), 200)
    ax.fill_betweenx(zz, np.interp(zz, zl, sl), np.interp(zz, zh, sh), color=PALETTE["fail"], alpha=0.10, lw=0)
    if mud_floor_ceiling:
        for k, col in (("min", PALETTE["pressure"]), ("max", PALETTE["fail"])):
            if mud_floor_ceiling.get(k):
                z, s = zip(*mud_floor_ceiling[k])
                ax.plot(s, z, color=col, lw=LW["thin"], ls=":")
    for st in strings:
        ax.plot([st["mud_sg"]] * 2, [st["top_m"], st["shoe_m"]], color=PALETTE["gas"], lw=3.2, solid_capstyle="butt", zorder=4)
        ax.plot([1.0, 2.15], [st["shoe_m"]] * 2, color=PALETTE["steel"], lw=0.5, ls=":", zorder=1)
        if st.get("fit_sg"):
            ax.scatter([st["fit_sg"]], [st["shoe_m"]], marker="v", s=46, color=PALETTE["steel"], zorder=5)
        ax.annotate("{}  {:.2f} sg".format(st["name"], st["mud_sg"]), (st["mud_sg"], (st["top_m"] + st["shoe_m"]) / 2.0), xytext=(6, 0), textcoords="offset points", fontsize=7.2,
                    color="#8A5A00", fontweight="bold", va="center", bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85), zorder=6)
    marks = {"FIT": ("^", PALETTE["fail"]), "LOT": ("s", PALETTE["fail"]), "pore_test": ("o", PALETTE["pressure"]), "pore_record": ("o", "#7FB3D5")}
    seen = set()
    for p in points or []:
        mk, col = marks.get(p.get("kind", ""), ("o", PALETTE["muted"]))
        ax.scatter([p["sg"]], [p["tvd_m"]], marker=mk, s=22, color=col, ec="white", lw=0.4, zorder=5, alpha=0.9)
        seen.add(p.get("kind", ""))
    txt = {"FIT": "offset FIT", "LOT": "offset LOT", "pore_test": "offset formation-pressure test", "pore_record": "offset pore-pressure record"}
    handles, hl = [], []
    for k in ("pore_record", "pore_test", "FIT", "LOT"):
        if k in seen:
            handles.append(plt.Line2D([], [], marker=marks[k][0], ls="", color=marks[k][1], ms=6))
            hl.append(txt[k])
    handles += [plt.Line2D([], [], color=PALETTE["gas"], lw=3), plt.Line2D([], [], marker="v", ls="", color=PALETTE["steel"], ms=7)]
    hl += ["planned mud weight", "planned FIT at shoe"]
    fig.legend(handles, hl, loc="lower center", ncol=3, fontsize=7.2, frameon=False)
    ax.set_ylim(zmax * 1.02, 300)
    ax.set_xlim(*xlim)
    ax.set_xlabel("Equivalent mud weight [sg]")
    ax.set_ylabel("True vertical depth below RKB [m]")
    ax.annotate("fracture / leak-off\n(low-base-high)", (xlim[1] - 0.02, 1150), ha="right", fontsize=7.5, color=PALETTE["fail"], fontweight="bold")
    ax.annotate("pore pressure\n(low-base-high)", (xlim[0] + 0.02, zmax * 0.80), ha="left", fontsize=7.5, color=PALETTE["pressure"], fontweight="bold")
    ax.set_title(title, loc="left")
    fig.subplots_adjust(left=0.13, right=0.97, bottom=0.13, top=0.94)
    return fig


def percentile_chart(samples: Dict[str, Sequence[float]], xlabel: str, title: str = "", size: Tuple[float, float] = (7.2, 3.8), bins: int = 40, ncols: Optional[int] = None) -> plt.Figure:
    """Histogram per sample set with P10/P50/P90 lines (low value = P10) and direct value labels, one panel per set."""
    n = len(samples)
    nc = ncols or n
    nr = int(np.ceil(n / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(size[0], size[1] * nr), squeeze=False)
    flat = axs.ravel()
    for ax, (name, v) in zip(flat, samples.items()):
        v = np.asarray(v, float)
        ax.hist(v, bins=bins, color=PALETTE["band_low_high"], ec="white", lw=0.3, zorder=2)
        p10, p50, p90 = np.percentile(v, [10, 50, 90])
        top_y = ax.get_ylim()[1]
        for p, lab, col, ha, yf in ((p10, "P10", PALETTE["pass"], "right", 0.97), (p50, "P50", PALETTE["text"], "center", 0.80), (p90, "P90", PALETTE["fail"], "left", 0.97)):
            ax.axvline(p, color=col, lw=LW["normal"], zorder=3)
            ax.annotate("{} {:.0f}".format(lab, p), (p, top_y * yf), xytext=(-3 if ha == "right" else (3 if ha == "left" else 0), 0), textcoords="offset points", fontsize=7.8, color=col, fontweight="bold",
                        va="top", ha=ha, bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85))
        ax.set_xlim(max(0.0, float(np.percentile(v, 0.2)) * 0.8), float(np.percentile(v, 99.6)))
        ax.set_xlabel(name if len(samples) > 1 else xlabel)
        ax.set_ylabel("Samples")
        ax.set_yticks([])
        ax.grid(False)
    for ax in flat[n:]:
        ax.set_visible(False)
    if title:
        fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94 if title else 1))
    return fig


def casing_programme_sheet(plan: Dict[str, Any], drawing_no: str = "IWP-DWG-001", revision: str = "A", revisions: Optional[List[Tuple[str, str, str]]] = None) -> plt.Figure:
    """A3 casing-programme / well-schematic sheet for a vertical or near-vertical well without completion (exploration, appraisal, suspended well).

    ``plan`` keys: ``title``, ``project``, ``well_id``, ``status``, ``note``, ``rkb_msl_m`` (air gap), ``water_depth_m``, ``td_m``, ``strings`` (``name, od_in, hole_in, top_m, shoe_m,
    toc_m, grade, weight_ppf, mud_sg, fit_sg``), ``open_hole`` (``hole_in, top_m, mud_sg``), ``formations`` (``name, top_m``), ``pore`` and ``frac`` (``{low, base, high: [(tvd, sg)]}``),
    ``points`` (offset measurements as in :func:`pressure_window_chart`), ``bop`` (``label``), ``synthetic``. Depth is below RKB (MD = TVD).
    """
    air = float(plan.get("rkb_msl_m", 0.0))
    wd = float(plan.get("water_depth_m", 0.0))
    seabed = wd + air
    td = float(plan["td_m"])
    fig, sheet, box = a3_sheet(plan.get("title", "Casing programme"), drawing_no, revision, project=str(plan.get("project", ""))[:52], scale_text="NTS (depth-true, width exaggerated)", revisions=revisions,
                               synthetic=bool(plan.get("synthetic", False)), status=plan.get("status", "FOR REVIEW"), drawn_by=plan.get("drawn_by", "neqsim-community"),
                               content_note=plan.get("note", ""))
    ytop, ybot = -0.07 * td, td * 1.03
    ax_s = sheet_axes(fig, box, (0.0, 0.03, 0.07, 0.93))
    ax_w = sheet_axes(fig, box, (0.075, 0.03, 0.43, 0.93), sharey=ax_s)
    ax_p = sheet_axes(fig, box, (0.525, 0.03, 0.17, 0.93), sharey=ax_s)
    ax_t = sheet_axes(fig, box, (0.715, 0.03, 0.285, 0.93))
    ax_s.set_ylim(ybot, ytop)
    ax_s.set_xlim(0, 1)
    ax_s.set_xticks([])
    ax_s.grid(False)
    ax_s.set_yticks([])
    for s in ("left", "bottom", "right"):
        ax_s.spines[s].set_visible(False)
    step = 250
    ax_s.text(0.5, ytop, "TVD / MD\n[m RKB]", fontsize=7, fontweight="bold", ha="center", va="bottom")
    for z in np.arange(0, td + 1, step):
        ax_s.text(0.5, z, "{:.0f}".format(z), fontsize=7, ha="center", va="center", fontweight="bold", bbox=dict(fc="white", ec="none", pad=0.6))
    ax_w.set_xlim(-1.0, 1.6)
    ax_w.set_xticks([])
    ax_w.grid(False)
    for s in ("left", "bottom", "top", "right"):
        ax_w.spines[s].set_visible(False)
    ax_w.add_patch(Rectangle((-1.0, ytop), 2.6, seabed - ytop, fc=PALETTE["seawater"], ec="none", alpha=0.9, zorder=0))
    ax_w.plot([-1.0, 1.6], [seabed, seabed], color="#1B4F72", lw=1.5, zorder=1)
    ax_w.text(-0.98, seabed - 6, "sea  (water depth {:g} m, RKB {:g} m above MSL)".format(wd, air), fontsize=7, va="bottom", color="#1B4F72", fontweight="bold")
    ax_w.text(-0.98, ytop + 4, plan.get("bop", {}).get("label", "marine riser and BOP"), fontsize=7, va="top", color=PALETTE["text"])
    forms = list(plan.get("formations") or [])
    for k, f in enumerate(forms):
        base = forms[k + 1]["top_m"] if k + 1 < len(forms) else ybot
        col = PALETTE["reservoir"] if "reservoir" in f["name"].lower() or "tofte" in f["name"].lower() else ("#F4F4F4" if k % 2 == 0 else "#FAFAFA")
        ax_w.add_patch(Rectangle((-1.0, f["top_m"]), 2.6, base - f["top_m"], fc=col, ec="none", alpha=0.7, zorder=0))
        ax_w.plot([-1.0, 1.6], [f["top_m"]] * 2, color=PALETTE["grid"], lw=0.6, zorder=1)
    # draw strings: widest first, centred, with a fixed half width per OD
    strings = sorted(plan["strings"], key=lambda s: -s["od_in"])
    max_od = max(s["od_in"] for s in strings)
    hw = lambda od: 0.62 * (od / max_od) ** 0.6  # noqa: E731 - compressed width scale keeps the small liners readable
    labels_y: List[float] = []
    for s in strings:
        half = hw(s["od_in"])
        wall = 0.022
        top, shoe = s["top_m"], s["shoe_m"]
        hole_half = hw(s.get("hole_in", s["od_in"] * 1.2)) * 1.0 if s.get("hole_in") else half * 1.1
        hole_half = max(hole_half, half + 0.025)
        if s.get("toc_m") is not None:
            for sgn in (-1, 1):
                x0 = half if sgn > 0 else -hole_half
                ax_w.add_patch(Rectangle((x0, s["toc_m"]), hole_half - half, shoe - s["toc_m"], fc="#D0D0D0", ec="#8A8A8A", lw=0.3, hatch="////", zorder=1))
        for sgn in (-1, 1):
            ax_w.add_patch(Rectangle((sgn * half - (wall if sgn < 0 else 0), top), wall, shoe - top, fc=PALETTE["steel"], ec="black", lw=0.4, zorder=3))
        ax_w.add_patch(Polygon([[half, shoe], [half + 0.06, shoe], [half, shoe - 14]], closed=True, fc="black", zorder=4))
        ax_w.add_patch(Polygon([[-half, shoe], [-half - 0.06, shoe], [-half, shoe - 14]], closed=True, fc="black", zorder=4))
        lab = '{} {}  {}{}'.format(_fmt_od(s["od_in"]), s.get("name", ""), s.get("grade", ""), " {:g} ppf".format(s["weight_ppf"]) if s.get("weight_ppf") else "")
        ytxt = shoe - 8
        for _ in range(8):
            if all(abs(ytxt - y) > 45 for y in labels_y):
                break
            ytxt += 48
        labels_y.append(ytxt)
        ax_w.annotate("{}\nshoe {:g} m{}".format(lab, shoe, "  (top {:g} m)".format(top) if top > seabed + 5 else ""), (half + 0.06, shoe - 6), xytext=(0.70, ytxt), textcoords="data", fontsize=7.2,
                      va="center", ha="left", arrowprops=dict(arrowstyle="-", lw=0.5, color=PALETTE["muted"]), bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9), zorder=7)
    oh = plan.get("open_hole")
    if oh:
        half = hw(oh.get("hole_in", 8.5)) * 0.9
        ax_w.add_patch(Rectangle((-half, oh["top_m"]), 2 * half, td - oh["top_m"], fc="#FFFFFF", ec=PALETTE["steel"], lw=1.0, ls="--", zorder=2, alpha=0.9))
        ax_w.annotate('{} open hole to TD {:g} m'.format(_fmt_od(oh.get("hole_in", 8.5)), td), (half, (oh["top_m"] + td) / 2.0), xytext=(0.70, (oh["top_m"] + td) / 2.0), fontsize=7.4, va="center", fontweight="bold",
                      arrowprops=dict(arrowstyle="-", lw=0.5, color=PALETTE["muted"]), bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))
    ax_w.plot([-0.6, 0.6], [td, td], color="black", lw=1.6, zorder=5)
    for f in forms:
        ax_w.text(-0.98, f["top_m"] + 6, "{}  {:g} m".format(f["name"], f["top_m"]), fontsize=6.6, va="top", ha="left", color=PALETTE["text"], zorder=6)
    ax_p.set_xlim(0.9, 2.15)
    ax_p.set_xlabel("EMW [sg]", fontsize=7.5)
    ax_p.set_title("Pressure window", fontsize=8.5, fontweight="bold")
    for name, curve in (plan.get("pore") or {}).items():
        z, s = zip(*curve)
        ax_p.plot(s, z, color=PALETTE["pressure"], lw=1.6 if name == "base" else 0.9, ls="-" if name == "base" else "--")
    for name, curve in (plan.get("frac") or {}).items():
        z, s = zip(*curve)
        ax_p.plot(s, z, color=PALETTE["fail"], lw=1.6 if name == "base" else 0.9, ls="-" if name == "base" else "--")
    for st in plan["strings"] + ([dict(oh, shoe_m=td, name="OH")] if oh else []):
        if st.get("mud_sg"):
            top = st.get("top_m", 0.0)
            ax_p.plot([st["mud_sg"]] * 2, [top, st["shoe_m"]], color=PALETTE["gas"], lw=3.0, solid_capstyle="butt")
        if st.get("fit_sg"):
            ax_p.scatter([st["fit_sg"]], [st["shoe_m"]], marker="v", s=30, color=PALETTE["steel"], zorder=5)
    for p in plan.get("points") or []:
        ax_p.scatter([p["sg"]], [p["tvd_m"]], marker="o", s=9, color=PALETTE["muted"], alpha=0.7)
    ax_p.annotate("pore", (1.0, td * 0.82), fontsize=7, color=PALETTE["pressure"], fontweight="bold")
    ax_p.annotate("fracture", (1.76, td * 0.30), fontsize=7, color=PALETTE["fail"], fontweight="bold")
    ax_p.annotate("mud", (1.62, td * 0.55), fontsize=7, color="#8A5A00", fontweight="bold")
    ax_p.tick_params(labelsize=7)
    plt.setp(ax_p.get_yticklabels(), visible=False)
    # section table
    ax_t.axis("off")
    ax_t.set_xlim(0, 1)
    ax_t.set_ylim(0, 1)
    ax_t.text(0, 0.99, "HOLE SECTIONS AND CASING", fontsize=8.5, fontweight="bold", va="top")
    hdr = ["Section", "Hole", "Casing / liner", "Top-shoe [m]", "Mud [sg]", "FIT [sg]"]
    xs = [0.0, 0.17, 0.30, 0.56, 0.78, 0.9]
    y = 0.945
    for xk, h in zip(xs, hdr):
        ax_t.text(xk, y, h, fontsize=6.8, fontweight="bold", va="top", color=PALETTE["muted"])
    ax_t.plot([0, 1], [y - 0.017, y - 0.017], color=PALETTE["text"], lw=0.6)
    rows = []
    for s in sorted(plan["strings"], key=lambda t: t["shoe_m"]):
        rows.append((s.get("section", s.get("name", "")), _fmt_od(s.get("hole_in", 0)) if s.get("hole_in") else "-", "{} {}".format(_fmt_od(s["od_in"]), s.get("grade", "")),
                     "{:g} - {:g}".format(s["top_m"], s["shoe_m"]), "{:.2f}".format(s["mud_sg"]) if s.get("mud_sg") else "-", "{:.2f}".format(s["fit_sg"]) if s.get("fit_sg") else "-"))
    if oh:
        rows.append(("Reservoir", _fmt_od(oh.get("hole_in", 8.5)), "open hole", "{:g} - {:g}".format(oh["top_m"], td), "{:.2f}".format(oh["mud_sg"]) if oh.get("mud_sg") else "-", "-"))
    y -= 0.04
    for r in rows:
        for xk, c in zip(xs, r):
            ax_t.text(xk, y, c, fontsize=6.8, va="top")
        y -= 0.034
    y -= 0.02
    ax_t.text(0, y, "KEY", fontsize=8.5, fontweight="bold", va="top")
    y -= 0.04
    for lab, col, kind in (("casing / liner steel", PALETTE["steel"], "r"), ("cement (hatched)", "#D0D0D0", "r"), ("planned mud weight", PALETTE["gas"], "l"), ("pore pressure low-base-high", PALETTE["pressure"], "l"),
                           ("fracture / leak-off low-base-high", PALETTE["fail"], "l"), ("planned FIT (shoe)", PALETTE["steel"], "m")):
        if kind == "r":
            ax_t.add_patch(Rectangle((0, y - 0.011), 0.05, 0.022, fc=col, ec="black", lw=0.3))
        elif kind == "l":
            ax_t.plot([0, 0.05], [y, y], color=col, lw=2.4)
        else:
            ax_t.scatter([0.025], [y], marker="v", s=24, color=col)
        ax_t.text(0.08, y, lab, fontsize=7, va="center")
        y -= 0.033
    for i, line in enumerate(plan.get("notes", [])[:8]):
        pass
    y -= 0.02
    ax_t.text(0, y, "NOTES", fontsize=8.5, fontweight="bold", va="top")
    y -= 0.04
    import textwrap

    for line in plan.get("notes", [])[:8]:
        for k, part in enumerate(textwrap.wrap(line, 62)):
            ax_t.text(0, y, ("- " if k == 0 else "  ") + part, fontsize=6.6, va="top", color=PALETTE["muted"])
            y -= 0.026
        y -= 0.006
    return fig


def _fmt_od(od: float) -> str:
    whole = int(od)
    frac = round(od - whole, 3)
    names = {0.5: "1/2", 0.25: "1/4", 0.75: "3/4", 0.625: "5/8", 0.875: "7/8", 0.375: "3/8", 0.125: "1/8"}
    return '{} {}"'.format(whole, names[frac]) if frac in names else '{:g}"'.format(od)


def offset_map_chart(planned: Dict[str, Any], offsets: Sequence[Dict[str, Any]], paths: Optional[Sequence[Dict[str, Any]]] = None, infrastructure: Optional[Sequence[Dict[str, Any]]] = None,
                     radius_m: float = 9000.0, title: str = "Location and offset wells", size: Tuple[float, float] = (7.2, 6.2)) -> plt.Figure:
    """Plan view around the planned well (origin) with offset wells, distance rings, optional well paths and infrastructure polylines.

    ``planned``: ``{"label"}``; ``offsets``: ``[{"label", "de_m", "dn_m", "kind"(optional: dry, oil, gas, other), "td_m"(optional)}]``; ``paths``: ``[{"label", "east", "north", "color"}]``;
    ``infrastructure``: ``[{"label", "east", "north", "color", "ls"}]`` coordinates relative to the planned well.
    """
    fig, ax = plt.subplots(figsize=size)
    for r in (2000, 5000, 8000):
        if r <= radius_m * 1.05:
            ax.add_patch(plt.Circle((0, 0), r, fill=False, ec=PALETTE["grid"], lw=0.8, ls="--", zorder=1))
            ax.annotate("{:g} km".format(r / 1000.0), (r * 0.707, r * 0.707), fontsize=6.8, color=PALETTE["muted"], ha="left", va="bottom")
    for inf in infrastructure or []:
        ax.plot(inf["east"], inf["north"], color=inf.get("color", PALETTE["muted"]), ls=inf.get("ls", "-"), lw=1.4, zorder=2)
        if inf.get("label"):
            ax.annotate(inf["label"], (inf["east"][-1], inf["north"][-1]), xytext=(4, 4), textcoords="offset points", fontsize=7, color=inf.get("color", PALETTE["muted"]), fontweight="bold")
    for p in paths or []:
        ax.plot(p["east"], p["north"], color=p.get("color", PALETTE["accent1"]), lw=2.0, zorder=4)
        if p.get("label"):
            ax.annotate(p["label"], (p["east"][-1], p["north"][-1]), xytext=(6, 6), textcoords="offset points", fontsize=7.4, fontweight="bold", color=p.get("color", PALETTE["accent1"]), zorder=8)
    kinds = {"gas": (PALETTE["gas"], "gas / condensate"), "oil": (PALETTE["oil"], "oil"), "dry": (PALETTE["muted"], "dry / other")}
    placed: List[Tuple[float, float]] = []
    for o in offsets:
        col = kinds.get(o.get("kind", "dry"), kinds["dry"])[0]
        ax.scatter([o["de_m"]], [o["dn_m"]], s=34, color=col, ec="white", lw=0.6, zorder=5)
        dx, dy = 5, 4
        for (px, py) in placed:
            if abs(px - o["de_m"]) < 900 and abs(py - o["dn_m"]) < 500:
                dy -= 11
        placed.append((o["de_m"], o["dn_m"]))
        ax.annotate(o["label"], (o["de_m"], o["dn_m"]), xytext=(dx, dy), textcoords="offset points", fontsize=6.8, color=PALETTE["text"], zorder=6)
    ax.scatter([0], [0], marker="*", s=190, color=PALETTE["fail"], ec="white", lw=0.8, zorder=7)
    ax.annotate(planned.get("label", "planned well"), (0, 0), xytext=(8, -14), textcoords="offset points", fontsize=8, fontweight="bold", color=PALETTE["fail"], zorder=8)
    ax.set_xlim(-radius_m, radius_m)
    ax.set_ylim(-radius_m, radius_m)
    ax.set_aspect("equal")
    ax.set_xlabel("East of planned well [m]")
    ax.set_ylabel("North of planned well [m]")
    ax.set_title(title, loc="left")
    handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=l) for c, l in kinds.values()]
    ax.legend(handles=handles, loc="lower right", fontsize=7, frameon=True, framealpha=0.9)
    fig.tight_layout()
    return fig
