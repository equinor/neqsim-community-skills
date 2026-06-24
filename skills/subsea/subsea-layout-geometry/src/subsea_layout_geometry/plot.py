"""Deterministic schematic plan-view renderer for subsea field layouts.

This module turns a supplied subsea layout (host, wells, manifolds, templates,
tie-in and riser-base nodes) into a public, screening-level schematic map. It is
intentionally simple: it draws a plan view with markers per node kind, dashed
host tie-back lines (or explicit routed flowline/umbilical segments) and step-out
distance labels. It is not a routing, bathymetry or hydraulic illustration.

Matplotlib is an optional dependency. Import this module only when a figure is
needed; the rest of the skill works without it.
"""

from __future__ import annotations

from .model import SubseaLayoutModel

# Marker style per node kind: (matplotlib marker, colour, legend label).
_KIND_STYLE = {
    "host": ("s", "black", "Host / processing"),
    "well": ("o", "tab:red", "Well"),
    "manifold": ("^", "tab:blue", "Manifold"),
    "template": ("D", "tab:purple", "Template"),
    "riser_base": ("P", "tab:orange", "Riser base"),
    "tie_in": ("X", "tab:green", "Tie-in"),
}
_DEFAULT_STYLE = ("o", "gray", "Other")


def _require_matplotlib():
    """Import matplotlib lazily with a clear, actionable error message.

    :return: the imported ``matplotlib.pyplot`` module.
    :raises ModuleNotFoundError: if matplotlib is not installed.
    """
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise ModuleNotFoundError(
            "plot_subsea_layout requires matplotlib. Install the optional plotting "
            "extra, e.g. 'pip install matplotlib' or "
            "'pip install neqsim-skill-subsea-layout-geometry[plot]'."
        ) from exc
    return plt


def _scaled_coords(node, coordinate_system):
    """Return display coordinates and axis labels for a node.

    Cartesian metres are scaled to kilometres; geographic degrees are passed
    through unchanged.

    :param node: a mapping with ``x`` and ``y`` keys.
    :param coordinate_system: ``"cartesian"`` or ``"geographic"``.
    :return: a tuple ``(x_display, y_display)``.
    """
    x = float(node["x"])
    y = float(node["y"])
    if coordinate_system == "geographic":
        return x, y
    return x / 1000.0, y / 1000.0


def _axis_labels(coordinate_system):
    """Return the x and y axis labels for the coordinate system.

    :param coordinate_system: ``"cartesian"`` or ``"geographic"``.
    :return: a tuple ``(x_label, y_label)``.
    """
    if coordinate_system == "geographic":
        return "Longitude [deg]", "Latitude [deg]"
    return "Easting [km]", "Northing [km]"


