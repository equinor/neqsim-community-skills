"""Geographic map of a designed SURF layout. Requires matplotlib."""

from __future__ import annotations

from typing import Sequence

from .layout import SurfLayout

_KIND_STYLE = {
    "well": ("o", "#1f77b4", 26, "well"),
    "xmas_tree": ("s", "#d62728", 18, "Xmas tree"),
    "template": ("D", "#2ca02c", 55, "template / manifold"),
    "plem": ("^", "#ff7f0e", 45, "PLEM"),
    "host": ("*", "#111111", 320, "host"),
}

_SERVICE_STYLE = {
    "production": ("#d62728", 1.8, "-", "production flowline"),
    "water_injection": ("#1f77b4", 1.4, "-", "water injection"),
    "gas_injection": ("#ff7f0e", 1.4, "-", "gas injection"),
    "umbilical": ("#7f7f7f", 0.9, "--", "umbilical"),
    "service": ("#9467bd", 1.0, "-.", "service line"),
}


def plot_layout_map(
    layout: SurfLayout,
    path: str,
    title: str = "",
    attribution: Sequence[str] = (),
    annotate_drill_centres: bool = True,
) -> str:
    """Draw the layout on latitude/longitude axes and save it to ``path``."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:  # pragma: no cover - optional dependency
        raise RuntimeError("plotting requires matplotlib; install the 'plot' extra") from error

    figure, axis = plt.subplots(figsize=(11, 9))

    outline = layout.summary.get("reservoir_outline")
    if outline:
        ring = list(outline) + [outline[0]]
        axis.plot(
            [lon for _, lon in ring],
            [lat for lat, _ in ring],
            color="#8c564b",
            lw=1.2,
            ls=":",
            label="reservoir outline",
        )

    drawn_services = set()
    for line in layout.lines:
        colour, width, style, label = _SERVICE_STYLE.get(
            line.service, ("#333333", 1.0, "-", line.service)
        )
        if "riser" in line.line_type:
            continue
        axis.plot(
            [lon for _, lon in line.route],
            [lat for lat, _ in line.route],
            color=colour,
            lw=width,
            ls=style,
            label=label if line.service not in drawn_services else None,
            zorder=2,
        )
        drawn_services.add(line.service)

    drawn_kinds = set()
    for node in layout.nodes:
        marker, colour, size, label = _KIND_STYLE.get(node.kind, ("x", "#555555", 20, node.kind))
        axis.scatter(
            node.longitude_deg,
            node.latitude_deg,
            marker=marker,
            c=colour,
            s=size,
            label=label if node.kind not in drawn_kinds else None,
            zorder=3,
            edgecolors="none",
        )
        drawn_kinds.add(node.kind)

    if annotate_drill_centres:
        for node in layout.nodes:
            if node.kind in ("template", "host"):
                axis.annotate(
                    node.tag,
                    (node.longitude_deg, node.latitude_deg),
                    textcoords="offset points",
                    xytext=(7, 5),
                    fontsize=8,
                )

    axis.set_xlabel("longitude [deg E]")
    axis.set_ylabel("latitude [deg N]")
    axis.grid(True, alpha=0.3, ls=":")
    axis.set_title(title or "%s SURF layout" % layout.field_name)

    latitude = layout.frame.origin_latitude_deg
    axis.set_aspect(1.0 / max(abs(_cos(latitude)), 1e-6))
    axis.legend(loc="best", fontsize=8, framealpha=0.9)

    footer = "screening layout - not for construction"
    if attribution:
        footer += " | " + "; ".join(attribution)
    figure.text(0.01, 0.01, footer, fontsize=7, color="#555555")

    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return path


def _cos(latitude_deg: float) -> float:
    from math import cos, radians

    return cos(radians(latitude_deg))
