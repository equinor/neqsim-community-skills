"""House style for the study illustrations (vendor neutral).

Rules that every figure of this skill follows:

1. Figures are designed at report text width (:data:`W_FULL` = 7.2 in) with 7-9 pt text;
   never wider, so that nothing prints smaller than 6 pt.
2. One shared LFL colour scheme and one legend at the bottom centre on every
   concentration figure (LFL bands plus the 10 percent dashed and 20 percent solid
   contour lines).
3. Plan views: true north up, north arrow top-right, wind arrow box top-left, axes in
   km, identical extent across panels; tip = orange star, helideck = blue hexagon,
   flight paths = green, obstacle-free sector shaded light green.
4. Titles state the finding (bold, wrapped to at most two lines) and a grey sub-line
   states case and conditions; title and legend margins are reserved explicitly.
5. Peaks written on figures are peaks ON THE FLIGHT PATHS, capped at ``> 100 % LFL``.
6. Vertical sections state their vertical exaggeration.

:func:`layout_problems` checks the title, sub-line and legend against the axes after the
layout has run; every saved figure is checked.
"""

from __future__ import annotations

import functools
import math
import os
import textwrap
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, Wedge

from .receptors import PlatformGeometry, Receptors

W_FULL = 7.2
"""Report text width, inches. Every figure has exactly this width."""
DPI = 220
"""Resolution of saved figures; the PNG width is ``W_FULL * DPI`` pixels."""

NAVY = "#12355b"
RED = "#b2281e"
ORANGE = "#e67e22"
GREEN = "#2e8b57"
BLUE = "#1f77b4"
GREY = "#6b7280"
SEA = "#2c7fb8"

LFL_LEVELS = [5, 10, 20, 50, 100, 1000]
"""Band edges, percent of the LFL."""
LFL_COLORS = ["#fff3b0", "#fdb863", "#e34a33", "#b30000", "#4d0000"]
"""Band colours, one per band."""
LFL_LABELS = ["5-10 % LFL", "10-20 % LFL", "20-50 % LFL", "50-100 % LFL", "> 100 % LFL"]
"""Legend text of the bands."""
LINE10 = "#b35900"
LINE20 = "#7f0000"
CASE_COLORS = ["#2c7fb8", ORANGE, RED, "#6a3d9a", "#7f7f7f", "#17becf"]
"""Consistent per-case colours (green is reserved for flight paths)."""

VERTICAL_EXAGGERATION = 3.0
"""Vertical exaggeration of every section view."""

RC = {
    "font.family": "DejaVu Sans",
    "font.size": 7.5,
    "axes.titlesize": 8,
    "axes.titleweight": "bold",
    "axes.labelsize": 7.5,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "lines.linewidth": 1.2,
    "figure.dpi": 120,
    "savefig.dpi": DPI,
    "savefig.facecolor": "white",
}
"""Matplotlib settings applied inside :func:`house_style` only."""


def house_style() -> Any:
    """Return a context manager that applies the house matplotlib settings.

    Returns:
        A ``matplotlib.rc_context`` for use in a ``with`` statement.
    """
    return matplotlib.rc_context(RC)


