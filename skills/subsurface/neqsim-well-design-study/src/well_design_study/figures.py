"""Figures for a well design study (matplotlib, Agg backend). Every function saves a PNG and returns its path."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .pressure import PressureModel  # noqa: E402


def _save(fig, path: Path) -> Path:
    path = Path(path)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


def window_plot(model: PressureModel, sections: Sequence[Dict[str, object]], path: Path, td_tvd_m: float,
                offsets: Optional[Dict[str, Sequence[Dict[str, object]]]] = None, title: str = "Pressure and mud-weight window",
                extras: Optional[Sequence[Dict[str, object]]] = None) -> Path:
    """Pore and fracture curves (low/base/high), planned mud weights, casing shoes and offset-well points.

    ``extras`` adds labelled point series (dicts with label, x, y, optional marker, color, size), for example planned leak-off values.
    """
    fig, ax = plt.subplots(figsize=(8.2, 8.6))
    z = np.linspace(max(50.0, model.mudline_tvd_m + 1.0), td_tvd_m, 200)
    for case, ls, a in (("low", ":", 0.9), ("base", "-", 1.0), ("high", "--", 0.9)):
        ax.plot([model.pore_sg(v, case) for v in z], z, color="#1f77b4", ls=ls, alpha=a, label=f"pore {case}")
        ax.plot([model.frac_sg(v, case) for v in z], z, color="#d62728", ls=ls, alpha=a, label=f"fracture {case}")
    for s in sections:
        top, bot, mw = float(s["top_tvd_m"]), float(s["bottom_tvd_m"]), float(s["mud_sg_planned"])
        ax.plot([mw, mw], [top, bot], color="#2ca02c", lw=3, solid_capstyle="butt")
        ax.axhline(bot, color="0.4", lw=0.8)
        ax.text(0.99, bot, (f'{s["casing_od_in"]:g}" shoe {bot:.0f} m' if float(s.get("casing_od_in") or 0) > 0 else f"TD {bot:.0f} m"), fontsize=7.5, va="bottom", ha="right",
                transform=ax.get_yaxis_transform())
    ax.plot([], [], color="#2ca02c", lw=3, label="planned mud weight")
    if offsets:
        mk = {"frac": ("v", "#d62728", "offset LOT/FIT"), "pore": ("o", "#1f77b4", "offset pore (measured)"), "mud": ("s", "#2ca02c", "offset mud weight")}
        for key, (m, c, lab) in mk.items():
            pts = offsets.get(key) or []
            if pts:
                xs = [p.get("emw_sg", p.get("mw_sg")) for p in pts]
                ys = [p["tvd_m"] for p in pts]
                ax.scatter(xs, ys, marker=m, s=26, color=c, edgecolors="k", linewidths=0.4, alpha=0.8, label=lab, zorder=5)
    for ex in extras or []:
        ax.scatter(ex["x"], ex["y"], marker=ex.get("marker", "D"), s=ex.get("size", 40), color=ex.get("color", "k"), edgecolors="k", linewidths=0.5,
                   label=ex["label"], zorder=6)
    ax.axhline(model.mudline_tvd_m, color="#17becf", lw=1)
    ax.text(0.01, model.mudline_tvd_m, "mudline", transform=ax.get_yaxis_transform(), fontsize=7.5, va="bottom")
    ax.set_ylim(td_tvd_m + 100, 0)
    ax.set_xlabel("Equivalent mud weight (sg)")
    ax.set_ylabel("TVD below RKB (m)")
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=3, frameon=False)
    return _save(fig, path)


def schematic(strings: Sequence[Dict[str, object]], path: Path, water_depth_m: float, air_gap_m: float, tops: Optional[Sequence[Sequence[object]]] = None,
              td_m: Optional[float] = None, title: str = "Casing and hole schematic") -> Path:
    """Nested casing schematic: shoes, hole sizes and optional formation tops (name, TVD)."""
    fig, ax = plt.subplots(figsize=(7.4, 9.0))
    td = td_m or max(float(s["shoe_tvd_m"]) for s in strings)
    ml = water_depth_m + air_gap_m
    ax.add_patch(plt.Rectangle((-14, 0), 42, ml, color="#bfe3f2"))
    ax.text(7, ml / 2, f"sea {water_depth_m:.0f} m (RKB above sea level {air_gap_m:.0f} m)", ha="center", va="center", fontsize=8)
    cmap = plt.get_cmap("viridis")
    order = sorted(strings, key=lambda s: -float(s["od_in"]))
    for i, s in enumerate(order):
        od = float(s["od_in"])
        w = od * 0.45
        top = float(s.get("top_tvd_m", ml))
        shoe = float(s["shoe_tvd_m"])
        ax.add_patch(plt.Rectangle((-w / 2, top), w, shoe - top, fill=False, edgecolor=cmap(i / max(1, len(order))), lw=2))
        ax.plot([-w / 2, w / 2], [shoe, shoe], color=cmap(i / max(1, len(order))), lw=3)
        ax.text(w / 2 + 0.6, shoe, f'{od:g}" shoe {shoe:.0f} m' + (f' (hole {s["hole_in"]:g}")' if s.get("hole_in") else ""), fontsize=7.5, va="center")
        toc = s.get("toc_tvd_m")
        if toc:
            ax.plot([-w / 2 - 0.5, -w / 2 - 0.5], [toc, shoe], color="0.5", lw=4, alpha=0.5)
    deepest = max(float(s["shoe_tvd_m"]) for s in strings)
    if td > deepest + 1.0:
        last = max(strings, key=lambda s: float(s["shoe_tvd_m"]))
        ax.plot([0, 0], [deepest, td], color="k", lw=1.5, ls="--")
        ax.text(1.0, td, f'TD {td:.0f} m (open hole below the {float(last["od_in"]):g}" shoe)', fontsize=7.5, va="center")
    if tops:
        for name, z in tops:
            ax.axhline(float(z), color="0.7", lw=0.5, ls="--", xmin=0.02, xmax=0.30)
            ax.text(-13.8, float(z) - 12.0, f"{name} {float(z):.0f}", fontsize=6.8, va="bottom")
    ax.set_xlim(-14, 28)
    ax.set_ylim(td * 1.04, 0)
    ax.set_ylabel("TVD below RKB (m)")
    ax.set_xticks([])
    ax.set_title(title, fontsize=10)
    ax.grid(axis="y", alpha=0.2)
    return _save(fig, path)


def design_factor_plot(rows: Sequence[Dict[str, object]], path: Path, minimums: Dict[str, float], title: str = "Casing design factors") -> Path:
    """Design factors per string against the minimum requirement."""
    names = [str(r["string"]) for r in rows]
    checks = ["burst_df", "collapse_df", "tension_df", "triaxial_df"]
    labels = ["burst", "collapse", "tension", "triaxial"]
    fig, ax = plt.subplots(figsize=(9.0, 0.9 * len(rows) + 2.4))
    y = np.arange(len(rows))
    h = 0.18
    for k, (c, lab) in enumerate(zip(checks, labels)):
        v = [min(float(r[c]), 6.0) for r in rows]
        ax.barh(y + (k - 1.5) * h, v, h, label=lab)
        ax.axvline(minimums[lab], color=f"C{k}", ls=":", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Design factor (capped at 6; dotted = minimum)")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    ax.grid(axis="x", alpha=0.25)
    return _save(fig, path)


def time_depth_plot(curves: Dict[str, Sequence[Sequence[float]]], path: Path, title: str = "Time-depth: offset wells and plan") -> Path:
    """Time-depth curves: dict name -> [(days, depth_m), ...]."""
    fig, ax = plt.subplots(figsize=(8.2, 6.2))
    for name, pts in curves.items():
        a = np.array(pts, dtype=float)
        ls = "-" if name.lower().startswith(("plan", "p50")) else "--" if name.lower().startswith(("p10", "p90")) else "-"
        ax.plot(a[:, 0], a[:, 1], ls=ls, lw=2.2 if name.lower().startswith(("plan", "p50")) else 1.2, label=name)
    ax.invert_yaxis()
    ax.set_xlabel("Days from spud")
    ax.set_ylabel("Depth (m MD)")
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7.5)
    return _save(fig, path)


def histogram_plot(samples: Dict[str, np.ndarray], path: Path, xlabel: str, title: str, units: Optional[Dict[str, str]] = None) -> Path:
    """Distribution histograms with P10/P50/P90 marks; ``units`` maps a sample name to its axis unit (default: ``xlabel``)."""
    fig, axes = plt.subplots(1, len(samples), figsize=(5.4 * len(samples), 4.2), squeeze=False)
    for ax, (name, a) in zip(axes[0], samples.items()):
        ax.hist(a, bins=60, color="#6baed6", edgecolor="white")
        ax.set_xlim(float(a.min()) * 0.95, float(np.percentile(a, 99.7)))
        top = ax.get_ylim()[1]
        for p, c, dx in ((10, "#2ca02c", -1), (50, "k", 1), (90, "#d62728", 1)):
            v = np.percentile(a, p)
            ax.axvline(v, color=c, lw=1.4)
            ax.text(v, top * 0.98, f"P{p} {v:.0f}", rotation=90, fontsize=7.5, va="top", ha="right" if dx < 0 else "left",
                    bbox={"fc": "white", "ec": "none", "alpha": 0.85, "pad": 0.6})
        ax.set_xlabel(f"{name} {(units or {}).get(name, xlabel)}")
        ax.set_ylabel("Samples")
        ax.grid(alpha=0.25)
    fig.suptitle(title, fontsize=10)
    return _save(fig, path)


def line_plot(series: Dict[str, Sequence[Sequence[float]]], path: Path, xlabel: str, ylabel: str, title: str, invert_y: bool = False,
              hlines: Optional[Dict[str, float]] = None) -> Path:
    """Generic multi-series line plot (hookload vs MD, ECD vs flow, etc.)."""
    fig, ax = plt.subplots(figsize=(8.0, 5.6))
    for name, pts in series.items():
        a = np.array(pts, dtype=float)
        ax.plot(a[:, 0], a[:, 1], lw=1.8, label=name)
    for lab, v in (hlines or {}).items():
        ax.axhline(v, color="k", ls=":", lw=1)
        ax.text(ax.get_xlim()[0], v, f" {lab}", fontsize=7.5, va="bottom")
    if invert_y:
        ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    return _save(fig, path)
