"""Map of the discoveries, fields, evaluation areas, hosts and pipelines around a target.

Needs matplotlib (extra ``map``). The figure is drawn in plain longitude/latitude with the
aspect corrected for latitude, so it needs no map projection library and no network.
Bathymetry is optional: pass a grid ``{"lats", "lons", "z"}`` (altitude in metres, negative
below sea level) such as ``anp_open_data.bathymetry.fetch_etopo_grid`` returns.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from .geo import circle_points, rings_from_geometry
from .inventory import Inventory
from .models import STAGE_COLOURS, STAGE_LABELS, STAGES

_PIPE_COLOURS = {"gas": "#d73027", "oil": "#1a9850", "condensate": "#1a9850", "rich gas": "#d73027"}


def plot_near_field(inv: Inventory, path: str | Path, *, title: str | None = None, bathymetry: Mapping[str, Any] | None = None,
                    max_labels: int = 30, max_host_labels: int = 12, figsize: tuple[float, float] = (11.5, 9.5), dpi: int = 170,
                    show_hosts: bool = True,
                    show_pipelines: bool = True, source_note: str | None = None) -> Path:
    """Draw the near-field map and save it as an image.

    Args:
        inv: Inventory from :func:`near_field_discoveries.inventory.near_field`.
        path: Output file (``.png``, ``.svg`` or ``.pdf``).
        title: Figure title; defaults to the target name and radius.
        bathymetry: Optional grid for depth contours.
        max_labels: Label the nearest ``max_labels`` discoveries and fields.
        max_host_labels: Label the nearest ``max_host_labels`` hosts; all hosts are drawn.
        figsize: Figure size in inches.
        dpi: Raster resolution.
        show_hosts: Draw host facilities.
        show_pipelines: Draw pipelines.
        source_note: Footnote; defaults to the sources named in the records.

    Returns:
        The written path.

    Raises:
        ImportError: matplotlib is not installed.
    """
    try:
        import matplotlib

        if "matplotlib.pyplot" not in __import__("sys").modules:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError("matplotlib is required for maps: pip install matplotlib") from exc

    lon0, lat0, radius = inv.target["lon"], inv.target["lat"], inv.radius_km
    coslat = math.cos(math.radians(lat0))
    dlat = math.degrees(radius * 1.08 / 6371.0088)
    dlon = dlat / coslat
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(lon0 - dlon, lon0 + dlon)
    ax.set_ylim(lat0 - dlat, lat0 + dlat)
    ax.set_aspect(1.0 / coslat)

    if bathymetry:
        lons, lats = bathymetry["lons"], bathymetry["lats"]
        depth = [[(-v if v == v and v < 0 else float("nan")) for v in row] for row in bathymetry["z"]]
        levels = [50, 100, 200, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
        ax.contourf(lons, lats, depth, levels=[0] + levels + [8000], cmap="Blues", alpha=0.35, zorder=0)
        cs = ax.contour(lons, lats, depth, levels=levels, colors="#4a6fa5", linewidths=0.4, alpha=0.7, zorder=0.5)
        ax.clabel(cs, fmt="%d m", fontsize=6)

    layer_style = {"blocks": dict(fc="none", ec="#7f7f7f", lw=0.5, ls="-"),
                   "relinquished_blocks": dict(fc="none", ec="#bbbbbb", lw=0.4, ls=":")}
    for key, style in layer_style.items():
        for f in inv.layers.get(key, []) or []:
            for ring in rings_from_geometry(f.get("geometry")):
                xs, ys = zip(*ring)
                ax.fill(xs, ys, zorder=1, **style)

    for r in inv.records:
        if not r.rings:
            continue
        col = STAGE_COLOURS.get(r.stage, "#d9d9d9")
        for ring in r.rings:
            xs, ys = zip(*ring)
            if r.kind == "evaluation_area":
                ax.fill(xs, ys, fc="none", ec=col, lw=1.1, ls="--", hatch="////", alpha=0.55, zorder=2)
            elif r.kind == "field":
                ax.fill(xs, ys, fc=col, ec="#333333", lw=0.6, alpha=0.55, zorder=3)
            else:
                ax.fill(xs, ys, fc=col, ec=col, lw=0.8, alpha=0.35, zorder=3)

    if show_pipelines:
        for p in inv.pipelines:
            colour = _PIPE_COLOURS.get(str(p.get("medium") or "").lower(), "#6a51a3")
            for part in p["parts"]:
                xs, ys = zip(*part)
                ax.plot(xs, ys, color=colour, lw=0.9, alpha=0.8, zorder=2.5)

    if show_hosts:
        ordered = sorted(inv.hosts, key=lambda h: (h["lon"] - lon0) ** 2 + ((h["lat"] - lat0) / coslat) ** 2)
        for i, h in enumerate(ordered):
            ax.scatter([h["lon"]], [h["lat"]], marker="s", s=34, c="#222222", edgecolors="white", linewidths=0.6, zorder=6)
            if h.get("name") and i < max_host_labels:
                ax.annotate(str(h["name"]), (h["lon"], h["lat"]), xytext=(4, -9), textcoords="offset points", fontsize=6, color="#222222", zorder=7)

    vols = [r.oe_msm3() for r in inv.records if r.oe_msm3()]
    vmax = max(vols) if vols else None
    labelled = 0
    for r in inv.records:
        if r.kind == "evaluation_area":
            continue
        col = STAGE_COLOURS.get(r.stage, "#d9d9d9")
        size = 40 + (160 * math.sqrt(r.oe_msm3() / vmax) if (vmax and r.oe_msm3()) else 30)
        marker = {"field": "D", "prospect": "^"}.get(r.kind, "o")
        ax.scatter([r.lon], [r.lat], marker=marker, s=size, c=col, edgecolors="black", linewidths=0.7, zorder=8)
        if labelled < max_labels:
            tag = r.name if r.oe_msm3() is None else "%s (%.1f)" % (r.name, r.oe_msm3())
            ax.annotate(tag, (r.lon, r.lat), xytext=(6, 5 if labelled % 2 else -11), textcoords="offset points", fontsize=7, zorder=9,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
            labelled += 1

    for frac in (1 / 3, 2 / 3, 1.0):
        pts = circle_points(lon0, lat0, radius * frac)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#555555", lw=0.8, ls="--", alpha=0.7, zorder=4)
        ax.annotate("%.0f km" % (radius * frac), (lon0, lat0 + math.degrees(radius * frac / 6371.0088)), xytext=(3, 2),
                    textcoords="offset points", fontsize=7, color="#555555")
    ax.scatter([lon0], [lat0], marker="*", s=420, c="gold", edgecolors="black", linewidths=1.0, zorder=10)
    ax.annotate(str(inv.target.get("name")), (lon0, lat0), xytext=(10, 8), textcoords="offset points", fontsize=10, fontweight="bold", zorder=11,
                bbox=dict(boxstyle="round,pad=0.2", fc="gold", ec="black", alpha=0.9))

    present = [s for s in STAGES if any(r.stage == s and r.kind != "evaluation_area" for r in inv.records)]
    handles = [Patch(fc=STAGE_COLOURS[s], ec="black", label=STAGE_LABELS[s]) for s in present]
    handles += [Line2D([], [], marker="o", ls="", mfc="white", mec="black", label="Discovery"),
                Line2D([], [], marker="D", ls="", mfc="white", mec="black", label="Field")]
    if any(r.kind == "prospect" for r in inv.records):
        handles.append(Line2D([], [], marker="^", ls="", mfc="white", mec="black", label="Prospect (user-supplied)"))
    if any(r.kind == "evaluation_area" for r in inv.records):
        handles.append(Patch(fc="none", ec="#f1a340", hatch="////", ls="--", label="Evaluation plan area"))
    if show_hosts and inv.hosts:
        handles.append(Line2D([], [], marker="s", ls="", mfc="#222222", mec="white", label="Host / platform"))
    if show_pipelines and inv.pipelines:
        handles += [Line2D([], [], color=_PIPE_COLOURS["gas"], label="Gas pipeline"), Line2D([], [], color=_PIPE_COLOURS["oil"], label="Oil pipeline")]
    handles.append(Line2D([], [], marker="*", ls="", mfc="gold", mec="black", ms=12, label="Target"))
    ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.9)

    s = inv.summary()
    ax.text(0.99, 0.99, "%d discoveries, %d fields, %d evaluation areas\nwithin %.0f km" % (s["n_discoveries"], s["n_fields"], s["n_evaluation_areas"], radius),
            transform=ax.transAxes, ha="right", va="top", fontsize=8, bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.9), zorder=12)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.grid(True, lw=0.3, alpha=0.4)
    ax.set_title(title or "Near-field discoveries around %s (%.0f km)" % (inv.target.get("name"), radius), fontsize=12)
    note = source_note or "Sources: " + "; ".join(sorted({r.source for r in inv.records if r.source})) + "."
    if vmax:
        note += " Marker size scales with recoverable oe (MSm3) where published."
    br = any(r.country == "BR" for r in inv.records)
    fig.text(0.01, 0.005, note + (" Screening only; positions of Brazilian discoveries are derived from wells." if br else " Screening only."),
             fontsize=6, color="#555555", wrap=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out