def in_house_style(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: run a figure function inside :func:`house_style`.

    Args:
        func: Figure function.

    Returns:
        The wrapped function.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with house_style():
            return func(*args, **kwargs)

    return wrapper


def case_color(index: int) -> str:
    """Colour of the ``index``-th case, cycling through :data:`CASE_COLORS`.

    Args:
        index: Case index.

    Returns:
        Hex colour.
    """
    return CASE_COLORS[index % len(CASE_COLORS)]


def new_fig(height_in: float, constrained: bool = True) -> Figure:
    """Create a page-width figure (no pyplot state).

    Args:
        height_in: Figure height, inches.
        constrained: Use the constrained layout engine.

    Returns:
        A figure attached to an Agg canvas, ``W_FULL`` inches wide.
    """
    fig = Figure(
        figsize=(W_FULL, height_in), layout="constrained" if constrained else None
    )
    FigureCanvasAgg(fig)
    fig._has_bottom_legend = False  # type: ignore[attr-defined]
    return fig


def headline(fig: Figure, text: str, sub: str | None = None, wrap: int = 74) -> None:
    """Bold finding as title (two lines at most) with an optional grey sub-line.

    Reserves the title and legend margins in the layout so that nothing overlaps the
    panels. Call it after the panels and the legend have been created.

    Args:
        fig: Figure created by :func:`new_fig`.
        text: Title stating the finding.
        sub: Case and conditions.
        wrap: Wrap width of the title in characters.
    """
    size = 10.0
    lines = textwrap.wrap(text, wrap)
    if len(lines) > 2:
        size = 9.0
        lines = textwrap.wrap(text, int(wrap * 10.0 / size * 1.0))
    if len(lines) > 2:
        raise ValueError(f"title needs more than two lines; shorten it: {text!r}")
    height = fig.get_size_inches()[1]
    y = 0.995
    title = fig.text(
        0.01,
        y,
        "\n".join(lines),
        ha="left",
        va="top",
        fontsize=size,
        fontweight="bold",
        linespacing=1.15,
    )
    title.set_gid("headline")
    used = len(lines) * size * 1.3 / 72.0
    if sub:
        sub_lines = textwrap.wrap(sub, 120)
        if len(sub_lines) > 2:
            raise ValueError(f"sub-line needs more than two lines; shorten it: {sub!r}")
        sub_text = fig.text(
            0.01,
            y - used / height - 0.004,
            "\n".join(sub_lines),
            ha="left",
            va="top",
            fontsize=6.8,
            color=GREY,
        )
        sub_text.set_gid("subline")
        used += len(sub_lines) * 6.8 * 1.5 / 72.0
    top = 1.0 - (used + 0.16) / height
    bottom = 0.34 / height if getattr(fig, "_has_bottom_legend", False) else 0.0
    engine = fig.get_layout_engine()
    if engine is not None:
        engine.set(rect=(0.0, bottom, 1.0, top - bottom))


def bottom_legend(
    fig: Figure,
    handles: Sequence[Any],
    labels: Sequence[str],
    ncol: int,
    fontsize: float = 6.8,
) -> None:
    """Legend centred at the bottom of the figure (margin reserved by :func:`headline`).

    Args:
        fig: Figure.
        handles: Legend handles.
        labels: Legend labels.
        ncol: Number of columns.
        fontsize: Font size, points.
    """
    fig._has_bottom_legend = True  # type: ignore[attr-defined]
    fig.legend(
        list(handles),
        list(labels),
        loc="lower center",
        ncol=ncol,
        frameon=False,
        bbox_to_anchor=(0.5, 0.0),
        fontsize=fontsize,
        columnspacing=1.2,
        handlelength=1.4,
    )


def lfl_legend(fig: Figure, lines: bool = True) -> None:
    """The one legend of all concentration figures, bottom centre.

    Args:
        fig: Figure.
        lines: Also list the 10 and 20 percent contour lines.
    """
    handles: list[Any] = [Patch(fc=c, ec="none") for c in LFL_COLORS]
    labels = list(LFL_LABELS)
    if lines:
        handles += [
            Line2D([0], [0], color=LINE10, lw=1.0, ls="--"),
            Line2D([0], [0], color=LINE20, lw=1.2),
        ]
        labels += ["10 % LFL contour", "20 % LFL contour"]
    bottom_legend(fig, handles, labels, 7 if lines else 5)


def lfl_contours(
    ax: Any, x: np.ndarray, y: np.ndarray, field: np.ndarray, alpha: float = 0.9
) -> None:
    """Filled LFL bands plus the 10 and 20 percent contour lines.

    Bands are drawn only when the field reaches the lowest band, so no empty contour
    call is made.

    Args:
        ax: Axes.
        x: Grid x coordinates.
        y: Grid y coordinates.
        field: Percent of LFL on the grid.
        alpha: Opacity of the bands.
    """
    if float(np.nanmax(field)) < LFL_LEVELS[0]:
        return
    ax.contourf(x, y, field, levels=LFL_LEVELS, colors=LFL_COLORS, alpha=alpha)
    if float(np.nanmax(field)) >= 10.0:
        ax.contour(
            x, y, field, levels=[10], colors=[LINE10], linewidths=0.8, linestyles="--"
        )
    if float(np.nanmax(field)) >= 20.0:
        ax.contour(x, y, field, levels=[20], colors=[LINE20], linewidths=1.0)


def peak_text(value: float) -> str:
    """Display text of a flight-path peak: floored at 0.1 and capped at 100.

    Args:
        value: Peak percent of the LFL on a flight path.

    Returns:
        ``"< 0.1 % LFL"``, ``"> 100 % LFL"`` or a rounded value.
    """
    if value < 0.1:
        return "< 0.1 % LFL"
    if value > 100.0:
        return "> 100 % LFL"
    return f"{value:.0f} % LFL" if value >= 1.0 else f"{value:.1f} % LFL"


def north_arrow(ax: Any, x: float = 0.93, y: float = 0.84) -> None:
    """North arrow in axes-fraction coordinates (top right).

    Args:
        ax: Plan axes.
        x: Axes-fraction x of the arrow foot.
        y: Axes-fraction y of the arrow foot.
    """
    ax.annotate(
        "",
        xy=(x, y + 0.11),
        xytext=(x, y),
        xycoords="axes fraction",
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "-|>", "color": "k", "lw": 1.0},
    )
    ax.text(
        x,
        y + 0.125,
        "N",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=7.5,
        fontweight="bold",
    )


