"""A3 engineering drawing sheets: well schematic and barrier schematics.

The well schematic draws casing and liner shoes with sizes and grades, cement hatching, tubing, packer, safety valve, gas-lift
mandrels, perforations, tree symbol, formation tops and fluid contacts, MD/TVD/TVDSS depth scales, and aligned side tracks for
pore/fracture/mud-weight and deviation/DLS on a shared depth axis. The barrier sheet shows primary (blue) and secondary (red)
barrier envelopes per well state with element status. Both carry a title block, revision block, drawing number and a SYNTHETIC
stamp when the basis is synthetic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Polygon, Rectangle

from .barriers import BarrierState
from .iwp_style import LW, PALETTE, a3_sheet, direct_label, provenance_record, save_figure, sheet_axes, status_color
from .registers import get_path

FRACTIONS = {0.375: "3/8", 0.625: "5/8", 0.5: "1/2", 0.25: "1/4", 0.75: "3/4", 0.875: "7/8", 0.125: "1/8"}


def _fmt_in(od: float) -> str:
    whole = int(od)
    frac = round(od - whole, 3)
    return '{} {}"'.format(whole, FRACTIONS[frac]) if frac in FRACTIONS else '{:g}"'.format(od)


def _md_to_tvd(survey: Optional[Dict[str, Sequence[float]]], md_td: float, tvd_td: float):
    if survey:
        return lambda md: float(np.interp(md, survey["md"], survey["tvd"]))
    return lambda md: float(md) * tvd_td / md_td


def _tree(ax, y_top: float, subsea: bool, width: float = 0.22) -> None:
    """Simple tree symbol above the wellhead (valves as bow-ties)."""
    h = abs(y_top)
    ax.add_patch(Rectangle((-width * 0.55, y_top), width * 1.1, h * 0.28, fc="#444444", ec="black", lw=0.6))
    for k, yy in enumerate((y_top + h * 0.34, y_top + h * 0.62)):
        ax.add_patch(Polygon([[-width * 0.5, yy], [width * 0.5, yy + h * 0.12], [width * 0.5, yy], [-width * 0.5, yy + h * 0.12]], closed=True, fc="white", ec="black", lw=0.7))
    ax.plot([0, 0], [y_top + h * 0.28, y_top + h * 0.9], color="black", lw=1.0)
    ax.plot([0, width * 1.1], [y_top + h * 0.5, y_top + h * 0.5], color="black", lw=1.0)
    ax.add_patch(Polygon([[width * 0.7, y_top + h * 0.44], [width * 1.0, y_top + h * 0.5 + h * 0.06], [width * 1.0, y_top + h * 0.44], [width * 0.7, y_top + h * 0.5 + h * 0.06]], closed=True, fc="white", ec="black", lw=0.7))
    ax.text(0, y_top - h * 0.12, "subsea tree" if subsea else "tree", ha="center", va="bottom", fontsize=6.5)


def well_schematic_sheet(basis: Dict[str, Any], survey: Optional[Dict[str, Sequence[float]]] = None, drawing_no: str = "IWP-DWG-001", revision: str = "A",
                         revisions: Optional[List[Tuple[str, str, str]]] = None) -> plt.Figure:
    """Draw the well schematic on an A3 sheet from the planning basis (and the survey for MD/TVD and deviation tracks)."""
    comp = get_path(basis, "completion") or {}
    md_td, tvd_td = float(get_path(basis, "trajectory.md_m")), float(get_path(basis, "trajectory.tvd_m"))
    rkb = float(get_path(basis, "datums.reference_elevation_msl_m") or 0.0)
    env = get_path(basis, "well.environment")
    wd = float(get_path(basis, "datums.water_depth_m") or 0.0)
    wtype = get_path(basis, "well.type")
    synthetic = bool(get_path(basis, "study.synthetic"))
    m2t = _md_to_tvd(survey, md_td, tvd_td)
    fig, sheet, box = a3_sheet("Well schematic - {} ({})".format(get_path(basis, "well.id"), wtype.replace("_", " ")), drawing_no, revision, project=str(get_path(basis, "study.title") or "")[:52],
                               scale_text="NTS (depth-true, width exaggerated)", revisions=revisions, synthetic=synthetic,
                               content_note="Depths in m below {} ({:g} m above MSL). Pressures bara. Formation tops/contacts are study assumptions.".format(get_path(basis, "datums.reference") or "RKB", rkb))
    ymin = -0.075 * tvd_td
    ax_s = sheet_axes(fig, box, (0.0, 0.03, 0.12, 0.93))
    ax_w = sheet_axes(fig, box, (0.125, 0.03, 0.36, 0.93), sharey=ax_s)
    ax_p = sheet_axes(fig, box, (0.505, 0.03, 0.15, 0.93), sharey=ax_s)
    ax_d = sheet_axes(fig, box, (0.675, 0.03, 0.12, 0.93), sharey=ax_s)
    ax_s.set_ylim(tvd_td * 1.02, ymin)
    for a in (ax_s, ax_w, ax_p, ax_d):
        a.tick_params(labelsize=7)
    # depth scale
    ax_s.set_xlim(0, 1)
    ax_s.set_xticks([])
    ax_s.grid(False)
    for s in ("left", "bottom"):
        ax_s.spines[s].set_visible(False)
    ax_s.set_yticks([])
    step = 250 if tvd_td > 1200 else 100
    ticks = np.arange(0, tvd_td + 1, step)
    ax_s.text(0.1, ymin * 1.0, "MD", fontsize=7, fontweight="bold", ha="center", va="bottom")
    ax_s.text(0.5, ymin * 1.0, "TVD", fontsize=7, fontweight="bold", ha="center", va="bottom")
    ax_s.text(0.9, ymin * 1.0, "TVDSS", fontsize=7, fontweight="bold", ha="center", va="bottom")
    tvd_grid = np.linspace(0, tvd_td, 400)
    md_of_tvd = (lambda z: float(np.interp(z, survey["tvd"], survey["md"]))) if survey else (lambda z: z * md_td / tvd_td)
    for z in ticks:
        ax_s.plot([0, 1], [z, z], color=PALETTE["grid"], lw=0.5)
        ax_s.text(0.1, z, "{:.0f}".format(md_of_tvd(z)), fontsize=6.5, ha="center", va="center", color=PALETTE["muted"], bbox=dict(fc="white", ec="none", pad=0.5))
        ax_s.text(0.5, z, "{:.0f}".format(z), fontsize=6.8, ha="center", va="center", fontweight="bold", bbox=dict(fc="white", ec="none", pad=0.5))
        ax_s.text(0.9, z, "{:.0f}".format(z - rkb), fontsize=6.5, ha="center", va="center", color=PALETTE["muted"], bbox=dict(fc="white", ec="none", pad=0.5))
    # schematic track
    ax_w.set_xlim(-1.0, 1.6)
    ax_w.set_xticks([])
    ax_w.grid(False)
    for s in ("left", "bottom", "top", "right"):
        ax_w.spines[s].set_visible(False)
    forms = comp.get("formations") or []
    right_labels: List[Tuple[float, str, str, str]] = []
    for k, f in enumerate(forms):
        if f.get("kind") == "contact":
            ax_w.plot([-1.0, 1.6], [f["top_tvd_m"]] * 2, color=PALETTE["water"], lw=1.3, ls="--")
            ax_w.text(1.58, f["top_tvd_m"], f["name"], ha="right", va="bottom", fontsize=6.5, color=PALETTE["water"], fontweight="bold")
            continue
        base = f.get("base_tvd_m") or (forms[k + 1]["top_tvd_m"] if k + 1 < len(forms) else tvd_td * 1.02)
        col = PALETTE["reservoir"] if f["name"].lower().startswith("reservoir") else (PALETTE["caprock"] if "cap" in f["name"].lower() else "#F7F7F7")
        ax_w.add_patch(Rectangle((-1.0, f["top_tvd_m"]), 2.6, base - f["top_tvd_m"], fc=col, ec="none", alpha=0.55, zorder=0))
        right_labels.append((float(f["top_tvd_m"]), "{} - {:.0f} m TVD".format(f["name"], f["top_tvd_m"]), PALETTE["text"], "right"))
        ax_s.plot([0, 1], [f["top_tvd_m"]] * 2, color=PALETTE["steel"], lw=0.9)
    if env == "subsea":
        sb = wd + rkb
        ax_w.add_patch(Rectangle((-1.0, 0), 2.6, sb, fc=PALETTE["seawater"], ec="none", alpha=0.9, zorder=0))
        ax_w.plot([-1.0, 1.6], [sb, sb], color="#1B4F72", lw=1.5)
        ax_w.text(-0.98, sb, "seabed  {:g} m MSL".format(-wd), fontsize=7, va="bottom", color="#1B4F72", fontweight="bold")
        top_y = sb
    else:
        ax_w.plot([-1.0, 1.6], [0, 0], color="#6B4F2A", lw=1.5)
        ax_w.text(-0.98, 0, "RKB / ground level" if env == "onshore" else "RKB / deck", fontsize=7, va="bottom", color="#6B4F2A", fontweight="bold")
        top_y = 0.0
    casings = sorted(comp.get("casing") or [], key=lambda c: -c["od_in"])
    max_od = max([c["od_in"] for c in casings] + [20.0])
    hw = lambda od: 0.82 * od / max_od  # noqa: E731
    tub = comp.get("tubing") or {}
    for k, c in enumerate(casings):
        top = m2t(c.get("top_md_m", 0.0))
        shoe = c.get("shoe_tvd_m") or m2t(c["shoe_md_m"])
        half = hw(c["od_in"]) * 0.5 + 0.06 * (len(casings) - k) * 0.0
        half = hw(c["od_in"]) * 0.55
        wall = 0.035
        hole_half = hw(c.get("hole_in", c["od_in"] * 1.25)) * 0.55
        ctop = m2t(c["cement_top_md_m"]) if c.get("cement_top_md_m") is not None else None
        if ctop is not None:
            for sgn in (-1, 1):
                x0 = sgn * half if sgn > 0 else -hole_half
                ax_w.add_patch(Rectangle((half if sgn > 0 else -hole_half, ctop), hole_half - half, shoe - ctop, fc="#D0D0D0", ec="#8A8A8A", lw=0.3, hatch="////", zorder=1))
        for sgn in (-1, 1):
            ax_w.add_patch(Rectangle((sgn * half - (wall if sgn < 0 else 0), top), wall, shoe - top, fc=PALETTE["steel"], ec="black", lw=0.4, zorder=3))
        ax_w.add_patch(Polygon([[half, shoe], [half + 0.1, shoe], [half, shoe - 14]], closed=True, fc="black", zorder=4))
        ax_w.add_patch(Polygon([[-half, shoe], [-half - 0.1, shoe], [-half, shoe - 14]], closed=True, fc="black", zorder=4))
        label = "{} {}{}{}".format(_fmt_in(c["od_in"]), c.get("grade", ""), " {:g} ppf".format(c["weight_ppf"]) if c.get("weight_ppf") else "", "  shoe {:.0f} m TVD / {:.0f} m MD".format(shoe, c["shoe_md_m"]))
        right_labels.append((float(shoe), label, PALETTE["text"], "casing", half + 0.1))
        ax_w.text(-half - 0.12, (top + shoe) / 2 if k else shoe * 0.5, c["name"] if k == 0 or True else "", fontsize=6.0, rotation=90, ha="right", va="center", color=PALETTE["muted"]) if k < 3 else None
    prod = [c for c in casings if "production" in c["name"].lower()]
    if prod:
        c = prod[-1]
        shoe = c.get("shoe_tvd_m") or m2t(c["shoe_md_m"])
        oh = hw(c.get("hole_in", 8.5)) * 0.3
        for sgn in (-1, 1):
            ax_w.plot([sgn * oh] * 2, [shoe, tvd_td], color=PALETTE["steel"], lw=1.0, ls="--", zorder=3)
        ax_w.plot([-oh, oh], [tvd_td, tvd_td], color=PALETTE["steel"], lw=1.0, zorder=3)
        ax_w.text(0, tvd_td + 8, "TD {:.0f} m MD / {:.0f} m TVD".format(md_td, tvd_td), ha="center", va="top", fontsize=7, fontweight="bold")
    min_gap = 0.024 * tvd_td
    order = sorted(range(len(right_labels)), key=lambda i: right_labels[i][0])
    ys = {}
    last = -1e9
    for i in order:
        y = max(right_labels[i][0], last + min_gap)
        ys[i] = y
        last = y
    for i, lab in enumerate(right_labels):
        y0, text, col, kind = lab[0], lab[1], lab[2], lab[3]
        y = ys[i]
        if kind == "casing":
            ax_w.annotate(text, (lab[4], y0 - 6), xytext=(0.75, y - 6), fontsize=6.5, va="center", ha="left", arrowprops=dict(arrowstyle="-", lw=0.4, color=PALETTE["muted"]), zorder=8)
        else:
            ax_w.text(1.58, y + 8, text, ha="right", va="top", fontsize=6.6, color=col, zorder=8)
            if abs(y - y0) > 2:
                ax_w.plot([1.0, 1.0], [y0, y], color=PALETTE["muted"], lw=0.0)
    # tubing
    t_od = tub.get("od_in", 5.5)
    th = hw(t_od) * 0.55
    t_shoe = m2t(tub.get("shoe_md_m", md_td * 0.9))
    for sgn in (-1, 1):
        ax_w.add_patch(Rectangle((sgn * th - (0.03 if sgn < 0 else 0), top_y), 0.03, t_shoe - top_y, fc=PALETTE["pressure"], ec="black", lw=0.3, zorder=5))
    ax_w.add_patch(Rectangle((-th, top_y), 2 * th, t_shoe - top_y, fc="#EAF2FB", ec="none", zorder=2, alpha=0.9))
    ax_w.annotate('tubing {} {} {}'.format(_fmt_in(t_od), tub.get("grade", ""), "{:g} ppf".format(tub["weight_ppf"]) if tub.get("weight_ppf") else ""),
                  (th, m2t(md_td * 0.42)), xytext=(th + 0.9, m2t(md_td * 0.42)), fontsize=6.6, va="center", arrowprops=dict(arrowstyle="-", lw=0.4, color=PALETTE["muted"]), color=PALETTE["pressure"])
    if comp.get("packer_md_m"):
        py = m2t(comp["packer_md_m"])
        inner = prod[-1] if prod else casings[-1]
        ch = hw(inner["od_in"]) * 0.55 - 0.03
        for sgn in (-1, 1):
            ax_w.add_patch(Rectangle((sgn * ch - (ch - th) * 0 if sgn > 0 else -ch, py - 12), ch - th, 24, fc="black", ec="black", zorder=6))
        ax_w.annotate("production packer {:.0f} m MD".format(comp["packer_md_m"]), (-ch, py), xytext=(-ch - 0.35, py - 30), fontsize=6.6, va="center", ha="right", arrowprops=dict(arrowstyle="-", lw=0.4, color=PALETTE["muted"]))
    if comp.get("sssv_md_m"):
        sy = m2t(comp["sssv_md_m"])
        ax_w.add_patch(Circle((0, sy), th * 0.9, fc="white", ec="black", lw=1.0, zorder=7))
        ax_w.plot([-th * 0.6, th * 0.6], [sy - th * 0.6 * 0, sy], color="black", lw=0.0)
        ax_w.plot([-th * 0.55, th * 0.55], [sy - 6, sy + 6], color="black", lw=1.0, zorder=8)
        ax_w.plot([-th * 0.55, th * 0.55], [sy + 6, sy - 6], color="black", lw=1.0, zorder=8)
        ax_w.annotate("SSSV {:.0f} m MD".format(comp["sssv_md_m"]), (th * 0.9, sy), xytext=(th + 0.9, sy), fontsize=6.6, va="center", arrowprops=dict(arrowstyle="-", lw=0.4, color=PALETTE["muted"]))
    for md_m in (comp.get("lift") or {}).get("mandrels_md_m", []) or []:
        my = m2t(md_m)
        ax_w.add_patch(Rectangle((th, my - 9), 0.07, 18, fc=PALETTE["gas"], ec="black", lw=0.4, zorder=6))
        ax_w.text(th + 0.1, my, "GLM {:.0f}".format(md_m), fontsize=6.0, va="center", color=PALETTE["gas"], fontweight="bold")
    inj = wtype in ("water_injector", "gas_injector")
    for pf in comp.get("perforations") or []:
        y0, y1 = m2t(pf["top_md_m"]), m2t(pf["base_md_m"])
        for yy in np.linspace(y0, y1, 7):
            for sgn in (-1, 1):
                x_from, x_to = (sgn * 0.5, sgn * 0.12) if not inj else (sgn * 0.12, sgn * 0.5)
                ax_w.annotate("", xy=(x_to, yy), xytext=(x_from, yy), arrowprops=dict(arrowstyle="-|>", lw=0.8, color=PALETTE["temperature"], mutation_scale=6), zorder=7)
        ax_w.text(-0.98, (y0 + y1) / 2, "perforations {:.0f}-{:.0f} m MD".format(pf["top_md_m"], pf["base_md_m"]), fontsize=6.6, va="center", ha="left", color=PALETTE["temperature"])
    _tree(ax_w, ymin + 4, env == "subsea", 0.3) if env != "subsea" else _tree(ax_w, top_y - 0.07 * tvd_td, True, 0.3)
    # pressure window track
    pw = get_path(basis, "drilling.pressure_window") or []
    if not pw:
        ax_p.set_visible(False)
        rows = []
        if tub:
            rows.append(("Tubing", "{} {} {}".format(_fmt_in(t_od), tub.get("grade", ""), "{:g} ppf".format(tub["weight_ppf"]) if tub.get("weight_ppf") else "").strip()))
        if comp.get("packer_md_m"):
            rows.append(("Packer", "{:.0f} m MD / {:.0f} m TVD".format(comp["packer_md_m"], m2t(comp["packer_md_m"]))))
        if comp.get("sssv_md_m"):
            rows.append(("SSSV", "{:.0f} m MD / {:.0f} m TVD".format(comp["sssv_md_m"], m2t(comp["sssv_md_m"]))))
        for pf in comp.get("perforations") or []:
            rows.append(("Inflow interval", "{:.0f}-{:.0f} m MD".format(pf["top_md_m"], pf["base_md_m"])))
        for cn, cv in comp.get("accessories", {}).items() if isinstance(comp.get("accessories"), dict) else []:
            rows.append((str(cn), str(cv)))
        ax_c = sheet_axes(fig, box, (0.505, 0.03, 0.15, 0.93))
        ax_c.axis("off")
        ax_c.text(0.0, 1.0, "COMPLETION SCHEDULE", fontsize=7.5, fontweight="bold", va="top", transform=ax_c.transAxes)
        for i, (a, b) in enumerate(rows):
            ax_c.text(0.0, 0.96 - 0.055 * i, a, fontsize=6.6, va="top", fontweight="bold", transform=ax_c.transAxes)
            ax_c.text(0.0, 0.96 - 0.055 * i - 0.022, b, fontsize=6.6, va="top", color=PALETTE["muted"], transform=ax_c.transAxes)
    else:
        ax_p.set_title("Pressure window [sg EMW]", fontsize=7.5, pad=2)
    if pw:
        z = np.array([p["tvd_m"] for p in pw])
        emw = lambda key: np.array([p[key] / (0.0980665 * p["tvd_m"]) for p in pw])  # noqa: E731
        pore, frac, mud = emw("pore_bara"), emw("frac_bara"), emw("mud_bara")
        ax_p.fill_betweenx(z, pore, frac, color=PALETTE["band_low_high"], alpha=0.35, lw=0)
        ax_p.plot(pore, z, color=PALETTE["pressure"], lw=LW["normal"])
        ax_p.plot(frac, z, color=PALETTE["fail"], lw=LW["normal"])
        ax_p.plot(mud, z, color=PALETTE["steel"], lw=LW["normal"], ls="--")
        direct_label(ax_p, pore[-2], z[-2], "pore", PALETTE["pressure"], dx=-3, ha="right", size=6.5)
        direct_label(ax_p, frac[-2], z[-2], "frac", PALETTE["fail"], dx=3, size=6.5)
        direct_label(ax_p, mud[-3], z[-3], "mud", PALETTE["steel"], dx=3, size=6.5)
        ax_p.set_xlim(0.9, max(2.1, float(np.nanmax(frac)) + 0.1))
    plt.setp(ax_p.get_yticklabels(), visible=False)
    # deviation track
    ax_d.set_title("Inclination / DLS", fontsize=7.5, pad=2)
    if survey:
        ax_d.plot(survey["inc"], survey["tvd"], color=PALETTE["accent1"], lw=LW["thick"])
        ax_d2 = ax_d.twiny()
        dls = survey.get("dls")
        if dls is None:
            inc = np.radians(np.asarray(survey["inc"], float))
            azi = np.radians(np.asarray(survey.get("azi", np.zeros(len(inc))), float))
            md = np.asarray(survey["md"], float)
            cosb = np.clip(np.cos(inc[1:]) * np.cos(inc[:-1]) + np.sin(inc[1:]) * np.sin(inc[:-1]) * np.cos(azi[1:] - azi[:-1]), -1.0, 1.0)
            dl = np.degrees(np.arccos(cosb)) / np.maximum(np.diff(md), 1e-6) * 30.0
            dls = np.concatenate([[dl[0]], dl]) if len(dl) else np.zeros(len(md))
        ax_d2.plot(dls, survey["tvd"], color=PALETTE["accent2"], lw=LW["normal"])
        ax_d2.tick_params(labelsize=6.5)
        ax_d2.set_xlabel("DLS [deg/30 m]", fontsize=6.5, color=PALETTE["accent2"])
        ax_d2.spines["top"].set_visible(True)
        ax_d.set_xlabel("Inclination [deg]", fontsize=6.5, color=PALETTE["accent1"])
    else:
        ax_d.text(0.5, 0.5, "no survey supplied", transform=ax_d.transAxes, ha="center", fontsize=7, color=PALETTE["muted"])
    plt.setp(ax_d.get_yticklabels(), visible=False)
    # key and casing table on the right
    kx = box[0] + 0.81 * box[2]
    ky = box[1] + box[3] - 4
    sheet.text(kx, ky, "KEY", fontsize=8, fontweight="bold", va="top")
    key = [("Casing / liner (steel)", PALETTE["steel"]), ("Cement (hatched)", "#B0B0B0"), ("Tubing", PALETTE["pressure"]), ("Perforations ({})".format("injection" if inj else "inflow"), PALETTE["temperature"]),
           ("Gas-lift mandrel", PALETTE["gas"]), ("Fluid contact (study assumption)", PALETTE["water"]), ("Reservoir interval", PALETTE["reservoir"])]
    for i, (name, col) in enumerate(key):
        yy = ky - 9 - i * 7
        sheet.add_patch(Rectangle((kx, yy - 2), 7, 4, fc=col, ec="black", lw=0.3))
        sheet.text(kx + 10, yy, name, fontsize=6.8, va="center")
    ty = ky - 9 - len(key) * 7 - 8
    sheet.text(kx, ty, "CASING PROGRAMME", fontsize=8, fontweight="bold", va="top")
    for i, c in enumerate(sorted(comp.get("casing") or [], key=lambda c: c["shoe_md_m"])):
        sheet.text(kx, ty - 8 - i * 6.5, "{:<16}  {:<8} {:<5} {:>5.0f} m".format(c["name"][:16], _fmt_in(c["od_in"]), c.get("grade", ""), c["shoe_md_m"]), fontsize=6.0, family="monospace", va="center")
    ny = ty - 8 - 6.5 * (len(casings) + 1) - 6
    sheet.text(kx, ny, "NOTES", fontsize=8, fontweight="bold", va="top")
    notes = ["1. Schematic is a planning sketch; not to scale in width.", "2. Grades/weights are study inputs (see source register).", "3. No compliance statement is made.",
             "4. Barrier elements: see barrier drawing."]
    for i, n in enumerate(notes):
        sheet.text(kx, ny - 8 - i * 6, n, fontsize=6.3, va="center", color=PALETTE["muted"])
    return fig


def barrier_schematic_sheet(states: List[BarrierState], basis: Dict[str, Any], drawing_no: str = "IWP-DWG-002", revision: str = "A",
                            revisions: Optional[List[Tuple[str, str, str]]] = None) -> plt.Figure:
    """Barrier schematics per well state on an A3 sheet.

    Upper half: one stylised well per state with the primary envelope (solid blue) and secondary envelope (dashed red), numbered element markers at their depth
    (or in order when no depth is known) and short labels. Lower half: one block per state listing every element with its function, verification status and
    the first unresolved dependencies, so nothing is truncated. The arrangement is a proposal; no acceptance criteria or compliance statement is made.
    """
    import textwrap

    synthetic = bool(get_path(basis, "study.synthetic"))
    fig, sheet, box = a3_sheet("Proposed well-barrier schematics - {}".format(get_path(basis, "well.id")), drawing_no, revision, project=str(get_path(basis, "study.title") or "")[:52],
                               synthetic=synthetic, status="FOR REVIEW - ELEMENTS UNVERIFIED", revisions=revisions,
                               content_note="Proposed arrangement only. Acceptance criteria, element lengths and compliance are NOT stated here. Verification status UNVERIFIED until evidence is supplied.")
    n = len(states)
    md_td = float(get_path(basis, "trajectory.md_m") or 1.0)
    env = get_path(basis, "well.environment")
    rw = 1.0 / n
    for k, st in enumerate(states):
        ax = sheet_axes(fig, box, (k * rw + 0.006, 0.50, rw - 0.012, 0.48))
        ax.set_xlim(-1.75, 1.75)
        ax.set_ylim(1.06, -0.14)
        ax.axis("off")
        ax.text(0, -0.115, st.state.replace("_", " ").upper(), ha="center", fontsize=10, fontweight="bold")
        ax.add_patch(Rectangle((-0.55, 0.0), 1.1, 1.0, fc="#F4F4F4", ec=PALETTE["steel"], lw=1.4))
        ax.add_patch(Rectangle((-0.55, 0.52), 0.35, 0.46, fc="#E4E4E4", ec="none", hatch="////", alpha=0.6))
        ax.add_patch(Rectangle((0.20, 0.52), 0.35, 0.46, fc="#E4E4E4", ec="none", hatch="////", alpha=0.6))
        ax.add_patch(Rectangle((-0.55, 0.96), 1.1, 0.06, fc=PALETTE["reservoir"], ec="none"))
        ax.text(0, 1.0, "reservoir", ha="center", va="center", fontsize=6.8)
        ax.add_patch(Rectangle((-0.2, 0.0), 0.4, 0.95, fc="#EAF2FB", ec=PALETTE["pressure"], lw=1.0))
        ax.add_patch(Rectangle((-0.25, 0.0), 0.5, 0.97, fc="none", ec=PALETTE["primary_barrier"], lw=2.8, zorder=5))
        ax.add_patch(Rectangle((-0.62, 0.0), 1.24, 1.0, fc="none", ec=PALETTE["secondary_barrier"], lw=2.2, ls="--", zorder=4))
        ax.add_patch(Rectangle((-0.3, -0.075), 0.6, 0.07, fc="#444444", ec="black"))
        ax.text(0, -0.085, "subsea tree / wellhead" if env == "subsea" else "tree / wellhead", ha="center", va="bottom", fontsize=6.6, color=PALETTE["muted"])
        n_prim = n_sec = 0
        for e in st.elements:
            if e.depth_md_m:
                yf = min(0.93, max(0.12, e.depth_md_m / md_td))
            elif e.envelope == "primary":
                yf = 0.08 + 0.12 * n_prim
                n_prim += 1
            else:
                yf = 0.14 + 0.15 * n_sec
                n_sec += 1
            prim = e.envelope == "primary"
            x = -0.02 if prim else 0.585
            ax.scatter([x], [yf], marker="s" if prim else "D", s=120, color=PALETTE["primary_barrier"] if prim else PALETTE["secondary_barrier"], ec="white", zorder=8)
            ax.text(x, yf, e.id, fontsize=6.2, color="white", ha="center", va="center", zorder=9, fontweight="bold")
            lab = "\n".join(textwrap.wrap(e.name, 24)[:3])
            xt = -0.72 if prim else 0.74
            ax.annotate(lab, (x, yf), xytext=(xt, yf), textcoords="data", fontsize=6.6, ha="right" if prim else "left", va="center", color=PALETTE["primary_barrier"] if prim else PALETTE["secondary_barrier"],
                        fontweight="bold", arrowprops=dict(arrowstyle="-", lw=0.5, color=PALETTE["muted"], shrinkA=0, shrinkB=4), zorder=7)
        ax2 = sheet_axes(fig, box, (k * rw + 0.006, 0.02, rw - 0.012, 0.46))
        ax2.set_xlim(0, 1)
        ax2.set_ylim(0, 1)
        ax2.axis("off")
        y = 0.995
        for line in textwrap.wrap(st.description, 58)[:2]:
            ax2.text(0, y, line, fontsize=7.4, fontweight="bold", va="top", color=PALETTE["text"])
            y -= 0.034
        y -= 0.012
        for e in st.elements:
            col = PALETTE["primary_barrier"] if e.envelope == "primary" else PALETTE["secondary_barrier"]
            head = "{}  {}".format(e.id, e.name)
            for j, line in enumerate(textwrap.wrap(head, 60)[:2]):
                ax2.text(0, y, line, fontsize=6.9, fontweight="bold", va="top", color=col)
                y -= 0.03
            body = "{} | {}".format(e.function, e.verification_status)
            for line in textwrap.wrap(body, 66)[:2]:
                ax2.text(0.02, y, line, fontsize=6.3, va="top", color=PALETTE["text"])
                y -= 0.027
            for u in e.unresolved[:1]:
                for line in textwrap.wrap("open: " + u, 66)[:2]:
                    ax2.text(0.02, y, line, fontsize=6.0, va="top", color=PALETTE["muted"], style="italic")
                    y -= 0.025
            y -= 0.012
        for note in st.notes[:1]:
            for line in textwrap.wrap("note: " + note, 66)[:3]:
                ax2.text(0, max(y, 0.02), line, fontsize=6.0, va="top", color=PALETTE["muted"])
                y -= 0.025
    sheet.text(box[0] + 2, box[1] + 3, "Blue square = primary barrier element   Red diamond = secondary barrier element   solid blue outline = primary envelope   dashed red outline = secondary envelope   all elements UNVERIFIED",
               fontsize=6.8, color=PALETTE["text"], ha="left")
    return fig


def render_sheet(fig, out_stem: Path, name: str, inputs: Any, drawing_no: str, caption: str, synthetic: bool = True, ledger_refs: Optional[List[str]] = None,
                 formats: Sequence[str] = ("png", "pdf", "svg")) -> Dict[str, str]:
    """Save a drawing sheet as 300 dpi PNG plus vector PDF and SVG with a provenance sidecar."""
    prov = provenance_record(Path(out_stem).name, name, "integrated_well_planning.iwp_drawings." + name, inputs, caption, synthetic, [], ledger_refs, drawing_no)
    return save_figure(fig, Path(out_stem), prov, formats)
