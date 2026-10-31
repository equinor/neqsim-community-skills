"""Chart library of the integrated well planning design system (all charts render from plain dictionaries).

Every function returns a matplotlib Figure that follows ``iwp_style``: semantic colours, direct labelling, shaded
low/base/high bands. Use :func:`render` to save a chart with its provenance sidecar. Nothing here calculates engineering
values - charts only draw results produced by the model chain.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from .iwp_style import (CATEGORICAL, LW, PALETTE, STATUS_COLOR, badge, band, direct_label, provenance_record, save_figure, small_multiples, status_color)

REGIME_COLORS = {"SINGLE_PHASE_LIQUID": "#9ECAE1", "SINGLE_PHASE_GAS": "#FDD0A2", "BUBBLE": "#C6DBEF", "SLUG": "#F2B134", "CHURN": "#E08E45", "ANNULAR": "#E7B7D6"}


def _depth_axis(ax, depth_max: float, label: bool = True) -> None:
    ax.set_ylim(depth_max, 0)
    ax.grid(True, axis="both")
    if label:
        ax.set_ylabel("TVD below tree [m]")


# ----------------------------------------------------------------------------- nodal
def nodal_chart(family: Dict[str, Any], ops: Optional[Dict[str, Dict[str, Any]]] = None, target_rate: Optional[float] = None, rate_label: str = "Rate [Sm3/d]",
                title: str = "Nodal analysis", ipr_band: Optional[Dict[str, Sequence[float]]] = None, outflow_min_rate: Optional[float] = None,
                rate_scale: float = 1.0, vlp_labels: Optional[Dict[str, str]] = None, points: Optional[Sequence[Dict[str, Any]]] = None,
                ymax: Optional[float] = None) -> plt.Figure:
    """IPR versus a family of VLP curves with operating points, stable/unstable regions and the target rate.

    Args:
        family: ``{"q": [...], "ipr_pwf": [...], "families": {key: [bhp...]}, "parameter": name}``.
        ops: optional ``{"low"|"base"|"high": {"q_op", "bhp_op"}}`` operating points (base drawn as a ring, low/high as triangles).
        rate_scale: divide rates by this number for display (for example ``1e6`` with a label in MSm3/d) so no axis offset text is needed.
        vlp_labels: optional ``{key: label}`` direct labels for the VLP curves.
        points: extra annotated points ``[{"q", "bhp", "label", "color"}]`` (for example operating points at several depletion states).
        ymax: upper limit of the pressure axis.
    """
    fig, ax = plt.subplots(figsize=(7.6, 4.9))
    s = float(rate_scale)
    q = np.asarray(family["q"], float) / s
    ipr = np.asarray(family["ipr_pwf"], float)
    if ipr_band:
        band(ax, q, np.asarray(ipr_band["low"]), np.asarray(ipr_band["high"]), PALETTE["band_low_high"], 0.35)
    ax.plot(q, ipr, color=PALETTE["pressure"], lw=LW["thick"], zorder=3)
    labels = list(family["families"].keys())
    cols = [PALETTE["temperature"], PALETTE["accent2"], PALETTE["accent3"], PALETTE["accent4"], PALETTE["accent5"]]
    param = family.get("parameter", "VLP")
    top = float(ymax) if ymax else float(np.nanmax(ipr)) * 1.45
    ax.set_ylim(0, top)
    ends = []
    for i, k in enumerate(labels):
        v = np.asarray(family["families"][k], float)
        ax.plot(q, v, color=cols[i % len(cols)], lw=LW["normal"], ls="-" if i == 0 else "--", zorder=3)
        txt = (vlp_labels or {}).get(k) or ("VLP, tubing ID {:.0f} mm".format(float(k) * 1000.0) if param == "tubing_id_m" else "VLP, {} = {}".format(param, k))
        inside = v <= top
        j = int(np.where(inside)[0][-1]) if inside.any() else len(v) - 1
        ends.append((float(v[j]), j, txt, cols[i % len(cols)]))
    placed: List[float] = []
    for y, j, txt, col in sorted(ends):
        yy = y
        for p in placed:
            if abs(yy - p) < 0.045 * top:
                yy = p + 0.045 * top
        placed.append(yy)
        ax.annotate(txt, (q[j], y), xytext=(q[-1] + 0.02 * (q[-1] - q[0]), yy), textcoords="data", fontsize=7.5, color=col, fontweight="bold", va="center", annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", lw=0.5, color=col, shrinkA=0, shrinkB=2))
    i0 = int(0.18 * (len(q) - 1))
    direct_label(ax, q[i0], ipr[i0], "IPR (reservoir inflow)", PALETTE["pressure"], dx=4, dy=10, bbox=True)
    if ops and ops.get("base") and ops["base"].get("bhp_op") is not None:
        o = ops["base"]
        ax.scatter([o["q_op"] / s], [o["bhp_op"]], s=70, color="white", ec=PALETTE["text"], lw=1.5, zorder=5)
        direct_label(ax, o["q_op"] / s, o["bhp_op"], "Operating point\n{:.2f} at {:.0f} bara".format(o["q_op"] / s, o["bhp_op"]), PALETTE["text"], dx=10, dy=-22, bbox=True)
        for c, mk in (("low", "v"), ("high", "^")):
            oc = ops.get(c)
            if oc and oc.get("bhp_op") is not None:
                ax.scatter([oc["q_op"] / s], [oc["bhp_op"]], s=28, marker=mk, color=PALETTE["muted"], zorder=4)
    for pt in points or []:
        ax.scatter([pt["q"] / s], [pt["bhp"]], s=55, color="white", ec=pt.get("color", PALETTE["text"]), lw=1.6, zorder=6)
        direct_label(ax, pt["q"] / s, pt["bhp"], pt["label"], pt.get("color", PALETTE["text"]), dx=7, dy=pt.get("dy", 9), size=7.2, bbox=True)
    if outflow_min_rate:
        ax.axvspan(q[0], outflow_min_rate / s, color=PALETTE["fail"], alpha=0.07, lw=0)
        ax.axvline(outflow_min_rate / s, color=PALETTE["fail"], ls=":", lw=LW["thin"])
        direct_label(ax, outflow_min_rate / s, top, "unstable / loading branch\n(left of VLP minimum)", PALETTE["fail"], dx=4, dy=-16, ha="left", size=7)
    if target_rate:
        ax.axvline(target_rate / s, color=PALETTE["limit"], ls="--", lw=LW["thin"])
        direct_label(ax, target_rate / s, top, "target", PALETTE["limit"], dx=3, dy=-8, size=7.5)
    ax.set_xlim(max(0.0, q[0] - 0.02 * (q[-1] - q[0])), q[-1])
    ax.set_xlabel(rate_label)
    ax.set_ylabel("Flowing bottom-hole pressure [bara]")
    ax.set_title(title, loc="left")
    fig.subplots_adjust(right=0.76, left=0.09, bottom=0.12, top=0.92)
    return fig


def wellbore_profiles(profile: Dict[str, Any], hydrate: Optional[Dict[str, Any]] = None, c_factor: float = 100.0, title: str = "Wellbore profiles (base case)") -> plt.Figure:
    """Aligned depth tracks (pressure, temperature with hydrate line, holdup, velocities with erosional limit, regime strip) sharing one depth axis."""
    zn = np.asarray(profile["node_tvd_m"], float)
    zm = np.asarray(profile["tvd_m"], float)
    fig, axs = plt.subplots(1, 5, figsize=(11.0, 5.6), sharey=True, gridspec_kw={"width_ratios": [1, 1, 0.8, 1, 0.22], "wspace": 0.08})
    dmax = float(zn[-1])
    ax = axs[0]
    ax.plot(profile["pressure_bara"], zn, color=PALETTE["pressure"], lw=LW["thick"])
    pp = np.asarray(profile["pressure_bara"], float)
    direct_label(ax, pp[0], zn[0], "tree {:.0f} bara".format(pp[0]), PALETTE["pressure"], dx=8, dy=-10, size=7.5)
    direct_label(ax, pp[-1], zn[-1], "bottom {:.0f} bara".format(pp[-1]), PALETTE["pressure"], dx=-8, dy=12, ha="right", size=7.5)
    ax.set_xlabel("Pressure [bara]")
    ax.set_title("Pressure", fontsize=9)
    _depth_axis(ax, dmax)
    ax = axs[1]
    t = np.asarray(profile["temperature_C"], float)
    ax.plot(t, zm, color=PALETTE["temperature"], lw=LW["thick"])
    direct_label(ax, t[len(t) // 2], zm[len(t) // 2], "flowing T", PALETTE["temperature"], dx=-6, dy=0, ha="right")
    if hydrate and hydrate.get("hydrate_T_C"):
        hz, ht = np.asarray(hydrate["tvd_m"], float), np.asarray(hydrate["hydrate_T_C"], float)
        ax.plot(ht, hz, color=PALETTE["hydrate"], lw=LW["normal"], ls="--")
        ax.fill_betweenx(hz, ht, np.interp(hz, zm, t), where=np.interp(hz, zm, t) < ht, color=PALETTE["fail"], alpha=0.25, lw=0)
        j_lab = int(len(hz) * 0.18)
        direct_label(ax, ht[j_lab], hz[j_lab], "hydrate T (CPA)", PALETTE["hydrate"], dx=6, dy=0, size=7.5)
    ax.set_xlabel("Temperature [C]")
    ax.set_title("Temperature", fontsize=9)
    _depth_axis(ax, dmax, label=False)
    ax = axs[2]
    hl = np.asarray(profile["liquid_holdup"], float)
    ax.plot(hl, zm, color=PALETTE["oil"], lw=LW["thick"])
    ax.fill_betweenx(zm, 0, hl, color=PALETTE["oil"], alpha=0.12, lw=0)
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Liquid holdup [-]")
    ax.set_title("Holdup", fontsize=9)
    _depth_axis(ax, dmax, label=False)
    ax = axs[3]
    vsg, vsl = np.asarray(profile["vsg_m_s"], float), np.asarray(profile["vsl_m_s"], float)
    ax.plot(vsg, zm, color=PALETTE["gas"], lw=LW["thick"])
    ax.plot(vsl, zm, color=PALETTE["water"], lw=LW["thick"])
    rho = np.asarray(profile["mixture_density"], float)
    ve = c_factor / np.sqrt(np.maximum(rho * 0.062428, 1e-3)) * 0.3048
    ax.plot(ve, zm, color=PALETTE["limit"], lw=LW["normal"], ls="--")
    ax.fill_betweenx(zm, ve, np.maximum(vsg + vsl, ve), where=(vsg + vsl) > ve, color=PALETTE["fail"], alpha=0.22, lw=0)
    direct_label(ax, vsg[len(vsg) // 2], zm[len(vsg) // 2], "gas", PALETTE["gas"], dx=4, dy=-6)
    direct_label(ax, vsl[len(vsl) // 3], zm[len(vsl) // 3], "liquid", PALETTE["water"], dx=4, dy=-6)
    direct_label(ax, ve[0], zm[0], "erosional (API RP 14E, C={:g})".format(c_factor), PALETTE["limit"], dx=-4, dy=-10, ha="right", size=7)
    ax.set_xlabel("Superficial velocity [m/s]")
    ax.set_title("Velocities", fontsize=9)
    _depth_axis(ax, dmax, label=False)
    ax = axs[4]
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.grid(False)
    dz = np.diff(zn)
    for z0, h, reg in zip(zn[:-1], dz, profile.get("regime", [])):
        ax.add_patch(Rectangle((0, z0), 1, h, fc=REGIME_COLORS.get(reg, "#EEEEEE"), ec="white", lw=0.4))
    prev = None
    for z0, h, reg in zip(zn[:-1], dz, profile.get("regime", [])):
        if reg != prev:
            ax.text(0.5, z0 + h / 2, reg.replace("SINGLE_PHASE_", "1ph ").title().replace("1Ph", "1ph"), rotation=90, ha="center", va="center", fontsize=5.8, color=PALETTE["text"])
        prev = reg
    ax.set_title("Regime", fontsize=9)
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", fontsize=11)
    fig.subplots_adjust(top=0.86, left=0.07, right=0.985, bottom=0.12)
    return fig


# ----------------------------------------------------------------------------- operating envelope
def operating_envelope_chart(rows: List[Dict[str, Any]], title: str = "Operating envelope: utilisation of limits") -> plt.Figure:
    """Limit bars with utilisation markers and traffic-light status text; hatched when the limit is not approved."""
    rows = [r for r in rows if r.get("utilisation") is not None]
    n = max(len(rows), 1)
    fig, ax = plt.subplots(figsize=(8.8, 0.46 * n + 1.8))
    for i, r in enumerate(rows):
        y = n - 1 - i
        u = float(r["utilisation"])
        col = status_color(r.get("indicative_status", "NOT_ASSESSED"))
        ax.add_patch(Rectangle((0, y - 0.28), 1.0, 0.56, fc="#F2F2F2", ec=PALETTE["limit"], lw=LW["thin"]))
        ax.add_patch(Rectangle((0, y - 0.28), min(u, 1.35), 0.56, fc=col, ec="none", alpha=0.85, hatch="///" if r["status"] == "NEEDS_REVIEW" else None))
        cond = r["condition"]
        cond = cond if len(cond) <= 44 else cond[:42].rstrip() + "..."
        ax.text(-0.02, y, "{}\n{}".format(r["parameter"].replace("_", " "), cond), ha="right", va="center", fontsize=7.6, linespacing=1.15)
        ax.text(1.42, y, r["status"].replace("_", " ") + ("\n[indicative {}]".format(r["indicative_status"]) if r["status"] == "NEEDS_REVIEW" else ""), va="center", fontsize=7.4,
                color=PALETTE["text"], fontweight="bold", clip_on=False)
    ax.axvline(1.0, color=PALETTE["limit"], lw=LW["normal"])
    ax.text(1.0, n - 0.3, "limit = 1.0", ha="center", va="bottom", fontsize=7.5, color=PALETTE["limit"], bbox=dict(fc="white", ec="none", pad=1))
    ax.set_xlim(0, 1.4)
    ax.set_ylim(-0.7, n)
    ax.set_yticks([])
    ax.set_xlabel("Utilisation of effective limit [-]  (hatched = limit not approved)")
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", fontsize=10.5)
    ax.spines["left"].set_visible(False)
    fig.subplots_adjust(left=0.44, right=0.77, bottom=0.11, top=0.94)
    return fig


def envelope_table_figure(rows: List[Dict[str, Any]], max_rows: int = 24, title: str = "Operating-envelope table") -> plt.Figure:
    """Rendered envelope table with coloured status cells (for the report and drawing register)."""
    rows = rows[:max_rows]
    cols = ["Parameter", "Condition", "Limit", "Source (basis)", "Predicted", "Margin", "Status"]
    cell = []
    for r in rows:
        lim = "{}{}".format("min {:.3g} ".format(r["min_limit"]) if r.get("min_limit") is not None else "", "max {:.3g}".format(r["max_limit"]) if r.get("max_limit") is not None else "") or "-"
        cell.append([r["parameter"], r["condition"][:34], lim, "{} ({})".format((r.get("limit_source") or "-")[:30], r.get("limit_basis", "")),
                     "-" if r.get("predicted") is None else "{:.3g}".format(r["predicted"]), "-" if r.get("margin_to_limit") is None else "{:.3g}".format(r["margin_to_limit"]), r["status"]])
    fig, ax = plt.subplots(figsize=(11.0, 0.32 * len(rows) + 1.0))
    ax.axis("off")
    tb = ax.table(cellText=cell, colLabels=cols, loc="center", cellLoc="left", colWidths=[0.2, 0.2, 0.11, 0.24, 0.07, 0.07, 0.11])
    tb.auto_set_font_size(False)
    tb.set_fontsize(6.8)
    tb.scale(1, 1.25)
    for (i, j), c in tb.get_celld().items():
        c.set_edgecolor("#CCCCCC")
        if i == 0:
            c.set_facecolor(PALETTE["text"])
            c.set_text_props(color="white", fontweight="bold")
        elif j == 6:
            c.set_facecolor(status_color(cell[i - 1][6]))
            c.set_text_props(color="white", fontweight="bold")
    ax.set_title(title, loc="left")
    return fig


# ----------------------------------------------------------------------------- alternatives
def alternatives_scorecard(sc: Dict[str, Any], labels: Dict[str, str], title: str = "Alternatives scorecard (1 = best of those compared)", crit_labels: Optional[Dict[str, str]] = None,
                           raw_fmt: Optional[Dict[str, str]] = None, raw_sign: Optional[Dict[str, float]] = None) -> plt.Figure:
    """Heat-map of normalised criterion scores with raw values annotated and a weighted total column.

    Args:
        sc: scorecard dict (``criteria``, ``scores``, ``raw``, ``totals``).
        labels: alternative id to display label.
        title: figure title.
        crit_labels: optional criterion id to column header (use ``\\n`` for line breaks).
        raw_fmt: optional criterion id to a ``str.format`` pattern for the raw value (default ``{:.2g}``).
        raw_sign: optional criterion id to a multiplier applied to the raw value before display (for example -1 for criteria stored as negatives).
    """
    ids = list(labels)
    crit = sc["criteria"]
    data = np.full((len(ids), len(crit)), np.nan)
    for i, a in enumerate(ids):
        for j, c in enumerate(crit):
            v = sc["scores"][c].get(a)
            if v is not None:
                data[i, j] = v
    fig, ax = plt.subplots(figsize=(1.0 * len(crit) + 3.5, 0.62 * len(ids) + 1.7))
    cmap = plt.get_cmap("YlGnBu").with_extremes(bad="#EDEDED")
    im = ax.imshow(np.ma.masked_invalid(data), cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(crit)))
    ax.set_xticklabels([(crit_labels or {}).get(c, c.replace("_", "\n")) for c in crit], fontsize=7.5)
    ax.set_yticks(range(len(ids)))
    ax.set_yticklabels([labels[a] for a in ids], fontsize=8)
    ax.xaxis.tick_top()
    ax.grid(False)
    for i, a in enumerate(ids):
        for j, c in enumerate(crit):
            raw = sc["raw"][c].get(a)
            if raw is not None and (raw_sign or {}).get(c) is None and c in ("energy_demand", "cost", "uncertainty_spread", "wellhead_pressure"):
                raw = abs(raw)
            elif raw is not None:
                raw = raw * (raw_sign or {}).get(c, 1.0)
            txt = "n/a" if raw is None else (raw_fmt or {}).get(c, "{:.2g}").format(raw)
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.2, color="white" if (not np.isnan(data[i, j]) and data[i, j] > 0.6) else PALETTE["text"])
        ax.text(len(crit) - 0.35, i, "{:.2f}".format(sc["totals"][a]), ha="left", va="center", fontsize=9, fontweight="bold")
    ax.text(len(crit) - 0.35, -0.75, "weighted\ntotal", ha="left", va="center", fontsize=7.5)
    ax.set_title("")
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold", fontsize=10.5)
    fig.subplots_adjust(left=0.32, right=0.97, top=0.78, bottom=0.05)
    ax.set_xlim(-0.5, len(crit) + 0.2)
    for s in ax.spines.values():
        s.set_visible(False)
    return fig


def alternatives_radar(sc: Dict[str, Any], labels: Dict[str, str], title: str = "Alternatives radar (normalised scores)") -> plt.Figure:
    """Radar chart of criterion scores per alternative (criteria without data are skipped)."""
    crit = [c for c in sc["criteria"] if any(sc["scores"][c].get(a) is not None for a in labels)]
    ang = np.linspace(0, 2 * np.pi, len(crit), endpoint=False).tolist()
    fig = plt.figure(figsize=(6.2, 5.6))
    ax = fig.add_subplot(111, polar=True)
    for k, a in enumerate(labels):
        v = [sc["scores"][c].get(a) or 0.0 for c in crit]
        ax.plot(ang + ang[:1], v + v[:1], color=CATEGORICAL[k % 8], lw=LW["normal"])
        ax.fill(ang + ang[:1], v + v[:1], color=CATEGORICAL[k % 8], alpha=0.08)
        direct_label(ax, ang[k % len(ang)], max(v) if v else 0.5, labels[a], CATEGORICAL[k % 8], size=7, dx=0, dy=6 + 4 * k, ha="center")
    ax.set_xticks(ang)
    ax.set_xticklabels([c.replace("_", "\n") for c in crit], fontsize=7.5)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels([])
    ax.set_title(title, loc="left", pad=18)
    return fig


def pareto_chart(points: Dict[str, Tuple[float, float]], front: Sequence[str], labels: Dict[str, str], xlabel: str, ylabel: str, title: str = "Pareto view") -> plt.Figure:
    """Scatter of alternatives with the non-dominated front highlighted and directly labelled."""
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    for k, (a, (x, y)) in enumerate(points.items()):
        on = a in front
        ax.scatter([x], [y], s=70 if on else 40, color=PALETTE["accent1"] if on else PALETTE["muted"], zorder=3, ec="white")
        direct_label(ax, x, y, labels.get(a, a), PALETTE["text"], dx=7, dy=5, size=7.5)
    fp = sorted([points[a] for a in front])
    if len(fp) > 1:
        ax.plot([p[0] for p in fp], [p[1] for p in fp], color=PALETTE["accent1"], lw=LW["normal"], ls="--")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left")
    return fig


def waterfall_chart(reference_label: str, reference_value: float, steps: List[Tuple[str, float]], unit: str = "Sm3/d", title: str = "Waterfall from the reference alternative",
                    result_label: str = "result") -> plt.Figure:
    """Waterfall of incremental changes relative to a reference value (decreases red, increases green, start blue, result orange) with connectors and value labels."""
    import textwrap

    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    x = 0
    run = reference_value
    ax.bar(x, run, color=PALETTE["accent1"], width=0.6, zorder=3)
    ax.text(x, run, "{:,.4g}".format(run), ha="center", va="bottom", fontsize=8, fontweight="bold")
    names = [reference_label]
    top = run
    for name, d in steps:
        x += 1
        lo, hi = (run + d, run) if d < 0 else (run, run + d)
        ax.bar(x, hi - lo, bottom=lo, color=PALETTE["pass"] if d >= 0 else PALETTE["fail"], width=0.6, zorder=3)
        ax.plot([x - 1 + 0.3, x - 0.3], [run, run], color=PALETTE["muted"], lw=0.8, zorder=2)
        ax.text(x, hi, "{:+,.4g}".format(d), ha="center", va="bottom", fontsize=8)
        run += d
        names.append(name)
        top = max(top, hi)
    x += 1
    ax.plot([x - 1 + 0.3, x - 0.3], [run, run], color=PALETTE["muted"], lw=0.8, zorder=2)
    ax.bar(x, run, color=PALETTE["accent2"], width=0.6, zorder=3)
    ax.text(x, run, "{:,.4g}".format(run), ha="center", va="bottom", fontsize=8, fontweight="bold")
    names.append(result_label)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([textwrap.fill(n, 16) for n in names], fontsize=7.8)
    ax.set_ylim(min(0.0, run) * 1.1, top * 1.12)
    ax.set_ylabel(unit)
    ax.set_title(title, loc="left")
    ax.grid(False, axis="x")
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- sensitivities
def tornado_chart(t: Dict[str, Any], title: str = "Tornado: one-at-a-time sensitivity") -> plt.Figure:
    """Tornado chart around the reference value; bars show the metric at the low and high parameter values."""
    rows = t["rows"][::-1]
    ref = t["reference"] or 0.0
    fig, ax = plt.subplots(figsize=(7.4, 0.5 * len(rows) + 1.8))
    for i, r in enumerate(rows):
        lo, hi = r["metric_at_low_value"] or 0.0, r["metric_at_high_value"] or 0.0
        for v, col in ((lo, PALETTE["accent5"]), (hi, PALETTE["accent2"])):
            ax.barh(i, v - ref, left=ref, color=col, height=0.55, alpha=0.95)
        direct_label(ax, min(lo, hi), i, "{:.3g}".format(min(lo, hi)), PALETTE["text"], dx=-3, ha="right", size=7)
        direct_label(ax, max(lo, hi), i, "{:.3g}".format(max(lo, hi)), PALETTE["text"], dx=3, ha="left", size=7)
    ax.axvline(ref, color=PALETTE["limit"], lw=LW["normal"])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(["{}  [{:.3g} to {:.3g}]".format(r["parameter"], r["range"][0], r["range"][2]) for r in rows], fontsize=7.8)
    import textwrap

    ax.set_xlabel("\n".join(textwrap.wrap(t["metric"], 80)))
    ax.set_title(title, loc="left", pad=20)
    ax.grid(False, axis="y")
    ax.annotate("blue = parameter at the low end of its range, orange = at the high end", (1.0, 1.0), xycoords="axes fraction", xytext=(0, 4), textcoords="offset points", ha="right", va="bottom",
                fontsize=7.2, color=PALETTE["muted"])
    fig.tight_layout()
    return fig


def sensitivity_heatmap(g: Dict[str, Any], target: Optional[float] = None, title: str = "Sensitivity grid") -> plt.Figure:
    """Heat-map of a metric over two parameters; the target contour is overlaid when given."""
    z = np.asarray(g["q_op"], float)
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    im = ax.imshow(z, origin="lower", aspect="auto", cmap="viridis", extent=[0, len(g["x"]), 0, len(g["y"])])
    ax.set_xticks(np.arange(len(g["x"])) + 0.5)
    ax.set_xticklabels(["{:.3g}".format(v) for v in g["x"]], fontsize=7.5)
    ax.set_yticks(np.arange(len(g["y"])) + 0.5)
    ax.set_yticklabels(["{:.3g}".format(v) for v in g["y"]], fontsize=7.5)
    for i in range(z.shape[0]):
        for j in range(z.shape[1]):
            ax.text(j + 0.5, i + 0.5, "{:.3g}".format(z[i, j]), ha="center", va="center", fontsize=7, color="white" if z[i, j] < np.nanmean(z) else "black")
    if target is not None and z.min() < target < z.max():
        ax.contour(np.arange(z.shape[1]) + 0.5, np.arange(z.shape[0]) + 0.5, z, levels=[target], colors=[PALETTE["fail"]], linewidths=2)
    ax.set_xlabel(g["x_param"])
    ax.set_ylabel(g["y_param"])
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="operating rate")
    ax.set_title(title, loc="left")
    return fig


def profile_bands(years: Sequence[float], cases: Dict[str, Sequence[float]], target: Optional[float] = None, unit: str = "Sm3/d",
                  title: str = "Deliverability versus time (low / base / high)") -> plt.Figure:
    """Deliverability profile with a low-high band; labelled as capacity, not a production forecast."""
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    y = np.asarray(years, float)
    lo, ba, hi = (np.asarray([v if v is not None else np.nan for v in cases[k]], float) for k in ("low", "base", "high"))
    band(ax, y, lo, hi)
    ax.plot(y, ba, color=PALETTE["accent1"], lw=LW["thick"])
    direct_label(ax, y[-1], ba[-1], "base", PALETTE["accent1"], dx=5)
    direct_label(ax, y[-1], hi[-1], "high", PALETTE["muted"], dx=5, size=7.5)
    direct_label(ax, y[-1], lo[-1], "low", PALETTE["muted"], dx=5, size=7.5)
    if target:
        ax.axhline(target, color=PALETTE["limit"], ls="--", lw=LW["thin"])
        direct_label(ax, y[0], target, "target", PALETTE["limit"], dx=3, dy=6)
    ax.set_xlabel("Years from start (linear depletion basis)")
    ax.set_ylabel("Deliverability [{}]".format(unit))
    ax.set_ylim(bottom=0)
    ax.set_title(title, loc="left")
    ax.text(0.99, 0.02, "capacity at the stated back pressure - not a production forecast", transform=ax.transAxes, ha="right", fontsize=6.8, color=PALETTE["muted"])
    return fig


# ----------------------------------------------------------------------------- planning charts
def gantt_chart(tasks: List[Dict[str, Any]], title: str = "Schedule (base with low-high whiskers)") -> plt.Figure:
    """Gantt chart: tasks with ``name, start, low, base, high`` durations in days; whiskers show the duration uncertainty."""
    fig, ax = plt.subplots(figsize=(8.4, 0.42 * len(tasks) + 1.6))
    for i, t in enumerate(tasks):
        y = len(tasks) - 1 - i
        s = float(t["start"])
        ax.barh(y, t["base"], left=s, color=CATEGORICAL[i % 6], height=0.5, alpha=0.9)
        ax.plot([s + t["low"], s + t["high"]], [y, y], color=PALETTE["text"], lw=1.3)
        for v in (t["low"], t["high"]):
            ax.plot([s + v, s + v], [y - 0.16, y + 0.16], color=PALETTE["text"], lw=1.3)
        ax.text(s + t["high"] + 0.4, y, "{:.0f} d (P10-P90 {:.0f}-{:.0f})".format(t["base"], t["low"], t["high"]), va="center", fontsize=7)
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t["name"] for t in tasks][::-1], fontsize=8)
    ax.set_xlabel("Days from start")
    ax.set_title(title, loc="left")
    ax.grid(False, axis="y")
    ax.set_xlim(0, max(float(t["start"]) + float(t["high"]) for t in tasks) * 1.32)
    fig.tight_layout()
    return fig


def risk_matrix(risks: List[Dict[str, Any]], title: str = "Risk matrix (likelihood x consequence)") -> plt.Figure:
    """5x5 risk matrix with numbered risks; cell colour is a presentation convention, not an acceptance criterion."""
    fig, ax = plt.subplots(figsize=(5.6, 5.0))
    for lk in range(1, 6):
        for cq in range(1, 6):
            s = lk * cq
            col = PALETTE["pass"] if s <= 4 else PALETTE["warn"] if s <= 9 else "#E08E45" if s <= 14 else PALETTE["fail"]
            ax.add_patch(Rectangle((cq - 0.5, lk - 0.5), 1, 1, fc=col, ec="white", lw=1.5, alpha=0.75))
    cells: Dict[Tuple[int, int], List[str]] = {}
    for r in risks:
        cells.setdefault((r["likelihood"], r["consequence"]), []).append(str(r["id"]))
    for (lk, cq), ids in cells.items():
        ax.text(cq, lk, ",".join(ids), ha="center", va="center", fontsize=8, fontweight="bold", color="white" if lk * cq > 9 else PALETTE["text"])
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xlabel("Consequence (1 low - 5 high)")
    ax.set_ylabel("Likelihood (1 low - 5 high)")
    ax.grid(False)
    ax.set_title(title, loc="left")
    return fig


def risk_register_heatmap(risks: List[Dict[str, Any]], title: str = "Risk register") -> plt.Figure:
    """Register table with colour-coded score cells."""
    cell = [[str(r["id"]), r["title"][:46], str(r["likelihood"]), str(r["consequence"]), str(r["likelihood"] * r["consequence"]), r.get("mitigation", "")[:40], r.get("owner", "")] for r in risks]
    fig, ax = plt.subplots(figsize=(10.5, 0.36 * len(cell) + 1.0))
    ax.axis("off")
    tb = ax.table(cellText=cell, colLabels=["ID", "Risk", "L", "C", "Score", "Mitigation / action", "Owner"], loc="center", cellLoc="left", colWidths=[0.04, 0.3, 0.04, 0.04, 0.06, 0.38, 0.12])
    tb.auto_set_font_size(False)
    tb.set_fontsize(7)
    tb.scale(1, 1.3)
    for (i, j), c in tb.get_celld().items():
        c.set_edgecolor("#CCCCCC")
        if i == 0:
            c.set_facecolor(PALETTE["text"])
            c.set_text_props(color="white", fontweight="bold")
        elif j == 4:
            s = int(cell[i - 1][4])
            c.set_facecolor(PALETTE["pass"] if s <= 4 else PALETTE["warn"] if s <= 9 else "#E08E45" if s <= 14 else PALETTE["fail"])
            c.set_text_props(color="white", fontweight="bold")
    ax.set_title(title, loc="left")
    return fig


def decision_tree(nodes: List[Dict[str, Any]], title: str = "Decision tree") -> plt.Figure:
    """Decision tree: nodes ``{id, parent, label, kind (decision|chance|outcome), edge}``; laid out by depth and leaf order."""
    by = {n["id"]: n for n in nodes}
    kids: Dict[Any, List[Any]] = {}
    for n in nodes:
        kids.setdefault(n.get("parent"), []).append(n["id"])
    depth: Dict[Any, int] = {}
    ypos: Dict[Any, float] = {}
    counter = [0.0]

    def walk(i: Any, d: int) -> float:
        depth[i] = d
        ch = kids.get(i, [])
        if not ch:
            ypos[i] = counter[0]
            counter[0] += 1.0
        else:
            ypos[i] = float(np.mean([walk(c, d + 1) for c in ch]))
        return ypos[i]

    roots = kids.get(None, [])
    for r in roots:
        walk(r, 0)
    fig, ax = plt.subplots(figsize=(9.0, 0.7 * max(counter[0], 3) + 1.6))
    for n in nodes:
        if n.get("parent") is not None:
            p = n["parent"]
            ax.plot([depth[p], depth[n["id"]]], [ypos[p], ypos[n["id"]]], color=PALETTE["muted"], lw=LW["normal"], zorder=1)
            if n.get("edge"):
                fx = 0.5
                ax.text(depth[p] + fx * (depth[n["id"]] - depth[p]), ypos[p] + fx * (ypos[n["id"]] - ypos[p]), n["edge"], fontsize=7, ha="center", va="center", color=PALETTE["muted"], zorder=5,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
    for n in nodes:
        x, y = depth[n["id"]], ypos[n["id"]]
        k = n.get("kind", "outcome")
        if k == "decision":
            ax.add_patch(Rectangle((x - 0.07, y - 0.18), 0.14, 0.36, fc=PALETTE["accent1"], ec="white", zorder=3))
        elif k == "chance":
            ax.add_patch(Circle((x, y), 0.14, fc=PALETTE["accent2"], ec="white", zorder=3))
        else:
            ax.plot([x], [y], marker="D", color=PALETTE["accent3"], ms=7, zorder=3)
        if k == "outcome":
            ax.text(x + 0.12, y, n["label"], fontsize=7.6, va="center", ha="left", zorder=4)
        else:
            ax.text(x - 0.12, y, n["label"], fontsize=7.6, va="center", ha="right", zorder=4, fontweight="bold", bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))
    ax.set_xlim(-2.4, max(depth.values()) + 2.6)
    ax.set_ylim(-0.8, counter[0])
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(title, loc="left")
    return fig


def time_depth_chart(curves: Dict[str, Sequence[Tuple[float, float]]], planned: Optional[Sequence[Tuple[float, float]]] = None, band_curves: Optional[Tuple[str, str]] = None,
                     title: str = "Time-depth curve") -> plt.Figure:
    """Time-depth chart for low/base/high (and planned) curves; ``curves`` maps a label to (day, depth) points."""
    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    for k, (name, pts) in enumerate(curves.items()):
        a = np.asarray(pts, float)
        ax.plot(a[:, 0], a[:, 1], color=CATEGORICAL[k % 8], lw=LW["thick"] if name == "base" else LW["normal"], ls="-" if name == "base" else "--")
        direct_label(ax, a[-1, 0], a[-1, 1], name, CATEGORICAL[k % 8], dx=5)
    if band_curves and band_curves[0] in curves and band_curves[1] in curves:
        a, b = np.asarray(curves[band_curves[0]], float), np.asarray(curves[band_curves[1]], float)
        d = np.linspace(max(a[:, 1].min(), b[:, 1].min()), min(a[:, 1].max(), b[:, 1].max()), 40)
        band(ax, d, np.interp(d, a[:, 1], a[:, 0]), np.interp(d, b[:, 1], b[:, 0]))
    if planned:
        p = np.asarray(planned, float)
        ax.plot(p[:, 0], p[:, 1], color=PALETTE["limit"], lw=LW["thin"], ls=":")
        direct_label(ax, p[-1, 0], p[-1, 1], "plan", PALETTE["limit"], dx=5, dy=-8)
    ax.invert_yaxis()
    ax.set_xlabel("Days")
    ax.set_ylabel("Depth [m]")
    ax.set_title(title, loc="left")
    return fig


# ----------------------------------------------------------------------------- trajectory
def trajectory_views(survey: Dict[str, Sequence[float]], offsets: Optional[Dict[str, Dict[str, Sequence[float]]]] = None, separation: Optional[Dict[str, Any]] = None,
                     title: str = "Trajectory: plan, section and separation") -> plt.Figure:
    """Plan view, vertical section and (optionally) separation-factor fans of offset wells."""
    ncols = 3 if separation else 2
    fig, axs = plt.subplots(1, ncols, figsize=(4.6 * ncols, 4.8))
    n, e, tvd = np.asarray(survey["north"]), np.asarray(survey["east"]), np.asarray(survey["tvd"])
    vs = np.hypot(n, e)
    ax = axs[0]
    ax.plot(e, n, color=PALETTE["accent1"], lw=LW["thick"])
    ax.scatter([e[-1]], [n[-1]], color=PALETTE["accent2"], zorder=4)
    direct_label(ax, e[-1], n[-1], "target", PALETTE["text"], dx=6, dy=6, size=7.5)
    for k, (nm, o) in enumerate((offsets or {}).items()):
        ax.plot(o["east"], o["north"], color=CATEGORICAL[(k + 2) % 8], lw=LW["normal"], ls="--")
        direct_label(ax, o["east"][-1], o["north"][-1], nm, CATEGORICAL[(k + 2) % 8], dx=4, size=7)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("East [m]")
    ax.set_ylabel("North [m]")
    ax.set_title("Plan view", fontsize=9.5, loc="left")
    ax = axs[1]
    ax.plot(vs, tvd, color=PALETTE["accent1"], lw=LW["thick"])
    for k, (nm, o) in enumerate((offsets or {}).items()):
        ax.plot(np.hypot(o["north"], o["east"]), o["tvd"], color=CATEGORICAL[(k + 2) % 8], lw=LW["normal"], ls="--")
    ax.invert_yaxis()
    ax.set_xlabel("Vertical section [m]")
    ax.set_ylabel("TVD [m]")
    ax.set_title("Section view", fontsize=9.5, loc="left")
    if separation:
        ax = axs[2]
        for k, (nm, d) in enumerate(separation["curves"].items()):
            ax.plot(d["md"], d["sf"], color=CATEGORICAL[(k + 2) % 8], lw=LW["normal"])
            direct_label(ax, d["md"][-1], d["sf"][-1], nm, CATEGORICAL[(k + 2) % 8], dx=4, size=7)
        thr = separation.get("threshold")
        if thr is not None:
            ax.axhline(thr, color=PALETTE["fail"], ls="--", lw=LW["normal"])
            direct_label(ax, ax.get_xlim()[0], thr, "operator threshold {:g} (supplied)".format(thr), PALETTE["fail"], dx=3, dy=6, size=7)
        ax.set_xlabel("Measured depth [m]")
        ax.set_ylabel("Separation factor [-]")
        ax.set_title("Anti-collision fan (from supplied data)", fontsize=9.5, loc="left")
    fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def trajectory_3d(survey: Dict[str, Sequence[float]], path: Path, offsets: Optional[Dict[str, Dict[str, Sequence[float]]]] = None, size: Tuple[int, int] = (1100, 800)) -> str:
    """Render a 3D view to ``path`` (PNG): PyVista off-screen when available, otherwise matplotlib 3D. Returns the renderer name."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyvista as pv

        pv.OFF_SCREEN = True
        pl = pv.Plotter(off_screen=True, window_size=list(size))
        pl.set_background("white")
        pts = np.column_stack([survey["east"], survey["north"], -np.asarray(survey["tvd"])])
        pl.add_mesh(pv.lines_from_points(pts), color=PALETTE["accent1"], line_width=5)
        pl.add_mesh(pv.Sphere(radius=max(8.0, float(np.ptp(pts[:, 2])) * 0.01), center=pts[-1]), color=PALETTE["accent2"])
        pl.add_point_labels(np.array([pts[-1]]), ["target"], font_size=16, text_color=PALETTE["text"], shape=None, always_visible=True, show_points=False)
        for k, (nm, o) in enumerate((offsets or {}).items()):
            op = np.column_stack([o["east"], o["north"], -np.asarray(o["tvd"])])
            pl.add_mesh(pv.lines_from_points(op), color=CATEGORICAL[(k + 2) % 8], line_width=3)
            pl.add_point_labels(np.array([op[0]]), [nm], font_size=14, text_color=CATEGORICAL[(k + 2) % 8], shape=None, always_visible=True, show_points=False)
        pl.show_grid(color="#888888", font_size=11, xtitle="East [m]", ytitle="North [m]", ztitle="TVD [m, negative down]", all_edges=False, n_xlabels=3, n_ylabels=3, n_zlabels=5, fmt="%.0f")
        pl.camera_position = "iso"
        pl.camera.zoom(0.82)
        pl.screenshot(str(path))
        pl.close()
        return "pyvista"
    except Exception:  # noqa: BLE001 - any VTK/GL problem falls back to matplotlib
        fig = plt.figure(figsize=(7.2, 5.6))
        ax = fig.add_subplot(111, projection="3d")
        ax.plot(survey["east"], survey["north"], -np.asarray(survey["tvd"]), color=PALETTE["accent1"], lw=2.5)
        for k, (nm, o) in enumerate((offsets or {}).items()):
            ax.plot(o["east"], o["north"], -np.asarray(o["tvd"]), color=CATEGORICAL[(k + 2) % 8], lw=1.5, ls="--")
        ax.set_xlabel("East [m]")
        ax.set_ylabel("North [m]")
        ax.set_zlabel("-TVD [m]")
        fig.savefig(path, dpi=200)
        plt.close(fig)
        return "matplotlib"


