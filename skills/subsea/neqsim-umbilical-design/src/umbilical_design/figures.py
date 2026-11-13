"""Charts and drawings of an umbilical design (matplotlib, Agg backend, no display needed)."""

from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

from .layout import cross_section_layout  # noqa: E402
from .runner import DesignResult  # noqa: E402

TYPE_COLOURS = {
    "hydraulic": "#1f77b4",
    "chemical": "#2ca02c",
    "electrical": "#d62728",
    "fiber": "#9467bd",
}
COPPER = "#b87333"
PASS_COLOUR = "#2e7d32"
FAIL_COLOUR = "#c62828"
DPI = 200

CHECK_LABELS = {
    "selfSinking": "Umbilical sinks under its own weight",
    "tubeBurstUtilizationBelow1": "Tube hoop stress at design pressure within allowable",
    "tubeCollapseUtilizationBelow1": "Tube collapse under hydrostatic pressure (safety factor applied)",
    "armorCapacityCoversDesignTension": "Armour capacity covers amplified top tension",
    "touchdownBendRadiusAboveMBR": "Touchdown bend radius above minimum bend radius",
    "installationTensionWithinVesselLimit": "Design tension within installation vessel limit",
    "lineFrictionDropWithinPressureBudget": "Line friction drop at design flow within half the line design pressure",
}


@dataclass
class FigureMeta:
    """Text that every figure carries, so a picture is never separated from its basis."""

    title: str
    basis_version: str = "not stated"
    source: str = "NeqSim UmbilicalMechanicalDesign (screening level)"


def _new_figure(*args, **kwargs):
    """Figure with constrained layout and a reserved strip for the title and the basis footer."""
    fig = plt.figure(*args, layout="constrained", **kwargs)
    fig.get_layout_engine().set(rect=(0.0, 0.03, 1.0, 0.94))
    return fig


