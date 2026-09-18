"""Presentation-grade cutaway illustration of a field, from reservoir to host.

``plot_reservoir_3d`` is the engineering view: labelled axes, a schematic
reservoir box, a legend. This module is the *communication* view - the block
diagram you put on a decision-gate slide. It draws the sea, the water column,
the seabed, the subsurface, a real gridded structural horizon coloured by depth,
every well from its tree down to the drain, the flowlines and the host, and it
carries the study's headline numbers as callouts so the picture and the analysis
cannot drift apart.

Nothing here invents geometry. The horizon comes from a reservoir model grid,
the seabed from bathymetry, the layout from ``design_surf_layout``. Facts are
passed in as :class:`KeyFact` with the source that produced them, so a number on
the slide can always be traced back to the calculation that made it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, radians, sin
from typing import Sequence

from .layout import SurfLayout
from .wells import WellPath

#: Service colours shared with the engineering 3D view.
SERVICE_COLOUR = {
    "production": "#e8542f",
    "water_injection": "#2f7fd1",
    "gas_injection": "#f2a33c",
    "umbilical": "#8d8d8d",
}

#: Palette for the illustration. Tuned for projection, not for a colour printer.
THEME = {
    "sky_top": "#cfe4f2",
    "sky_bottom": "#eaf3fa",
    "sea_surface": "#4a90c4",
    "water": "#2e6b96",
    "seabed": "#9a9384",
    "subsurface": "#20262e",
    "horizon_cmap": "turbo",
    "well": "#f2f2f2",
    "text": "#1b2733",
    "muted": "#5b6b7a",
    "callout_face": "#ffffff",
    "callout_edge": "#c7d3de",
}


@dataclass(frozen=True)
class KeyFact:
    """One headline number, with the calculation that produced it."""

    label: str
    value: str
    unit: str = ""
    source: str = ""
    group: str = ""

    def rendered(self) -> str:
        return "%s %s" % (self.value, self.unit) if self.unit else self.value


@dataclass(frozen=True)
class Horizon:
    """A gridded structural surface in the layout's local east/north frame."""

    name: str
    east_m: Sequence[Sequence[float]]
    north_m: Sequence[Sequence[float]]
    depth_m_tvdmsl: Sequence[Sequence[float]]
    contact_depth_m_tvdmsl: float | None = None
    attribution: str = ""


@dataclass(frozen=True)
class Seabed:
    """A gridded bathymetric surface in the layout's local east/north frame."""

    east_m: Sequence[Sequence[float]]
    north_m: Sequence[Sequence[float]]
    depth_m: Sequence[Sequence[float]]
    attribution: str = ""


@dataclass
class Annotation:
    """A leader-line label pinned to a point in the scene."""

    text: str
    east_m: float
    north_m: float
    depth_m: float
    dx: float = 0.0
    dy: float = 0.0
    colour: str = THEME["text"]


def horizon_from_model_grid(
    depth_values: Sequence[float],
    *,
    nx: int,
    ny: int,
    dx_m: float,
    dy_m: float,
    origin_east_m: float,
    origin_north_m: float,
    axis_bearing_deg: float,
    name: str = "reservoir top",
    contact_depth_m_tvdmsl: float | None = None,
    attribution: str = "",
) -> Horizon:
    """Rotate a reservoir model grid onto a true bearing in the local frame.

    ``depth_values`` is the flattened top surface in model order, x fastest.
    ``origin_*`` is where model (0, 0) sits, and ``axis_bearing_deg`` is the true
    bearing the model's +x axis points along.
    """
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - optional dependency
        raise RuntimeError("gridding the horizon requires numpy") from error

    values = np.asarray(depth_values, dtype=float)
    if values.size != nx * ny:
        raise ValueError(
            "depth_values has %d entries but nx*ny is %d" % (values.size, nx * ny))
    depth = values.reshape(ny, nx)

    along = (np.arange(nx) + 0.5) * dx_m
    across = (np.arange(ny) + 0.5) * dy_m
    across = across - across.mean()
    along_grid, across_grid = np.meshgrid(along, across)

    # Same axis convention as layout._place: east leads with sin, north with cos.
    angle = radians(axis_bearing_deg)
    east = origin_east_m + along_grid * sin(angle) + across_grid * cos(angle)
    north = origin_north_m + along_grid * cos(angle) - across_grid * sin(angle)
    return Horizon(
        name=name,
        east_m=east,
        north_m=north,
        depth_m_tvdmsl=depth,
        contact_depth_m_tvdmsl=contact_depth_m_tvdmsl,
        attribution=attribution,
    )


