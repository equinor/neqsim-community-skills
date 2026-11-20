"""Report illustrations of the study, in the house style of :mod:`.style`.

All figures are 7.2 in wide, share one LFL colour scheme and legend, and carry a title
that states the finding. Every number in a title, sub-line or label is computed from the
study result passed in; nothing is typed in. Concentration peaks shown on the figures are
peaks on the flight paths, capped at ``> 100 % LFL``.

There is deliberately no figure that repeats a table: the case summary is written to
``results.json`` as a table (see :mod:`flare_helideck_dispersion.results`).

Requires matplotlib (declared in the ``figures`` extra of the skill package).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from matplotlib import colormaps
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from . import style as st
from .model import Release
from .receptors import Receptors, angular_difference_deg
from .study import (
    BenchmarkScenario,
    StudyResult,
    helideck_peak_over_directions,
    threshold_key,
)
from .wind import pasquill_by_speed

Extent = tuple[tuple[float, float], tuple[float, float]]
Scenario = tuple[str, float, float]
LFL_CMAP = LinearSegmentedColormap.from_list(
    "lfl", ["#ffffff", "#fff3b0", "#fdb863", "#e34a33", "#7f0000"]
)
FOLDERS = str | Sequence[str]


@dataclass
class FigureRecord:
    """A saved figure with the facts that its title and labels were computed from.

    Attributes:
        name: File name.
        paths: Saved file paths.
        title: Title (the finding).
        sub: Sub-line with case and conditions.
        width_in: Figure width, inches.
        height_in: Figure height, inches.
        problems: Layout problems found by :func:`flare_helideck_dispersion.style.layout_problems`.
        facts: Numbers behind the title, for captions and discussion.
        notes: Informational notes (for example panels without cloud).
        figure: The matplotlib figure (kept for inspection; drop the record to free it).
    """

    name: str
    paths: list[str]
    title: str
    sub: str
    width_in: float
    height_in: float
    problems: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    figure: Any = None


def _finish(
    fig: Any,
    folders: FOLDERS,
    name: str,
    title: str,
    sub: str,
    facts: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> FigureRecord:
    """Add the headline, check the layout, save and return a record."""
    st.headline(fig, title, sub)
    paths, problems = st.save(fig, folders, name)
    w, h = fig.get_size_inches()
    return FigureRecord(
        name,
        paths,
        title,
        sub,
        float(w),
        float(h),
        problems,
        facts or {},
        notes or [],
        fig,
    )


def slug(text: str) -> str:
    """File-name slug of a case name.

    Args:
        text: Case name.

    Returns:
        Lower-case text with non-alphanumerics replaced by underscores.
    """
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()


def top_cases(study: StudyResult, n: int, mode: str = "briggs") -> list[str]:
    """Case names ordered by the peak on any flight path, highest first.

    Args:
        study: Study result.
        n: Maximum number of names.
        mode: Plume mode.

    Returns:
        Up to ``n`` case names.
    """
    names = list(study.releases)
    names.sort(
        key=lambda c: -study.summaries[c]["modes"][mode]["peak_pct_lfl_any_path"]
    )
    return names[:n]


def z_top(receptors: Receptors) -> float:
    """Top of the plan-projection height range (m ASL)."""
    g = receptors.geometry
    path_top = float(receptors.deck[2]) + g.flight_paths.length_m * math.tan(
        math.radians(g.flight_paths.climb_deg)
    )
    return math.ceil((max(path_top, g.tip_height_asl_m) + 60.0) / 50.0) * 50.0


def section_zmax(receptors: Receptors) -> float:
    """Top of the vertical-section height axis (m ASL)."""
    g = receptors.geometry
    path_top = float(receptors.deck[2]) + g.flight_paths.length_m * math.tan(
        math.radians(g.flight_paths.climb_deg)
    )
    return math.ceil((max(path_top, g.tip_height_asl_m) + 40.0) / 50.0) * 50.0


def plan_field(
    release: Release,
    wind_from: float,
    speed: float,
    stability: str,
    receptors: Receptors,
    extent: Extent,
    step_m: float = 25.0,
    mode: str = "briggs",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Projected maximum percent of the LFL over height on a plan grid.

    Args:
        release: Release.
        wind_from: Wind direction (FROM), degrees true.
        speed: Wind speed, m/s.
        stability: Pasquill class.
        receptors: Receptor set (tip position, heights).
        extent: Plan extent.
        step_m: Grid step, m.
        mode: Plume mode.

    Returns:
        Grids ``(X, Y, F)`` with ``F`` the maximum over 10 m to :func:`z_top` m ASL.
    """
    xs = np.arange(extent[0][0], extent[0][1] + 1, step_m)
    ys = np.arange(extent[1][0], extent[1][1] + 1, step_m)
    gx, gy = np.meshgrid(xs, ys)
    tip = receptors.geometry.tip_position
    best = np.zeros(gx.shape)
    for z in np.arange(10.0, z_top(receptors) + 1.0, 15.0):
        pts = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, z)])
        best = np.maximum(
            best,
            release.pct_lfl(pts, wind_from, speed, stability, tip, mode).reshape(
                gx.shape
            ),
        )
    return gx, gy, best


