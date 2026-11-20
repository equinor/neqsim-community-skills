"""Report for an H2S estimate: figures, Markdown and (when python-docx is installed) a Word document.

The report states the estimate first, then the basis, the method, the reasoning with the uncertainty budget, the
analogue wells, the screening against sour service and a gas specification, and the accuracy. All numbers come from
the result record of :func:`reservoir_h2s.estimate.estimate_prospect`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

from .buffer import haaland_ppm
from .formatting import fmt
from .model import not_detected
from .setting import classify_setting

DEFAULT_REFERENCES = [
    (
        "Håland, K., Barrufet, M.A., Rønningsen, H.P., Meisingset, K.K. (1999). An empirical correlation between "
        "reservoir temperature and the concentration of hydrogen sulfide. SPE International Symposium on Oilfield "
        "Chemistry, Houston. SPE-50763-MS. https://doi.org/10.2118/50763-MS"
    ),
    (
        "Smith, J.T., Ehrenberg, S.N. (1989). Correlation of carbon dioxide abundance with temperature in clastic "
        "hydrocarbon reservoirs: relationship to inorganic chemical equilibrium. Marine and Petroleum Geology 6, "
        "129-135. https://doi.org/10.1016/0264-8172(89)90016-0"
    ),
    (
        "Hutcheon, I., Abercrombie, H. (1990). Carbon dioxide in clastic rocks and silicate hydrolysis. Geology 18, "
        "541-544."
    ),
    (
        "Machel, H.G. (2001). Bacterial and thermochemical sulfate reduction in diagenetic settings - old and new "
        "insights. Sedimentary Geology 140, 143-175. https://doi.org/10.1016/S0037-0738(00)00176-7"
    ),
    "Robie, R.A., Hemingway, B.S. (1995). Thermodynamic properties of minerals. USGS Bulletin 2131.",
    (
        "ISO 15156-2:2020. Petroleum and natural gas industries - Materials for use in H2S-containing environments in "
        "oil and gas production - Part 2."
    ),
]


def pct(probability: float) -> str:
    """Format a probability as a whole percentage, with ``<1 %`` and ``>99 %`` at the ends.

    Args:
        probability: Probability between 0 and 1.

    Returns:
        Text such as ``"38 %"``.
    """
    if probability < 0.005:
        return "<1 %"
    if probability > 0.995:
        return ">99 %"
    return f"{100 * probability:.0f} %"


def _figures(
    result: Mapping[str, Any],
    wells: Sequence[Mapping[str, Any]] | None,
    out_dir: str,
    prefix: str,
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
    pts = [
        w
        for w in (wells or [])
        if w.get("measured_ppm") not in (None, "")
        and w.get("res_T_C") not in (None, "")
        and not not_detected(w)
    ]
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    if pts:
        same = [
            w
            for w in pts
            if classify_setting(w.get("formation"), w.get("setting"))
            == p.get("setting")
        ]
        other = [
            w
            for w in pts
            if classify_setting(w.get("formation"), w.get("setting"))
            != p.get("setting")
        ]
        ax.scatter(
            [float(w["res_T_C"]) for w in other],
            [float(w["measured_ppm"]) for w in other],
            s=22,
            c="#bdc3c7",
            edgecolor="grey",
            linewidth=0.3,
            label=f"measured wells, other setting ({len(other)})",
        )
        ax.scatter(
            [float(w["res_T_C"]) for w in same],
            [float(w["measured_ppm"]) for w in same],
            s=34,
            c="#2e86c1",
            edgecolor="k",
            linewidth=0.4,
            label=f"measured wells, {p.get('setting')} ({len(same)})",
            zorder=3,
        )
    ts = [40.0 + 5.0 * i for i in range(33)]
    ax.plot(
        ts,
        [haaland_ppm(t) for t in ts],
        "k--",
        lw=1.1,
        label="Håland et al. (1999) correlation",
    )
    curve = result.get("curve") or []
    if curve:
        ax.plot(
            [c["T_C"] for c in curve],
            [c["buffer_ppm"] for c in curve],
            color="purple",
            lw=1.7,
            label="mineral buffer at the CO2 and pressure of the estimate",
        )
    x = float(p["res_T_C"])
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
    ax.set_ylim(0.03, 200.0)
    ax.set_xlim(40.0, 200.0)
    ax.set_xlabel("Reservoir temperature (°C)")
    ax.set_ylabel("H2S in test gas (ppm by mole)")
    ax.set_title(f"{name} against measured wells")
    ax.legend(fontsize=7.5, loc="lower right")
    path = os.path.join(out_dir, f"{prefix}_estimate_vs_wells.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    figs.append(
        {
            "file": path,
            "caption": f"Estimate for {name} (red) against H2S measured in the test gas of wells, the mineral buffer "
            "and the temperature correlation. Wells of the same depositional setting are highlighted.",
        }
    )
    an = [a for a in result.get("analogues", []) if a.get("measured_ppm")]
    if an:
        fig, ax = plt.subplots(figsize=(8.0, 0.36 * len(an) + 1.9))
        labels = [
            "{}, {}{}".format(
                a["well"],
                (a["formation"] or "formation not recorded")
                .replace(" Fm.", "")
                .replace(" FM.", ""),
                (
                    ""
                    if a["distance_km"] is None
                    else " ({:.0f} km)".format(a["distance_km"])
                ),
            )
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
        ax.scatter(
            [a["measured_ppm"] for a in an],
            ypos,
            s=70,
            color="#2e86c1",
            edgecolor="k",
            linewidth=0.5,
            label="measured in the well",
            zorder=3,
        )
        mod = [(a["buffer_ppm"], y) for a, y in zip(an, ypos) if a.get("buffer_ppm")]
        if mod:
            ax.scatter(
                [m[0] for m in mod],
                [m[1] for m in mod],
                s=55,
                marker="x",
                color="purple",
                linewidth=1.4,
                label="buffer at the conditions of the well",
                zorder=4,
            )
        ax.set_yticks(ypos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_ylim(-0.7, len(an) - 0.3)
        ax.set_xscale("log")
        ax.grid(True, axis="x", which="major", alpha=0.3)
        ax.grid(True, axis="y", alpha=0.15)
        ax.set_xlabel("H2S in test gas (ppm by mole)")
        ax.set_title("Analogue wells")
        handles, names = ax.get_legend_handles_labels()
        fig.legend(
            handles, names, loc="lower center", ncol=2, fontsize=8, frameon=False
        )
        fig.tight_layout(rect=(0.0, 0.5 / fig.get_figheight(), 1.0, 1.0))
        path = os.path.join(out_dir, f"{prefix}_analogue_wells.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        figs.append(
            {
                "file": path,
                "caption": "H2S measured in the analogue wells and the buffer value at the conditions of each well, "
                f"with the estimate for {name}.",
            }
        )
    return figs


def build_sections(
    result: Mapping[str, Any], extra: Sequence[Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Turn a result record into report sections (heading, paragraphs, bullet lists, tables).

    Args:
        result: Output of :func:`reservoir_h2s.estimate.estimate_prospect`.
        extra: Further sections (``heading`` with ``paragraphs``, ``bullets`` or ``table``) placed before the
            recommendations, for example the specification of the receiving gas system.

    Returns:
        Sections in reading order.
    """
    p = result["prospect"]
    rr = result["recommended_range"]
    sour = result["sour_service"]
    spec = result["gas_specification"]
    measured = result["measurements"]["median"] is not None
    name = p.get("name", "the prospect")
    summary = [
        "The best estimate of H2S in the test gas from {} is {} ppm, with a P10 to P90 range of {} to {} ppm. "
        "For design, use {} to {} ppm.".format(
            name,
            fmt(result["best_estimate"]),
            fmt(result["p10"]),
            fmt(result["p90"]),
            fmt(rr["low"]),
            fmt(rr["high"]),
        ),
        "Basis: {}.".format(result["basis"]),
        "The H2S partial pressure at reservoir pressure is {} kPa (P50) against the sour-service limit of {} kPa in "
        "ISO 15156-2; the probability of sour service is {}. The probability that the test gas exceeds the gas "
        "limit of {} ppm ({} mg/Nm³) is {}.".format(
            fmt(sour["partial_pressure_kpa_p50"]),
            fmt(sour["limit_kpa"]),
            pct(sour["probability_sour"]),
            fmt(spec["limit_ppm"]),
            fmt(spec["limit_mg_nm3"]),
            pct(spec["probability_above"]),
        ),
        (
            "The estimate is for the reservoir before production. H2S formed later by bacteria where seawater is injected "
            "is not included."
        ),
    ]
    pa = result["probability_above"]
    sections: list[dict[str, Any]] = [
        {
            "heading": "Summary",
            "paragraphs": summary,
            "table": {
                "header": ["Quantity", "Value"],
                "rows": [
                    [
                        "Best estimate (P50)",
                        "{} ppm".format(fmt(result["best_estimate"])),
                    ],
                    [
                        "P10 / P50 / P90",
                        "{} / {} / {} ppm".format(
                            fmt(result["p10"]), fmt(result["p50"]), fmt(result["p90"])
                        ),
                    ],
                    [
                        "Range for design",
                        "{} to {} ppm".format(fmt(rr["low"]), fmt(rr["high"])),
                    ],
                    [
                        "P50 / P90 in mg/Nm³",
                        "{} / {} mg/Nm³".format(
                            fmt(spec["p50_mg_nm3"]), fmt(spec["p90_mg_nm3"])
                        ),
                    ],
                ]
                + [[f"Probability above {k} ppm", pct(v)] for k, v in pa.items()]
                + [
                    [
                        "H2S partial pressure at reservoir pressure, P50 / P90",
                        "{} / {} kPa".format(
                            fmt(sour["partial_pressure_kpa_p50"]),
                            fmt(sour["partial_pressure_kpa_p90"]),
                        ),
                    ],
                    [
                        "Probability of sour service (above 0.3 kPa)",
                        pct(sour["probability_sour"]),
                    ],
                    ["Basis", result["basis"]],
                ],
            },
        }
    ]
    buf = result["buffer"]
    basis_rows = [
        ["Name", name],
        [
            "Position",
            (
                "{}°N, {}°E".format(fmt(p.get("lat"), 4), fmt(p.get("lon"), 4))
                if p.get("lat")
                else "-"
            ),
        ],
        ["Reservoir formation", p.get("formation") or "-"],
        ["Depositional setting", p.get("setting") or "-"],
        ["Reservoir temperature", "{} °C".format(fmt(p.get("res_T_C"), 3))],
        [
            "Reservoir pressure",
            "{} bara ({})".format(
                fmt(p.get("res_P_used_bara"), 3), p.get("pressure_basis")
            ),
        ],
        [
            "CO2 in the reservoir fluid",
            "{} mol % ({})".format(fmt(p.get("co2_used_molpct")), p.get("co2_basis")),
        ],
        ["Fluid", "{}, {}".format(p.get("fluid_type"), buf.get("fluid_basis", "-"))],
        ["Test-separator basis", buf.get("separator_basis", "-")],
        [
            "H2S readings in the discovery",
            (
                ", ".join(fmt(v) for v in result["measurements"]["gas_readings"])
                + " ppm"
                if measured
                else "none"
            ),
        ],
    ]
    sections.append(
        {
            "heading": "Basis",
            "paragraphs": [
                (
                    "The estimate uses the data below. Values that were assumed or taken from a trend are listed under "
                    "assumptions and data gaps."
                )
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
                    "In sandstone reservoirs that hold pyrite and an iron-bearing carbonate (siderite or ankerite), the two "
                    "minerals fix the H2S content of the fluid: 4 FeS2 + CH4 + 3 CO2 + 6 H2O = 4 FeCO3 + 8 H2S. H2S then "
                    "follows from the reservoir temperature, the CO2 content and, weakly, the pressure. NeqSim solves this "
                    "equilibrium with the fugacities of the reservoir fluid (SRK) and flashes the fluid to test-separator "
                    "conditions, because H2S is measured in separator gas."
                ),
                (
                    f"The buffer was compared with H2S measured in the test gas of {cal['wells']} wells. "
                    if cal.get("wells")
                    else "The buffer was compared with H2S measured in the test gas of wells. "
                )
                + "The comparison gives, per depositional setting, how far measured wells lie from the buffer and how "
                "much they scatter. Wells with only readings below the detection limit are kept apart and used as a check.",
                (
                    "For a prospect, the temperature, CO2 content and pressure are predictions. Their uncertainty is carried "
                    "to H2S through the sensitivity of the buffer and added to the scatter of the measured wells. The result "
                    "is a lognormal distribution, reported as P10, P50 and P90."
                ),
                (
                    "When the discovery has its own readings in test gas, their median replaces the buffer value, and the "
                    "buffer is used as a check on the readings."
                ),
            ],
        }
    )
    sections.append(
        {
            "heading": "Estimate and reasoning",
            "bullets": list(result["reasoning"]),
            "table": {
                "header": [
                    "Source of uncertainty",
                    "Input (one standard deviation)",
                    "Effect on H2S",
                    "Share of variance",
                ],
                "rows": [
                    [
                        b["source"],
                        b["input_scatter"],
                        "factor {:.2f}".format(b["factor"]),
                        "{:.0f} %".format(100 * b["share_of_variance"]),
                    ]
                    for b in result["uncertainty_budget"]
                ]
                + [
                    [
                        "Total (buffer estimate)",
                        "-",
                        "factor {:.2f}".format(
                            10 ** result["statistical"]["sd_total_log10"]
                        ),
                        "100 %",
                    ]
                ],
            },
        }
    )
    an = result.get("analogues") or []
    if an:
        sections.append(
            {
                "heading": "Analogue wells",
                "paragraphs": [
                    (
                        "The table lists measured wells of the same formation or setting, nearest first. The ratio compares "
                        "the measured value with the buffer at the temperature, pressure and CO2 of that well."
                    )
                ],
                "table": {
                    "header": [
                        "Well",
                        "Field",
                        "Formation",
                        "Match",
                        "Distance (km)",
                        "T (°C)",
                        "CO2 (mol %)",
                        "Measured (ppm)",
                        "Buffer (ppm)",
                        "Ratio",
                    ],
                    "rows": [
                        [
                            a["well"],
                            a["field"] or "-",
                            a["formation"] or "-",
                            a["match"],
                            fmt(a["distance_km"], 2),
                            fmt(a["reservoir_T_C"], 3),
                            fmt(a["co2_molpct"]),
                            fmt(a["measured_ppm"]),
                            fmt(a["buffer_ppm"]),
                            fmt(a["ratio"]),
                        ]
                        for a in an
                    ],
                },
            }
        )
    sections.append(
        {
            "heading": "Sour service and gas specification",
            "paragraphs": [
                "ISO 15156-2 defines sour service by an H2S partial pressure of 0.3 kPa or more. The partial pressure "
                "here is the {}, {} bara. It governs material selection for the well and the equipment at well "
                "pressure; equipment at lower pressure sees a lower partial pressure.".format(
                    sour["basis"], fmt(sour["pressure_bara"], 3)
                ),
                "The gas limit used is {} mg/Nm³, or {} ppm. The comparison is made on test-separator gas: "
                "the H2S content of the export gas also depends on the process (pressures, glycol and amine contact, "
                "mixing with other gas) and on the specification of the receiving system, which must be checked.".format(
                    fmt(spec["limit_mg_nm3"]), fmt(spec["limit_ppm"])
                ),
            ],
            "table": {
                "header": [
                    "Check",
                    "P50",
                    "P90",
                    "Limit",
                    "Probability above the limit",
                ],
                "rows": [
                    [
                        "H2S partial pressure at reservoir pressure (kPa)",
                        fmt(sour["partial_pressure_kpa_p50"]),
                        fmt(sour["partial_pressure_kpa_p90"]),
                        fmt(sour["limit_kpa"]),
                        pct(sour["probability_sour"]),
                    ],
                    [
                        "H2S in test gas (mg/Nm³)",
                        fmt(spec["p50_mg_nm3"]),
                        fmt(spec["p90_mg_nm3"]),
                        fmt(spec["limit_mg_nm3"]),
                        pct(spec["probability_above"]),
                    ],
                ],
            },
        }
    )
    sections.append(
        {"heading": "Accuracy of the estimate", "bullets": list(result["accuracy"])}
    )
    sections += [dict(s) for s in (extra or [])]
    rec = [
        (
            "Confirm the readings in the test gas of further wells and in the first production gas, and record the "
            "separator pressure and temperature with every reading."
            if measured
            else "Measure H2S in the test gas of the first well with detector tubes at the separator, several times "
            "through the flow period, and record the separator pressure and temperature."
        ),
        (
            "Record the mud type and any H2S scavenger used: both remove H2S from early samples. Laboratory values from "
            "steel sample bottles are too low and should not replace the readings at the rig."
        ),
        "Measure CO2 in the same gas: it is the second control on H2S after temperature.",
    ]
    rec.insert(
        0,
        "{} {} to {} ppm in process and material studies and check sour service against the upper value.".format(
            "Carry" if measured else "Until a well is tested, carry",
            fmt(rr["low"]),
            fmt(rr["high"]),
        ),
    )
    rec.append(
        "Where seawater injection is planned, assess reservoir souring separately: it can raise H2S well above the "
        "values here during the life of the field."
    )
    sections.append({"heading": "Recommendations", "bullets": rec})
    notes = list(result.get("assumptions") or []) + list(result.get("data_gaps") or [])
    if notes:
        sections.append({"heading": "Assumptions and data gaps", "bullets": notes})
    return sections


