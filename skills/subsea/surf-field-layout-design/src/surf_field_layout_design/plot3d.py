"""Three-dimensional illustration of the reservoir, the wells and the SURF layout.

Draws the sea surface and the host, the seabed with the subsea hardware and the
flowlines, the reservoir body, and every well trajectory from its tree down to
the drain inside the reservoir. Requires matplotlib.
"""

from __future__ import annotations

from typing import Sequence

from .layout import SurfLayout
from .wells import WellPath

_SERVICE_COLOUR = {
    "production": "#d62728",
    "water_injection": "#1f77b4",
    "gas_injection": "#ff7f0e",
    "umbilical": "#7f7f7f",
}


def plot_reservoir_3d(
    layout: SurfLayout,
    paths: Sequence[WellPath],
    path: str,
    *,
    reservoir_depth_m_tvdmsl: float,
    net_pay_m: float = 45.0,
    title: str = "",
    attribution: Sequence[str] = (),
    elevation_deg: float = 22.0,
    azimuth_deg: float = -60.0,
) -> str:
    """Render the reservoir, wells and layout in 3D and save it to ``path``.

    Axes are local east and north in kilometres and true vertical depth below
    mean sea level in metres, with depth increasing downwards.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Patch
        from matplotlib.lines import Line2D
    except ImportError as error:  # pragma: no cover - optional dependency
        raise RuntimeError("the 3D view requires matplotlib and numpy") from error

    figure = plt.figure(figsize=(13, 9))
    axis = figure.add_subplot(111, projection="3d")

    water_depth = layout.summary["water_depth_m"]
    length_km = layout.summary.get("reservoir_length_km", 6.0)
    width_km = layout.summary.get("reservoir_width_km", 3.0)
    bearing = layout.summary.get("field_axis_bearing_deg", 0.0)

    easts = [node.east_m for node in layout.nodes]
    norths = [node.north_m for node in layout.nodes]
    for well_path in paths:
        easts.extend(point[0] for point in well_path.points)
        norths.extend(point[1] for point in well_path.points)
    margin = 600.0
    east_range = (min(easts) - margin, max(easts) + margin)
    north_range = (min(norths) - margin, max(norths) + margin)

    def km(value):
        return np.asarray(value) / 1000.0

    # --- sea surface and seabed -------------------------------------------
    corner_e = np.array([east_range[0], east_range[1]])
    corner_n = np.array([north_range[0], north_range[1]])
    grid_e, grid_n = np.meshgrid(corner_e, corner_n)
    axis.plot_surface(km(grid_e), km(grid_n), np.zeros_like(grid_e), color="#9ecae1", alpha=0.25)
    axis.plot_surface(
        km(grid_e), km(grid_n), np.full_like(grid_e, water_depth), color="#8c8c7a", alpha=0.30
    )

    # --- reservoir body ----------------------------------------------------
    from math import cos, radians, sin

    angle = radians(bearing)
    outline = []
    for along_sign, across_sign in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        along = along_sign * length_km * 500.0
        across = across_sign * width_km * 500.0
        outline.append(
            (
                along * sin(angle) + across * cos(angle),
                along * cos(angle) - across * sin(angle),
            )
        )
    ring_e = km([point[0] for point in outline] + [outline[0][0]])
    ring_n = km([point[1] for point in outline] + [outline[0][1]])
    top = reservoir_depth_m_tvdmsl
    base = reservoir_depth_m_tvdmsl + net_pay_m
    for depth in (top, base):
        axis.plot(ring_e, ring_n, np.full_like(ring_e, depth), color="#8c564b", lw=1.4)
    for index in range(len(outline)):
        axis.plot(
            [ring_e[index], ring_e[index]],
            [ring_n[index], ring_n[index]],
            [top, base],
            color="#8c564b",
            lw=1.0,
            alpha=0.7,
        )
    axis.plot_surface(
        km(np.array([[outline[0][0], outline[1][0]], [outline[3][0], outline[2][0]]])),
        km(np.array([[outline[0][1], outline[1][1]], [outline[3][1], outline[2][1]]])),
        np.full((2, 2), top),
        color="#c49a8a",
        alpha=0.35,
    )

    # --- flowlines on the seabed ------------------------------------------
    drawn = set()
    for line in layout.lines:
        if "riser" in line.line_type or line.service == "umbilical":
            continue
        try:
            start = layout.node(line.from_tag)
            end = layout.node(line.to_tag)
        except KeyError:
            continue
        colour = _SERVICE_COLOUR.get(line.service, "#333333")
        axis.plot(
            km([start.east_m, end.east_m]),
            km([start.north_m, end.north_m]),
            [start.water_depth_m, end.water_depth_m],
            color=colour,
            lw=1.6,
            alpha=0.9,
        )
        drawn.add(line.service)

    # --- subsea hardware and the host -------------------------------------
    for node in layout.nodes_of_kind("template"):
        axis.scatter(
            km(node.east_m), km(node.north_m), node.water_depth_m,
            marker="D", s=45, c="#2ca02c", depthshade=False,
        )
        axis.text(
            km(node.east_m), km(node.north_m), node.water_depth_m - 25.0, node.tag, fontsize=7
        )
    for node in layout.nodes_of_kind("plem"):
        axis.scatter(
            km(node.east_m), km(node.north_m), node.water_depth_m,
            marker="^", s=28, c="#ff7f0e", depthshade=False,
        )
    for node in layout.nodes_of_kind("xmas_tree"):
        axis.scatter(
            km(node.east_m), km(node.north_m), node.water_depth_m,
            marker="s", s=12, c="#d62728", depthshade=False,
        )

    host = layout.node("HOST")
    axis.scatter(km(host.east_m), km(host.north_m), 0.0, marker="*", s=420, c="#111111",
                 depthshade=False)
    axis.text(km(host.east_m), km(host.north_m), -30.0, host.tag, fontsize=9)

    riser_base = layout.node("RB-PLEM")
    axis.plot(
        km([riser_base.east_m, host.east_m]),
        km([riser_base.north_m, host.north_m]),
        [riser_base.water_depth_m, 0.0],
        color="#111111",
        lw=1.6,
        ls="-",
    )

    # --- well trajectories -------------------------------------------------
    for well_path in paths:
        colour = _SERVICE_COLOUR.get(well_path.service, "#333333")
        style = "-" if well_path.drillable else "--"
        axis.plot(
            km([point[0] for point in well_path.points]),
            km([point[1] for point in well_path.points]),
            [point[2] for point in well_path.points],
            color=colour,
            lw=1.3,
            ls=style,
            alpha=0.95,
        )
        toe = well_path.points[-1]
        axis.scatter(km(toe[0]), km(toe[1]), toe[2], marker="o", s=14, c=colour,
                     depthshade=False)

    axis.set_xlabel("east [km]")
    axis.set_ylabel("north [km]")
    axis.set_zlabel("true vertical depth [m MSL]")
    axis.set_zlim(base + 120.0, -80.0)
    axis.view_init(elev=elevation_deg, azim=azimuth_deg)
    axis.set_title(title or "%s reservoir, wells and SURF layout" % layout.field_name)

    legend = [
        Line2D([], [], color="#111111", marker="*", ls="", ms=14, label="host"),
        Line2D([], [], color="#2ca02c", marker="D", ls="", label="template / manifold"),
        Line2D([], [], color="#ff7f0e", marker="^", ls="", label="PLEM"),
        Line2D([], [], color="#d62728", marker="s", ls="", ms=5, label="Xmas tree"),
        Patch(facecolor="#c49a8a", alpha=0.5, label="reservoir"),
        Patch(facecolor="#8c8c7a", alpha=0.4, label="seabed"),
        Patch(facecolor="#9ecae1", alpha=0.4, label="sea surface"),
    ]
    for service in ("production", "water_injection", "gas_injection"):
        if any(item.service == service for item in paths) or service in drawn:
            legend.append(
                Line2D([], [], color=_SERVICE_COLOUR[service], label=service.replace("_", " "))
            )
    if any(not item.drillable for item in paths):
        legend.append(Line2D([], [], color="#333333", ls="--", label="dogleg above the screening limit"))
    axis.legend(handles=legend, loc="upper left", fontsize=8, framealpha=0.9)

    footer = "screening illustration - not for construction or well planning"
    if attribution:
        footer += " | " + "; ".join(attribution)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#555555")

    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return path
