"""Engineering-drawing graphics for a well plan: A3 sheet frame and title block, well schematic sheet with depth scales and side tracks,
BOP stack sketch, abandonment barrier schematic and trajectory plan/section plots (matplotlib, Agg backend).

All drawings are concept-level sketches built from the numbers the caller supplies; nothing here invents data. Every function saves a PNG
(at least 170 dpi) and returns its path.
"""

from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402

A3_MM = (420.0, 297.0)
DPI = 200
NAVY = "#1f3a5f"
SEA = "#cfe8f5"
STATUS_FILL = {"VERIFIED": "#d9f0e1", "UNVERIFIED-SOURCE": "#fdecc8", "DERIVED": "#dbe7f7", "ASSUMED": "#f6d9d9", "PLACEHOLDER": "#e6e6e6"}


def dodge(values: Sequence[float], min_gap: float, lo: Optional[float] = None, hi: Optional[float] = None) -> List[float]:
    """Spread sorted label positions so that neighbours are at least ``min_gap`` apart (order preserved).

    Args:
        values: desired positions (any order).
        min_gap: minimum spacing in the same unit.
        lo: optional lower bound of the label range.
        hi: optional upper bound of the label range.

    Returns:
        Adjusted positions in the order of ``values``.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    pos = [float(values[i]) for i in order]
    if lo is not None and pos:
        pos[0] = max(pos[0], lo)
    for k in range(1, len(pos)):
        pos[k] = max(pos[k], pos[k - 1] + min_gap)
    if hi is not None and pos and pos[-1] > hi:
        pos[-1] = hi
        for k in range(len(pos) - 2, -1, -1):
            pos[k] = min(pos[k], pos[k + 1] - min_gap)
    out = [0.0] * len(values)
    for k, i in enumerate(order):
        out[i] = pos[k]
    return out


def _save(fig, path: Path) -> Path:
    path = Path(path)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


class A3Sheet:
    """A3 landscape drawing sheet in millimetre coordinates with frame, title block, revision table and notes box.

    The sheet owns a figure of 420 x 297 mm. ``ax`` spans the whole sheet (x right, y up, units mm). ``add_axes_mm`` places a data
    axes at a millimetre rectangle so that drawing tracks line up on a common depth scale.
    """

    def __init__(self, margin_mm: float = 10.0) -> None:
        self.margin = margin_mm
        self.fig = plt.figure(figsize=(A3_MM[0] / 25.4, A3_MM[1] / 25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, A3_MM[0])
        self.ax.set_ylim(0, A3_MM[1])
        self.ax.axis("off")
        self.ax.add_patch(Rectangle((margin_mm, margin_mm), A3_MM[0] - 2 * margin_mm, A3_MM[1] - 2 * margin_mm, fill=False, lw=1.4, ec="k"))
        self.ax.add_patch(Rectangle((margin_mm - 4, margin_mm - 4), A3_MM[0] - 2 * margin_mm + 8, A3_MM[1] - 2 * margin_mm + 8, fill=False, lw=0.4, ec="0.4"))

    def add_axes_mm(self, x: float, y: float, w: float, h: float, **kw):
        """Add a data axes whose lower-left corner is (x, y) mm with size w x h mm."""
        return self.fig.add_axes([x / A3_MM[0], y / A3_MM[1], w / A3_MM[0], h / A3_MM[1]], **kw)

    def text(self, x: float, y: float, s: str, size: float = 7.0, **kw) -> None:
        """Place text at millimetre coordinates."""
        self.ax.text(x, y, s, fontsize=size, **kw)

    def title_block(self, fields: Dict[str, str], x: float = 262.0, y: float = 10.0, w: float = 148.0, h: float = 46.0) -> None:
        """Draw the title block (bottom right).

        Args:
            fields: keys ``title``, ``subtitle``, ``doc_id``, ``rev``, ``date``, ``status``, ``classification``, ``scale``, ``sheet``,
                ``drawn``, ``checked``, ``approved`` (all optional strings; unnamed people stay blank).
            x: left edge in mm.
            y: bottom edge in mm.
            w: width in mm.
            h: height in mm.
        """
        ax = self.ax
        ax.add_patch(Rectangle((x, y), w, h, fill=False, lw=1.2, ec="k"))
        ax.plot([x, x + w], [y + h - 16, y + h - 16], color="k", lw=0.8)
        ax.text(x + 3, y + h - 6.0, fields.get("title", ""), fontsize=11.5, fontweight="bold", va="center")
        ax.text(x + 3, y + h - 12.2, fields.get("subtitle", ""), fontsize=7.8, va="center", color="0.25")
        cols = [("Document", fields.get("doc_id", "")), ("Rev", fields.get("rev", "")), ("Date", fields.get("date", "")), ("Sheet", fields.get("sheet", "1 of 1")),
                ("Scale", fields.get("scale", "NTS")), ("Status", fields.get("status", "")), ("Class.", fields.get("classification", "")),
                ("Drawn", fields.get("drawn", "")), ("Checked", fields.get("checked", "")), ("Approved", fields.get("approved", ""))]
        cw = w / 5.0
        rh = (h - 16) / 2.0
        for i, (k, v) in enumerate(cols):
            r, c = divmod(i, 5)
            cx, cy = x + c * cw, y + h - 16 - (r + 1) * rh
            ax.add_patch(Rectangle((cx, cy), cw, rh, fill=False, lw=0.5, ec="0.2"))
            ax.text(cx + 1.5, cy + rh - 2.2, k, fontsize=5.8, va="top", color="0.35")
            ax.text(cx + 1.5, cy + 3.2, textwrap.shorten(str(v), 26, placeholder="..") if v else "", fontsize=7.2, va="bottom", fontweight="bold" if k in ("Status", "Document") else None)

    def notes_box(self, title: str, lines: Sequence[str], x: float, y: float, w: float, h: float, size: float = 6.6, wrap: int = 70) -> None:
        """Draw a boxed list of notes; lines are wrapped to ``wrap`` characters and clipped to the box height."""
        ax = self.ax
        ax.add_patch(Rectangle((x, y), w, h, fill=False, lw=0.8, ec="k"))
        ax.text(x + 2, y + h - 3, title, fontsize=size + 1.0, fontweight="bold", va="top")
        yy = y + h - 8.0
        step = size * 0.42
        for ln in lines:
            for k, part in enumerate(textwrap.wrap(ln, wrap) or [""]):
                if yy < y + 1.5:
                    return
                ax.text(x + 2 + (3 if k else 0), yy, part, fontsize=size, va="top")
                yy -= step

    def revision_table(self, rows: Sequence[Sequence[str]], x: float, y: float, w: float, row_h: float = 4.6) -> None:
        """Revision table; ``rows`` = [(rev, date, description, by), ...] drawn bottom-up from (x, y)."""
        heads = ("Rev", "Date", "Description", "By")
        widths = [10.0, 20.0, w - 10.0 - 20.0 - 14.0, 14.0]
        ax = self.ax
        all_rows = [heads] + list(rows)
        for i, r in enumerate(all_rows):
            yy = y + (len(all_rows) - 1 - i) * row_h
            cx = x
            for j, cell in enumerate(r):
                ax.add_patch(Rectangle((cx, yy), widths[j], row_h, fill=(i == 0), fc="#e8edf5", lw=0.5, ec="0.2"))
                ax.text(cx + 1.0, yy + row_h / 2, textwrap.shorten(str(cell), 60, placeholder=".."), fontsize=6.0, va="center", fontweight="bold" if i == 0 else None)
                cx += widths[j]

    def save(self, path: Path) -> Path:
        """Save the sheet as PNG and close it."""
        return _save(self.fig, path)


def _casing_half_width(od_in: float, scale: float, min_od: float = 7.0) -> float:
    """Half width on the sheet for a pipe of ``od_in`` (compressed so that 36 in and 7 in both stay readable)."""
    return scale * (max(od_in, min_od) ** 0.8) / 2.0


def well_schematic_sheet(spec: Dict[str, object], path: Path) -> Path:
    """A3 well schematic sheet: depth scales (MD / TVD RKB / TVDSS), formation column, nested casing with cement, side tracks and section table.

    ``spec`` keys:

    * ``well``, ``subtitle``, ``rig``, ``water_depth_m``, ``air_gap_m`` (RKB above MSL), ``td_md_m``, ``td_tvd_m`` (equal for a vertical well).
    * ``strings``: list of dicts with ``name``, ``casing_od_in`` (None for open hole), ``hole_in``, ``top_tvd_m`` (hanger depth of a liner or the
      mudline for a casing), ``shoe_tvd_m``, ``shoe_md_m`` (optional), ``toc_tvd_m`` (optional), ``mud_type`` (text), ``mud_sg`` (planned), ``liner`` (bool),
      ``pipe`` (text, e.g. grade and weight), ``riserless`` (bool), ``status`` (status label for the numbers).
    * ``tops``: list of (name, tvd_rkb_m) formation tops, ``target``: (name, tvd_rkb_m) optional.
    * ``tracks``: dict with ``z`` (TVD array), ``pore_low``, ``pore_base``, ``pore_high``, ``frac_low``, ``frac_base``, ``frac_high`` (sg) and optional
      ``extras``: list of dicts with ``label`` and either ``x`` and ``z`` (a curve) or ``x`` and ``y`` (points), plus ``marker``, ``color``.
    * ``bop``: dict with ``label`` (text next to the seabed marker, use a newline for two lines).
    * ``title_block``: fields for :meth:`A3Sheet.title_block`; ``notes``: list of note strings; ``revisions``: list of rows.
    * ``md_of_tvd``: optional callable giving MD for a TVD (deviated wells); default MD = TVD.

    Args:
        spec: drawing specification (see above).
        path: output PNG path.

    Returns:
        The PNG path.
    """
    sh = A3Sheet()
    ax0 = sh.ax
    air = float(spec.get("air_gap_m", 0.0))
    wd = float(spec.get("water_depth_m", 0.0))
    mudline = air + wd
    td = float(spec["td_tvd_m"])
    td_md = float(spec.get("td_md_m", td))
    md_of = spec.get("md_of_tvd") or (lambda z: z)
    strings = list(spec["strings"])
    y_lo, y_hi = 70.0, 258.0
    ymax = td + 80.0
    ytop = -(0.085 * (ymax + 0.0))  # headroom above RKB for the rig symbol
    dm = (ymax - ytop) / (y_hi - y_lo)  # metres of depth per millimetre of sheet

    def mk(x, w):
        a = sh.add_axes_mm(x, y_lo, w, y_hi - y_lo)
        a.set_ylim(ymax, ytop)
        a.set_xlim(0, 1)
        return a

    # header strip
    ax0.text(14, 282.0, str(spec.get("well", "")), fontsize=13.5, fontweight="bold", va="center", color=NAVY)
    ax0.text(14, 275.5, str(spec.get("subtitle", "")), fontsize=7.4, va="center", color="0.25")
    info = [f"Rig: {spec.get('rig', 'n/a')}", f"Water depth {wd:.0f} m", f"RKB {air:.0f} m above MSL", f"TD {td_md:.0f} m MD / {td:.0f} m TVD RKB"]
    ax0.text(406, 282.0, "   |   ".join(info), fontsize=7.6, ha="right", va="center")

    # column headers (two text lines in a 10 mm band)
    heads = [(14, 58, "DEPTH (m)", "MD  |  TVD RKB  |  TVDSS"), (72, 36, "FORMATION", "indicative tops, TVD RKB"), (110, 82, "WELL SCHEMATIC", "casing, cement, open hole"),
             (196, 62, "PRESSURE / MUD WEIGHT", "equivalent mud weight (sg)"), (262, 148, "SECTION DATA", "hole, pipe, shoe MD / TVD / TVDSS, cement top, mud")]
    for x, w, t1, t2 in heads:
        ax0.add_patch(Rectangle((x, y_hi + 1), w, 10.5, fc="#e8edf5", ec="k", lw=0.6))
        ax0.text(x + w / 2, y_hi + 8.3, t1, fontsize=7.6, fontweight="bold", ha="center", va="center")
        ax0.text(x + w / 2, y_hi + 3.6, t2, fontsize=6.0, ha="center", va="center", color="0.3")

    # depth scales
    ad = sh.add_axes_mm(14, y_lo, 58, y_hi - y_lo)
    ad.set_ylim(ymax, ytop)
    ad.set_xlim(0, 58)
    ad.axis("off")
    for z in np.arange(0.0, ymax, 500.0):
        ad.plot([0, 58], [z, z], color="0.8", lw=0.4)
        for x0, val in ((8, md_of(z)), (27, z), (46, z - air)):
            ad.text(x0, z, f"{val:.0f}", fontsize=6.4, ha="center", va="bottom")
    for z, lab in ((air, "MSL"), (mudline, "SEABED")):
        ad.plot([0, 58], [z, z], color="#0b6fa4", lw=0.9)
        ad.text(57, z - 2.2 * dm, lab, fontsize=5.8, ha="right", va="bottom", color="#0b6fa4", fontweight="bold")
    ad.plot([0, 58], [td, td], color="k", lw=1.0)
    ad.text(57, td - 0.5 * dm, "TD", fontsize=6.4, ha="right", va="bottom", fontweight="bold")

    # formation column
    af = mk(72, 36)
    af.axis("off")
    tops = sorted([(str(n), float(z)) for n, z in spec.get("tops", [])], key=lambda t: t[1])
    palette = ["#f2e6c9", "#e6dcb8", "#d9cfa5", "#cfd9c4", "#c6d4d9", "#d9c6d4", "#d4cfc6", "#e0e0c0"]
    edges = [0.0] + [z for _, z in tops] + [ymax]
    af.add_patch(Rectangle((0, air), 1, wd, fc=SEA, ec="none"))
    for i in range(len(tops)):
        af.add_patch(Rectangle((0, tops[i][1]), 1, edges[i + 2] - tops[i][1], fc=palette[i % len(palette)], ec="0.5", lw=0.5))
    lab_y = dodge([z for _, z in tops], 3.0 * dm, lo=mudline + 30.0, hi=ymax - 20.0)
    for (n, z), ly in zip(tops, lab_y):
        af.plot([0, 1], [z, z], color="0.3", lw=0.7)
        af.text(0.04, ly, f"{n}", fontsize=5.8, va="bottom", ha="left")
        af.text(0.96, ly, f"{z:.0f}", fontsize=5.4, va="bottom", ha="right", color="0.25")
        if abs(ly - z) > 0.6 * dm:
            af.plot([0.0, 0.03], [z, ly + 0.6 * dm], color="0.3", lw=0.4)
    af.set_xlim(0, 1)

    # schematic
    asx = sh.add_axes_mm(110, y_lo, 82, y_hi - y_lo)
    asx.set_xlim(-41, 41)
    asx.set_ylim(ymax, ytop)
    asx.axis("off")
    asx.add_patch(Rectangle((-41, air), 82, wd, fc=SEA, ec="none"))
    asx.plot([-41, 41], [air, air], color="#0b6fa4", lw=0.9)
    asx.plot([-41, 41], [mudline, mudline], color="#6b4f2a", lw=1.6)
    k = 2.0
    ordered = sorted(strings, key=lambda s: -float(s.get("casing_od_in") or s.get("hole_in") or 0))
    for s in ordered:
        od = s.get("casing_od_in")
        top = float(s.get("top_tvd_m", mudline))
        shoe = float(s["shoe_tvd_m"])
        hole = float(s.get("hole_in") or od or 8.5)
        hw = _casing_half_width(hole, k * 0.78)
        if od:
            cw = _casing_half_width(float(od), k * 0.78) * 0.86
            toc = s.get("toc_tvd_m")
            if toc is not None:
                z0 = max(float(toc), mudline)
                for sgn in (-1, 1):
                    xa, xb = sorted((sgn * hw, sgn * cw))
                    asx.add_patch(Rectangle((xa, z0), xb - xa, shoe - z0, fc="#bdbdbd", ec="none", hatch="////", lw=0))
            for sgn in (-1, 1):
                asx.plot([sgn * cw, sgn * cw], [top, shoe], color=NAVY, lw=1.9 if not s.get("liner") else 1.5, solid_capstyle="butt")
                asx.add_patch(Polygon([[sgn * cw, shoe], [sgn * (cw + 1.6), shoe + 0.5 * dm], [sgn * cw, shoe + 0.5 * dm]], closed=True, fc=NAVY, ec=NAVY))
            if s.get("liner"):
                for sgn in (-1, 1):
                    asx.add_patch(Rectangle((sgn * cw - 1.4, top), 2.8, 1.3 * dm, fc="#8a8a8a", ec="k", lw=0.4))
        else:
            asx.add_patch(Rectangle((-hw, top), 2 * hw, td - top, fc="#fbf3d6", ec="0.4", lw=0.8, ls="--"))
            asx.text(0, (top + td) / 2, f"{hole:g} in open hole", fontsize=6.4, ha="center", va="center", rotation=90, color="0.25")
    asx.plot([-6, 6], [td, td], color="k", lw=2.0)
    if spec.get("target"):
        tn, tz = spec["target"]
        asx.annotate("", xy=(0, tz), xytext=(12, tz - 2.0 * dm), arrowprops=dict(arrowstyle="-|>", color="#b02a2a", lw=1.4))
        asx.text(13, tz - 2.0 * dm, f"TARGET\n{tn}", fontsize=5.8, ha="left", va="bottom", color="#b02a2a", fontweight="bold")
    # rig, riser and BOP markers
    asx.plot([0, 0], [-1.2 * dm, mudline - 8], color="0.2", lw=1.0, ls=(0, (4, 2)))
    asx.add_patch(Rectangle((-5, mudline - 1.6 * dm), 10, 1.5 * dm, fc="#c9302c", ec="k", lw=0.7, zorder=5))
    asx.text(8, mudline - 2.6 * dm, str(spec.get("bop", {}).get("label", "BOP")), fontsize=5.8, va="center", ha="left")
    asx.text(3, air + 0.55 * (mudline - air), "marine riser", fontsize=5.8, va="center", ha="left", color="0.3")
    asx.add_patch(Polygon([[-22, -1.0 * dm], [22, -1.0 * dm], [14, -4.2 * dm], [-14, -4.2 * dm]], closed=True, fc="#555", ec="k"))
    asx.add_patch(Rectangle((-3, -7.5 * dm), 6, 3.3 * dm, fc="#777", ec="k", lw=0.5))
    asx.text(0, -8.3 * dm, "semi-submersible rig", fontsize=5.8, ha="center", va="bottom")
    asx.plot([-26, 26], [0, 0], color="k", lw=0.8)
    asx.text(-26, 0.3 * dm, f"RKB (+{air:.0f} m MSL)", fontsize=5.8, ha="left", va="top")

    # pressure track
    ap = sh.add_axes_mm(196, y_lo, 62, y_hi - y_lo)
    ap.set_ylim(ymax, ytop)
    ap.set_xlim(0.9, 2.4)
    ap.grid(alpha=0.25, lw=0.4)
    ap.tick_params(labelsize=6)
    ap.set_yticklabels([])
    tr = spec.get("tracks") or {}
    if tr:
        z = np.asarray(tr["z"], dtype=float)
        ap.fill_betweenx(z, tr["pore_low"], tr["pore_high"], color="#9ecae1", alpha=0.55, lw=0, label="pore low-high")
        ap.plot(tr["pore_base"], z, color="#08519c", lw=1.0, label="pore base")
        ap.fill_betweenx(z, tr["frac_low"], tr["frac_high"], color="#fcae91", alpha=0.55, lw=0, label="fracture low-high")
        ap.plot(tr["frac_low"], z, color="#a50f15", lw=1.0, label="fracture low")
        for ex in tr.get("extras", []):
            if "z" in ex:
                ap.plot(ex["x"], ex["z"], color=ex.get("color", "k"), lw=ex.get("lw", 1.0), ls=ex.get("ls", "--"), label=ex["label"])
            else:
                ap.scatter(ex["x"], ex["y"], s=ex.get("size", 10), marker=ex.get("marker", "o"), color=ex.get("color", "k"), edgecolors="k", linewidths=0.3, label=ex["label"], zorder=6)
    for s in strings:
        top, bot = float(s["top_tvd_m"]), float(s["shoe_tvd_m"])
        hole_top = float(s.get("hole_top_tvd_m", top))
        if s.get("mud_sg"):
            ap.plot([float(s["mud_sg"])] * 2, [hole_top, bot], color="#238b45", lw=3.0, solid_capstyle="butt")
        if s.get("casing_od_in"):
            ap.axhline(bot, color="0.4", lw=0.5)
    ap.plot([], [], color="#238b45", lw=3, label="planned mud weight")
    ap.axhline(mudline, color="#6b4f2a", lw=1.0)
    ap.axhline(td, color="k", lw=1.0)
    ap.legend(fontsize=5.4, loc="upper center", bbox_to_anchor=(0.5, -0.055), ncol=2, frameon=False)

    # section table: boxes at the shoe depth, dodged in millimetres
    at = sh.add_axes_mm(262, y_lo, 148, y_hi - y_lo)
    at.set_xlim(0, 148)
    at.set_ylim(ymax, ytop)
    at.axis("off")
    boxes = []
    for s in strings:
        shoe = float(s["shoe_tvd_m"])
        smd = float(s.get("shoe_md_m", md_of(shoe)))
        pipe = f"{float(s['casing_od_in']):g} in {'liner' if s.get('liner') else 'casing'}" if s.get("casing_od_in") else "open hole"
        l1 = f"{s['name']}  |  hole {s.get('hole_label') or format(float(s.get('hole_in') or 0), 'g') + ' in'}" + ("  |  riserless" if s.get("riserless") else "")
        l2 = f"{pipe}: {s.get('pipe', '')}".strip(": ")
        l3 = (f"shoe {smd:.0f} m MD / {shoe:.0f} m TVD / {shoe - air:.0f} m TVDSS" if s.get("casing_od_in") else f"TD {smd:.0f} m MD / {shoe:.0f} m TVD / {shoe - air:.0f} m TVDSS")
        toc = s.get("toc_tvd_m")
        l4 = (f"TOC {float(toc):.0f} m" if toc is not None else "no cement (open hole)") + f"  |  mud: {s.get('mud_type', 'n/a')} {float(s.get('mud_sg', 0)):.2f} sg"
        boxes.append((shoe, [l1, l2, l3, l4], str(s.get("status", ""))))
    bh = 16.0  # box height in mm
    ly = dodge([b[0] - 0.6 * bh * dm for b in boxes], (bh + 1.2) * dm, lo=mudline + 10.0, hi=ymax - (bh + 2.5) * dm)
    for (shoe, lines, status), yy in zip(boxes, ly):
        at.plot([0, 6], [shoe, yy + 0.5 * bh * dm], color="0.45", lw=0.5)
        at.add_patch(Rectangle((6, yy), 140, bh * dm, fc=STATUS_FILL.get(status, "#ffffff"), ec="0.4", lw=0.5))
        for i, ln in enumerate(lines):
            at.text(8, yy + (2.2 + i * 3.7) * dm, textwrap.shorten(ln, 80, placeholder=".."), fontsize=6.0 if i else 6.8, fontweight="bold" if i == 0 else None, va="center")

    # legend and notes
    ax0.text(14, 64.2, "LEGEND", fontsize=7, fontweight="bold", va="center")
    lx = 14
    for lab, fc, hatch in (("cement", "#bdbdbd", "////"), ("casing / liner", "white", None), ("open hole", "#fbf3d6", None), ("sea", SEA, None)):
        ax0.add_patch(Rectangle((lx, 57.5), 7, 3.2, fc=fc, ec="k", lw=0.5, hatch=hatch))
        ax0.text(lx + 8.5, 59.1, lab, fontsize=6.0, va="center")
        lx += 33
    ax0.text(14, 54.0, "Box colour in the section data = status of the numbers: green VERIFIED, amber UNVERIFIED-SOURCE, blue DERIVED, red ASSUMED.", fontsize=5.8, va="center", color="0.3")
    sh.notes_box("NOTES", list(spec.get("notes", [])), 14, 12, 244, 39, wrap=148)
    rev = spec.get("revisions")
    if rev:
        sh.revision_table(rev, 262, 58.5, 148)
    sh.title_block(dict(spec.get("title_block", {})))
    return sh.save(path)


def bop_stack_sketch(spec: Dict[str, object], path: Path) -> Path:
    """Block sketch of a subsea BOP stack and riser: elements are drawn bottom-up with their pressure ratings.

    ``spec`` keys: ``title``, ``subtitle``, ``elements``: list (bottom to top) of dicts with ``label``, ``kind`` (one of ``wellhead``, ``connector``,
    ``ram``, ``annular``, ``shear``, ``flex``, ``riser``), ``rating`` (text, e.g. "15 ksi") and ``status`` (label); ``lines``: list of text lines for
    choke and kill line notes, ``footer``: status note.

    Args:
        spec: drawing specification.
        path: output PNG path.

    Returns:
        The PNG path.
    """
    fig, ax = plt.subplots(figsize=(8.6, 9.6))
    ax.set_xlim(-60, 150)
    els = list(spec["elements"])
    heights = {"wellhead": 14, "connector": 7, "ram": 13, "annular": 16, "shear": 13, "flex": 10, "riser": 18}
    colors = {"wellhead": "#8a8a8a", "connector": "#b0b0b0", "ram": "#c9302c", "annular": "#e08a3c", "shear": "#7d1f1f", "flex": "#5c7a99", "riser": "#d9e2ec"}
    y = 0.0
    for e in els:
        h = heights.get(e.get("kind", "ram"), 12)
        kind = e.get("kind", "ram")
        w = 34 if kind in ("ram", "annular", "shear") else 26 if kind in ("wellhead", "connector") else 18
        ax.add_patch(FancyBboxPatch((-w / 2, y + 0.8), w, h - 1.6, boxstyle="round,pad=0.0,rounding_size=1.5", fc=colors.get(kind, "#cccccc"), ec="k", lw=0.9))
        if kind in ("ram", "shear"):
            ax.plot([-w / 2 - 4, -w / 2], [y + h / 2, y + h / 2], color="k", lw=2)
            ax.plot([w / 2, w / 2 + 4], [y + h / 2, y + h / 2], color="k", lw=2)
        ax.text(31, y + h / 2, f"{e['label']}", fontsize=8.0, va="center", ha="left")
        if e.get("rating"):
            ax.text(104, y + h / 2, f"{e['rating']}  [{e.get('status', 'ASSUMED')}]", fontsize=7.4, va="center", ha="left", color="#7d1f1f")
        y += h
    for sgn in (-1, 1):
        ax.plot([sgn * 27] * 2, [8, y - 8], color="#444", lw=2.2)
    ax.text(-29.5, y / 2, "choke / kill lines", fontsize=7, rotation=90, va="center", ha="right")
    ax.plot([0, 0], [y, y + 22], color="#7a8b99", lw=7, solid_capstyle="butt")
    ax.text(5, y + 15, "marine riser to rig", fontsize=8, va="center")
    ax.annotate("", xy=(0, y + 30), xytext=(0, y + 22), arrowprops=dict(arrowstyle="-|>", color="k"))
    ax.plot([-50, 90], [0.5, 0.5], color="#6b4f2a", lw=3)
    ax.text(-50, -4.2, "seabed", fontsize=7.5, va="top", color="#6b4f2a")
    ax.set_ylim(-8, y + 36)
    ax.axis("off")
    ax.set_title(str(spec.get("title", "BOP stack sketch")), fontsize=11, fontweight="bold", loc="left")
    notes = list(spec.get("lines", []))
    foot = str(spec.get("footer", ""))
    fig.text(0.02, 0.025, "\n".join(textwrap.fill(n, 125) for n in notes + ([foot] if foot else [])), fontsize=7.0, va="bottom", ha="left", color="0.2")
    fig.subplots_adjust(bottom=0.14)
    return _save(fig, path)


def barrier_schematic(spec: Dict[str, object], path: Path) -> Path:
    """Concept sketch of a permanent abandonment barrier arrangement (NORSOK D-010 style principle: primary and secondary barrier envelopes).

    ``spec`` keys: ``title``, ``water_depth_m``, ``air_gap_m``, ``td_m``, ``strings``: list of dicts (``label``, ``od_in``, ``top_m``, ``shoe_m``);
    ``plugs``: list of dicts (``label``, ``top_m``, ``bottom_m``, ``role`` in ``primary``, ``secondary``, ``environmental``), ``zones``: list of
    (label, top_m, bottom_m) permeable/reservoir intervals, ``cap_rock``: (label, top_m, bottom_m), ``cut_depth_m`` (wellhead cut below seabed),
    ``footer`` text. Depths m RKB.

    Args:
        spec: drawing specification.
        path: output PNG path.

    Returns:
        The PNG path.
    """
    fig, ax = plt.subplots(figsize=(8.8, 9.6))
    air = float(spec.get("air_gap_m", 0))
    wd = float(spec.get("water_depth_m", 0))
    ml = air + wd
    td = float(spec["td_m"])
    ax.set_xlim(-45, 128)
    ax.add_patch(Rectangle((-45, air), 173, wd, fc=SEA, ec="none"))
    ax.plot([-45, 128], [ml, ml], color="#6b4f2a", lw=2)
    ax.text(-44, ml - 10, "seabed", fontsize=7, color="#6b4f2a", va="bottom")
    zones = spec.get("zones", [])
    for lab, t, b in zones:
        ax.add_patch(Rectangle((-40, t), 22, b - t, fc="#fbe3a6", ec="0.5", lw=0.5))
        ax.text(-39, (t + b) / 2, "\n".join(textwrap.wrap(lab, 22)), fontsize=6.8, va="center")
    if spec.get("cap_rock"):
        lab, t, b = spec["cap_rock"]
        ax.add_patch(Rectangle((-40, t), 22, b - t, fc="#c8c8c8", ec="0.5", lw=0.5))
        ax.text(-39, (t + b) / 2, "\n".join(textwrap.wrap(lab, 22)), fontsize=6.8, va="center")
    strs = sorted(spec["strings"], key=lambda s: -s["od_in"])
    for s in strs:
        w = s["od_in"] ** 0.8 * 0.55
        top = max(float(s.get("top_m", ml)), ml)
        for sg in (-1, 1):
            ax.plot([sg * w, sg * w], [top, s["shoe_m"]], color=NAVY, lw=1.6)
        ax.plot([-w, w], [s["shoe_m"], s["shoe_m"]], color=NAVY, lw=1.6)
        ax.text(w + 1.2, s["shoe_m"] + 45, f"{s['label']} shoe {s['shoe_m']:.0f} m", fontsize=6.6, va="top", ha="left")
    wmax = max(s["od_in"] ** 0.8 * 0.55 for s in strs)
    cols = {"primary": "#2c7fb8", "secondary": "#e67e22", "environmental": "#7d3c98"}
    for p in spec.get("plugs", []):
        cover = [s["od_in"] ** 0.8 * 0.55 for s in strs if s["shoe_m"] >= p["top_m"] and max(float(s.get("top_m", ml)), ml) <= p["bottom_m"]]
        w = min(cover) if cover else wmax
        ax.add_patch(Rectangle((-w, p["top_m"]), 2 * w, p["bottom_m"] - p["top_m"], fc=cols.get(p["role"], "#999"), ec="k", lw=0.8, alpha=0.8))
        ax.text(wmax + 18, (p["top_m"] + p["bottom_m"]) / 2, f"{p['label']}  ({p['top_m']:.0f}-{p['bottom_m']:.0f} m)", fontsize=7.0, va="center", ha="left",
                bbox=dict(fc="white", ec=cols.get(p["role"], "#999"), lw=1.0, pad=1.5))
        ax.plot([w, wmax + 17.5], [(p["top_m"] + p["bottom_m"]) / 2] * 2, color=cols.get(p["role"], "#999"), lw=0.8)
    if spec.get("cut_depth_m") is not None:
        zc = ml + float(spec["cut_depth_m"])
        ax.plot([-wmax - 3, wmax + 3], [zc, zc], color="r", lw=1.4, ls="--")
        ax.text(-wmax - 5, zc + 30, f"casings cut {float(spec['cut_depth_m']):.0f} m below seabed,\nwellhead recovered", fontsize=6.6, ha="right", va="top", color="r")
    ax.set_ylim(td + 120, air - 40)
    ax.set_xticks([])
    ax.set_ylabel("Depth below RKB (m)")
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    handles = [Rectangle((0, 0), 1, 1, fc=cols[k], ec="k", label=f"{k} barrier element") for k in ("primary", "secondary", "environmental")]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=7.5, frameon=False)
    ax.set_title(str(spec.get("title", "Abandonment barrier concept")), fontsize=11, fontweight="bold", loc="left")
    if spec.get("footer"):
        fig.text(0.02, 0.012, str(spec["footer"]), fontsize=7.0, va="bottom", ha="left", color="0.2", wrap=True)
    fig.subplots_adjust(bottom=0.13)
    return _save(fig, path)


def trajectory_plan_section(paths: Dict[str, Dict[str, Sequence[float]]], path: Path, offsets: Optional[Sequence[Dict[str, object]]] = None,
                            title: str = "Trajectory: plan view and vertical section", section_azimuth_deg: Optional[float] = None,
                            rings_m: Sequence[float] = (), plan_extent_m: Optional[float] = None) -> Path:
    """Plan view (east/north) and vertical section (departure versus TVD) of one or more planned paths with offset-well markers.

    Args:
        paths: name -> dict with arrays ``e``, ``n``, ``tvd`` (m, east and north relative to the surface location or in grid coordinates).
        path: output PNG path.
        offsets: optional list of dicts with ``name``, ``e``, ``n`` and optional ``td_m`` (plotted in plan only as a vertical well).
        title: figure title.
        section_azimuth_deg: azimuth of the section plane; default = the direction of the last point of the first path.
        rings_m: optional distance rings (m) around the first path's surface location.
        plan_extent_m: half width of the plan view around the first surface location; offsets outside are not drawn (default: show all).

    Returns:
        The PNG path.
    """
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.2, 5.8), gridspec_kw={"width_ratios": [1.0, 1.0]})
    names = list(paths)
    e0 = float(paths[names[0]]["e"][0])
    n0 = float(paths[names[0]]["n"][0])
    cm = plt.get_cmap("tab10")
    if section_azimuth_deg is None:
        de, dn = float(paths[names[0]]["e"][-1]) - e0, float(paths[names[0]]["n"][-1]) - n0
        section_azimuth_deg = math.degrees(math.atan2(de, dn)) % 360.0
    az = math.radians(section_azimuth_deg)
    for i, nm in enumerate(names):
        p = paths[nm]
        e, n, tvd = (np.asarray(p[k], dtype=float) for k in ("e", "n", "tvd"))
        a1.plot(e, n, color=cm(i), lw=2.0, label=nm)
        a1.plot(e[0], n[0], "s", color=cm(i), ms=6)
        a1.plot(e[-1], n[-1], "o", color=cm(i), ms=6)
        dep = (e - e0) * math.sin(az) + (n - n0) * math.cos(az)
        a2.plot(dep, tvd, color=cm(i), lw=2.0, label=nm)
    for r in rings_m:
        t = np.linspace(0, 2 * math.pi, 181)
        a1.plot(e0 + r * np.cos(t), n0 + r * np.sin(t), color="0.6", lw=0.7, ls=":")
        a1.text(e0 + r * 0.707, n0 - r * 0.707, f"{r:.0f} m", fontsize=6.5, color="0.4", va="top", ha="left")
    off_pts = []
    for o in offsets or []:
        if plan_extent_m is not None and math.hypot(float(o["e"]) - e0, float(o["n"]) - n0) > plan_extent_m * 1.2:
            continue
        a1.plot(float(o["e"]), float(o["n"]), "^", color="#6b4f2a", ms=7, mec="k", mew=0.4)
        off_pts.append((float(o["e"]), float(o["n"]), str(o["name"])))
    for (oe, on, nm) in off_pts:
        a1.annotate(nm, (oe, on), xytext=(6, 5), textcoords="offset points", fontsize=7.0)
    if plan_extent_m is not None:
        a1.set_xlim(e0 - plan_extent_m, e0 + plan_extent_m)
        a1.set_ylim(n0 - plan_extent_m, n0 + plan_extent_m)
        a1.set_aspect("equal", adjustable="box")
    else:
        a1.set_aspect("equal", adjustable="datalim")
    a1.set_xlabel("Easting (m)")
    a1.set_ylabel("Northing (m)")
    a1.set_title("Plan view (north up); square = surface, circle = TD", fontsize=8.5)
    a1.grid(alpha=0.25)
    a1.legend(fontsize=7.5, loc="best")
    a2.invert_yaxis()
    a2.set_xlabel(f"Departure along azimuth {section_azimuth_deg:.0f} deg (m)")
    a2.set_ylabel("TVD below RKB (m)")
    a2.set_title("Vertical section", fontsize=8.5)
    a2.grid(alpha=0.25)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    return _save(fig, path)


def anticollision_sweep_plot(azimuths_deg: Sequence[float], min_centre_distance_m: Sequence[float], min_separation_factor: Sequence[float], path: Path,
                             sf_limit: float = 1.5, title: str = "Offset clearance versus planned azimuth") -> Path:
    """Minimum centre distance and minimum separation factor of a planned path against offset wells for a sweep of azimuths.

    Args:
        azimuths_deg: tested azimuths.
        min_centre_distance_m: governing centre-to-centre distance per azimuth.
        min_separation_factor: governing separation factor per azimuth (use NaN when not computed).
        path: output PNG path.
        sf_limit: separation-factor acceptance line (screening convention).
        title: figure title.

    Returns:
        The PNG path.
    """
    fig, a1 = plt.subplots(figsize=(8.4, 4.6))
    az = np.asarray(azimuths_deg, dtype=float)
    a1.plot(az, min_centre_distance_m, color=NAVY, lw=2.0, marker="o", ms=3.5, label="minimum centre distance (left)")
    a1.set_xlabel("Planned azimuth (deg)")
    a1.set_ylabel("Centre distance (m)", color=NAVY)
    a1.set_xlim(0, 360)
    a1.set_xticks(range(0, 361, 45))
    a1.grid(alpha=0.25)
    a2 = a1.twinx()
    sf = np.asarray(min_separation_factor, dtype=float)
    a2.plot(az, np.minimum(sf, 60.0), color="#c0392b", lw=1.6, ls="--", marker="s", ms=3, label="minimum separation factor (right, capped at 60)")
    a2.axhline(sf_limit, color="#c0392b", lw=0.9, ls=":")
    a2.text(358, sf_limit, f" SF {sf_limit:g}", color="#c0392b", fontsize=7, va="bottom", ha="right")
    a2.set_ylabel("Separation factor (-)", color="#c0392b")
    h1, l1 = a1.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    a1.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False)
    a1.set_title(title, fontsize=10)
    fig.subplots_adjust(bottom=0.27)
    return _save(fig, path)