def _platform_glyph(axis, east_km, north_km, water_depth_m, *, span_km, colour):
    """A four-shaft concrete platform drawn at its real footprint, not the scene scale."""
    import numpy as np

    half = 0.5 * span_km
    deck_top = -120.0
    deck_bottom = -40.0
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    ring_e = [east_km + c[0] for c in corners] + [east_km + corners[0][0]]
    ring_n = [north_km + c[1] for c in corners] + [north_km + corners[0][1]]
    for depth in (deck_top, deck_bottom):
        axis.plot(ring_e, ring_n, [depth] * len(ring_e), color=colour, lw=2.2, zorder=60)
    for c in corners:
        axis.plot([east_km + c[0]] * 2, [north_km + c[1]] * 2,
                  [deck_top, deck_bottom], color=colour, lw=1.8, zorder=60)
    axis.plot_surface(
        np.array([[east_km - half, east_km + half], [east_km - half, east_km + half]]),
        np.array([[north_km - half, north_km - half], [north_km + half, north_km + half]]),
        np.full((2, 2), deck_top), color=colour, alpha=0.95, shade=False, zorder=60)

    shaft = 0.45 * half
    for sx, sy in ((-shaft, -shaft), (shaft, -shaft), (shaft, shaft), (-shaft, shaft)):
        axis.plot([east_km + sx] * 2, [north_km + sy] * 2, [deck_bottom, water_depth_m],
                  color="#d0d0d0", lw=3.4, solid_capstyle="round", zorder=55)
    axis.plot([east_km] * 2, [north_km] * 2, [deck_top, deck_top - 130.0],
              color=colour, lw=1.6, zorder=61)


