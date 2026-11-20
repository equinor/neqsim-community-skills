"""Report for a mercury estimate: figures, Markdown and (when python-docx is installed) a Word document.

The report states the estimate first, then the basis, the reasoning, the analogue wells, the mineral limits and the
accuracy. All numbers come from the result record of :func:`reservoir_mercury.estimate.estimate_prospect`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

from .formatting import fmt


def _figures(
    result: Mapping[str, Any],
    registry: Mapping[str, Any] | None,
    tests: Sequence[Mapping[str, Any]] | None,
    out_dir: str,
    prefix: str = "mercury",
) -> list[dict[str, str]]:
    """Draw the figures of the report; returns an empty list when matplotlib is not installed."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return []
    figs: list[dict[str, str]] = []
    p = result["prospect"]
    name = p.get("name", "prospect")
    plt.rcParams.update(
        {"font.size": 10, "axes.grid": True, "grid.alpha": 0.3, "savefig.bbox": "tight"}
    )
    tests = [t for t in (tests or []) if t.get("hg") not in (None, "")]
    t_res = p.get("res_T_C")
    if tests:
        fig, ax = plt.subplots(figsize=(8.0, 5.0))
        cls = p.get("source_class")
        plotted = [t for t in tests if t.get("res_T_C") not in (None, "")]
        same = [t for t in plotted if cls and t.get("source_class") == cls]
        other = [t for t in plotted if not cls or t.get("source_class") != cls]
        ax.scatter(
            [float(t["res_T_C"]) for t in other],
            [float(t["hg"]) for t in other],
            s=22,
            c="#bdc3c7",
            edgecolor="grey",
            linewidth=0.3,
            label=(
                f"tests, other reservoir age ({len(other)})"
                if cls
                else f"tests, all reservoir ages ({len(other)})"
            ),
        )
        if same:
            ax.scatter(
                [float(t["res_T_C"]) for t in same],
                [float(t["hg"]) for t in same],
                s=34,
                c="#e67e22",
                edgecolor="k",
                linewidth=0.4,
                label=f"tests, same reservoir age class ({len(same)})",
                zorder=3,
            )
        curves = (registry or {}).get("limit_curves") or []
        if curves:
            ts = [c["T_C"] for c in curves]
            ax.plot(
                ts,
                [c["liquid"] for c in curves],
                "k-",
                lw=1.3,
                label="liquid mercury limit",
            )
            ax.plot(
                ts,
                [c["trace"] for c in curves],
                color="purple",
                lw=1.7,
                label="trace-sulfide limit",
            )
        x = float(t_res) if t_res not in (None, "") else 115.0
        ax.plot(
            [x, x],
            [result["p10"], result["p90"]],
            color="#c0392b",
            lw=5,
            alpha=0.6,
            solid_capstyle="butt",
            label=f"{name}: P10 to P90",
            zorder=4,
        )
        ax.plot(
            x,
            result["best_estimate"],
            "D",
            color="#c0392b",
            mec="k",
            ms=9,
            label=f"{name}: best estimate",
            zorder=5,
        )
        ax.set_yscale("log")
        ax.set_ylim(0.005, 1e5)
        ax.set_xlabel("Reservoir temperature (°C)")
        ax.set_ylabel("Mercury in gas (µg/Sm³)")
        ax.set_title(f"{name} against the tests on the shelf")
        ax.legend(fontsize=7.5, loc="upper left")
        path = os.path.join(out_dir, f"{prefix}_estimate_vs_tests.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        figs.append(
            {
                "file": path,
                "caption": f"Estimate for {name} (red) against mercury in gas of the tests on the shelf and the "
                "mineral limits."
                + (
                    " Tests of the same reservoir age class are highlighted."
                    if same
                    else " The reservoir age class is not known, so no tests are highlighted."
                ),
            }
        )
    an = [a for a in result.get("analogues", []) if a.get("mercury")]
    if an:
        fig, ax = plt.subplots(figsize=(8.0, 0.36 * len(an) + 1.9))

        def short(text: str) -> str:
            text = text.replace(" Fm.", "").replace(" FM.", "")
            return text.title() if text.isupper() else text

        labels = [
            "{}, {}{}".format(
                a["well"],
                short(a["formation"] or a["group"] or ""),
                (
                    ""
                    if a["distance_km"] is None
                    else " ({:.0f} km)".format(a["distance_km"])
                ),
            )
            for a in an
        ]
        # points, not bars: on a log axis the length of a bar depends on where the axis starts
        kinds = [
            ("production gas", "gold", "D"),
            ("same formation or group", "#d35400", "o"),
            ("same reservoir age class", "#f5cba7", "o"),
        ]
        kind_of = [
            0 if a["production_gas"] else (1 if a["match_level"] >= 2 else 2)
            for a in an
        ]
        ypos = list(range(len(an)))[::-1]
        ax.axvspan(
            result["p10"],
            result["p90"],
            color="#c0392b",
            alpha=0.12,
            label="estimate, P10 to P90",
        )
        ax.axvline(
            result["best_estimate"], color="#c0392b", lw=1.8, label="best estimate"
        )
        for k, (label, color, marker) in enumerate(kinds):
            pts = [(a["mercury"], y) for a, y, kk in zip(an, ypos, kind_of) if kk == k]
            if pts:
                ax.scatter(
                    [q[0] for q in pts],
                    [q[1] for q in pts],
                    s=70,
                    color=color,
                    marker=marker,
                    edgecolor="k",
                    linewidth=0.5,
                    label=label,
                    zorder=3,
                )
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_ylim(-0.7, len(an) - 0.3)
        ax.set_xscale("log")
        ax.grid(True, axis="x", which="major", alpha=0.3)
        ax.grid(True, axis="y", alpha=0.15)
        ax.set_xlabel("Mercury in gas, highest reading of the test (µg/Sm³)")
        ax.set_title("Analogue tests, nearest first")
        handles, names = ax.get_legend_handles_labels()
        fig.legend(
            handles, names, loc="lower center", ncol=3, fontsize=8, frameon=False
        )
        fig.tight_layout(rect=(0.0, 0.3 / fig.get_figheight(), 1.0, 1.0))
        path = os.path.join(out_dir, f"{prefix}_analogue_tests.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        figs.append(
            {
                "file": path,
                "caption": "Mercury in gas of the analogue tests, nearest first, "
                f"with the estimate for {name}.",
            }
        )
    return figs