def _finish(fig, meta: FigureMeta, path: Path, pdf: bool = False) -> Path:
    fig.suptitle(meta.title, x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.text(
        0.01,
        0.005,
        "Basis version: %s  |  Source: %s  |  Screening design, not for construction"
        % (meta.basis_version, meta.source),
        fontsize=7,
        color="#555555",
        ha="left",
        va="bottom",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor="white")
    if pdf:
        fig.savefig(path.with_suffix(".pdf"), facecolor="white")
    plt.close(fig)
    return path


def draw_cross_section(ax, result: DesignResult) -> Dict[str, Any]:
    """Draw the cross-section (outer sheath, armour wires, inner sheath, filler, elements)."""
    lay = cross_section_layout(result)
    ax.set_aspect("equal")
    r_out = lay["overall_radius"]
    ax.add_patch(Circle((0, 0), r_out, facecolor="#404040", edgecolor="black", lw=0.8))
    ax.add_patch(Circle((0, 0), lay["armor_outer_radius"], facecolor="#c8c8c8", edgecolor="#6e6e6e", lw=0.5))
    for w in lay["armor_wires"]:
        ax.add_patch(Circle((w["x"], w["y"]), w["radius"], facecolor="#8c8c8c", edgecolor="#505050", lw=0.3))
    ax.add_patch(Circle((0, 0), lay["core_radius"], facecolor="#e6e6e6", edgecolor="#6e6e6e", lw=0.5))
    ax.add_patch(Circle((0, 0), lay["bundle_radius"], facecolor="#f7f1d9", edgecolor="#9a9a9a", lw=0.4))
    for number, el in enumerate(lay["elements"], start=1):
        colour = TYPE_COLOURS.get(el["type"], "#888888")
        ax.add_patch(Circle((el["x"], el["y"]), el["radius"], facecolor=colour, edgecolor="black", lw=0.5, alpha=0.9))
        for core in el["cores"]:
            ax.add_patch(Circle((core["x"], core["y"]), core["radius"], facecolor="white", edgecolor="black", lw=0.3))
            ax.add_patch(Circle((core["x"], core["y"]), core["conductor_radius"], facecolor=COPPER, edgecolor="none"))
        if not el["cores"]:
            ax.text(
                el["x"], el["y"], str(number), ha="center", va="center", fontsize=7 if el["radius"] > 4 else 5.5,
                color="white", fontweight="bold",
            )
        else:
            ax.text(el["x"], el["y"] + el["radius"] * 1.0 + 1.0, str(number), ha="center", va="bottom", fontsize=7,
                    color="black", fontweight="bold")
    lim = r_out * 1.18
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim * 1.12, lim)
    ax.axis("off")
    ax.annotate("", xy=(-r_out, -r_out * 1.1), xytext=(r_out, -r_out * 1.1),
                arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(0, -r_out * 1.2, "OD %.1f mm" % (2 * r_out), ha="center", va="top", fontsize=8)
    return lay


def draw_element_schedule(ax, result: DesignResult) -> None:
    """Element schedule table next to the cross-section (numbers match the drawing)."""
    rows = []
    colours = []
    for i, e in enumerate(result.elements, start=1):
        kind = e["type"]
        if kind in ("hydraulic", "chemical"):
            dims = "ID %.2f / wall %.2f / OD %.2f" % (e["innerDiameterMm"], e["wallThicknessMm"], e["outerDiameterMm"])
            extra = "%.0f bar, %s" % (e["designPressureBar"], textwrap.shorten(str(e.get("fluid", "")), width=18, placeholder="."))
        elif kind == "electrical":
            dims = "%d x %.1f mm2, OD %.1f" % (e["cores"], e["conductorAreaMm2"], e["outerDiameterMm"])
            extra = "%.0f V" % e["voltageV"]
        else:
            dims = "OD %.1f" % e["outerDiameterMm"]
            extra = "fibre tube"
        rows.append([str(i), e["name"], kind, dims, extra])
        colours.append(TYPE_COLOURS.get(kind, "#888888"))
    ax.axis("off")
    if not rows:
        return
    table = ax.table(
        cellText=rows,
        colLabels=["No.", "Element", "Type", "Dimensions (mm)", "Rating / fluid"],
        loc="upper center",
        cellLoc="left",
        colWidths=[0.06, 0.26, 0.13, 0.32, 0.23],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    table.scale(1.0, 1.35)
    for (r, c), cell in table.get_celld().items():
        cell.set_linewidth(0.3)
        if r == 0:
            cell.set_facecolor("#e0e0e0")
            cell.set_text_props(fontweight="bold")
        elif c == 0:
            cell.set_facecolor(colours[r - 1])
            cell.set_text_props(color="white", fontweight="bold")


def draw_hydraulics(ax_curve, ax_resp, result: DesignResult) -> None:
    """Friction drop versus flow per fluid line, and signal response time of each line."""
    curves = result.data.get("hydraulicCurves", [])
    for c in curves:
        flows = c["flowM3PerHr"][1:]
        drops = c["frictionDropBar"][1:]
        (line,) = ax_curve.plot(flows, drops, lw=1.4, label=c["name"])
        if c["designFlowM3PerHr"] > 0:
            half = len(flows) // 2
            ax_curve.plot([flows[half]], [drops[half]], "o", color=line.get_color(), ms=5)
    ax_curve.set_xscale("log")
    ax_curve.set_yscale("log")
    ax_curve.set_xlabel("Flow (m3/h)")
    ax_curve.set_ylabel("Friction pressure drop (bar)")
    ax_curve.set_title("Line friction drop, %.1f km (dot = design flow)" % (result.length_m / 1000.0), fontsize=9)
    ax_curve.grid(alpha=0.3, which="both")
    if curves:
        ax_curve.legend(fontsize=6.5, loc="upper left")
    lines = result.fluid_lines
    names = [l["name"] for l in lines]
    y = list(range(len(lines)))
    t90 = [l["time90PercentS"] / 60.0 for l in lines]
    transit = [l["acousticTransitTimeS"] / 60.0 for l in lines]
    ax_resp.barh([v + 0.2 for v in y], t90, height=0.38, color="#1f77b4", label="90 % pressure response")
    ax_resp.barh([v - 0.2 for v in y], transit, height=0.38, color="#ff7f0e", label="acoustic transit (lower bound)")
    ax_resp.set_yticks(y)
    ax_resp.set_yticklabels(names, fontsize=7)
    ax_resp.set_xscale("log")
    ax_resp.set_xlabel("Time (min)")
    ax_resp.set_title("Far-end response to a topside pressure step", fontsize=9)
    ax_resp.grid(alpha=0.3, which="both")
    ax_resp.legend(fontsize=6.5, loc="lower right")


def draw_mechanical(ax_cat, ax_util, result: DesignResult) -> None:
    """Catenary shape coloured by tension, and utilisation bars (1.0 = limit)."""
    res = result.data["calculatedResults"]
    prof = result.data.get("catenaryProfile")
    if prof:
        x = prof["horizontalDistanceM"]
        z = prof["heightAboveSeabedM"]
        t = prof["tensionKN"]
        pts = [[(x[i], z[i]), (x[i + 1], z[i + 1])] for i in range(len(x) - 1)]
        lc = LineCollection(pts, cmap="viridis", linewidths=3)
        lc.set_array([(t[i] + t[i + 1]) / 2 for i in range(len(t) - 1)])
        ax_cat.add_collection(lc)
        ax_cat.set_xlim(-0.05 * max(x), 1.12 * max(x))
        ax_cat.set_ylim(-0.08 * max(z), 1.1 * max(z))
        ax_cat.axhline(0, color="#8b6b3d", lw=2)
        cb = ax_cat.figure.colorbar(lc, ax=ax_cat, pad=0.02)
        cb.set_label("Tension (kN)", fontsize=7)
        cb.ax.tick_params(labelsize=6)
        ax_cat.annotate(
            "top %.1f kN (design %.1f kN)\n%.0f deg from vertical" % (
                res["staticTopTensionKN"], res["designTopTensionKN"], res["topAngleFromVerticalDeg"]),
            xy=(x[-1], z[-1]), xytext=(0.35 * max(x), 0.9 * max(z)), fontsize=7,
            arrowprops=dict(arrowstyle="->", lw=0.6),
        )
        ax_cat.text(0.02 * max(x), 0.06 * max(z), "touchdown radius %.0f m" % res["touchdownBendRadiusM"], fontsize=7)
    else:
        ax_cat.text(0.5, 0.5, "No catenary (umbilical is buoyant)", ha="center", transform=ax_cat.transAxes)
    ax_cat.set_xlabel("Horizontal distance from touchdown (m)")
    ax_cat.set_ylabel("Height above seabed (m)")
    ax_cat.set_title("Free-hanging catenary, %.0f m water depth" % result.water_depth_m, fontsize=9)
    ax_cat.grid(alpha=0.3)

    cap = res["armorCapacityKN"]
    mbr = res["calculatedMinBendRadiusM"]
    td = res["touchdownBendRadiusM"]
    util = [
        ("Armour tension", res["designTopTensionKN"] / cap if cap > 0 else 0.0),
        ("Tube collapse", res["maxCollapseUtilization"]),
        ("Tube hoop stress", res["maxBurstUtilization"]),
        ("Bend radius (MBR / touchdown)", mbr / td if td and math.isfinite(td) else 0.0),
    ]
    names = [u[0] for u in util]
    vals = [u[1] for u in util]
    colours = [PASS_COLOUR if v <= 1.0 + 1e-6 else FAIL_COLOUR for v in vals]
    ax_util.barh(names, vals, color=colours)
    ax_util.axvline(1.0, color="black", lw=1.0, ls="--")
    ax_util.set_xlim(0, max(1.2, 1.1 * max(vals)))
    ax_util.invert_yaxis()
    ax_util.set_xlabel("Utilisation (1.0 = limit)")
    ax_util.set_title("Mechanical utilisation", fontsize=9)
    ax_util.tick_params(axis="y", labelsize=7)
    for i, v in enumerate(vals):
        ax_util.text(v + 0.02, i, "%.2f" % v, va="center", fontsize=7)


def draw_electrical(ax, result: DesignResult) -> bool:
    """Voltage drop and charging current against cable length. Returns False if no power cable."""
    sweep = result.data.get("powerSweep")
    if not sweep:
        ax.axis("off")
        ax.text(0.5, 0.5, "No power load defined", ha="center", va="center", transform=ax.transAxes, fontsize=8)
        return False
    ln = sweep["lengthKm"]
    ax.plot(ln, sweep["voltageDropPercent"], color="#d62728", lw=1.5, label="Voltage drop (%)")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("Cable length (km)")
    ax.set_ylabel("Voltage drop (% of receiving voltage)", color="#d62728")
    ax2 = ax.twinx()
    ax2.plot(ln, sweep["chargingCurrentA"], color="#1f77b4", lw=1.5, ls="--", label="Charging current (A)")
    ax2.set_ylabel("Cable charging current (A)", color="#1f77b4")
    ax.axvline(result.length_m / 1000.0, color="grey", ls=":", lw=1.2)
    ax.text(result.length_m / 1000.0, ax.get_ylim()[1], " design length", fontsize=7, va="top", color="grey")
    ax.set_title("Power cable against step-out distance", fontsize=9)
    ax.grid(alpha=0.3)
    pt = result.data.get("powerTransmission", {})
    if pt:
        ax.text(
            0.03, 0.97,
            "%.2f MW load at design length:\nloss %.3f MW, voltage drop %.2f %%,\ncharging current %.1f A" % (
                pt["loadMW"], pt["lossMW"], pt["voltageDropPercent"], pt["chargingCurrentA"]),
            transform=ax.transAxes, fontsize=7, va="top", bbox=dict(boxstyle="round", fc="white", ec="#aaaaaa"),
        )
    return True


def draw_checks(ax, result: DesignResult) -> None:
    """Pass/fail list of the design checks plus headline numbers (text rows, no clipping)."""
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    checks = list(result.checks.items())
    w = result.data["weight"]
    res = result.data["calculatedResults"]
    headline = [
        ("Overall diameter", "%.1f mm" % res["calculatedOuterDiameterMm"]),
        ("Armour layers", "%d" % res["requiredArmorLayers"]),
        ("Weight in air, empty / filled", "%.1f / %.1f kg/m" % (w["dryWeightPerMeterKgM"], w["filledWeightPerMeterKgM"])),
        ("Weight in seawater, filled", "%.1f kg/m" % w["submergedWeightPerMeterKgM"]),
        ("Weight ratio (air / displaced seawater)", "%.2f" % res["weightRatio"] if "weightRatio" in res else "n/a"),
        ("Optical budget", "%.1f dB" % res["opticalBudgetDb"] if "opticalBudgetDb" in res else "no fibre"),
        ("Total dry weight", "%.0f t" % w["totalDryWeightTonnes"]),
    ]
    n_rows = len(checks) + len(headline) + 2
    step = 1.0 / (n_rows + 0.5)
    y = 1.0 - step * 0.6
    ax.text(0.0, y, "Design checks", fontsize=8.5, fontweight="bold", va="center")
    for key, ok in checks:
        y -= step
        ax.text(0.0, y, "PASS" if ok else "FAIL", fontsize=7, fontweight="bold", color="white", va="center",
                ha="left", bbox=dict(boxstyle="round,pad=0.25", fc=PASS_COLOUR if ok else FAIL_COLOUR, ec="none"))
        ax.text(0.17, y, textwrap.shorten(CHECK_LABELS.get(key, key), width=64, placeholder="..."), fontsize=7,
                va="center")
    y -= step * 1.2
    ax.text(0.0, y, "Headline numbers", fontsize=8.5, fontweight="bold", va="center")
    for label, value in headline:
        y -= step
        ax.text(0.0, y, label, fontsize=7, va="center")
        ax.text(0.78, y, value, fontsize=7, va="center", ha="right")


def figure_cross_section(result: DesignResult, meta: FigureMeta, path: Path) -> Path:
    fig = _new_figure(figsize=(13, 6.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.25])
    draw_cross_section(fig.add_subplot(gs[0]), result)
    draw_element_schedule(fig.add_subplot(gs[1]), result)
    return _finish(fig, meta, path)


def figure_hydraulics(result: DesignResult, meta: FigureMeta, path: Path) -> Path:
    fig = _new_figure(figsize=(13, 5.5))
    a, b = fig.subplots(1, 2)
    draw_hydraulics(a, b, result)
    return _finish(fig, meta, path)


def figure_mechanical(result: DesignResult, meta: FigureMeta, path: Path) -> Path:
    fig = _new_figure(figsize=(13, 5.5))
    a, b = fig.subplots(1, 2, gridspec_kw={"width_ratios": [1.3, 1]})
    draw_mechanical(a, b, result)
    return _finish(fig, meta, path)


def figure_electrical(result: DesignResult, meta: FigureMeta, path: Path) -> Optional[Path]:
    if not result.data.get("powerSweep"):
        return None
    fig = _new_figure(figsize=(9, 5))
    draw_electrical(fig.add_subplot(1, 1, 1), result)
    return _finish(fig, meta, path)


def figure_checks(result: DesignResult, meta: FigureMeta, path: Path) -> Path:
    fig = _new_figure(figsize=(9, 5))
    draw_checks(fig.add_subplot(1, 1, 1), result)
    return _finish(fig, meta, path)


def figure_on_a_page(result: DesignResult, meta: FigureMeta, path: Path) -> Path:
    """A3 landscape summary: cross-section, schedule, hydraulics, mechanical, power and checks."""
    fig = _new_figure(figsize=(16.54, 11.69))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.2, 1, 1])
    top = gs[0].subgridspec(1, 3, width_ratios=[1.0, 1.7, 1.3])
    draw_cross_section(fig.add_subplot(top[0]), result)
    draw_element_schedule(fig.add_subplot(top[1]), result)
    draw_checks(fig.add_subplot(top[2]), result)
    mid = gs[1].subgridspec(1, 2)
    draw_hydraulics(fig.add_subplot(mid[0]), fig.add_subplot(mid[1]), result)
    bottom = gs[2].subgridspec(1, 3, width_ratios=[1.5, 1.0, 1.0])
    draw_mechanical(fig.add_subplot(bottom[0]), fig.add_subplot(bottom[1]), result)
    draw_electrical(fig.add_subplot(bottom[2]), result)
    return _finish(fig, meta, path, pdf=True)