def wind_box(ax: Any, wind_from: float, speed: float, label: str | None = None) -> None:
    """Wind arrow and caption box in the top left of a plan panel.

    The arrow points where the wind blows TO.

    Args:
        ax: Plan axes.
        wind_from: Wind direction (FROM), degrees true.
        speed: Wind speed, m/s.
        label: Caption; default ``Wind from NNN deg, u m/s``.
    """
    ang = math.radians(wind_from + 180.0)
    cx, cy, r = 0.12, 0.88, 0.075
    ax.annotate(
        "",
        xy=(cx + r * math.sin(ang), cy + r * math.cos(ang)),
        xytext=(cx - r * math.sin(ang), cy - r * math.cos(ang)),
        xycoords="axes fraction",
        textcoords="axes fraction",
        arrowprops={"arrowstyle": "-|>", "color": NAVY, "lw": 1.6},
    )
    ax.text(
        0.22,
        0.93,
        label or (f"Wind from {wind_from:03.0f} deg\n{speed:.1f} m/s"),
        transform=ax.transAxes,
        fontsize=6.8,
        va="center",
        color=NAVY,
        fontweight="bold",
        bbox={"fc": "white", "ec": "none", "alpha": 0.75, "pad": 1.2},
    )


def km_axes(ax: Any, step: float = 1000.0) -> None:
    """Show metre data as km on both axes.

    Args:
        ax: Axes with metre data.
        step: Tick spacing, m.
    """
    lo, hi = ax.get_xlim()
    ax.set_xticks(np.arange(math.ceil(lo / step) * step, hi + 1, step))
    lo, hi = ax.get_ylim()
    ax.set_yticks(np.arange(math.ceil(lo / step) * step, hi + 1, step))
    ax.set_xticklabels(["%g" % (t / 1000.0) for t in ax.get_xticks()])
    ax.set_yticklabels(["%g" % (t / 1000.0) for t in ax.get_yticks()])