# ----------------------------------------------------------------------------- registry
CHARTS: Dict[str, Callable[..., plt.Figure]] = {
    "nodal": nodal_chart, "wellbore_profiles": wellbore_profiles, "operating_envelope": operating_envelope_chart, "envelope_table": envelope_table_figure,
    "alternatives_scorecard": alternatives_scorecard, "alternatives_radar": alternatives_radar, "pareto": pareto_chart, "waterfall": waterfall_chart,
    "tornado": tornado_chart, "sensitivity_heatmap": sensitivity_heatmap, "profile_bands": profile_bands, "gantt": gantt_chart, "risk_matrix": risk_matrix,
    "risk_register": risk_register_heatmap, "decision_tree": decision_tree, "time_depth": time_depth_chart, "trajectory_views": trajectory_views,
}


def render(name: str, out_stem: Path, provenance_inputs: Any, caption: str = "", synthetic: bool = True, formats: Sequence[str] = ("png",), ledger_refs: Optional[List[str]] = None,
           sources: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, str]:
    """Render chart ``name`` with ``kwargs`` and save it (PNG at 300 dpi by default) with a provenance sidecar."""
    fig = CHARTS[name](**kwargs)
    prov = provenance_record(Path(out_stem).name, name, "integrated_well_planning.iwp_graphics." + CHARTS[name].__name__, provenance_inputs, caption, synthetic, sources, ledger_refs)
    return save_figure(fig, Path(out_stem), prov, formats)


from . import iwp_charts_extra as _extra  # noqa: E402

CHARTS.update({"multi_line": _extra.multi_line_chart, "hbar_grouped": _extra.hbar_grouped_chart, "grouped_bar": _extra.grouped_bar_chart, "pressure_window": _extra.pressure_window_chart, "percentile": _extra.percentile_chart,
               "casing_programme": _extra.casing_programme_sheet, "offset_map": _extra.offset_map_chart})