def build_sections(
    result: Mapping[str, Any], downstream: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Turn a result record into report sections (heading, paragraphs, bullet lists, tables).

    Args:
        result: Output of :func:`reservoir_mercury.estimate.estimate_prospect`.
        downstream: Optional ``{"route", "risk", "description", "source"}`` describing how sensitive the receiving
            gas system is to mercury.

    Returns:
        Sections in reading order.
    """
    p = result["prospect"]
    rr = result["recommended_range"]
    pa = result["probability_above"]
    measured = result["measurements"]["highest"] is not None
    name = p.get("name", "the prospect")
    summary = [
        "The best estimate of mercury in the gas from {} is {} µg/Sm³, with a P10 to P90 range of {} to {} µg/Sm³. "
        "For design and for the choice of export route, use {} to {} µg/Sm³.".format(
            name,
            fmt(result["best_estimate"]),
            fmt(result["p10"]),
            fmt(result["p90"]),
            fmt(rr["low"], 1),
            fmt(rr["high"], 1),
        ),
        "Basis: {}. The probability of more than 10 µg/Sm³ is {:.0f} % and of more than 100 µg/Sm³ {:.0f} %.".format(
            result["basis"], 100 * pa["10"], 100 * pa["100"]
        ),
    ]
    if not measured:
        summary.append(
            "This is an order-of-magnitude estimate. Mercury on the shelf is predicted poorly from "
            "reservoir data; a gas sample from the reservoir is the only way to narrow it."
        )
    sections: list[dict[str, Any]] = [
        {
            "heading": "Summary",
            "paragraphs": summary,
            "table": {
                "header": ["Quantity", "Value"],
                "rows": [
                    ["Best estimate", "{} µg/Sm³".format(fmt(result["best_estimate"]))],
                    [
                        "P10 / P50 / P90",
                        "{} / {} / {} µg/Sm³".format(
                            fmt(result["p10"]), fmt(result["p50"]), fmt(result["p90"])
                        ),
                    ],
                    [
                        "Range for design",
                        "{} to {} µg/Sm³".format(fmt(rr["low"], 1), fmt(rr["high"], 1)),
                    ],
                    ["Probability above 10 µg/Sm³", "%.0f %%" % (100 * pa["10"])],
                    ["Probability above 100 µg/Sm³", "%.0f %%" % (100 * pa["100"])],
                    ["Basis", result["basis"]],
                ],
            },
        }
    ]
    basis_rows = [
        [k, v]
        for k, v in [
            ("Name", name),
            (
                "Position",
                (
                    "{}°N, {}°E".format(fmt(p.get("lat"), 4), fmt(p.get("lon"), 4))
                    if p.get("lat")
                    else "-"
                ),
            ),
            ("Reservoir formation", p.get("formation") or "-"),
            ("Group", p.get("group") or "-"),
            ("Epoch", p.get("epoch") or "-"),
            ("Reservoir age class", p.get("source_class") or "-"),
            (
                "Structural province",
                (p.get("province") or "-")
                + (
                    " ({})".format(p["province_source"])
                    if p.get("province_source")
                    else ""
                ),
            ),
            (
                "Reservoir temperature",
                "{} °C".format(fmt(p.get("res_T_C"), 3)) if p.get("res_T_C") else "-",
            ),
            (
                "Reservoir pressure",
                (
                    "{} bara".format(fmt(p.get("res_P_bara"), 3))
                    if p.get("res_P_bara")
                    else "-"
                ),
            ),
            ("Fluid", p.get("fluid_type") or "gas (assumed)"),
            (
                "CO2",
                (
                    "{} mol %".format(fmt(p.get("co2_molpct")))
                    if p.get("co2_molpct")
                    else "-"
                ),
            ),
            (
                "Gas readings in the discovery",
                ", ".join(fmt(v) for v in result["measurements"]["gas_readings"])
                or "none",
            ),
        ]
    ]
    sections.append(
        {
            "heading": "Basis",
            "paragraphs": [
                "The estimate uses the data below. Values that were not given are listed under data gaps."
            ],
            "table": {"header": ["Input", "Value"], "rows": basis_rows},
        }
    )
    cal = result["calibration"]
    sections.append(
        {
            "heading": "Method",
            "paragraphs": [
                (
                    f"Mercury in gas was measured in {cal['tests']} tests in {cal['wells']} exploration and appraisal "
                    "wells. The highest gas reading of each test is used, because gas readings can be too low but are "
                    "unlikely to be too high."
                ),
                (
                    "A statistical model relates log10 of mercury to the reservoir age class, the structural province and the "
                    "reservoir temperature. Group effects are shrunk towards the overall mean, so a class with few tests moves "
                    "the estimate only a little. Its error is taken from predictions with the whole well left out."
                ),
                (
                    "Production gas has followed the highest reading found in a discovery. Without a measurement, the estimate is "
                    "therefore stated for the highest reading expected in the discovery."
                ),
                (
                    "NeqSim gives two upper limits from mineral equilibrium at reservoir conditions: mercury held as a trace in "
                    "sulfide minerals, and liquid mercury. They bound the estimate; they do not predict it."
                ),
            ],
        }
    )
    st = result["statistical"]
    sections.append(
        {
            "heading": "Estimate and reasoning",
            "bullets": list(result["reasoning"]),
            "table": {
                "header": ["Level", "P10", "P50", "P90"],
                "rows": [
                    [
                        "Typical test in a well (µg/Sm³)",
                        fmt(st["typical_test"]["p10"]),
                        fmt(st["typical_test"]["p50"]),
                        fmt(st["typical_test"]["p90"]),
                    ],
                    [
                        "Highest reading in the discovery (µg/Sm³)",
                        fmt(st["highest_reading_in_discovery"]["p10"]),
                        fmt(st["highest_reading_in_discovery"]["p50"]),
                        fmt(st["highest_reading_in_discovery"]["p90"]),
                    ],
                ],
            },
        }
    )
    an = result.get("analogues") or []
    if an:
        sections.append(
            {
                "heading": "Analogue tests",
                "paragraphs": [
                    "The table lists the tested intervals of the same group or formation, or else of the same reservoir age class, nearest first."
                ],
                "table": {
                    "header": [
                        "Well",
                        "Field",
                        "Formation",
                        "Match",
                        "Distance (km)",
                        "Reservoir T (°C)",
                        "Hg (µg/Sm³)",
                    ],
                    "rows": [
                        [
                            a["well"],
                            a["field"] or "-",
                            a["formation"] or a["group"] or "-",
                            a["match"]
                            + (", production gas" if a["production_gas"] else ""),
                            fmt(a["distance_km"], 2),
                            fmt(a["reservoir_T_C"], 3),
                            fmt(a["mercury"]),
                        ]
                        for a in an
                    ],
                },
            }
        )
    lim = result.get("limits")
    if lim:
        sections.append(
            {
                "heading": "Mineral-equilibrium limits",
                "paragraphs": [
                    "Limits at reservoir conditions, expressed in separator gas ({}; {}, {}).".format(
                        lim["separator_basis"],
                        lim["equation_of_state"],
                        lim["fluid_basis"],
                    ),
                    "Pure cinnabar would allow far more mercury than is measured anywhere on the shelf. A sulfide that holds "
                    "mercury as a trace, with an HgS activity of {:g}, follows the highest measured values and serves as the "
                    "worst case. The buffered H2S used in the limit is {} ppm.".format(
                        lim["trace_activity"], fmt(lim["buffered_h2s_ppm"])
                    ),
                ],
                "table": {
                    "header": ["Limit", "Mercury in gas (µg/Sm³)"],
                    "rows": [
                        [
                            "Trace mercury in sulfide (worst case)",
                            fmt(lim["trace_sulfide_limit"]),
                        ],
                        ["Pure cinnabar", fmt(lim["cinnabar_limit"])],
                        ["Liquid mercury in the reservoir", fmt(lim["liquid_limit"])],
                    ],
                },
            }
        )
    sections.append(
        {"heading": "Accuracy of the estimate", "bullets": list(result["accuracy"])}
    )
    if downstream:
        sections.append(
            {
                "heading": "Consequence for the gas route",
                "paragraphs": [
                    "Route: {}. Sensitivity to mercury: {}. {}".format(
                        downstream.get("route", "-"),
                        downstream.get("risk", "-"),
                        downstream.get("description", ""),
                    ),
                    "Source: {}.".format(downstream.get("source", "not stated")),
                ],
            }
        )
    rec = [
        (
            "Take gas samples for mercury in the first well that flows or is sampled by wireline; ask for mercury "
            "sampling when the well is planned, because it needs dedicated sample chambers."
        ),
        "Sample late in the flow period and analyse at the rig; trust the highest gas reading.",
        "Record whether methanol or glycol was injected during the test: both can remove mercury from the gas.",
    ]
    if not measured:
        rec.insert(
            0,
            "Until a sample exists, carry {} to {} µg/Sm³ in process and material studies and check the "
            "mercury tolerance of the receiving system against the upper value.".format(
                fmt(rr["low"], 1), fmt(rr["high"], 1)
            ),
        )
    sections.append({"heading": "Recommendations", "bullets": rec})
    if result.get("data_gaps"):
        sections.append({"heading": "Data gaps", "bullets": list(result["data_gaps"])})
    return sections


def write_report(
    result: Mapping[str, Any],
    out_dir: str,
    registry: Mapping[str, Any] | None = None,
    tests: Sequence[Mapping[str, Any]] | None = None,
    downstream: Mapping[str, Any] | None = None,
    references: Sequence[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Write the estimate as JSON, Markdown and Word (when python-docx is installed), with figures.

    Args:
        result: Output of :func:`reservoir_mercury.estimate.estimate_prospect`.
        out_dir: Folder for the files (created when missing).
        registry: Calibration registry, for the limit curves in the first figure.
        tests: Tested intervals of the calibration set, for the first figure.
        downstream: Optional gas-route sensitivity, see :func:`build_sections`.
        references: Reference list; a default list of the public sources is used when omitted.
        title: Report title; default ``"Mercury in gas - estimate for <name>"``.

    Returns:
        ``{"json", "markdown", "docx", "figures"}`` with the paths written (``docx`` is ``None`` without python-docx).
    """
    os.makedirs(out_dir, exist_ok=True)
    name = result["prospect"].get("name", "prospect")
    safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "prospect"
    title = title or f"Mercury in gas - estimate for {name}"
    figs = _figures(result, registry, tests, out_dir, safe)
    sections = build_sections(result, downstream)
    refs = list(
        references
        or [
            (
                "Sandengen, K. (2024). Mercury on the Norwegian Continental Shelf (NCS). What value to use for design? "
                "Geoenergy Science and Engineering 242, 213263. https://doi.org/10.1016/j.geoen.2024.213263"
            ),
            (
                "Bryndzia, L.T., Burgess, J.M., Bourdet, J. (2022). Predicting the solubility of mercury in hydrocarbons. "
                "SPE Journal, SPE-212271-PA. https://doi.org/10.2118/212271-PA"
            ),
            "Robie, R.A., Hemingway, B.S. (1995). Thermodynamic properties of minerals. USGS Bulletin 2131.",
            (
                "Huber, M.L., Laesecke, A., Friend, D.G. (2006). Correlation for the vapor pressure of mercury. "
                "Ind. Eng. Chem. Res. 45, 7351-7361. https://doi.org/10.1021/ie060560s"
            ),
            (
                "Koulocheris, V., Louli, V., Panteli, E., Skouras, S., Voutsas, E. (2018). Modelling of elemental mercury "
                "solubility in natural gas components. Fuel 233, 558-564. https://doi.org/10.1016/j.fuel.2018.06.077"
            ),
        ]
    )
    json_path = os.path.join(out_dir, f"mercury_estimate_{safe}.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False, default=str)
    # ---- Markdown
    md = [f"# {title}", ""]
    fig_after = {"Estimate and reasoning": 0, "Analogue tests": 1}
    fig_no = 0
    for i, sec in enumerate(sections, 1):
        md += [f"## {i} {sec['heading']}", ""]
        for par in sec.get("paragraphs", []):
            md += [par, ""]
        for b in sec.get("bullets", []):
            md.append("- " + b)
        if sec.get("bullets"):
            md.append("")
        tab = sec.get("table")
        if tab:
            md.append("| " + " | ".join(tab["header"]) + " |")
            md.append("|" + "|".join(" --- " for _ in tab["header"]) + "|")
            md += ["| " + " | ".join(str(c) for c in row) + " |" for row in tab["rows"]]
            md.append("")
        k = fig_after.get(sec["heading"])
        if k is not None and k < len(figs):
            fig_no += 1
            md += [
                "![{}]({})".format(
                    figs[k]["caption"], os.path.basename(figs[k]["file"])
                ),
                "",
                f"*Figure {fig_no}: {figs[k]['caption']}*",
                "",
            ]
    md += [f"## {len(sections) + 1} References", ""] + [
        f"{i}. {r}" for i, r in enumerate(refs, 1)
    ]
    md_path = os.path.join(out_dir, f"{safe}.md")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(md) + "\n")
    # ---- Word
    docx_path = None
    try:
        from docx import Document
        from docx.shared import Cm, Pt
    except Exception:  # noqa: BLE001
        Document = None
    if Document is not None:
        doc = Document()
        doc.styles["Normal"].font.size = Pt(10.5)
        doc.add_heading(title, level=0)
        fig_no = 0
        for i, sec in enumerate(sections, 1):
            doc.add_heading(f"{i} {sec['heading']}", level=1)
            for par in sec.get("paragraphs", []):
                doc.add_paragraph(par)
            for b in sec.get("bullets", []):
                doc.add_paragraph(b, style="List Bullet")
            tab = sec.get("table")
            if tab:
                table = doc.add_table(rows=1, cols=len(tab["header"]))
                table.style = "Light Grid Accent 1"
                for j, h in enumerate(tab["header"]):
                    cell = table.rows[0].cells[j]
                    cell.text = str(h)
                    for run in cell.paragraphs[0].runs:
                        run.font.bold = True
                for row in tab["rows"]:
                    cells = table.add_row().cells
                    for j, c in enumerate(row):
                        cells[j].text = str(c)
                for row in table.rows:
                    for cell in row.cells:
                        for par in cell.paragraphs:
                            for run in par.runs:
                                run.font.size = Pt(9)
                doc.add_paragraph()
            k = fig_after.get(sec["heading"])
            if k is not None and k < len(figs):
                fig_no += 1
                doc.add_picture(figs[k]["file"], width=Cm(16))
                cap = doc.add_paragraph(f"Figure {fig_no}: {figs[k]['caption']}")
                cap.runs[0].italic = True
        doc.add_heading(f"{len(sections) + 1} References", level=1)
        for r in refs:
            doc.add_paragraph(r, style="List Number")
        docx_path = os.path.join(out_dir, f"{safe}.docx")
        doc.save(docx_path)
    return {
        "json": json_path,
        "markdown": md_path,
        "docx": docx_path,
        "figures": [f["file"] for f in figs],
    }