def plan_extent(
    receptors: Receptors, margin_m: float = 150.0
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Common plan extent that contains the tip, helideck and all flight paths.

    Args:
        receptors: Receptor set.
        margin_m: Margin added on every side, m.

    Returns:
        ``((xmin, xmax), (ymin, ymax))`` rounded outward to 100 m.
    """
    pts = np.vstack([receptors.all_paths[:, :2], [[0.0, 0.0]], [receptors.deck[:2]]])
    lo = pts.min(axis=0) - margin_m
    hi = pts.max(axis=0) + margin_m
    r = lambda v, f: float(f(v / 100.0) * 100.0)
    return (
        (r(lo[0], math.floor), r(hi[0], math.ceil)),
        (r(lo[1], math.floor), r(hi[1], math.ceil)),
    )


def plan_base(
    ax: Any,
    receptors: Receptors,
    extent: tuple[tuple[float, float], tuple[float, float]],
    path_bearing_stride_deg: float = 15.0,
    rings: bool = True,
    label_markers: bool = False,
) -> None:
    """Draw the standard plan frame: sector, flight paths, rings, tip and helideck.

    Args:
        ax: Axes.
        receptors: Receptor set.
        extent: Axis limits from :func:`plan_extent`.
        path_bearing_stride_deg: Draw every n-th degree path only (all are evaluated).
        rings: Draw the range rings.
        label_markers: Label the tip and helideck markers.
    """
    geo: PlatformGeometry = receptors.geometry
    cx, cy = float(receptors.deck[0]), float(receptors.deck[1])
    length = geo.flight_paths.length_m
    ax.add_patch(
        Wedge(
            (cx, cy),
            length,
            90.0 - geo.ofs_end_deg,
            90.0 - geo.ofs_end_deg + geo.ofs_width_deg,
            fc=GREEN,
            alpha=0.07,
            ec="none",
        )
    )
    for bearing in receptors.path_bearings:
        phase = (bearing - geo.ofs_start_deg) % path_bearing_stride_deg
        if min(phase, path_bearing_stride_deg - phase) > 1e-6:
            continue
        p = receptors.path_points(float(bearing))
        ax.plot(p[:, 0], p[:, 1], color=GREEN, lw=0.45, alpha=0.8, zorder=3)
    if rings:
        for r, txt in (
            (500.0, "500 m"),
            (1000.0, "1 km"),
            (length, "1 NM" if abs(length - 1852.0) < 1 else f"{length:.0f} m"),
        ):
            if r > length + 1:
                continue
            ax.add_patch(Circle((cx, cy), r, fill=False, ls=":", lw=0.5, ec=GREY))
            a = math.radians(-30.0)
            tx, ty = cx + r * math.cos(a), cy + r * math.sin(a)
            if (
                extent[0][0] < tx < extent[0][1]
                and extent[1][0] < ty < extent[1][1] - 120
            ):
                ax.text(
                    tx,
                    ty,
                    txt,
                    fontsize=5.8,
                    color=GREY,
                    ha="center",
                    va="center",
                    clip_on=True,
                    bbox={"fc": "white", "ec": "none", "alpha": 0.7, "pad": 0.3},
                )
    ax.plot([0, cx], [0, cy], color="#444", lw=2.2, solid_capstyle="round", zorder=4)
    ax.plot(cx, cy, marker="H", ms=7, mfc=BLUE, mec="k", mew=0.6, zorder=6)
    ax.plot(0, 0, marker="*", ms=10, mfc=ORANGE, mec="k", mew=0.6, zorder=6)
    if label_markers:
        ax.annotate(
            "Helideck",
            (cx, cy),
            (cx - 520, cy - 380),
            fontsize=6.5,
            ha="center",
            arrowprops={"arrowstyle": "-", "lw": 0.5},
        )
        ax.annotate(
            "Flare tip",
            (0, 0),
            (330, 330),
            fontsize=6.5,
            ha="center",
            arrowprops={"arrowstyle": "-", "lw": 0.5},
        )
    ax.set_aspect("equal")
    ax.set_xlim(*extent[0])
    ax.set_ylim(*extent[1])
    km_axes(ax)
    north_arrow(ax)


def _overlap(a: Any, b: Any, tol: float = 1.0) -> bool:
    """Whether two display-space boxes overlap by more than ``tol`` pixels."""
    return not (
        a.x1 - tol <= b.x0
        or b.x1 - tol <= a.x0
        or a.y1 - tol <= b.y0
        or b.y1 - tol <= a.y0
    )


def layout_problems(fig: Figure) -> list[str]:
    """Check title, sub-line and legend against the axes after the layout has run.

    Args:
        fig: Figure created by :func:`new_fig`.

    Returns:
        Human-readable problems; an empty list means no overlap and nothing outside the
        figure.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_box = fig.bbox
    texts = [t for t in fig.texts if t.get_gid() in ("headline", "subline")]
    legends = list(fig.legends)
    axes = [ax for ax in fig.axes if ax.get_visible()]
    ax_boxes = [(ax, ax.get_tightbbox(renderer)) for ax in axes]
    problems: list[str] = []
    labelled: list[tuple[str, Any]] = [
        (t.get_gid(), t.get_window_extent(renderer)) for t in texts
    ]
    labelled += [("legend", lg.get_window_extent(renderer)) for lg in legends]
    for name, box in labelled:
        if (
            box.x0 < fig_box.x0 - 1
            or box.x1 > fig_box.x1 + 1
            or box.y0 < fig_box.y0 - 1
            or box.y1 > fig_box.y1 + 1
        ):
            problems.append(f"{name} extends outside the figure")
        for ax, ab in ax_boxes:
            if ab is not None and _overlap(box, ab):
                problems.append(
                    "{} overlaps axes {!r}".format(
                        name,
                        ax.get_title(loc="left") or ax.get_title() or ax.get_label(),
                    )
                )
    for i, (n1, b1) in enumerate(labelled):
        for n2, b2 in labelled[i + 1 :]:
            if _overlap(b1, b2):
                problems.append(f"{n1} overlaps {n2}")
    axis_titles = []
    for ax in axes:
        for artist in (ax.title, ax._left_title, ax._right_title):
            if artist.get_visible() and artist.get_text():
                axis_titles.append(
                    (artist.get_text()[:40], artist.get_window_extent(renderer))
                )
    for i, (n1, b1) in enumerate(axis_titles):
        for n2, b2 in axis_titles[i + 1 :]:
            if _overlap(b1, b2):
                problems.append(f"axes title {n1!r} overlaps axes title {n2!r}")
    return problems


def save(
    fig: Figure, folders: str | Iterable[str], name: str
) -> tuple[list[str], list[str]]:
    """Check the layout and save a figure into every folder.

    Args:
        fig: Figure.
        folders: One folder or several folders.
        name: File name.

    Returns:
        Tuple ``(paths, layout_problems)``.
    """
    if isinstance(folders, str):
        folders = [folders]
    problems = layout_problems(fig)
    paths = []
    for d in folders:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        fig.savefig(path, dpi=DPI, facecolor="white")
        paths.append(path)
    return paths, problems
