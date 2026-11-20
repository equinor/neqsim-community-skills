"""Report illustrations of a facility study, in the house style of :mod:`.style`.

Two figures: a plan of the sources and receptors with the footprint of the worst
condition, and the conditional exceedance of every receptor. Every number in a title,
sub-line or label is computed from the study result; nothing is typed in.

Requires matplotlib (declared in the ``figures`` extra of the skill package).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from matplotlib.lines import Line2D

from . import style as st
from .facility import FacilityStudyResult
from .figures import FOLDERS, FigureRecord, _finish
from .study import threshold_key
from .wind import pasquill_by_speed

KIND_COLORS = [
    st.BLUE,
    st.ORANGE,
    st.GREEN,
    "#6a3d9a",
    "#17becf",
    st.GREY,
    "#8c564b",
    "#e377c2",
]
"""Receptor-kind colours, cycled."""


def _kind_colors(study: FacilityStudyResult) -> dict[str, str]:
    """One colour per receptor kind in the order of first use."""
    kinds: list[str] = []
    for r in study.receptors:
        if r.kind not in kinds:
            kinds.append(r.kind)
    return {k: KIND_COLORS[i % len(KIND_COLORS)] for i, k in enumerate(kinds)}


def _key_threshold(study: FacilityStudyResult) -> float:
    """The threshold used in titles: 20 percent if present, else the largest."""
    t = sorted(study.settings.thresholds_pct_lfl)
    return 20.0 if 20.0 in t else t[-1]


def _pct(value: float) -> str:
    """Peak concentration text."""
    return f"{value:.0f}" if value >= 10.0 else f"{value:.1f}"


@st.in_house_style
def fig_facility_layout(
    study: FacilityStudyResult, folders: FOLDERS, name: str = "facility_layout.png"
) -> FigureRecord:
    """Plan of sources and receptors with the footprint of the worst condition.

    Args:
        study: Facility study result.
        folders: One folder or several folders.
        name: File name.

    Returns:
        The figure record; ``facts`` holds the counts and the worst pair.
    """
    mode = "briggs" if "briggs" in study.settings.modes else study.settings.modes[0]
    thr = _key_threshold(study)
    worst = study.ranking(thr, mode)[0]
    entry = study.summaries[worst["case"]]["modes"][mode]["receptors"][
        worst["receptor"]
    ]
    cond = entry["peak_condition"]
    src = next(fr.source for fr in study.freleases if fr.case.name == worst["case"])
    release = study.releases[worst["case"]]
    colors = _kind_colors(study)

    pts = np.vstack(
        [r.points[:, :2] for r in study.receptors]
        + [s.position[:2][None, :] for s in study.sources]
    )
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    margin = max(0.15 * float(np.max(hi - lo)), 30.0)
    lo, hi = lo - margin, hi + margin
    step = max(float(np.max(hi - lo)) / 110.0, 2.0)
    gx, gy = np.meshgrid(
        np.arange(lo[0], hi[0] + step, step), np.arange(lo[1], hi[1] + step, step)
    )
    grid = np.column_stack(
        [gx.ravel(), gy.ravel(), np.full(gx.size, cond["point_up_m"])]
    )
    stab = pasquill_by_speed(float(cond["speed_m_s"]), study.settings.stability_scheme)
    field = release.pct_lfl(
        grid, cond["wind_from_deg"], cond["speed_m_s"], stab, src.position, mode
    ).reshape(gx.shape)

    fig = st.new_fig(4.6)
    ax = fig.add_subplot(111)
    st.lfl_contours(ax, gx, gy, field)
    for r in study.receptors:
        if not r.follows_wind:
            ax.scatter(
                r.points[:, 0],
                r.points[:, 1],
                s=7 if len(r.points) > 20 else 22,
                color=colors[r.kind],
                zorder=3,
                linewidths=0,
            )
    for i, r in enumerate(study.receptors[:12]):
        c = r.points[0] if r.follows_wind else r.points.mean(axis=0)
        ax.annotate(
            r.name,
            (c[0], c[1]),
            xytext=(3, 3 if i % 2 == 0 else -9),
            textcoords="offset points",
            fontsize=6.0,
            zorder=5,
        )
    for s in study.sources:
        ax.scatter(
            [s.east_m],
            [s.north_m],
            marker="*",
            s=90,
            color=st.RED,
            edgecolors="white",
            linewidths=0.5,
            zorder=6,
        )
        ax.annotate(
            s.name,
            (s.east_m, s.north_m),
            xytext=(5, -9),
            textcoords="offset points",
            fontsize=6.5,
            color=st.RED,
            fontweight="bold",
            zorder=6,
        )
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_aspect("equal")
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    st.north_arrow(ax)
    st.wind_box(ax, cond["wind_from_deg"], cond["speed_m_s"])
    handles: list[Any] = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor=st.RED, markersize=9)
    ]
    labels = ["release source"]
    for kind, color in colors.items():
        handles.append(
            Line2D([0], [0], marker="o", color="w", markerfacecolor=color, markersize=5)
        )
        labels.append(kind.replace("_", " "))
    st.bottom_legend(fig, handles, labels, min(len(labels), 5))
    title = (
        "{} has the highest exceedance: {} % LFL peak, {:g} % LFL exceeded in {:.1f} % of wind hours".format(
            worst["receptor"],
            _pct(worst["peak_pct_lfl"]),
            thr,
            worst["exceed_pct_hours"],
        )
        if worst["exceed_pct_hours"] > 0.0
        else "No receptor reaches {:g} % LFL; {} comes closest at {} % LFL peak".format(
            thr, worst["receptor"], _pct(worst["peak_pct_lfl"])
        )
    )
    sub = "{} from {}; footprint at {:.0f} m ASL for wind from {:03.0f} deg at {:.1f} m/s. Conditional on an unignited release.".format(
        worst["case"],
        src.name,
        cond["point_up_m"],
        cond["wind_from_deg"],
        cond["speed_m_s"],
    )
    return _finish(
        fig,
        folders,
        name,
        title,
        sub,
        {
            "n_receptors": len(study.receptors),
            "n_sources": len(study.sources),
            "worst_receptor": worst["receptor"],
            "worst_case": worst["case"],
            "threshold": thr,
        },
    )


@st.in_house_style
def fig_facility_exceedance(
    study: FacilityStudyResult, folders: FOLDERS, name: str = "facility_exceedance.png"
) -> FigureRecord:
    """Conditional exceedance of every receptor, one bar per case.

    Args:
        study: Facility study result.
        folders: One folder or several folders.
        name: File name.

    Returns:
        The figure record; ``facts`` holds the threshold and the largest exceedance.
    """
    mode = "briggs" if "briggs" in study.settings.modes else study.settings.modes[0]
    thr = _key_threshold(study)
    cases = [fr.case.name for fr in study.freleases]
    order = sorted(
        (r.name for r in study.receptors),
        key=lambda n: -max(study.exceedance(c, n, thr, mode) for c in cases),
    )
    worst = study.ranking(thr, mode)[0]
    show_hours = worst["exceed_pct_hours"] > 0.0
    n, m = len(order), len(cases)
    fig = st.new_fig(min(max(2.6, 1.3 + 0.17 * n * m), 8.0))
    ax = fig.add_subplot(111)
    bar = 0.8 / m

    def value(case: str, receptor: str) -> float:
        if show_hours:
            return study.exceedance(case, receptor, thr, mode)
        return float(study.arrays[f"{case}_{mode}"].peak[receptor].max())

    for ci, case in enumerate(cases):
        vals = [value(case, rn) for rn in order]
        ypos = [i + (ci - (m - 1) / 2.0) * bar for i in range(n)]
        ax.barh(ypos, vals, height=bar * 0.9, color=st.case_color(ci))
        for y, rn, v in zip(ypos, order, vals):
            peak = float(study.arrays[f"{case}_{mode}"].peak[rn].max())
            text = f" {_pct(peak)} % LFL peak" if show_hours else f" {_pct(peak)} %"
            ax.text(v, y, text, va="center", fontsize=5.8, color=st.GREY)
    ax.set_yticks(range(n))
    ax.set_yticklabels(order)
    ax.invert_yaxis()
    top = max([value(c, o) for c in cases for o in order] + [0.1])
    if show_hours:
        ax.set_xlim(0.0, top * 1.4)
        ax.set_xlabel(
            f"Wind hours with at least {thr:g} % LFL, given an unignited release (%)"
        )
    else:
        ax.set_xlim(0.0, max(top, thr) * 1.25)
        ax.axvline(thr, color=st.RED, lw=1.0, ls="--")
        ax.set_xlabel(
            f"Peak concentration over all winds (% LFL); dashed line: {thr:g} % LFL"
        )
    st.bottom_legend(
        fig,
        [Line2D([0], [0], color=st.case_color(i), lw=5) for i in range(m)],
        cases,
        min(m, 4),
    )
    if show_hours:
        title = "{} has {:.2f} % of wind hours above {:g} % LFL, the most of any receptor".format(
            worst["receptor"], worst["exceed_pct_hours"], thr
        )
        sub = f"{n} receptors, {m} case(s); labels give the peak concentration over all winds. Conditional, not an annual frequency."
    else:
        title = (
            "No receptor reaches {:g} % LFL; {} comes closest at {} % LFL peak".format(
                thr, worst["receptor"], _pct(worst["peak_pct_lfl"])
            )
        )
        sub = f"{n} receptors, {m} case(s); peak concentration over all winds. Conditional on an unignited release."
    return _finish(
        fig,
        folders,
        name,
        title,
        sub,
        {
            "threshold": thr,
            "threshold_key": threshold_key(thr),
            "metric": "exceedance" if show_hours else "peak",
            "max_pct": worst["exceed_pct_hours"],
            "peak_pct_lfl": worst["peak_pct_lfl"],
            "worst_receptor": worst["receptor"],
        },
    )


def make_facility_figures(
    study: FacilityStudyResult, folders: FOLDERS
) -> list[FigureRecord]:
    """Create the facility figures.

    Args:
        study: Facility study result.
        folders: One folder or several folders.

    Returns:
        The figure records (layout problems are listed in each record).
    """
    return [
        fig_facility_layout(study, folders),
        fig_facility_exceedance(study, folders),
    ]


__all__: Sequence[str] = [
    "fig_facility_exceedance",
    "fig_facility_layout",
    "make_facility_figures",
]