def section_field(
    release: Release,
    wind_from: float,
    speed: float,
    stability: str,
    receptors: Receptors,
    s_range: tuple[float, float] = (-100.0, 1800.0),
    z_range: tuple[float, float] = (2.0, 300.0),
    ds: float = 10.0,
    dz: float = 3.0,
    mode: str = "briggs",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Percent of the LFL in the vertical plane through the tip along the wind.

    Args:
        release: Release.
        wind_from: Wind direction (FROM), degrees true.
        speed: Wind speed, m/s.
        stability: Pasquill class.
        receptors: Receptor set.
        s_range: Distance range along the travel direction, m.
        z_range: Height range ASL, m.
        ds: Distance step, m.
        dz: Height step, m.
        mode: Plume mode.

    Returns:
        Grids ``(S, Z, F)``.
    """
    travel = math.radians(wind_from + 180.0)
    s = np.arange(s_range[0], s_range[1] + 1, ds)
    z = np.arange(z_range[0], z_range[1], dz)
    gs, gz = np.meshgrid(s, z)
    pts = np.column_stack(
        [gs.ravel() * math.sin(travel), gs.ravel() * math.cos(travel), gz.ravel()]
    )
    f = release.pct_lfl(
        pts, wind_from, speed, stability, receptors.geometry.tip_position, mode
    )
    return gs, gz, f.reshape(gs.shape)


def flight_path_peak(
    release: Release,
    wind_from: float,
    speed: float,
    stability: str,
    receptors: Receptors,
    mode: str = "briggs",
) -> float:
    """Peak percent of the LFL on any flight path for one wind.

    Args:
        release: Release.
        wind_from: Wind direction (FROM), degrees true.
        speed: Wind speed, m/s.
        stability: Pasquill class.
        receptors: Receptor set.
        mode: Plume mode.

    Returns:
        Peak over all bearings and distances.
    """
    tip = receptors.geometry.tip_position
    return float(
        release.pct_lfl(
            receptors.all_paths, wind_from, speed, stability, tip, mode
        ).max()
    )


def deck_peak(
    release: Release,
    wind_from: float,
    speed: float,
    stability: str,
    receptors: Receptors,
    mode: str = "briggs",
) -> float:
    """Peak percent of the LFL at the helideck points for one wind."""
    tip = receptors.geometry.tip_position
    return float(
        release.pct_lfl(
            receptors.deck_points, wind_from, speed, stability, tip, mode
        ).max()
    )


def _next_best(
    cells: list[tuple[float, float, float]],
    chosen: list[tuple[float, float]],
    min_sep_deg: float,
) -> tuple[float, float] | None:
    """Highest cell whose direction differs from every chosen one by ``min_sep_deg``."""
    for _value, wd, u in cells:
        if all(
            not (
                angular_difference_deg(wd, c[0]) < min_sep_deg and abs(u - c[1]) < 1e-6
            )
            for c in chosen
        ):
            return wd, u
    return None


def select_scenarios(
    study: StudyResult, case: str, mode: str = "briggs"
) -> list[Scenario]:
    """Choose four informative winds for a case.

    (a) wind blowing from the tip toward the helideck at the second speed bin,
    (b) the worst flight-path condition of the sweep, (c) the worst condition on the
    other flank (at least 60 degrees from (b)), and (d) the most frequent wind.

    Args:
        study: Study result.
        case: Case name.
        mode: Plume mode.

    Returns:
        Four ``(title, wind_from_deg, speed_m_s)`` tuples.
    """
    wind = study.wind
    toward = study.geometry.azimuth_toward_deck_wind_from_deg
    u2 = float(wind.speed_rep_ms[1 if len(wind.speed_rep_ms) > 1 else 0])
    chosen: list[tuple[float, float]] = [(toward, u2)]
    scen: list[Scenario] = [("(a) Wind toward the helideck", toward, u2)]
    pk = study.summaries[case]["modes"][mode]["peak_any_path_condition"]
    a = study.case_arrays(case, mode).any_path.max(axis=1)
    cells = sorted(
        (
            (float(a[i, k]), float(wind.sector_deg[i]), float(wind.speed_rep_ms[k]))
            for i in range(a.shape[0])
            for k in range(a.shape[1])
        ),
        reverse=True,
    )
    wd_b, u_b = float(pk["wind_from_deg"]), float(pk["speed_m_s"])
    chosen.append((wd_b, u_b))
    scen.append(("(b) Worst flight-path condition", wd_b, u_b))
    other = _next_best(
        [c for c in cells if angular_difference_deg(c[1], wd_b) >= 60.0], chosen, 10.0
    )
    if other is not None:
        chosen.append(other)
        scen.append(("(c) Worst on the other flank", other[0], other[1]))
    i, k = np.unravel_index(np.argmax(wind.table_pct), wind.table_pct.shape)
    scen.append(
        (
            "(d) Most frequent wind",
            float(wind.sector_deg[i]),
            float(wind.speed_rep_ms[k]),
        )
    )
    return scen


def _label_scenario(title: str, wd: float, u: float) -> str:
    """Panel title with direction and speed."""
    return f"{title}: {wd:03.0f} deg, {u:.1f} m/s"


# ---------------------------------------------------------------- basis figures
@st.in_house_style
def fig_layout(study: StudyResult, folders: FOLDERS, name: str) -> FigureRecord:
    """Layout plan and elevation of the flare tip, helideck and flight paths.

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.

    Returns:
        Figure record.
    """
    rec, geo = study.receptors, study.geometry
    extent = st.plan_extent(rec)
    fig = st.new_fig(4.2)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.45, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    st.plan_base(ax, rec, extent, label_markers=True)
    toward = geo.azimuth_toward_deck_wind_from_deg
    ax.annotate(
        f"Wind from {toward:03.0f} deg carries\nunignited gas toward the deck",
        (-0.04 * (extent[0][1] - extent[0][0]), -0.03 * (extent[1][1] - extent[1][0])),
        (
            extent[0][1] - 0.28 * (extent[0][1] - extent[0][0]),
            extent[1][0] + 0.30 * (extent[1][1] - extent[1][0]),
        ),
        fontsize=6.5,
        color=st.RED,
        ha="center",
        arrowprops={"arrowstyle": "-|>", "color": st.RED, "lw": 0.9},
    )
    fp = geo.flight_paths
    ax.text(
        extent[0][0] + 40,
        extent[1][0] + 40,
        f"Obstacle-free sector {geo.ofs_start_deg:.0f}-{geo.ofs_end_deg:.0f} deg T (shaded); paths every 15 deg shown,\nevaluated every {fp.bearing_step_deg:.0f} deg; {fp.climb_deg:.0f} deg climb/descent to {fp.length_m:.0f} m",
        fontsize=5.8,
        color=st.GREEN,
        va="bottom",
        bbox={"fc": "white", "ec": "none", "alpha": 0.8, "pad": 0.8},
    )
    ax.set_xlabel("East of flare tip (km)")
    ax.set_ylabel("North of flare tip (km)")
    ax.set_title("Plan, true north up")
    bx = fig.add_subplot(gs[0, 1])
    d_deck = geo.helideck_distance_m
    zmax = section_zmax(rec)
    bearing = geo.helideck_azimuth_from_tip_deg
    if not rec.in_obstacle_free_sector(bearing):
        bearing = geo.ofs_start_deg + 0.5 * geo.ofs_width_deg
    along = math.cos(math.radians(bearing - geo.helideck_azimuth_from_tip_deg))
    dp = np.arange(0.0, fp.length_m + 0.1, fp.distance_step_m)
    xs_end = d_deck + fp.length_m * abs(along)
    xspan = xs_end * 1.05 + 100.0
    bx.axhline(0, color=st.SEA, lw=1.6)
    bx.plot([0, 0], [0, geo.tip_height_asl_m], color="#444", lw=3)
    bx.plot(0, geo.tip_height_asl_m, marker="*", ms=10, mfc=st.ORANGE, mec="k", mew=0.6)
    bx.plot([d_deck, d_deck], [0, geo.helideck_height_asl_m], color="#444", lw=3)
    bx.plot(
        d_deck,
        geo.helideck_height_asl_m,
        marker="H",
        ms=7,
        mfc=st.BLUE,
        mec="k",
        mew=0.6,
    )
    z_path = rec.deck[2] + dp * math.tan(math.radians(fp.climb_deg))
    bx.plot(d_deck + dp * along, z_path, color=st.GREEN, lw=1.5)
    bx.annotate(
        f"Flare tip {geo.tip_height_asl_m:.0f} m ASL\n({study.settings.params.tilt_deg:.0f} deg inclination)",
        (0, geo.tip_height_asl_m),
        (0.07 * xspan, 0.86 * zmax),
        fontsize=6.3,
        arrowprops={"arrowstyle": "-", "lw": 0.5},
    )
    bx.annotate(
        f"Helideck {geo.helideck_height_asl_m:.0f} m ASL\n{d_deck:.0f} m from tip",
        (d_deck, geo.helideck_height_asl_m),
        (d_deck + 0.12 * xspan, 0.06 * zmax),
        fontsize=6.3,
        arrowprops={"arrowstyle": "-", "lw": 0.5},
    )
    bx.text(
        d_deck + 0.50 * fp.length_m * abs(along),
        float(z_path[len(z_path) // 2]) - 0.16 * zmax,
        f"{fp.climb_deg:.0f} deg flight path\nalong {bearing:03.0f} deg T",
        fontsize=6.3,
        color=st.GREEN,
    )
    bx.set_xlim(-100, xspan)
    bx.set_ylim(-5, zmax)
    bx.set_xlabel("Distance from tip along the tip-helideck axis (m)")
    bx.set_ylabel("Height above sea level (m)")
    bx.set_title("Elevation (vertical scale exaggerated)")
    dz = geo.tip_height_asl_m - geo.helideck_height_asl_m
    facts = {
        "distance_m": d_deck,
        "tip_above_deck_m": dz,
        "azimuth_deg": geo.helideck_azimuth_from_tip_deg,
    }
    return _finish(
        fig,
        folders,
        name,
        "The helideck is {:.0f} m from the flare tip, {:.0f} m {}, on bearing {:03.0f} deg T".format(
            d_deck,
            abs(dz),
            "lower" if dz >= 0 else "higher",
            geo.helideck_azimuth_from_tip_deg,
        ),
        "Generic platform layout; positions and the obstacle-free sector are inputs, not survey data",
        facts,
    )


@st.in_house_style
def fig_wind(study: StudyResult, folders: FOLDERS, name: str) -> FigureRecord:
    """Wind rose, joint frequency table and speed distribution.

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.

    Returns:
        Figure record.
    """
    wind, geo = study.wind, study.geometry
    m = wind.table_pct
    bins = wind.speed_bins
    n = len(wind.sectors)
    toward = geo.azimuth_toward_deck_wind_from_deg
    width = wind.sector_width_deg
    toward_idx = int(((toward + 0.5 * width) % 360.0) // width)
    toward_pct = float(wind.sector_frequency_pct()[toward_idx])
    fig = st.new_fig(6.4)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 0.85], width_ratios=[1.0, 1.15])
    ax = fig.add_subplot(gs[0, 0], projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    th = np.radians(wind.sector_deg)
    bottom = np.zeros(n)
    cmap = colormaps["viridis_r"](np.linspace(0.05, 0.95, len(bins)))
    for k, b in enumerate(bins):
        ax.bar(
            th,
            m[:, k],
            width=np.radians(0.85 * width),
            bottom=bottom,
            color=cmap[k],
            edgecolor="white",
            lw=0.2,
            label=b,
        )
        bottom += m[:, k]
    ax.annotate(
        "",
        xy=(math.radians(toward), bottom.max() * 1.02),
        xytext=(0, 0),
        arrowprops={"arrowstyle": "-", "color": st.RED, "lw": 1.0, "ls": "--"},
    )
    ax.text(
        math.radians(toward),
        bottom.max() * 1.14,
        f"{toward:03.0f} deg:\nflare to deck",
        color=st.RED,
        fontsize=6,
        ha="center",
    )
    ax.tick_params(axis="x", labelsize=6.5)
    ax.tick_params(axis="y", labelsize=5)
    ax.set_title("Wind rose (from), % of hours", pad=8)
    ax.legend(
        title="m/s",
        fontsize=5.5,
        title_fontsize=6,
        ncol=6,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        frameon=False,
        columnspacing=0.7,
        handlelength=0.9,
    )
    bx = fig.add_subplot(gs[0, 1])
    im = bx.imshow(m.T, aspect="auto", cmap="YlGnBu", origin="lower")
    bx.set_xticks(range(n))
    bx.set_xticklabels(wind.sectors, rotation=90, fontsize=6)
    bx.set_yticks(range(len(bins)))
    bx.set_yticklabels(bins, fontsize=6)
    bx.set_xlabel("Wind from sector")
    bx.set_ylabel("10 m speed (m/s)")
    bx.set_title("Joint frequency (% of hours)")
    bx.add_patch(
        Rectangle(
            (toward_idx - 0.5, -0.5), 1.0, len(bins), fill=False, ec=st.RED, lw=1.2
        )
    )
    cb = fig.colorbar(im, ax=bx, fraction=0.05, pad=0.02)
    cb.ax.tick_params(labelsize=6)
    cx = fig.add_subplot(gs[1, :])
    freq = wind.speed_bin_frequency_pct()
    cum = np.cumsum(freq)
    cx.bar(range(len(bins)), freq, color="#2c7fb8", width=0.7)
    for i, v in enumerate(freq):
        cx.text(i, v + 0.01 * freq.max(), f"{v:.1f}", ha="center", fontsize=6)
    cx.set_xticks(range(len(bins)))
    cx.set_xticklabels(bins)
    cx.set_xlabel("10 m wind speed bin (m/s)")
    cx.set_ylabel("% of hours")
    cx.set_ylim(0, freq.max() * 1.15)
    cx2 = cx.twinx()
    cx2.plot(range(len(bins)), cum, color=st.RED, marker="o", ms=2.5, lw=1.0)
    cx2.set_ylabel("Cumulative %", color=st.RED)
    cx2.set_ylim(0, 105)
    cx2.spines["right"].set_visible(True)
    below4 = float(freq[wind.speed_rep_ms < 4.0].sum())
    cx.set_title(
        f"Speed distribution: {freq[0]:.1f} % of hours in bin {bins[0]}, {below4:.1f} % below 4 m/s (representative speeds)"
    )
    n_hours = wind.metadata.get("n_hours")
    source = wind.metadata.get("source", "supplied wind table")
    sub = "{}{}; 10 m wind speed".format(
        source,
        (
            ", {} hourly records".format(format(n_hours, ",").replace(",", " "))
            if n_hours
            else ""
        ),
    )
    return _finish(
        fig,
        folders,
        name,
        f"Wind blows from the flare toward the deck only {toward_pct:.1f} % of the time",
        sub,
        {
            "toward_deck_sector": wind.sectors[toward_idx],
            "toward_deck_pct": toward_pct,
            "pct_below_4ms": below4,
        },
    )


@st.in_house_style
def fig_source_terms(
    study: StudyResult,
    folders: FOLDERS,
    name: str,
    psv_table: Sequence[Mapping[str, Any]] | None = None,
) -> FigureRecord:
    """Tip jet source terms of all cases, and optionally PSV sizing.

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.
        psv_table: Optional rows with ``name``, ``relief_load_kg_s``, ``rated_kg_s``,
            ``required_area_cm2`` and ``selected_area_cm2``.

    Returns:
        Figure record.
    """
    names = list(study.releases)
    v = np.array([study.releases[c].tip["v_exit_ms"] for c in names])
    r = np.array([study.releases[c].tip["rho_ratio_to_air"] for c in names])
    fig = st.new_fig(5.6 if psv_table else 3.2)
    if psv_table:
        gs = fig.add_gridspec(2, 2)
        x = np.arange(len(psv_table))
        labels = [str(p["name"]) for p in psv_table]
        load = [p["relief_load_kg_s"] for p in psv_table]
        rated = [p["rated_kg_s"] for p in psv_table]
        a = fig.add_subplot(gs[0, 0])
        a.bar(x - 0.19, load, 0.38, color="#2c7fb8", label="Relief load")
        a.bar(x + 0.19, rated, 0.38, color=st.ORANGE, label="API 520 rated capacity")
        for i in range(len(x)):
            a.text(
                x[i] + 0.19,
                rated[i] * 1.02,
                "%.0f %%" % (100 * load[i] / rated[i]),
                ha="center",
                fontsize=6.2,
            )
        a.set_xticks(x)
        a.set_xticklabels(labels, fontsize=6.2, rotation=20, ha="right")
        a.set_ylabel("kg/s")
        a.set_ylim(0, max(rated) * 1.3)
        a.set_title("Load vs rated capacity (utilisation)")
        a.legend(loc="upper left", frameon=False)
        b = fig.add_subplot(gs[0, 1])
        b.bar(
            x - 0.19,
            [p["required_area_cm2"] for p in psv_table],
            0.38,
            color="#2c7fb8",
            label="Required (API 520)",
        )
        b.bar(
            x + 0.19,
            [p["selected_area_cm2"] for p in psv_table],
            0.38,
            color=st.ORANGE,
            label="Selected (API 526)",
        )
        b.set_xticks(x)
        b.set_xticklabels(labels, fontsize=6.2, rotation=20, ha="right")
        b.set_ylabel("cm2 per valve")
        b.set_ylim(0, max(p["selected_area_cm2"] for p in psv_table) * 1.3)
        b.set_title("Effective orifice area")
        b.legend(loc="upper left", frameon=False)
        c = fig.add_subplot(gs[1, :])
    else:
        c = fig.add_subplot(1, 1, 1)
    c.bar(
        range(len(names)),
        v,
        color=[st.case_color(i) for i in range(len(names))],
        width=0.65,
    )
    c.set_xticks(range(len(names)))
    c.set_xticklabels(names, rotation=20, ha="right")
    c.set_ylabel("Notional jet velocity (m/s)")
    c.set_ylim(0, v.max() * 1.2)
    c2 = c.twinx()
    c2.plot(range(len(names)), r, color=st.RED, marker="D", ms=3.5, lw=1.0)
    c2.axhline(1.0, color=st.RED, lw=0.6, ls=":")
    c2.set_ylim(0, max(r.max() * 1.25, 1.3))
    c2.text(
        len(names) - 0.5, 1.02, "air", color=st.RED, fontsize=6, ha="right", va="bottom"
    )
    c2.set_ylabel("Gas density / air density", color=st.RED)
    c2.spines["right"].set_visible(True)
    c.set_title("Flare-tip jet of each release case, with gas density relative to air")
    title = (
        f"The {len(names)} release cases give tip jets of {v.min():.0f} to {v.max():.0f} m/s "
        f"and gas densities of {r.min():.2f} to {r.max():.2f} times air"
    )
    if psv_table:
        title = "Relief valves are rated for {:.0f}-{:.0f} kg/s; the cases give tip jets of {:.0f}-{:.0f} m/s".format(
            min(p["rated_kg_s"] for p in psv_table),
            max(p["rated_kg_s"] for p in psv_table),
            v.min(),
            v.max(),
        )
    return _finish(
        fig,
        folders,
        name,
        title,
        "Choked-flow notional nozzle; the rated capacity of the selected orifice (or the blowdown peak) is the release rate",
        {
            "v_min": float(v.min()),
            "v_max": float(v.max()),
            "rho_ratio_min": float(r.min()),
            "rho_ratio_max": float(r.max()),
        },
    )


# ---------------------------------------------------------------- results figures
@st.in_house_style
def fig_footprints(
    study: StudyResult,
    case: str,
    folders: FOLDERS,
    name: str,
    scenarios: Sequence[Scenario] | None = None,
    mode: str = "briggs",
) -> FigureRecord:
    """Plan footprints of the flammable cloud for four winds.

    Args:
        study: Study result.
        case: Case name.
        folders: Output folder(s).
        name: File name.
        scenarios: ``(title, wind_from_deg, speed_m_s)`` panels; default
            :func:`select_scenarios`.
        mode: Plume mode.

    Returns:
        Figure record.
    """
    rec = study.receptors
    release = study.releases[case]
    scen = list(scenarios) if scenarios else select_scenarios(study, case, mode)
    extent = st.plan_extent(rec)
    rows = (len(scen) + 1) // 2
    fig = st.new_fig(3.95 * rows)
    gs = fig.add_gridspec(rows, 2)
    fp_peaks, d_peaks, notes = [], [], []
    for k, (t, wd, u) in enumerate(scen):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        stab = pasquill_by_speed(u, study.settings.stability_scheme)
        gx, gy, f = plan_field(release, wd, u, stab, rec, extent, mode=mode)
        st.lfl_contours(ax, gx, gy, f)
        st.plan_base(ax, rec, extent, label_markers=(k == 0))
        st.wind_box(ax, wd, u, f"Wind from {wd:03.0f} deg\n{u:.1f} m/s, class {stab}")
        fp = flight_path_peak(release, wd, u, stab, rec, mode)
        dk = deck_peak(release, wd, u, stab, rec, mode)
        fp_peaks.append(fp)
        d_peaks.append(dk)
        if float(f.max()) < st.LFL_LEVELS[0]:
            notes.append(f"panel {t} has no cloud above {st.LFL_LEVELS[0]:g} % LFL")
            ax.text(
                0.5,
                0.5,
                f"no cloud above {st.LFL_LEVELS[0]:g} % LFL",
                transform=ax.transAxes,
                ha="center",
                fontsize=6.5,
                color=st.GREY,
            )
        ax.set_title(t, fontsize=7.5, loc="left")
        ax.text(
            0.02,
            0.02,
            f"peak on flight paths: {st.peak_text(fp)}",
            transform=ax.transAxes,
            fontsize=6.3,
            bbox={"fc": "white", "ec": "none", "alpha": 0.8, "pad": 1.0},
        )
        if k % 2 == 0:
            ax.set_ylabel("North of tip (km)")
        if k // 2 == rows - 1:
            ax.set_xlabel("East of tip (km)")
    st.lfl_legend(fig)
    n_fp = sum(1 for p in fp_peaks if p >= 20.0)
    n_deck = sum(1 for p in d_peaks if p >= 20.0)
    tip = release.tip
    sub = "Unignited release {}: {:.0f} kg/s, tip jet {:.0f} m/s, gas density {:.2f} x air; projected maximum % LFL between 10 and {:.0f} m ASL".format(
        case, release.mdot, tip["v_exit_ms"], tip["rho_ratio_to_air"], z_top(rec)
    )
    return _finish(
        fig,
        folders,
        name,
        f"{case}: the cloud reaches 20 % LFL on the flight paths in {n_fp} of {len(scen)} winds shown, at the helideck in {n_deck}",
        sub,
        {
            "case": case,
            "flight_path_peaks": fp_peaks,
            "helideck_peaks": d_peaks,
            "scenarios": [list(s) for s in scen],
        },
        notes,
    )


@st.in_house_style
def fig_sections(
    study: StudyResult,
    folders: FOLDERS,
    name: str,
    scenarios: Sequence[tuple[str, str, float, float]] | None = None,
    mode: str = "briggs",
) -> FigureRecord:
    """Vertical sections through the plume centre plane (vertical scale exaggerated).

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.
        scenarios: ``(panel_label, case, wind_from_deg, speed_m_s)`` panels; default
            the toward-deck and worst flight-path winds of the two highest cases.
        mode: Plume mode.

    Returns:
        Figure record.
    """
    rec, geo = study.receptors, study.geometry
    if scenarios is None:
        panels = []
        for case in top_cases(study, 2, mode):
            sc = select_scenarios(study, case, mode)
            for _t, wd, u in sc[:2]:
                panels.append((case, wd, u))
        scenarios = [
            (
                "({}) {}, wind {:03.0f} deg, {:.1f} m/s".format(
                    "abcdefgh"[i], c, wd, u
                ),
                c,
                wd,
                u,
            )
            for i, (c, wd, u) in enumerate(panels)
        ]
    rows = (len(scenarios) + 1) // 2
    fig = st.new_fig(2.7 * rows)
    gs = fig.add_gridspec(rows, 2, hspace=0.12)
    zmax = section_zmax(rec)
    s_max = round(0.97 * geo.flight_paths.length_m / 100.0) * 100.0
    fp_peaks, d_peaks = [], []
    for k, (label, case, wd, u) in enumerate(scenarios):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        release = study.releases[case]
        stab = pasquill_by_speed(u, study.settings.stability_scheme)
        travel = math.radians(wd + 180.0)
        gs_, gz, f = section_field(
            release, wd, u, stab, rec, (-100.0, s_max), (2.0, zmax), mode=mode
        )
        st.lfl_contours(ax, gs_, gz, f)
        ax.axhline(0, color=st.SEA, lw=1.4)
        ax.plot([0, 0], [0, geo.tip_height_asl_m], color="#444", lw=2.5)
        ax.plot(
            0, geo.tip_height_asl_m, marker="*", ms=8, mfc=st.ORANGE, mec="k", mew=0.5
        )
        dd = float(rec.deck[0] * math.sin(travel) + rec.deck[1] * math.cos(travel))
        if dd > 0:
            ax.plot(
                dd,
                rec.deck[2],
                marker="H",
                ms=6,
                mfc=st.BLUE,
                mec="k",
                mew=0.5,
                zorder=5,
            )
        pb = (wd + 180.0) % 360.0
        if rec.in_obstacle_free_sector(pb):
            path = rec.path_points(pb)
            sp = path[:, 0] * math.sin(travel) + path[:, 1] * math.cos(travel)
            ax.plot(
                sp,
                path[:, 2],
                color=st.GREEN,
                lw=1.4,
                label=f"flight path {pb:03.0f} deg T",
            )
            ax.legend(loc="upper right", frameon=False, fontsize=6)
        ax.set_xlim(-100, s_max)
        ax.set_ylim(0, zmax)
        ax.set_aspect(st.VERTICAL_EXAGGERATION, adjustable="box")
        ax.set_title(label, fontsize=7.5, loc="left")
        if k % 2 == 0:
            ax.set_ylabel("Height ASL (m)")
        if k // 2 == rows - 1:
            ax.set_xlabel("Distance downwind of tip (m)")
        fp_peaks.append(flight_path_peak(release, wd, u, stab, rec, mode))
        d_peaks.append(deck_peak(release, wd, u, stab, rec, mode))
    st.lfl_legend(fig)
    n_fp = sum(1 for p in fp_peaks if p >= 20.0)
    n_deck = sum(1 for p in d_peaks if p >= 20.0)
    return _finish(
        fig,
        folders,
        name,
        f"Vertical sections: the cloud reaches 20 % LFL on a flight path in {n_fp} of {len(scenarios)} winds shown and at the helideck in {n_deck}",
        f"Plume centre plane along the wind; vertical scale exaggerated {st.VERTICAL_EXAGGERATION:g} times; helideck marker projected onto the plane",
        {
            "flight_path_peaks": fp_peaks,
            "helideck_peaks": d_peaks,
            "vertical_exaggeration": st.VERTICAL_EXAGGERATION,
        },
    )


@st.in_house_style
def fig_heatmaps(
    study: StudyResult, folders: FOLDERS, name: str, mode: str = "briggs"
) -> FigureRecord:
    """Worst flight-path exposure by wind direction and speed.

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.
        mode: Plume mode.

    Returns:
        Figure record.
    """
    wind = study.wind
    cases = top_cases(study, 4, mode)
    rows = (len(cases) + 1) // 2
    fig = st.new_fig(3.3 * rows)
    gs = fig.add_gridspec(rows, 2)
    norm = LogNorm(vmin=1, vmax=300)
    im = None
    exposed = np.zeros((len(wind.sectors), len(wind.speed_bins)), dtype=bool)
    deck_max = 0.0
    for k, case in enumerate(cases):
        ax = fig.add_subplot(gs[k // 2, k % 2])
        arr = study.case_arrays(case, mode)
        a = arr.any_path.max(axis=1)
        exposed |= a >= 20.0
        deck_max = max(deck_max, float(arr.deck.max()))
        im = ax.imshow(
            np.clip(a.T, 0.5, 300),
            aspect="auto",
            origin="lower",
            cmap=LFL_CMAP,
            norm=norm,
        )
        ax.set_xticks(range(len(wind.sectors)))
        ax.set_xticklabels(wind.sectors, rotation=90, fontsize=6)
        ax.set_yticks(range(len(wind.speed_bins)))
        ax.set_yticklabels(wind.speed_bins, fontsize=6)
        for i in range(a.shape[0]):
            for kk in range(a.shape[1]):
                if a[i, kk] >= 20.0:
                    ax.text(
                        i,
                        kk,
                        f"{a[i, kk]:.0f}",
                        ha="center",
                        va="center",
                        fontsize=5,
                        color="white" if a[i, kk] > 60 else "k",
                    )
        ax.set_title("({}) {}".format("abcd"[k], case), fontsize=7.5, loc="left")
        if k % 2 == 0:
            ax.set_ylabel("10 m wind speed (m/s)")
        if k // 2 == rows - 1:
            ax.set_xlabel("Wind from sector")
    cb = fig.colorbar(im, ax=fig.axes, shrink=0.55, pad=0.02)
    cb.set_label("worst % LFL on any flight path (log scale)", fontsize=6.5)
    cb.ax.tick_params(labelsize=6)
    sec_idx = sorted(set(np.nonzero(exposed)[0].tolist()))
    spd_idx = sorted(set(np.nonzero(exposed)[1].tolist()))
    if sec_idx:
        secs = [wind.sectors[i] for i in sec_idx]
        sec_text = (
            ", ".join(secs)
            if len(secs) <= 6
            else f"{len(secs)} of {len(wind.sectors)} sectors"
        )
        title = f"Exposure of 20 % LFL or more needs wind from {sec_text} and speeds up to the {wind.speed_bins[spd_idx[-1]]} m/s bin"
    else:
        title = "No wind direction or speed gives 20 % LFL or more on a flight path"
    return _finish(
        fig,
        folders,
        name,
        title,
        f"Worst % LFL on any flight path per sector and speed bin; numbers where 20 % LFL or more; helideck peak over all cells: {deck_max:.2f} % LFL",
        {
            "exposed_sectors": [wind.sectors[i] for i in sec_idx],
            "helideck_peak_all_cells": deck_max,
        },
    )


@st.in_house_style
def fig_polar(
    study: StudyResult, folders: FOLDERS, name: str, mode: str = "briggs"
) -> FigureRecord:
    """Worst flight-path exposure against the wind-from direction.

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.
        mode: Plume mode.

    Returns:
        Figure record.
    """
    wind = study.wind
    cases = top_cases(study, 3, mode)
    fig = st.new_fig(3.5)
    sel_bins = sorted({0, 1, 2, int(np.argmin(np.abs(wind.speed_rep_ms - 8.0)))})
    cols = ["#7f0000", "#e34a33", "#fdae61", "#2c7fb8"]
    th = np.radians(wind.sector_deg)
    n_exposed = []
    for k, case in enumerate(cases):
        ax = fig.add_subplot(1, len(cases), k + 1, projection="polar")
        a = study.case_arrays(case, mode).any_path
        n_exposed.append(int(np.sum(a.max(axis=(1, 2)) >= 20.0)))
        for c, kk in zip(cols, sel_bins):
            v = a[:, :, kk].max(axis=1)
            ax.plot(
                np.r_[th, th[0]],
                np.r_[v, v[0]],
                color=c,
                lw=1.1,
                label=wind.speed_bins[kk] + " m/s",
            )
        ax.plot(
            np.linspace(0, 2 * np.pi, 100),
            np.full(100, 20.0),
            color="k",
            lw=0.7,
            ls="--",
        )
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rmax(120)
        ax.set_rticks([20, 60, 100])
        ax.set_yticklabels(["20", "60", "100"], fontsize=5.5)
        ax.tick_params(axis="x", labelsize=6)
        ax.set_title(case, pad=6, fontsize=7.5)
    h, lab = fig.axes[0].get_legend_handles_labels()
    st.bottom_legend(
        fig,
        h + [Line2D([0], [0], color="k", ls="--", lw=0.7)],
        lab + ["20 % LFL"],
        len(lab) + 1,
        6.5,
    )
    best = int(np.argmax(n_exposed))
    return _finish(
        fig,
        folders,
        name,
        f"Flight-path exposure by wind direction: {cases[best]} reaches 20 % LFL from {n_exposed[best]} of {len(wind.sectors)} sectors at some speed",
        "Worst % LFL on any flight path vs wind-from direction, radial axis capped at 120 %",
        {"sectors_exposed": dict(zip(cases, n_exposed))},
    )


@st.in_house_style
def fig_exceedance(
    study: StudyResult, folders: FOLDERS, name: str, mode: str = "briggs"
) -> FigureRecord:
    """Conditional exceedance hours by case for the 10 and 20 percent LFL criteria.

    Args:
        study: Study result.
        folders: Output folder(s).
        name: File name.
        mode: Plume mode.

    Returns:
        Figure record.
    """
    cases = list(study.releases)
    keys = [threshold_key(t) for t in study.settings.thresholds_pct_lfl]
    thr = [k for k in ("10", "20") if k in keys] or keys[:2]
    fig = st.new_fig(3.7)
    gs = fig.add_gridspec(1, len(thr), wspace=0.08)
    x = np.arange(len(cases))
    data = {
        t: {
            w: [
                study.summaries[c]["modes"][mode]["exceed_pct_hours"][t][w]
                for c in cases
            ]
            for w in ("any_path", "into_wind_path", "helideck")
        }
        for t in thr
    }
    ymax = max(max(max(v) for v in d.values()) for d in data.values())
    first = None
    for k, t in enumerate(thr):
        ax = fig.add_subplot(gs[0, k], sharey=first)
        first = first or ax
        ax.bar(
            x - 0.27,
            data[t]["any_path"],
            0.27,
            color=st.ORANGE,
            label="Any flight path bearing",
        )
        ax.bar(
            x, data[t]["into_wind_path"], 0.27, color=st.GREEN, label="Into-wind path"
        )
        ax.bar(x + 0.27, data[t]["helideck"], 0.27, color=st.BLUE, label="Helideck")
        ax.set_xticks(x)
        ax.set_xticklabels(cases, rotation=45, ha="right", fontsize=6.5)
        ax.set_title(f">= {t} % LFL", loc="left")
        ax.set_ylim(0, max(ymax * 1.15, 1.0))
        if k == 0:
            ax.set_ylabel("% of hours, given a release")
        else:
            ax.tick_params(labelleft=False)
    st.bottom_legend(
        fig,
        [Rectangle((0, 0), 1, 1, fc=c) for c in (st.ORANGE, st.GREEN, st.BLUE)],
        ["Any flight path bearing", "Into-wind path", "Helideck"],
        3,
        6.8,
    )
    last = thr[-1]
    iw = max(data[last]["into_wind_path"])
    dk = max(data[last]["helideck"])
    if iw == 0.0 and dk == 0.0:
        note = "Into-wind path and helideck: 0 % in every case"
    else:
        note = f"Maximum over cases: into-wind path {iw:.2f} %, helideck {dk:.2f} %"
    first.text(
        0.02,
        0.97,
        note,
        transform=first.transAxes,
        ha="left",
        va="top",
        fontsize=6.2,
        color=st.GREEN,
    )
    worst = int(np.argmax(data[last]["any_path"]))
    return _finish(
        fig,
        folders,
        name,
        "Flight paths exceed {} % LFL in up to {:.1f} % of hours ({}); into-wind path {:.1f} %, helideck {:.1f} %".format(
            last, data[last]["any_path"][worst], cases[worst], iw, dk
        ),
        "Wind-climate weighted exceedance, conditional on an unignited release being ongoing (not an annual frequency)",
        {
            "thresholds": thr,
            "worst_case": cases[worst],
            "max_any_path_pct": data[last]["any_path"][worst],
            "max_into_wind_pct": iw,
            "max_helideck_pct": dk,
        },
    )


@st.in_house_style
def fig_benchmark(
    study: StudyResult,
    scenarios: Sequence[BenchmarkScenario],
    folders: FOLDERS,
    name: str,
    criterion_pct: float = 20.0,
) -> FigureRecord:
    """Peak helideck percent of the LFL for benchmark scenarios on a log axis.

    Args:
        study: Study result (receptors and settings).
        scenarios: Benchmark scenarios; the model values are computed here.
        folders: Output folder(s).
        name: File name.
        criterion_pct: Criterion drawn as a vertical line, percent of the LFL.

    Returns:
        Figure record.
    """
    peaks = [
        helideck_peak_over_directions(s, study.receptors, study.settings)
        for s in scenarios
    ]
    vals = np.array([max(p["peak_pct_lfl"], 1e-5) for p in peaks])
    fig = st.new_fig(max(3.0, 2.0 + 0.4 * len(scenarios)))
    ax = fig.add_subplot(1, 1, 1)
    y = np.arange(len(scenarios))[::-1]
    ax.barh(y, vals, color=st.BLUE, height=0.55)
    ax.set_xscale("log")
    ax.set_xlim(1e-5, 100)
    ax.axvline(criterion_pct, color="k", ls="--", lw=0.8)
    ax.axvline(10.0, color=st.GREY, ls=":", lw=0.8)
    ax.text(
        criterion_pct * 0.9,
        0.98,
        f"{criterion_pct:g} % LFL",
        transform=ax.get_xaxis_transform(),
        fontsize=6.5,
        ha="right",
        va="top",
    )
    ax.set_yticks(y)
    ax.set_yticklabels([s.label for s in scenarios])
    for yy, v in zip(y, vals):
        ax.text(
            max(v, 2e-5) * 1.5,
            yy,
            "<0.00001 %" if v <= 1.01e-5 else f"{v:.2g} %",
            va="center",
            fontsize=6.3,
        )
    ax.set_xlabel(
        "Peak % LFL at the helideck over all wind directions (model, log scale)"
    )
    worst = int(np.argmax(vals))
    refs = sorted({s.reference_source for s in scenarios if s.reference_source})
    sub = "Worst case {}: {:.2f} % LFL{}".format(
        scenarios[worst].label,
        vals[worst],
        "; reference: {}".format("; ".join(refs)) if refs else "",
    )
    title = (
        f"Benchmark: helideck peak stays below {vals.max():.1f} % LFL in all {len(scenarios)} scenarios, far below the {criterion_pct:g} % criterion"
        if vals.max() < criterion_pct
        else f"Benchmark: the helideck peak reaches {vals.max():.0f} % LFL in {scenarios[worst].label}, above the {criterion_pct:g} % criterion"
    )
    return _finish(
        fig,
        folders,
        name,
        title,
        sub,
        {
            "peaks_pct_lfl": {s.label: float(v) for s, v in zip(scenarios, vals)},
            "worst": scenarios[worst].label,
            "worst_pct_lfl": float(vals[worst]),
        },
    )


_TORNADO_LABELS = {
    "tilt_deg": "Tip inclination",
    "sigma0_divisor": "Spread sigma0 = dh/x, x",
    "wind_exponent": "Wind exponent",
    "mass_flow_scale": "Release rate",
}


def _tornado_label(entry: Mapping[str, Any]) -> str:
    """Short tornado label with the varied range."""
    key = entry["parameter_key"]
    return "{} {:g}-{:g}".format(
        _TORNADO_LABELS.get(key, key),
        entry["low_input"],
        entry["high_input"],
    )


@st.in_house_style
def fig_tornado(
    sensitivity: Mapping[str, Any], folders: FOLDERS, name: str
) -> FigureRecord:
    """Tornado and Monte Carlo of the 20 percent LFL flight-path exceedance.

    The x axis starts at zero and is shared between panels so that small effects are
    not magnified.

    Args:
        sensitivity: Result of :func:`flare_helideck_dispersion.sensitivity.run_sensitivity`.
        folders: Output folder(s).
        name: File name.

    Returns:
        Figure record.
    """
    cases = [c for c in sensitivity if c != "tilt_scan" and "tornado" in sensitivity[c]]
    cases = cases[:3]
    allv = []
    for c in cases:
        e = sensitivity[c]
        allv.append(e["base"]["hours_ge20_pct"])
        for t in e["tornado"]:
            allv += [t["hours20_low"], t["hours20_high"]]
    xmax = max(allv) * 1.15 if max(allv) > 0 else 1.0
    fig = st.new_fig(3.6)
    gs = fig.add_gridspec(1, len(cases), wspace=0.1)
    first = None
    for k, c in enumerate(cases):
        ax = fig.add_subplot(gs[0, k], sharex=first)
        first = first or ax
        e = sensitivity[c]
        base = e["base"]["hours_ge20_pct"]
        rows = e["tornado"][::-1]
        for i, t in enumerate(rows):
            ax.barh(
                i,
                t["hours20_high"] - base,
                left=base,
                color="#e34a33",
                alpha=0.9,
                height=0.55,
            )
            ax.barh(
                i,
                t["hours20_low"] - base,
                left=base,
                color="#2c7fb8",
                alpha=0.9,
                height=0.55,
            )
        ax.axvline(base, color="k", lw=0.8)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(
            [_tornado_label(t) for t in rows] if k == 0 else [], fontsize=6.3
        )
        mc = e.get("hours_ge20_pct")
        suffix = (
            ", Monte Carlo P10-P90 {:.1f}-{:.1f} %".format(mc["p10"], mc["p90"])
            if isinstance(mc, dict)
            else ""
        )
        ax.set_title(
            "{}\nbase {:.1f} %{}".format(
                c, base, suffix.replace(", Monte Carlo", "; Monte Carlo")
            ),
            fontsize=7,
            loc="left",
        )
        ax.set_xlim(0, xmax)
        ax.set_xlabel("% of hours >= 20 % LFL on a flight path")
    st.bottom_legend(
        fig,
        [Rectangle((0, 0), 1, 1, fc="#2c7fb8"), Rectangle((0, 0), 1, 1, fc="#e34a33")],
        ["low input", "high input"],
        2,
        6.5,
    )
    lo, hi = min(allv), max(allv)
    n_mc = next(
        (
            sensitivity[c].get("monte_carlo_n")
            for c in cases
            if sensitivity[c].get("monte_carlo_n")
        ),
        0,
    )
    seed = next(
        (sensitivity[c].get("seed") for c in cases if "seed" in sensitivity[c]), None
    )
    return _finish(
        fig,
        folders,
        name,
        f"Flight-path exceedance of 20 % LFL stays between {lo:.1f} and {hi:.1f} % of hours across the parameter ranges",
        f"One-at-a-time ranges and uniform Monte Carlo ({n_mc} samples, seed {seed}); common axis starting at zero",
        {"min_hours20": lo, "max_hours20": hi, "cases": cases},
    )


@st.in_house_style
def fig_tilt(
    study: StudyResult,
    sensitivity: Mapping[str, Any],
    folders: FOLDERS,
    name: str,
    criterion_pct: float = 20.0,
) -> FigureRecord:
    """Helideck peak and flight-path hours against the tip inclination.

    Args:
        study: Study result (base inclination).
        sensitivity: Result of :func:`flare_helideck_dispersion.sensitivity.run_sensitivity`.
        folders: Output folder(s).
        name: File name.
        criterion_pct: Criterion line, percent of the LFL.

    Returns:
        Figure record.
    """
    scan = sensitivity["tilt_scan"]
    base_tilt = study.settings.params.tilt_deg
    fig = st.new_fig(3.4)
    gs = fig.add_gridspec(1, 2)
    a = fig.add_subplot(gs[0, 0])
    b = fig.add_subplot(gs[0, 1])
    exceeding: dict[str, float] = {}
    hmax = 0.0
    for i, (case, rows) in enumerate(scan.items()):
        col = st.case_color(i)
        t = [r["tilt_deg"] for r in rows]
        a.plot(
            t,
            [max(r["helideck_peak"], 0.01) for r in rows],
            marker="o",
            ms=3,
            color=col,
            label=case,
        )
        b.plot(
            t, [r["hours_ge20"] for r in rows], marker="o", ms=3, color=col, label=case
        )
        hmax = max(hmax, max(r["hours_ge20"] for r in rows))
        bad = [r["tilt_deg"] for r in rows if r["helideck_peak"] >= criterion_pct]
        if bad:
            exceeding[case] = max(bad)
    a.set_yscale("log")
    a.axhline(criterion_pct, color="k", ls="--", lw=0.8)
    a.text(
        0.98,
        criterion_pct * 1.15,
        f"{criterion_pct:g} % LFL",
        fontsize=6.3,
        ha="right",
        transform=a.get_yaxis_transform(),
    )
    a.set_ylabel("Peak % LFL at the helideck")
    a.set_title("Helideck", loc="left")
    b.set_ylabel("% of hours >= 20 % LFL on a path")
    b.set_ylim(0, max(hmax * 1.15, 1.0))
    b.set_title("Flight paths", loc="left")
    for ax in (a, b):
        ax.axvline(base_tilt, color=st.GREY, ls=":")
        ax.set_xlabel("Tip inclination above horizontal (deg)")
        ax.legend(frameon=False, loc="lower left" if ax is b else "upper right")
    if exceeding:
        worst = max(exceeding, key=exceeding.get)
        title = "The helideck reaches {:g} % LFL for {} at tip inclinations of {:.0f} deg or less".format(
            criterion_pct, ", ".join(sorted(exceeding)), exceeding[worst]
        )
    else:
        title = "The helideck stays below {:g} % LFL for every tip inclination from {:.0f} to {:.0f} deg".format(
            criterion_pct,
            min(r["tilt_deg"] for rows in scan.values() for r in rows),
            max(r["tilt_deg"] for rows in scan.values() for r in rows),
        )
    return _finish(
        fig,
        folders,
        name,
        title,
        f"Base inclination {base_tilt:.1f} deg (dotted); confirm the tip angle from the flare-tip drawing",
        {"cases_exceeding_at_deg": exceeding, "base_tilt_deg": base_tilt},
    )


# ---------------------------------------------------------------- driver
def make_all_figures(
    study: StudyResult,
    folders: FOLDERS,
    sensitivity: Mapping[str, Any] | None = None,
    benchmarks: Sequence[BenchmarkScenario] | None = None,
    psv_table: Sequence[Mapping[str, Any]] | None = None,
    footprint_cases: Sequence[str] | None = None,
    mode: str = "briggs",
) -> list[FigureRecord]:
    """Create the full figure set; optional figures are skipped when their data is absent.

    Args:
        study: Study result.
        folders: Output folder(s).
        sensitivity: Sensitivity result (enables tornado and tilt figures).
        benchmarks: Benchmark scenarios (enables the benchmark figure).
        psv_table: PSV sizing rows for the source-term figure.
        footprint_cases: Cases for the plan footprints (default two highest).
        mode: Plume mode.

    Returns:
        One :class:`FigureRecord` per saved figure, in figure-number order.
    """
    records: list[FigureRecord] = []
    counter = [0]

    def nxt(label: str) -> str:
        counter[0] += 1
        return f"fig{counter[0]:02d}_{label}.png"

    records.append(fig_layout(study, folders, nxt("layout_helideck_flare_flightpath")))
    records.append(fig_wind(study, folders, nxt("wind_climate_statistics")))
    records.append(fig_source_terms(study, folders, nxt("source_terms"), psv_table))
    for case in footprint_cases or top_cases(study, 2, mode):
        records.append(
            fig_footprints(
                study, case, folders, nxt("plan_footprints_" + slug(case)), mode=mode
            )
        )
    records.append(
        fig_sections(study, folders, nxt("vertical_sections_plume"), mode=mode)
    )
    records.append(
        fig_heatmaps(study, folders, nxt("flightpath_pct_lfl_heatmaps"), mode)
    )
    records.append(fig_polar(study, folders, nxt("polar_flightpath_exposure"), mode))
    records.append(fig_exceedance(study, folders, nxt("exceedance_by_case"), mode))
    if benchmarks:
        records.append(
            fig_benchmark(study, benchmarks, folders, nxt("benchmark_helideck_peak"))
        )
    if sensitivity:
        if any("tornado" in v for k, v in sensitivity.items() if k != "tilt_scan"):
            records.append(
                fig_tornado(sensitivity, folders, nxt("tornado_sensitivity"))
            )
        if sensitivity.get("tilt_scan"):
            records.append(
                fig_tilt(study, sensitivity, folders, nxt("tilt_sensitivity"))
            )
    return records
