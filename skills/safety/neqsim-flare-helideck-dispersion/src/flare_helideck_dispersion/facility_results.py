"""``results.json`` fragment of a facility study (any sources, any receptors).

Every number in the conclusions, tables and discussion is taken from the study result,
the sensitivity rows or the figure records. The fragment follows the layout of
:mod:`flare_helideck_dispersion.results` so that :func:`validate_fragment` accepts it:
``conclusions`` is a string, ``benchmark_validation`` is ``{"points": [...]}`` and every
figure has an observation, mechanism, implication and recommendation.

Exceedance values are conditional on an unignited release; an annual figure is produced
only for an explicit flame-out frequency and duration.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .facility import FacilityStudyResult
from .results import REFERENCES, validate_fragment
from .study import annualise_exposure, threshold_key

__all__ = ["DEFAULT_FACILITY_CRITERIA", "build_facility_results", "validate_fragment"]

DEFAULT_FACILITY_CRITERIA: list[dict[str, Any]] = [
    {
        "name": "10 % LFL",
        "pct_lfl": 10.0,
        "source": "screening threshold; confirm the governing criterion of each receptor "
        "(for example a gas-detection or air-intake setpoint) in the project design basis",
    },
    {
        "name": "20 % LFL",
        "pct_lfl": 20.0,
        "source": "screening threshold; confirm the governing criterion of each receptor "
        "in the project design basis",
    },
]
"""Both thresholds are always reported; the source of each criterion must be stated."""


def _fmt(value: float) -> str:
    """Format a percentage with sensible precision."""
    if value >= 100.0:
        return f"{value:.0f}"
    if value >= 1.0:
        return f"{value:.1f}"
    return f"{value:.2f}"


def build_facility_results(
    study: FacilityStudyResult,
    figures: Sequence[Any] = (),
    sensitivity: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    criteria: Sequence[Mapping[str, Any]] | None = None,
    release_frequency_per_year: float | None = None,
    hours_per_release: float | None = None,
    extra_assumptions: Sequence[str] | None = None,
    extra_data_gaps: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the ``results.json`` fragment of a facility study.

    Args:
        study: The facility study result.
        figures: Figure records from :mod:`flare_helideck_dispersion.facility_figures`.
        sensitivity: Optional tilt-scan rows by case name, as returned by
            :func:`flare_helideck_dispersion.facility.facility_tilt_scan`.
        criteria: Acceptance criteria with their source; defaults to 10 % and 20 % LFL.
        release_frequency_per_year: Optional flame-out frequency, 1/year.
        hours_per_release: Optional release duration, hours.
        extra_assumptions: Assumptions to append.
        extra_data_gaps: Data gaps (mappings with gap, source, status, assumed, effect).

    Returns:
        The results fragment.
    """
    mode = "briggs" if "briggs" in study.settings.modes else study.settings.modes[0]
    criteria = list(criteria or DEFAULT_FACILITY_CRITERIA)
    thresholds = sorted(
        {float(c["pct_lfl"]) for c in criteria} | set(study.settings.thresholds_pct_lfl)
    )
    key_thr = 20.0 if 20.0 in thresholds else thresholds[-1]
    low_thr = 10.0 if 10.0 in thresholds else thresholds[0]
    ranking = study.ranking(key_thr, mode)
    worst = ranking[0]
    summ = study.summaries
    cases = [fr.case.name for fr in study.freleases]
    receptors = study.receptors

    def rsum(case: str, receptor: str, m: str = mode) -> dict[str, Any]:
        return summ[case]["modes"][m]["receptors"][receptor]

    exposed = [r for r in ranking if r["exceed_pct_hours"] > 0.0]
    clean = [r for r in ranking if r["peak_pct_lfl"] < low_thr]
    wc = rsum(worst["case"], worst["receptor"])["peak_condition"]
    tilt_note = ""
    if sensitivity:
        flat = []
        for case, rows in sensitivity.items():
            for rec in receptors:
                hit = [
                    row["tilt_deg"]
                    for row in rows
                    if row["receptors"][rec.name]["peak"] >= key_thr
                ]
                base_hit = rsum(case, rec.name)["peak_pct_lfl"] >= key_thr
                if hit and not base_hit:
                    flat.append(
                        f"{rec.name} ({case}) reaches {_fmt(key_thr)} % LFL at {min(hit):.0f} to {max(hit):.0f} deg"
                    )
        tilt_note = (
            " The base inclination hides exposure at other inclinations: "
            + "; ".join(flat)
            + "."
            if flat
            else " No receptor changes class over the inclination scan."
        )
    conclusions = (
        "Screening result, conditional on an unignited release being ongoing (no annual frequency is implied). "
        "{n_pairs} case-receptor pairs from {n_src} source(s) and {n_rec} receptor(s) were evaluated; {n_exp} reach {thr} % LFL in some wind and {n_clean} stay below {low} % LFL. "
        "The most exposed pair is {receptor} ({kind}) for {case} from {source}: peak {peak} % LFL, {thr} % LFL exceeded in {exc} % of wind hours ({low} % LFL in {exc_low} % of hours); "
        "the worst condition is wind from {wd:03.0f} deg at {u:.1f} m/s (Pasquill {st}), {dist:.0f} m from the source at {dz:+.0f} m relative height.{tilt} "
        "The model has no platform wake, building or ventilation effects; the worst conditions are handed to CFD tools.".format(
            n_pairs=len(ranking),
            n_src=len(study.sources),
            n_rec=len(receptors),
            n_exp=len(exposed),
            thr=_fmt(key_thr),
            low=_fmt(low_thr),
            n_clean=len(clean),
            receptor=worst["receptor"],
            kind=worst["kind"],
            case=worst["case"],
            source=worst["source"],
            peak=_fmt(worst["peak_pct_lfl"]),
            exc=_fmt(worst["exceed_pct_hours"]),
            exc_low=_fmt(
                study.exceedance(worst["case"], worst["receptor"], low_thr, mode)
            ),
            wd=wc["wind_from_deg"],
            u=wc["speed_m_s"],
            st=wc["pasquill_class"],
            dist=wc["distance_from_source_m"],
            dz=wc["height_above_source_m"],
            tilt=tilt_note,
        )
    )
    conclusions = re.sub(r"\s+", " ", conclusions).strip()

    tables: list[dict[str, Any]] = [
        {
            "title": "Release cases and sources (conditional on an unignited release)",
            "headers": [
                "Case",
                "Source",
                "Kind",
                "Rate (kg/s)",
                "Tip jet (m/s)",
                "Inclination (deg)",
                "Height ASL (m)",
            ],
            "rows": [
                [
                    fr.case.name,
                    fr.source.name,
                    fr.source.kind,
                    fr.case.mass_flow_kg_s,
                    round(study.releases[fr.case.name].tip["v_exit_ms"], 1),
                    (
                        fr.source.tilt_deg
                        if fr.source.tilt_deg is not None
                        else study.settings.params.tilt_deg
                    ),
                    fr.source.height_asl_m,
                ]
                for fr in study.freleases
            ],
        },
        {
            "title": "Receptor register",
            "headers": [
                "Receptor",
                "Kind",
                "Points",
                "Thresholds (% LFL)",
                "Criterion source",
            ],
            "rows": [
                [
                    r.name,
                    r.kind,
                    len(r.points),
                    ", ".join(
                        threshold_key(t)
                        for t in (
                            r.thresholds_pct_lfl or study.settings.thresholds_pct_lfl
                        )
                    ),
                    r.criterion_source or "not stated (data gap)",
                ]
                for r in receptors
            ],
        },
    ]
    shown = [t for t in thresholds if t in set(study.settings.thresholds_pct_lfl)][
        :4
    ] or [key_thr]
    exc_rows = []
    for fr in study.freleases:
        for r in receptors:
            entry = rsum(fr.case.name, r.name)
            exc_rows.append(
                [fr.case.name, r.name, round(entry["peak_pct_lfl"], 2)]
                + [
                    round(study.exceedance(fr.case.name, r.name, t, mode), 3)
                    for t in shown
                ]
            )
    tables.append(
        {
            "title": "Peak and exceedance by receptor (percent of wind hours, given a release)",
            "headers": ["Case", "Receptor", "Peak (% LFL)"]
            + [f">= {threshold_key(t)} % LFL (% of hours)" for t in shown],
            "rows": exc_rows,
        }
    )
    cond_rows = []
    for r in receptors:
        best = max(cases, key=lambda c: rsum(c, r.name)["peak_pct_lfl"])
        pc = rsum(best, r.name)["peak_condition"]
        cond_rows.append(
            [
                r.name,
                best,
                round(rsum(best, r.name)["peak_pct_lfl"], 2),
                round(pc["wind_from_deg"]),
                pc["speed_m_s"],
                pc["pasquill_class"],
                round(pc["distance_from_source_m"]),
                round(pc["height_above_source_m"]),
            ]
        )
    tables.append(
        {
            "title": "Worst condition per receptor (worst case)",
            "headers": [
                "Receptor",
                "Case",
                "Peak (% LFL)",
                "Wind from (deg)",
                "Speed (m/s)",
                "Pasquill",
                "Distance (m)",
                "Height rel. source (m)",
            ],
            "rows": cond_rows,
        }
    )
    tables.append(
        {
            "title": "Acceptance criteria and their sources",
            "headers": ["Criterion", "Value (% LFL)", "Source"],
            "rows": [[c["name"], c["pct_lfl"], c["source"]] for c in criteria],
        }
    )
    if sensitivity:
        rows = []
        for case, scan in sensitivity.items():
            for row in scan:
                peaks = [row["receptors"][r.name]["peak"] for r in receptors]
                top = max(range(len(peaks)), key=lambda i: peaks[i])
                rows.append(
                    [case, row["tilt_deg"], receptors[top].name, round(peaks[top], 2)]
                )
        tables.append(
            {
                "title": "Release-inclination scan (most exposed receptor per inclination)",
                "headers": [
                    "Case",
                    "Inclination (deg)",
                    "Most exposed receptor",
                    "Peak (% LFL)",
                ],
                "rows": rows,
            }
        )

    bins = study.summaries[worst["case"]]["modes"][mode]["receptors"][
        worst["receptor"]
    ]["exceed_by_speed_bin_pct_hours"]
    by_bin = bins.get(threshold_key(key_thr)) or {}
    contributor = [
        {"contributor": f"speed bin {b} m/s", "share_pct_of_hours": v}
        for b, v in sorted(by_bin.items(), key=lambda kv: -kv[1])
        if v > 0.0
    ] or [{"contributor": "none", "share_pct_of_hours": 0.0}]
    ruled_out = [
        f"{r['receptor']} ({r['case']}): {_fmt(low_thr)} % LFL is never reached in any wind (peak {_fmt(r['peak_pct_lfl'])} % LFL)."
        for r in clean
    ]
    robustness: list[dict[str, Any]] = []
    if "none" in study.settings.modes and mode == "briggs":
        passive = study.exceedance(worst["case"], worst["receptor"], key_thr, "none")
        robustness.append(
            {
                "conclusion": f"{worst['receptor']} exceedance of {_fmt(key_thr)} % LFL ({worst['case']})",
                "test": "passive release bound (no plume rise)",
                "result": f"{_fmt(passive)} % of hours without rise versus {_fmt(worst['exceed_pct_hours'])} % with rise",
                "status": (
                    "robust"
                    if passive <= worst["exceed_pct_hours"] * 1.5 + 1e-9
                    else "sensitive to plume rise"
                ),
            }
        )
    for case, scan in (sensitivity or {}).items():
        values = [
            row["receptors"][worst["receptor"]]["hours_ge20"]
            for row in scan
            if "hours_ge20" in row["receptors"][worst["receptor"]]
        ]
        if values:
            robustness.append(
                {
                    "conclusion": f"{worst['receptor']} exceedance of 20 % LFL ({case})",
                    "test": "release inclination scan",
                    "result": f"{min(values):.2f} to {max(values):.2f} % of hours over the scan",
                    "status": (
                        "robust"
                        if max(values) - min(values) < 0.5 * max(max(values), 1e-9)
                        else "sensitive to inclination"
                    ),
                }
            )
    conservatism = [
        "Release rate is the rated or peak flow, held constant; depressurisation decay is not credited.",
        "Only the vertical momentum component of an inclined release lifts the plume; the horizontal component is ignored.",
        "The maximum over all points of a receptor is used, so an area or route is judged by its worst point.",
    ]
    evidence_against = [
        "No platform wake, downwash, building effects or mechanical turbulence is modelled; a lifted cloud could be pulled down in the lee of the structure.",
        "Air intakes and enclosed spaces are judged by the outside concentration; ventilation, dilution and detection inside the building are not modelled.",
        "A Gaussian plume is not valid much below 1 m/s and meander is ignored.",
    ]
    discriminating_test = "Run a CFD simulation with the facility geometry for {case} from {source} at wind from {wd:03.0f} deg and {u:.1f} m/s (the worst condition) and compare the {thr} % LFL envelope at {receptor} with this screening result.".format(
        case=worst["case"],
        source=worst["source"],
        wd=wc["wind_from_deg"],
        u=wc["speed_m_s"],
        thr=_fmt(key_thr),
        receptor=worst["receptor"],
    )
    handoff = []
    for row in ranking[:6]:
        if row["exceed_pct_hours"] <= 0.0 and row["peak_pct_lfl"] < 0.5 * low_thr:
            continue
        entry = rsum(row["case"], row["receptor"])
        rel = study.releases[row["case"]]
        src = next(fr.source for fr in study.freleases if fr.case.name == row["case"])
        handoff.append(
            {
                "case": row["case"],
                "source": src.to_dict(),
                "receptor": row["receptor"],
                "kind": row["kind"],
                "mass_flow_kg_s": rel.mdot,
                "tip_exit": {
                    k: rel.tip[k]
                    for k in ("v_exit_ms", "d_eff_m", "rho_exp", "t_exp_k", "choked")
                },
                "wind_from_deg": entry["peak_condition"]["wind_from_deg"],
                "wind_speed_ms": entry["peak_condition"]["speed_m_s"],
                "peak_pct_lfl": row["peak_pct_lfl"],
                "peak_point_enu_m": [
                    entry["peak_condition"]["point_east_m"],
                    entry["peak_condition"]["point_north_m"],
                    entry["peak_condition"]["point_up_m"],
                ],
            }
        )
    internal: list[dict[str, Any]] = []
    total = float(study.wind.total_pct)
    internal.append(
        {
            "name": "wind table sums to 100 % of hours",
            "reference_value": 100.0,
            "neqsim_value": total,
            "status": "pass" if abs(total - 100.0) <= 1.0 else "fail",
        }
    )
    monotone = all(
        study.exceedance(fr.case.name, r.name, hi, mode)
        <= study.exceedance(fr.case.name, r.name, lo, mode) + 1e-9
        for fr in study.freleases
        for r in receptors
        for lo, hi in itertools.pairwise(thresholds)
    )
    internal.append(
        {
            "name": "exceedance never increases with the threshold",
            "reference_value": 1.0,
            "neqsim_value": 1.0 if monotone else 0.0,
            "status": "pass" if monotone else "fail",
        }
    )
    consistent = all(
        study.exceedance(fr.case.name, r.name, t, mode) == 0.0
        or rsum(fr.case.name, r.name)["peak_pct_lfl"] >= t
        for fr in study.freleases
        for r in receptors
        for t in thresholds
    )
    internal.append(
        {
            "name": "exceedance above zero only where the peak reaches the threshold",
            "reference_value": 1.0,
            "neqsim_value": 1.0 if consistent else 0.0,
            "status": "pass" if consistent else "fail",
        }
    )
    assumptions = [
        "Exceedance values are percent of wind hours given an unignited release of the stated rate; they are conditional, not annual frequencies.",
        "Receptor positions, heights and shapes are as supplied in one facility frame (true-north axes, height above sea level); positions taken from drawings are approximate until surveyed.",
        "The wind table is representative ({}); Pasquill class by speed: {}.".format(
            study.wind.metadata.get("source", "supplied"),
            (
                study.settings.stability_scheme
                if isinstance(study.settings.stability_scheme, str)
                else "user defined"
            ),
        ),
        f"Plume model: choked tip with Birch notional nozzle, Briggs momentum rise with stable-air caps, Gaussian plume with sea reflection and sigma0 = dh / {study.settings.params.sigma0_divisor:g}.",
        "Several simultaneous releases are represented by one combined mass flow of one source; the cases are not superposed.",
    ] + list(extra_assumptions or [])
    no_source = [r.name for r in receptors if not r.criterion_source]
    data_gaps: list[Mapping[str, str]] = [
        {
            "gap": "Flame-out (unignited release) frequency and duration",
            "source": "operator reliability data",
            "status": "open" if release_frequency_per_year is None else "supplied",
            "assumed": (
                "none; results are conditional"
                if release_frequency_per_year is None
                else "supplied by the user"
            ),
            "effect": "annual exposure cannot be stated without it",
        },
        {
            "gap": "Governing acceptance criterion and its source per receptor",
            "source": "project design basis",
            "status": "open",
            "assumed": "10 % and 20 % LFL both reported"
            + (f"; no source for {', '.join(no_source)}" if no_source else ""),
            "effect": "pass or fail depends on the governing value of each receptor",
        },
        {
            "gap": "Platform wake, building effects and CFD validation",
            "source": "CFD study",
            "status": "open",
            "assumed": "none; open-terrain Gaussian plume",
            "effect": "non-conservative if the cloud is pulled down or trapped in the lee of the structure",
        },
        {
            "gap": "Surveyed receptor and source coordinates and heights",
            "source": "general arrangement and survey",
            "status": "open",
            "assumed": "coordinates as supplied",
            "effect": "exposure near a criterion is sensitive to a few metres of height or distance",
        },
    ] + list(extra_data_gaps or [])
    captions = {f.name: f"{f.title}. {f.sub}." for f in figures}
    discussion = []
    for f in figures:
        if f.name.startswith("facility_layout"):
            d = {
                "observation": f"{f.facts.get('n_receptors', 0)} receptors and {f.facts.get('n_sources', 0)} source(s) are shown; the most exposed pair is {f.facts.get('worst_receptor', '-')}.",
                "mechanism": "Receptors are assessed by the maximum over their points; the plan shows where the points lie relative to each source.",
                "implication": "Receptors close to a source and at similar height are the first to check; height difference matters as much as distance.",
                "recommendation": "Confirm every coordinate and height against the general arrangement before quoting a result.",
            }
        else:
            if f.facts.get("metric") == "peak":
                obs = f"No receptor reaches {f.facts.get('threshold', '-')} % LFL; the highest peak is {_fmt(float(f.facts.get('peak_pct_lfl', 0.0)))} % LFL at {f.facts.get('worst_receptor', '-')}."
            else:
                obs = f"At {f.facts.get('threshold', '-')} % LFL the largest exceedance is {_fmt(float(f.facts.get('max_pct', 0.0)))} % of hours ({f.facts.get('worst_receptor', '-')})."
            d = {
                "observation": obs,
                "mechanism": "Exceedance is the wind-weighted share of hours with the threshold exceeded somewhere on the receptor, given that a release is ongoing.",
                "implication": "These are conditional shares of wind hours, not annual frequencies.",
                "recommendation": "Obtain a flame-out frequency before quoting any annual figure and take the worst conditions to CFD.",
            }
        d.update({"figure": f.name, "title": f.title})
        discussion.append(d)
    key_results: dict[str, Any] = {
        "n_cases": len(cases),
        "n_sources": len(study.sources),
        "n_receptors": len(receptors),
        "most_exposed_receptor": worst["receptor"],
        "most_exposed_case": worst["case"],
        "most_exposed_peak_pct_lfl": worst["peak_pct_lfl"],
        f"most_exposed_pct_hours_ge{threshold_key(key_thr)}": worst["exceed_pct_hours"],
        "receptors_reaching_threshold": len(exposed),
    }
    result: dict[str, Any] = {
        "key_results": key_results,
        "approach": "Choked tip and Birch notional nozzle, Briggs momentum rise with stable-air limits, Gaussian plume with sea reflection; wind-weighted sweep over direction and speed against named receptors of any shape (conditional on an unignited release).",
        "conclusions": conclusions,
        "validation": {
            "method": "internal consistency checks; independent CFD or a reference study is needed for design use"
        },
        "tables": tables,
        "references": REFERENCES,
        "assumptions": assumptions,
        "data_gaps": data_gaps,
        "contributor_ranking": contributor,
        "ruled_out": ruled_out,
        "robustness": robustness,
        "conservatism": conservatism,
        "discriminating_test": discriminating_test,
        "evidence_against": evidence_against,
        "benchmark_validation": {"points": internal},
        "cfd_handoff": handoff,
        "ranking": ranking,
        "warnings": list(study.warnings),
    }
    if captions:
        result["figure_captions"] = captions
        result["figure_discussion"] = discussion
    if release_frequency_per_year is not None and hours_per_release is not None:
        result["annual_exposure"] = {
            f"{worst['case']} at {worst['receptor']}": annualise_exposure(
                worst["exceed_pct_hours"], release_frequency_per_year, hours_per_release
            )
        }
    if not np.isfinite(worst["peak_pct_lfl"]):
        result["warnings"].append("non-finite peak concentration")
    return result