def render_all(result: DesignResult, out_dir: Path, meta: FigureMeta) -> Dict[str, Path]:
    """Render every figure into ``out_dir`` and return name -> path (electrical only if a load exists)."""
    out_dir = Path(out_dir)

    def sub(title: str) -> FigureMeta:
        return FigureMeta(title=title, basis_version=meta.basis_version, source=meta.source)

    figs: Dict[str, Path] = {
        "cross_section": figure_cross_section(result, sub(meta.title + ": cross-section"), out_dir / "fig1_cross_section.png"),
        "hydraulics": figure_hydraulics(result, sub(meta.title + ": line hydraulics"), out_dir / "fig2_hydraulics.png"),
        "mechanical": figure_mechanical(result, sub(meta.title + ": tension and bending"), out_dir / "fig3_mechanical.png"),
        "checks": figure_checks(result, sub(meta.title + ": design checks"), out_dir / "fig5_design_checks.png"),
        "on_a_page": figure_on_a_page(result, sub(meta.title + ": umbilical on a page"), out_dir / "fig6_umbilical_on_a_page.png"),
    }
    electrical = figure_electrical(result, sub(meta.title + ": power cable"), out_dir / "fig4_electrical.png")
    if electrical is not None:
        figs["electrical"] = electrical
    return figs