def plot_subsea_layout(
    nodes,
    *,
    host_name,
    coordinate_system="cartesian",
    flowlines=None,
    umbilical=None,
    max_step_out_km=50.0,
    title="Subsea field layout (plan view)",
    show_step_out=True,
    ax=None,
    save_path=None,
    dpi=150,
):
    """Render a deterministic schematic plan-view map of a subsea field layout.

    The figure shows each node with a kind-specific marker, dashed host tie-back
    lines (or explicit routed segments when ``flowlines`` is given), an optional
    umbilical route, and optional step-out distance labels. The same geometry
    screening as :class:`SubseaLayoutModel` is used for the step-out labels so
    the illustration is consistent with the numeric result.

    This is a public, screening-level illustration only. It is not a routed
    flowline drawing, a bathymetric chart, or a georeferenced basemap.

    :param nodes: list of node mappings with ``name``, ``x``, ``y``, optional
        ``water_depth_m`` and optional ``kind`` (``well``, ``manifold``,
        ``host``, ``template``, ``tie_in``, ``riser_base``). Cartesian ``x``/``y``
        are in metres; geographic ``x``/``y`` are longitude/latitude in degrees.
    :param host_name: name of the node treated as the host reference.
    :param coordinate_system: ``"cartesian"`` (metres) or ``"geographic"``
        (degrees). Defaults to ``"cartesian"``.
    :param flowlines: optional list of ``(from_name, to_name)`` pairs drawn as
        solid routed flowline segments. When omitted, dashed star tie-back lines
        from the host to every other node are drawn instead.
    :param umbilical: optional list of ``(from_name, to_name)`` pairs drawn as a
        distinct dotted umbilical route.
    :param max_step_out_km: configurable public step-out guideline used for the
        geometry screening. Defaults to 50 km.
    :param title: figure title. Defaults to a generic plan-view title.
    :param show_step_out: when True, annotate host tie-back lines with the
        horizontal step-out distance in km. Defaults to True.
    :param ax: optional existing matplotlib Axes to draw into. When omitted, a
        new figure and axes are created.
    :param save_path: optional path. When given, the figure is saved as a PNG at
        ``dpi`` resolution for the report pipeline.
    :param dpi: resolution used when ``save_path`` is given. Defaults to 150.
    :return: the matplotlib ``Figure`` containing the schematic map.
    :raises ValueError: if the host node is missing or a referenced segment node
        is not in the node list.
    :raises ModuleNotFoundError: if matplotlib is not installed.
    """
    plt = _require_matplotlib()

    system = str(coordinate_system).strip().lower()
    # Reuse the model for validation and step-out labels (keeps map == numbers).
    result = SubseaLayoutModel(max_step_out_km=max_step_out_km).evaluate(
        nodes=nodes, host_name=host_name, coordinate_system=system
    )

    node_by_name = {str(n["name"]).strip(): n for n in nodes}
    if host_name not in node_by_name:
        raise ValueError(f"host_name {host_name!r} not found in nodes")
    host = node_by_name[host_name]
    host_x, host_y = _scaled_coords(host, system)

    if ax is None:
        fig, ax = plt.subplots(figsize=(7.5, 6.0))
    else:
        fig = ax.figure

    # --- connection lines (drawn first so markers sit on top) ---
    if flowlines:
        for from_name, to_name in flowlines:
            _draw_segment(ax, node_by_name, from_name, to_name, system,
                          style="-", colour="dimgray", lw=1.6, label="Flowline")
    else:
        # Default schematic: dashed star tie-back from host to each node.
        for name, node in node_by_name.items():
            if name == host_name:
                continue
            nx, ny = _scaled_coords(node, system)
            ax.plot([host_x, nx], [host_y, ny], ls="--", c="gray", lw=1.0,
                    zorder=1, label="Tie-back (schematic)")
            if show_step_out and name in result.step_out_km:
                ax.annotate(
                    f"{result.step_out_km[name]:.1f} km",
                    ((host_x + nx) / 2.0, (host_y + ny) / 2.0),
                    color="gray", fontsize=8, zorder=2,
                )

    if umbilical:
        for from_name, to_name in umbilical:
            _draw_segment(ax, node_by_name, from_name, to_name, system,
                          style=":", colour="tab:green", lw=1.4, label="Umbilical")

    # --- node markers ---
    seen_kinds = set()
    for name, node in node_by_name.items():
        kind = str(node.get("kind", "well")).strip().lower()
        marker, colour, label = _KIND_STYLE.get(kind, _DEFAULT_STYLE)
        nx, ny = _scaled_coords(node, system)
        legend_label = label if kind not in seen_kinds else None
        seen_kinds.add(kind)
        ax.scatter(nx, ny, marker=marker, s=130, c=colour, edgecolors="black",
                   linewidths=0.6, zorder=3, label=legend_label)
        ax.annotate(name, (nx, ny), textcoords="offset points", xytext=(7, 6),
                    fontsize=9, zorder=4)

    x_label, y_label = _axis_labels(system)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, ls=":", alpha=0.6)
    if system == "cartesian":
        ax.set_aspect("equal", adjustable="datalim")

    # De-duplicate legend entries.
    handles, labels = ax.get_legend_handles_labels()
    unique = {}
    for handle, label in zip(handles, labels):
        if label and label not in unique:
            unique[label] = handle
    if unique:
        ax.legend(unique.values(), unique.keys(), loc="best", fontsize=8,
                  framealpha=0.9)

    fig.tight_layout()
    if save_path is not None:
        fig.savefig(str(save_path), dpi=dpi, bbox_inches="tight")
    return fig


def _draw_segment(ax, node_by_name, from_name, to_name, system, *, style, colour,
                  lw, label):
    """Draw a single connection segment between two named nodes.

    :param ax: matplotlib Axes to draw into.
    :param node_by_name: mapping of node name to node mapping.
    :param from_name: name of the start node.
    :param to_name: name of the end node.
    :param system: coordinate system, ``"cartesian"`` or ``"geographic"``.
    :param style: matplotlib line style string.
    :param colour: matplotlib colour for the line.
    :param lw: line width.
    :param label: legend label for the segment kind.
    :raises ValueError: if either endpoint name is not in ``node_by_name``.
    """
    from_name = str(from_name).strip()
    to_name = str(to_name).strip()
    if from_name not in node_by_name:
        raise ValueError(f"segment endpoint {from_name!r} not found in nodes")
    if to_name not in node_by_name:
        raise ValueError(f"segment endpoint {to_name!r} not found in nodes")
    ax_from = _scaled_coords(node_by_name[from_name], system)
    ax_to = _scaled_coords(node_by_name[to_name], system)
    ax.plot([ax_from[0], ax_to[0]], [ax_from[1], ax_to[1]], ls=style, c=colour,
            lw=lw, zorder=1, label=label)