def render_field_illustration(
    layout: SurfLayout,
    paths: Sequence[WellPath],
    path: str,
    *,
    horizon: Horizon | None = None,
    seabed: Seabed | None = None,
    key_facts: Sequence[KeyFact] = (),
    annotations: Sequence[Annotation] = (),
    title: str = "",
    subtitle: str = "",
    footer: str = "",
    attribution: Sequence[str] = (),
    elevation_deg: float = 24.0,
    azimuth_deg: float = -62.0,
    vertical_exaggeration: float = 1.0,
    host_span_m: float = 260.0,
    figure_size: tuple[float, float] = (17.0, 9.5),
    show_water: bool = True,
    dpi: int = 190,
) -> str:
    """Render the field from reservoir to host and save it to ``path``.

    ``key_facts`` are drawn as a callout column on the right. Facts are grouped
    by their ``group`` field in the order they first appear.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except ImportError as error:  # pragma: no cover - optional dependency
        raise RuntimeError("the illustration requires matplotlib and numpy") from error

    figure = plt.figure(figsize=figure_size, facecolor="white")
    has_panel = bool(key_facts)
    axis = figure.add_axes([0.06, 0.03, 0.68 if has_panel else 0.94, 0.88],
                           projection="3d")
    axis.set_facecolor("white")

    water_depth = float(layout.summary["water_depth_m"])

    easts = [node.east_m for node in layout.nodes]
    norths = [node.north_m for node in layout.nodes]
    for well_path in paths:
        easts.extend(point[0] for point in well_path.points)
        norths.extend(point[1] for point in well_path.points)
    if horizon is not None:
        easts.extend(np.asarray(horizon.east_m).ravel().tolist())
        norths.extend(np.asarray(horizon.north_m).ravel().tolist())
    margin = 700.0
    e_lo, e_hi = min(easts) - margin, max(easts) + margin
    n_lo, n_hi = min(norths) - margin, max(norths) + margin
    scale_km = max(e_hi - e_lo, n_hi - n_lo) / 1000.0

    def km(value):
        return np.asarray(value, dtype=float) / 1000.0

    deepest = water_depth + 200.0
    if horizon is not None:
        deepest = max(deepest, float(np.nanmax(np.asarray(horizon.depth_m_tvdmsl))) + 90.0)
    for well_path in paths:
        deepest = max(deepest, max(point[2] for point in well_path.points) + 60.0)

    corner_e = np.array([e_lo, e_hi])
    corner_n = np.array([n_lo, n_hi])
    grid_e, grid_n = np.meshgrid(corner_e, corner_n)

    # --- sea ---------------------------------------------------------------
    if show_water:
        axis.plot_surface(km(grid_e), km(grid_n), np.zeros_like(grid_e),
                          color=THEME["sea_surface"], alpha=0.30, shade=False, zorder=2)
        # Front and left water curtains give the cutaway its block-diagram edge.
        axis.plot_surface(
            km(np.array([[e_lo, e_hi], [e_lo, e_hi]])),
            km(np.full((2, 2), n_lo)),
            np.array([[0.0, 0.0], [water_depth, water_depth]]),
            color=THEME["water"], alpha=0.22, shade=False, zorder=1)
        axis.plot_surface(
            km(np.full((2, 2), e_lo)),
            km(np.array([[n_lo, n_hi], [n_lo, n_hi]])),
            np.array([[0.0, 0.0], [water_depth, water_depth]]),
            color=THEME["water"], alpha=0.16, shade=False, zorder=1)

    # --- seabed ------------------------------------------------------------
    if seabed is not None:
        axis.plot_surface(km(seabed.east_m), km(seabed.north_m),
                          np.asarray(seabed.depth_m, dtype=float),
                          color=THEME["seabed"], alpha=0.62, shade=True,
                          linewidth=0, antialiased=True, zorder=10)
    else:
        axis.plot_surface(km(grid_e), km(grid_n), np.full_like(grid_e, water_depth),
                          color=THEME["seabed"], alpha=0.58, shade=False, zorder=10)

    # Subsurface curtain between seabed and the deepest thing drawn.
    axis.plot_surface(
        km(np.array([[e_lo, e_hi], [e_lo, e_hi]])),
        km(np.full((2, 2), n_lo)),
        np.array([[water_depth, water_depth], [deepest, deepest]]),
        color=THEME["subsurface"], alpha=0.10, shade=False, zorder=3)
    axis.plot_surface(
        km(np.full((2, 2), e_lo)),
        km(np.array([[n_lo, n_hi], [n_lo, n_hi]])),
        np.array([[water_depth, water_depth], [deepest, deepest]]),
        color=THEME["subsurface"], alpha=0.07, shade=False, zorder=3)

    # --- reservoir horizon -------------------------------------------------
    horizon_artist = None
    if horizon is not None:
        depth = np.asarray(horizon.depth_m_tvdmsl, dtype=float)
        horizon_artist = axis.plot_surface(
            km(horizon.east_m), km(horizon.north_m), depth,
            cmap=THEME["horizon_cmap"], rstride=1, cstride=1,
            linewidth=0, antialiased=True, alpha=0.97, shade=False, zorder=20)
        if horizon.contact_depth_m_tvdmsl is not None:
            contact = float(horizon.contact_depth_m_tvdmsl)
            closure = np.where(depth <= contact, contact, np.nan)
            if np.isfinite(closure).any():
                axis.plot_surface(
                    km(horizon.east_m), km(horizon.north_m), closure,
                    color="#2f6fb5", alpha=0.30, linewidth=0, shade=False, zorder=19)

    # --- flowlines and umbilicals -----------------------------------------
    seen_services = set()
    for line in layout.lines:
        if "riser" in line.line_type:
            continue
        try:
            start = layout.node(line.from_tag)
            end = layout.node(line.to_tag)
        except KeyError:
            continue
        colour = SERVICE_COLOUR.get(line.service, "#444444")
        axis.plot(km([start.east_m, end.east_m]), km([start.north_m, end.north_m]),
                  [start.water_depth_m - 3.0, end.water_depth_m - 3.0],
                  color=colour, lw=3.0 if line.service == "production" else 1.8,
                  alpha=0.95, solid_capstyle="round", zorder=30)
        seen_services.add(line.service)

    # --- wells -------------------------------------------------------------
    for well_path in paths:
        colour = SERVICE_COLOUR.get(well_path.service, "#dddddd")
        axis.plot(km([p[0] for p in well_path.points]),
                  km([p[1] for p in well_path.points]),
                  [p[2] for p in well_path.points],
                  color="#ffffff", lw=3.0, alpha=0.85,
                  solid_capstyle="round", zorder=40)
        axis.plot(km([p[0] for p in well_path.points]),
                  km([p[1] for p in well_path.points]),
                  [p[2] for p in well_path.points],
                  color="#3f4a56", lw=1.4,
                  ls="-" if well_path.drillable else "--", alpha=1.0, zorder=41)
        toe = well_path.points[-1]
        axis.scatter(km(toe[0]), km(toe[1]), toe[2], marker="o", s=22,
                     c=colour, edgecolors="white", linewidths=0.5,
                     depthshade=False, zorder=42)

    # --- subsea hardware ---------------------------------------------------
    for node in layout.nodes_of_kind("template"):
        axis.scatter(km(node.east_m), km(node.north_m), node.water_depth_m - 6.0,
                     marker="s", s=110, c="#ffd24a", edgecolors="#3b2f00",
                     linewidths=0.8, depthshade=False, zorder=50)
    for node in layout.nodes_of_kind("plem"):
        axis.scatter(km(node.east_m), km(node.north_m), node.water_depth_m - 4.0,
                     marker="^", s=52, c="#ffd24a", edgecolors="#3b2f00",
                     linewidths=0.6, depthshade=False, zorder=50)
    for node in layout.nodes_of_kind("xmas_tree"):
        axis.scatter(km(node.east_m), km(node.north_m), node.water_depth_m - 4.0,
                     marker="o", s=14, c="#ff5c33", edgecolors="none",
                     depthshade=False, zorder=49)

    # --- host and risers ---------------------------------------------------
    host = layout.node("HOST")
    _platform_glyph(axis, float(km(host.east_m)), float(km(host.north_m)),
                    water_depth, span_km=host_span_m / 1000.0, colour="#c8102e")
    try:
        riser_base = layout.node("RB-PLEM")
        axis.plot(km([riser_base.east_m, host.east_m]),
                  km([riser_base.north_m, host.north_m]),
                  [riser_base.water_depth_m, -18.0],
                  color="#e8542f", lw=2.6, alpha=0.95, zorder=52)
    except KeyError:
        pass

    # --- in-scene annotations ---------------------------------------------
    for note in annotations:
        axis.text(float(km(note.east_m)) + note.dx, float(km(note.north_m)) + note.dy,
                  note.depth_m, note.text, color=note.colour, fontsize=9.5,
                  fontweight="bold", zorder=70,
                  bbox=dict(boxstyle="round,pad=0.28", fc="white", ec=THEME["callout_edge"],
                            alpha=0.88, lw=0.7))

    # --- framing -----------------------------------------------------------
    axis.set_xlim(e_lo / 1000.0, e_hi / 1000.0)
    axis.set_ylim(n_lo / 1000.0, n_hi / 1000.0)
    axis.set_zlim(deepest, -140.0)
    axis.view_init(elev=elevation_deg, azim=azimuth_deg)
    try:
        axis.set_box_aspect((scale_km, scale_km, scale_km * 0.62 * vertical_exaggeration))
    except AttributeError:  # pragma: no cover - very old matplotlib
        pass

    axis.set_xlabel("east [km]", color=THEME["muted"], fontsize=9, labelpad=2)
    axis.set_ylabel("north [km]", color=THEME["muted"], fontsize=9, labelpad=2)
    axis.set_zlabel("depth [m MSL]", color=THEME["muted"], fontsize=9, labelpad=2)
    axis.tick_params(colors=THEME["muted"], labelsize=8)
    for pane_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
        pane_axis.pane.set_alpha(0.0)
        pane_axis.pane.set_edgecolor("none")
    axis.grid(False)

    if horizon_artist is not None:
        bar_axis = figure.add_axes([0.045, 0.10, 0.013, 0.26])
        bar = figure.colorbar(horizon_artist, cax=bar_axis)
        bar.set_label("%s [m TVDMSL]" % horizon.name, fontsize=8.0,
                      color=THEME["muted"])
        bar.ax.tick_params(labelsize=7.0, colors=THEME["muted"])
        bar.ax.invert_yaxis()
        bar.outline.set_edgecolor(THEME["callout_edge"])

    legend = [
        Line2D([], [], color="#c8102e", lw=3, label="host facility"),
        Line2D([], [], color="#ffd24a", marker="s", ls="", ms=9,
               markeredgecolor="#3b2f00", label="template / manifold"),
        Line2D([], [], color="#ff5c33", marker="o", ls="", ms=6, label="Xmas tree"),
        Line2D([], [], color="#5a6572", lw=2.6, label="well trajectory"),
    ]
    for service in ("production", "water_injection", "gas_injection", "umbilical"):
        if service in seen_services:
            legend.append(Line2D([], [], color=SERVICE_COLOUR[service], lw=2.6,
                                 label=service.replace("_", " ")))
    if horizon is not None and horizon.contact_depth_m_tvdmsl is not None:
        legend.append(Patch(facecolor="#2f6fb5", alpha=0.45, label="hydrocarbon closure"))
    figure.legend(handles=legend, loc="lower left", bbox_to_anchor=(0.035, 0.40),
                  fontsize=8.0, framealpha=0.92, edgecolor=THEME["callout_edge"],
                  borderpad=0.7, labelspacing=0.55)

    # --- titles ------------------------------------------------------------
    figure.text(0.015, 0.965, title or layout.field_name, fontsize=20,
                fontweight="bold", color=THEME["text"], va="top")
    if subtitle:
        figure.text(0.015, 0.922, subtitle, fontsize=11, color=THEME["muted"], va="top")

    # --- key-fact callout column ------------------------------------------
    if has_panel:
        _draw_fact_panel(figure, key_facts)

    tail = footer or "screening illustration - not for construction"
    if attribution:
        tail += "  |  " + "; ".join(attribution)
    if horizon is not None and horizon.attribution:
        tail += "  |  horizon: " + horizon.attribution
    if seabed is not None and seabed.attribution:
        tail += "  |  bathymetry: " + seabed.attribution
    figure.text(0.015, 0.012, tail, fontsize=7.5, color=THEME["muted"])

    figure.savefig(path, dpi=dpi, facecolor="white")
    plt.close(figure)
    return path


def _draw_fact_panel(figure, key_facts: Sequence[KeyFact]) -> None:
    """Draw the headline numbers as a grouped column on the right.

    Row spacing is derived from the number of rows so the column always fits the
    figure; a long fact list shrinks rather than running off the bottom.
    """
    from matplotlib.lines import Line2D

    groups: list[str] = []
    for fact in key_facts:
        if fact.group not in groups:
            groups.append(fact.group)

    rows = len(key_facts) + len(groups)
    sources = sum(1 for f in key_facts if f.source)
    top, bottom = 0.905, 0.045
    available = top - bottom
    unit = available / (rows + 0.62 * sources + 0.5 * len(groups))
    unit = min(unit, 0.030)
    label_size = max(6.4, min(9.2, unit * 330.0))
    value_size = label_size * 1.16
    source_size = max(5.2, label_size * 0.74)

    x_label, x_value = 0.760, 0.988
    y = top
    for group in groups:
        if group:
            figure.text(x_label, y, group.upper(), fontsize=label_size * 0.94,
                        fontweight="bold", color="#8b9aa8", va="top")
            y -= unit * 0.78
            figure.add_artist(Line2D([x_label, x_value], [y, y],
                                     color=THEME["callout_edge"], lw=0.9,
                                     transform=figure.transFigure))
            y -= unit * 0.42
        for fact in [f for f in key_facts if f.group == group]:
            figure.text(x_label, y, fact.label, fontsize=label_size,
                        color=THEME["muted"], va="top")
            figure.text(x_value, y, fact.rendered(), fontsize=value_size,
                        fontweight="bold", color=THEME["text"], va="top", ha="right")
            y -= unit
            if fact.source:
                figure.text(x_label, y + unit * 0.16, fact.source, fontsize=source_size,
                            color="#9fb0bf", va="top", style="italic")
                y -= unit * 0.62
        y -= unit * 0.5