def write_report(
    result: Mapping[str, Any],
    out_dir: str,
    wells: Sequence[Mapping[str, Any]] | None = None,
    extra_sections: Sequence[Mapping[str, Any]] | None = None,
    references: Sequence[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Write the estimate as JSON, Markdown and Word (when python-docx is installed), with figures.

    Args:
        result: Output of :func:`reservoir_h2s.estimate.estimate_prospect`.
        out_dir: Folder for the files (created when missing).
        wells: Calibration wells, for the first figure.
        extra_sections: Further sections placed before the recommendations, see :func:`build_sections`.
        references: Reference list; a default list of the public sources is used when omitted.
        title: Report title; default ``"H2S in gas - estimate for <name>"``.

    Returns:
        ``{"json", "markdown", "docx", "figures"}`` with the paths written (``docx`` is ``None`` without python-docx).
    """
    os.makedirs(out_dir, exist_ok=True)
    name = result["prospect"].get("name", "prospect")
    safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "prospect"
    title = title or f"H2S in gas - estimate for {name}"
    figs = _figures(result, wells, out_dir, safe)
    sections = build_sections(result, extra_sections)
    refs = list(references or DEFAULT_REFERENCES)
    json_path = os.path.join(out_dir, f"h2s_estimate_{safe}.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False, default=str)
    fig_after = {"Estimate and reasoning": 0, "Analogue wells": 1}
    md = [f"# {title}", ""]
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
                size = Pt(8 if len(tab["header"]) > 7 else 9)
                for row in table.rows:
                    for cell in row.cells:
                        for par in cell.paragraphs:
                            for run in par.runs:
                                run.font.size = size
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
