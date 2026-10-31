"""Visual design system for integrated well planning figures and drawing sheets.

* colour-blind-safe palette (Okabe-Ito based) with fixed semantic colours: pressure, temperature, gas, oil, water, hydrate,
  limit/margin traffic lights (always paired with a text label, never colour alone) and primary/secondary barrier;
* typography from fonts that exist on the machine (Segoe UI, Calibri, Arial, DejaVu Sans fallbacks), TrueType embedded in PDF;
* consistent line weights, direct labelling helpers instead of legends, shaded uncertainty bands;
* A3 drawing sheets (420 x 297 mm) with border, title block, revision block, drawing number, optional scale bar and north arrow;
* export: 300 dpi PNG for Word, vector PDF/SVG for the drawing sheets, and a JSON provenance sidecar for every figure.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402

PALETTE: Dict[str, str] = {
    "pressure": "#0072B2", "temperature": "#D55E00", "gas": "#E69F00", "oil": "#2B8A3E", "water": "#56B4E9", "hydrate": "#CC79A7", "wax": "#8C6D31",
    "pass": "#3A923A", "warn": "#F2B134", "fail": "#C0392B", "review": "#7F8FA6", "na": "#BDBDBD",
    "primary_barrier": "#1F5FA8", "secondary_barrier": "#C0392B", "limit": "#333333", "grid": "#D9D9D9", "text": "#1A1A1A", "muted": "#6B6B6B",
    "band_low_high": "#9ECAE1", "band_alt": "#FDD0A2", "steel": "#5C5C5C", "cement": "#B8B8B8", "reservoir": "#F6E7B4", "caprock": "#CFCFCF", "seawater": "#D6EAF8",
    "accent1": "#0072B2", "accent2": "#E69F00", "accent3": "#009E73", "accent4": "#CC79A7", "accent5": "#56B4E9", "accent6": "#D55E00",
}
CATEGORICAL = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
STATUS_COLOR = {"PASS": PALETTE["pass"], "WARN": PALETTE["warn"], "FAIL": PALETTE["fail"], "NEEDS_REVIEW": PALETTE["review"], "NOT_ASSESSED": PALETTE["na"]}
FONT_CANDIDATES = ["Segoe UI", "Calibri", "Arial", "DejaVu Sans"]
LW = {"hair": 0.4, "thin": 0.7, "normal": 1.2, "thick": 1.9, "heavy": 2.8}
A3_MM = (420.0, 297.0)
MM = 1.0 / 25.4

_FONT: Optional[str] = None


def pick_font() -> str:
    """Return the first candidate family installed on this machine (DejaVu Sans ships with matplotlib)."""
    global _FONT
    if _FONT is None:
        names = {f.name for f in fm.fontManager.ttflist}
        _FONT = next((c for c in FONT_CANDIDATES if c in names), "DejaVu Sans")
    return _FONT


def setup_style() -> str:
    """Apply the design-system rcParams and return the font family used."""
    font = pick_font()
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": [font, "DejaVu Sans"], "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.labelsize": 9,
        "axes.edgecolor": PALETTE["text"], "axes.labelcolor": PALETTE["text"], "axes.linewidth": LW["normal"], "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": PALETTE["text"], "ytick.color": PALETTE["text"], "xtick.labelsize": 8, "ytick.labelsize": 8, "grid.color": PALETTE["grid"], "grid.linewidth": LW["thin"],
        "axes.grid": True, "axes.axisbelow": True, "axes.prop_cycle": matplotlib.cycler(color=CATEGORICAL), "legend.frameon": False, "legend.fontsize": 8,
        "figure.dpi": 100, "savefig.dpi": 300, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "path", "lines.linewidth": LW["normal"], "figure.facecolor": "white",
        "savefig.facecolor": "white", "axes.unicode_minus": True,
    })
    return font


setup_style()


def status_color(status: str) -> str:
    """Traffic-light colour for a status string (prefix match, NEEDS_REVIEW variants included)."""
    for key in ("NEEDS_REVIEW", "NOT_ASSESSED", "PASS", "WARN", "FAIL"):
        if str(status).startswith(key):
            return STATUS_COLOR[key]
    return PALETTE["na"]


def direct_label(ax, x: float, y: float, text: str, color: Optional[str] = None, dx: float = 0.0, dy: float = 0.0, ha: str = "left", va: str = "center", size: float = 8,
                 weight: str = "bold", bbox: bool = False) -> Any:
    """Label a line/point directly on the plot (offset in points) instead of using a legend."""
    return ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=size, color=color or PALETTE["text"], fontweight=weight,
                       bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85) if bbox else None)


def band(ax, x, low, high, color: Optional[str] = None, alpha: float = 0.25, label: Optional[str] = None) -> None:
    """Shaded low-high uncertainty band."""
    ax.fill_between(x, low, high, color=color or PALETTE["band_low_high"], alpha=alpha, linewidth=0, label=label)


def badge(ax, x: float, y: float, status: str, size: float = 7.5, transform=None) -> None:
    """Status badge: coloured rounded box with the status text (colour is never the only carrier)."""
    ax.text(x, y, status.replace("_", " "), fontsize=size, color="white", fontweight="bold", ha="center", va="center", transform=transform or ax.transData,
            bbox=dict(boxstyle="round,pad=0.25", fc=status_color(status), ec="none"))


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def provenance_record(figure_id: str, title: str, generator: str, inputs: Any, caption: str = "", synthetic: bool = True, sources: Optional[List[str]] = None,
                      ledger_refs: Optional[List[str]] = None, drawing_no: str = "") -> Dict[str, Any]:
    """Provenance sidecar content for one figure."""
    return {"schema": "iwp_figure_provenance.v1", "figure_id": figure_id, "title": title, "caption": caption, "generator": generator, "inputs_sha256_16": _hash(inputs),
            "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "synthetic": synthetic, "sources": sources or [], "ledger_refs": ledger_refs or [],
            "drawing_no": drawing_no, "font": pick_font(), "matplotlib": matplotlib.__version__, "python": platform.python_version()}


def save_figure(fig, stem: Path, provenance: Dict[str, Any], formats: Sequence[str] = ("png",), dpi: int = 300) -> Dict[str, str]:
    """Save a figure in the requested formats plus a ``<stem>.provenance.json`` sidecar; returns the written paths."""
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    written: Dict[str, str] = {}
    for fmt in formats:
        p = stem.with_suffix("." + fmt)
        fig.savefig(p, dpi=dpi, format=fmt, facecolor="white")
        written[fmt] = str(p)
    side = stem.with_suffix(".provenance.json")
    prov = dict(provenance)
    prov["files"] = {k: Path(v).name for k, v in written.items()}
    side.write_text(json.dumps(prov, indent=2), encoding="utf-8")
    written["provenance"] = str(side)
    plt.close(fig)
    return written


def small_multiples(n: int, ncols: int = 3, size: Tuple[float, float] = (3.4, 2.7), sharex: bool = False, sharey: bool = False):
    """Grid of small-multiple axes; unused axes are hidden."""
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(size[0] * ncols, size[1] * nrows), sharex=sharex, sharey=sharey, squeeze=False)
    flat = axes.ravel()
    for ax in flat[n:]:
        ax.set_visible(False)
    return fig, flat[:n]


def a3_sheet(title: str, drawing_no: str, revision: str = "A", project: str = "Integrated well planning", scale_text: str = "NTS", drawn_by: str = "neqsim-community",
             status: str = "FOR REVIEW", revisions: Optional[List[Tuple[str, str, str]]] = None, synthetic: bool = True, north_arrow: bool = False, scale_bar_m: Optional[float] = None,
             sheet_no: str = "1 of 1", content_note: str = "") -> Tuple[Any, Any, Tuple[float, float, float, float]]:
    """Create an A3 landscape sheet with border, title block and revision block.

    Returns:
        ``(fig, sheet_ax, content_box_mm)`` where ``sheet_ax`` uses millimetre coordinates (0..420, 0..297) and
        ``content_box_mm = (x0, y0, width, height)`` is the free drawing area above the title strip.
    """
    fig = plt.figure(figsize=(A3_MM[0] * MM, A3_MM[1] * MM))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, A3_MM[0])
    ax.set_ylim(0, A3_MM[1])
    ax.axis("off")
    ax.set_zorder(0)
    m = 10.0
    ax.add_patch(Rectangle((m, m), A3_MM[0] - 2 * m, A3_MM[1] - 2 * m, fill=False, ec=PALETTE["text"], lw=1.6))
    ax.add_patch(Rectangle((m + 2, m + 2), A3_MM[0] - 2 * m - 4, A3_MM[1] - 2 * m - 4, fill=False, ec=PALETTE["text"], lw=0.5))
    strip_h = 42.0
    ax.plot([m, A3_MM[0] - m], [m + strip_h, m + strip_h], color=PALETTE["text"], lw=1.0)
    tb_w = 190.0
    x0 = A3_MM[0] - m - tb_w
    ax.plot([x0, x0], [m, m + strip_h], color=PALETTE["text"], lw=1.0)
    rows = [("Project", project), ("Title", title), ("Drawing no.", drawing_no), ("Scale / sheet", "{} / {}".format(scale_text, sheet_no))]
    row_h = strip_h / 4.0
    for i, (k, v) in enumerate(rows):
        y = m + strip_h - (i + 1) * row_h
        ax.plot([x0, A3_MM[0] - m], [y, y], color=PALETTE["text"], lw=0.4)
        ax.text(x0 + 2, y + row_h / 2, k.upper(), fontsize=5.5, color=PALETTE["muted"], va="center")
        ax.text(x0 + 26, y + row_h / 2, v[:46] if k != "Title" else v[:58], fontsize=8.5 if k == "Title" else 7.5, fontweight="bold" if k in ("Title", "Drawing no.") else "normal", va="center", color=PALETTE["text"])
    rx = x0 - 115.0
    ax.plot([rx, rx], [m, m + strip_h], color=PALETTE["text"], lw=1.0)
    ax.text(rx + 2, m + strip_h - 3.5, "REV   DATE         DESCRIPTION", fontsize=5.5, color=PALETTE["muted"], va="center")
    revs = revisions or [(revision, _dt.date.today().isoformat(), "Issued for review" + (" (SYNTHETIC)" if synthetic else ""))]
    for i, (r, d, desc) in enumerate(revs[-4:][::-1]):
        y = m + strip_h - 9.0 - i * 7.5
        ax.text(rx + 2, y, "{:<3} {:<11} {}".format(r, d, desc[:36]), fontsize=6.5, va="center", family="monospace")
    ax.text(m + 3, m + strip_h - 5.0, "STATUS: {}   DRAWN: {}".format(status, drawn_by), fontsize=7, va="center", fontweight="bold")
    if synthetic:
        ax.text(m + 3, m + strip_h - 12.0, "SYNTHETIC DEMONSTRATION - NOT FIELD DATA, NOT FOR CONSTRUCTION", fontsize=7, color=PALETTE["fail"], va="center", fontweight="bold")
    if content_note:
        import textwrap

        lines = [ln for part in content_note.split("\n") for ln in textwrap.wrap(part, 60)][:4]
        for i, line in enumerate(lines):
            ax.text(m + 3, m + strip_h - 19.0 - i * 5.0, line, fontsize=6.0, va="center", color=PALETTE["muted"])
    if north_arrow:
        cx, cy = m + 22, m + strip_h + 20
        ax.add_patch(Polygon([[cx, cy + 12], [cx - 5, cy - 6], [cx, cy - 2], [cx + 5, cy - 6]], closed=True, fc=PALETTE["text"], ec=PALETTE["text"]))
        ax.text(cx, cy + 15, "N", ha="center", fontsize=8, fontweight="bold")
    if scale_bar_m:
        sx, sy = m + 50, m + strip_h + 10
        ax.plot([sx, sx + 40], [sy, sy], color=PALETTE["text"], lw=2.0)
        for t in (0, 20, 40):
            ax.plot([sx + t, sx + t], [sy - 1.5, sy + 1.5], color=PALETTE["text"], lw=1.0)
        ax.text(sx, sy + 4, "0", ha="center", fontsize=6.5)
        ax.text(sx + 40, sy + 4, "{:g} m".format(scale_bar_m), ha="center", fontsize=6.5)
    return fig, ax, (m + 4.0, m + strip_h + 4.0, A3_MM[0] - 2 * m - 8.0, A3_MM[1] - 2 * m - strip_h - 8.0)


def sheet_axes(fig, box_mm: Tuple[float, float, float, float], rel: Tuple[float, float, float, float], **kw):
    """Add an axes at ``rel = (x, y, w, h)`` fractions of the sheet content box (millimetre-based placement)."""
    x0, y0, w, h = box_mm
    rx, ry, rw, rh = rel
    return fig.add_axes([(x0 + rx * w) / A3_MM[0], (y0 + ry * h) / A3_MM[1], rw * w / A3_MM[0], rh * h / A3_MM[1]], **kw)
