"""``results.json`` fragments for the study.

Every number that appears in the conclusions, captions and discussion is taken from the
study result, the sensitivity result or the figure records; nothing is typed in. The
fragment follows the task ``results.json`` layout: ``key_results``, ``conclusions`` (a
string), ``figure_captions``, ``figure_discussion``, ``tables``, ``assumptions``,
``data_gaps``, ``uncertainty``, ``risk_evaluation``, the analytical-depth keys
(``contributor_ranking``, ``ruled_out``, ``robustness``, ``conservatism``,
``discriminating_test``, ``evidence_against``) and
``benchmark_validation = {"points": [{"name", "reference_value", "neqsim_value",
"status"}]}``.

Exceedance values are conditional on an unignited release being ongoing; the fragment
says so in ``conclusions`` and in the assumptions and gives no annual frequency unless a
flame-out frequency is supplied.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .model import Release, ReleaseCase
from .study import (
    BenchmarkScenario,
    StudyResult,
    annualise_exposure,
    helideck_peak_over_directions,
)
from .wind import pasquill_by_speed

DEFAULT_CRITERIA: list[dict[str, Any]] = [
    {
        "name": "10 % LFL",
        "pct_lfl": 10.0,
        "source": "screening threshold; confirm the governing helideck and flight-path "
        "criterion and its source in the project design basis",
    },
    {
        "name": "20 % LFL",
        "pct_lfl": 20.0,
        "source": "screening threshold (integral dispersion tools); confirm the governing "
        "criterion and its source in the project design basis",
    },
]
"""Both thresholds are always reported; the source of the criterion must be stated."""

REFERENCES: list[dict[str, str]] = [
    {
        "id": "NORSOK-S-001",
        "text": "NORSOK S-001 Technical safety (requirements on unignited flare gas at the helideck; check the clause in the edition in force).",
    },
    {
        "id": "API-520",
        "text": "API Standard 520 Parts I and II, Sizing, Selection and Installation of Pressure-relieving Devices.",
    },
    {
        "id": "API-521",
        "text": "API Standard 521 / ISO 23251, Pressure-relieving and Depressuring Systems.",
    },
    {
        "id": "CAP-437",
        "text": "UK CAA CAP 437, Offshore Helicopter Landing Areas: Guidance on Standards.",
    },
    {
        "id": "ICAO-Annex-14-V2",
        "text": "ICAO Annex 14 Volume II, Heliports (obstacle-free sector and approach surfaces).",
    },
    {
        "id": "Briggs1969",
        "text": "Briggs, G. A. (1969) Plume Rise, USAEC Critical Review Series.",
    },
    {
        "id": "Briggs1973",
        "text": "Briggs, G. A. (1973) Diffusion estimation for small emissions, ATDL-106 (open-country sigmas).",
    },
    {
        "id": "Briggs1975",
        "text": "Briggs, G. A. (1975) Plume rise predictions, in Lectures on Air Pollution and Environmental Impact Analyses, AMS.",
    },
    {
        "id": "Birch1984",
        "text": "Birch, A. D., Brown, D. R., Dodson, M. G. and Swaffield, F. (1984) The structure and concentration decay of high pressure jets of natural gas, Combust. Sci. Technol. 36, 249-261.",
    },
    {
        "id": "ChenRodi1980",
        "text": "Chen, C. J. and Rodi, W. (1980) Vertical Turbulent Buoyant Jets: A Review of Experimental Data, Pergamon.",
    },
]

EQUATIONS: list[dict[str, str]] = [
    {
        "label": "Gaussian plume with sea reflection",
        "latex": "C = \\frac{Q}{2\\pi u \\sigma_y \\sigma_z} e^{-y^2/2\\sigma_y^2}\\left[e^{-(z-h)^2/2\\sigma_z^2} + e^{-(z+h)^2/2\\sigma_z^2}\\right]",
    },
    {
        "label": "Neutral momentum final rise (Briggs)",
        "latex": "\\Delta h = 3 d v_z / u",
    },
    {
        "label": "Free-jet centreline decay (Chen and Rodi)",
        "latex": "C/C_0 = 6.2 \\frac{d}{x}\\sqrt{\\rho_0/\\rho_a}",
    },
    {"label": "Virtual-source spread", "latex": "\\sigma_0 = |\\Delta h| / 3.5"},
]


def _slug(text: str) -> str:
    """Lower-case identifier of a case name."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()


def _fmt(value: float) -> str:
    """Compact number text for prose."""
    if value == 0.0:
        return "0"
    if abs(value) >= 100.0:
        return f"{value:.0f}"
    if abs(value) >= 10.0:
        return f"{value:.1f}"
    if abs(value) >= 0.1:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _exc(study: StudyResult, case: str, mode: str, thr: str, where: str) -> float:
    """Exceedance (percent of hours given a release) from a case summary."""
    return float(study.summaries[case]["modes"][mode]["exceed_pct_hours"][thr][where])


def _require_thresholds(study: StudyResult) -> None:
    """Both the 10 and 20 percent LFL thresholds must have been computed."""
    keys = {(f"{t:g}") for t in study.settings.thresholds_pct_lfl}
    missing = {"10", "20"} - keys
    if missing:
        raise ValueError(
            f"study must include the {sorted(missing)} % LFL thresholds in thresholds_pct_lfl"
        )


def internal_benchmark_points(study: StudyResult) -> list[dict[str, Any]]:
    """Implementation-verification points (not validation against measurements).

    1. Choked-flow mass closure: the mass flow recomputed from the stagnation pressure
       of the first choked case equals the input mass flow.
    2. Gaussian mass conservation: the plume mass flux integrated over a crosswind-
       vertical plane equals the release rate (checks normalisation and unit chain).
    3. Briggs neutral final rise: the model rise far downwind in neutral air equals
       ``3 d v_z / u`` for a buoyant reference release.

    Args:
        study: Study result.

    Returns:
        Points with ``name``, ``reference_value``, ``neqsim_value``, ``status``,
        ``unit`` and ``tolerance_pct``.
    """
    points: list[dict[str, Any]] = []
    params = study.settings.params
    for name, rel in study.releases.items():
        tip = rel.tip
        if tip["choked"]:
            g, mw, t0 = rel.case.gamma, rel.mw, rel.case.t0_k
            area = math.pi * rel.case.tip_diameter_m**2 / 4.0
            flux = (
                tip["p0_bara"]
                * 1e5
                * math.sqrt(g * mw / (8.314462618 * t0))
                * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
            )
            points.append(
                _point(
                    f"Choked-flow mass closure ({name})",
                    rel.mdot,
                    flux * area,
                    "kg/s",
                    0.1,
                )
            )
            break
    rel = next(iter(study.releases.values()))
    u10, stab, tip_z = 8.0, "D", study.geometry.tip_height_asl_m
    x = 600.0
    ys = np.arange(-1500.0, 1500.1, 5.0)
    zs = np.arange(0.0, 1500.1, 5.0)
    gy, gz = np.meshgrid(ys, zs)
    pts = np.column_stack([np.full(gy.size, x), gy.ravel(), gz.ravel()])
    pct = rel.pct_lfl(
        pts, 270.0, u10, stab, np.array([0.0, 0.0, tip_z]), "briggs"
    ).reshape(gy.shape)
    conc = pct / 100.0 * rel.lfl / rel.fuel_y * rel.rho_gas_amb
    u = u10 * (tip_z / params.reference_height_m) ** params.wind_exponent
    flux_int = float(np.sum(conc) * 5.0 * 5.0 * u)
    points.append(
        _point(
            f"Gaussian plume mass conservation across a plane (x = {x:.0f} m)",
            rel.mdot,
            flux_int,
            "kg/s",
            1.0,
        )
    )
    neutral = Release(
        ReleaseCase("neutral check", 50.0, 0.016, 1.3, 600.0, 0.05, 1.0, 0.6), params
    )
    u_n = u10 * (tip_z / params.reference_height_m) ** params.wind_exponent
    d_n, v_n = neutral.tip["d_eff_m"], neutral.tip["v_exit_ms"] * math.sin(
        math.radians(params.tilt_deg)
    )
    ref_rise = 3.0 * d_n * v_n / u_n
    model_rise = float(
        neutral.centreline_height(np.array([1.0e6]), u10, tip_z, "briggs", "D")[0]
    )
    if neutral.tip["rho_ratio_to_air"] <= 1.0:
        points.append(
            _point("Briggs neutral momentum final rise", ref_rise, model_rise, "m", 0.1)
        )
    return points


def _point(
    name: str, reference: float, value: float, unit: str, tol_pct: float
) -> dict[str, Any]:
    """Benchmark point with a PASS/FAIL status from a relative tolerance."""
    dev = abs(value - reference) / abs(reference) * 100.0 if reference else float("nan")
    return {
        "name": name,
        "reference_value": reference,
        "neqsim_value": value,
        "unit": unit,
        "deviation_pct": dev,
        "tolerance_pct": tol_pct,
        "status": "PASS" if dev <= tol_pct else "FAIL",
        "type": "implementation verification",
    }


def benchmark_points(
    study: StudyResult,
    scenarios: Sequence[BenchmarkScenario] | None = None,
    criterion_pct: float = 20.0,
) -> list[dict[str, Any]]:
    """Verification points plus user scenarios compared with an independent study.

    For a scenario the model helideck peak is computed here. The status is ``PASS`` when
    the model and the independent study classify the helideck the same way relative to
    the criterion (both below), ``FAIL`` otherwise and ``INFO`` when the independent
    study gave no number. The numeric difference is reported in ``detail``.

    Args:
        study: Study result.
        scenarios: Scenarios with the independent study's outcome.
        criterion_pct: Criterion, percent of the LFL.

    Returns:
        List of benchmark points.
    """
    points = internal_benchmark_points(study)
    for s in scenarios or []:
        peak = helideck_peak_over_directions(s, study.receptors, study.settings)[
            "peak_pct_lfl"
        ]
        ref = s.reference_pct_lfl_max
        if ref is None:
            status = "INFO"
        else:
            status = (
                "PASS" if (peak < criterion_pct and ref < criterion_pct) else "FAIL"
            )
        points.append(
            {
                "name": f"Helideck peak vs independent study: {s.label}",
                "reference_value": ref,
                "neqsim_value": peak,
                "unit": "% LFL",
                "status": status,
                "type": "comparison with independent study",
                "detail": "same classification relative to the {:g} % criterion; model {:.3f} % LFL, reference bound {}; source: {}".format(
                    criterion_pct,
                    peak,
                    "none given" if ref is None else f"{ref:g} %",
                    s.reference_source or "not stated",
                ),
            }
        )
    return points


def _speed_bin_ranking(
    study: StudyResult, case: str, mode: str
) -> list[dict[str, Any]]:
    """Speed-bin contributions to the flight-path exceedance of the worst case."""
    for thr in ("20", "10"):
        by_bin = study.summaries[case]["modes"][mode][
            "exceed_any_path_by_speed_bin_pct_hours"
        ][thr]
        total = sum(by_bin.values())
        if total > 0.0:
            ranked = sorted(by_bin.items(), key=lambda kv: -kv[1])
            return [
                {
                    "contributor": f"wind speed bin {label} m/s",
                    "share_pct": 100.0 * v / total,
                    "basis": f"share of the {thr} % LFL flight-path exceedance hours ({total:.2f} % of hours in total)",
                }
                for label, v in ranked
                if v > 0.0
            ]
    return []


def _worst_case(study: StudyResult, mode: str) -> str:
    """Case with the largest 20 percent flight-path exceedance (peak as tie-break)."""
    return max(
        study.releases,
        key=lambda c: (
            _exc(study, c, mode, "20", "any_path"),
            study.summaries[c]["modes"][mode]["peak_pct_lfl_any_path"],
        ),
    )


def _descr(label: str, rec: Mapping[str, Any] | None) -> str:
    """Figure label key from a file name such as ``fig04_plan_footprints_x.png``."""
    m = re.match(r"fig\d+_(.*)\.png", label)
    return m.group(1) if m else label


def figure_discussion(
    records: Sequence[Any], study: StudyResult, mode: str = "briggs"
) -> list[dict[str, Any]]:
    """Observation, mechanism, implication and recommendation for every figure.

    Args:
        records: Figure records from :func:`flare_helideck_dispersion.figures.make_all_figures`.
        study: Study result.
        mode: Plume mode.

    Returns:
        Discussion blocks in the ``results.json`` layout.
    """
    geo = study.geometry
    out: list[dict[str, Any]] = []
    for rec in records:
        key = _descr(rec.name, None)
        f = rec.facts
        d: dict[str, str]
        if key.startswith("layout"):
            d = {
                "observation": "The helideck is {:.0f} m from the flare tip on bearing {:03.0f} deg T and {:.0f} m below it.".format(
                    f["distance_m"], f["azimuth_deg"], f["tip_above_deck_m"]
                ),
                "mechanism": "A buoyant or momentum-driven plume has to travel {:.0f} m horizontally and sink {:.0f} m to reach the deck, so the deck is reached only when the wind blows from {:03.0f} deg T and the cloud is held low.".format(
                    f["distance_m"],
                    f["tip_above_deck_m"],
                    geo.azimuth_toward_deck_wind_from_deg,
                ),
                "implication": "The geometry decides which wind sector can carry gas to the deck and where the flight paths lie in the downwind sector.",
                "recommendation": "Confirm tip and helideck positions, heights, the obstacle-free sector and the approved flight paths from drawings and the helideck operations manual.",
            }
        elif key.startswith("wind"):
            d = {
                "observation": "Wind from the {} sector (towards the deck) occurs {:.1f} % of hours; {:.1f} % of hours are below 4 m/s.".format(
                    f["toward_deck_sector"], f["toward_deck_pct"], f["pct_below_4ms"]
                ),
                "mechanism": "Low wind gives little dilution and, with stable stratification, limits plume rise; the direction table decides which flight paths are downwind.",
                "implication": "Exposure results are weighted by this table, so its resolution matters most in the low-speed bins.",
                "recommendation": "Use measured platform wind (anemometer) or a high-resolution hindcast for the low-speed bins; reanalysis cells smooth calms and lulls.",
            }
        elif key.startswith("source"):
            d = {
                "observation": "Tip jet velocities range from {:.0f} to {:.0f} m/s and gas density from {:.2f} to {:.2f} times air.".format(
                    f["v_min"], f["v_max"], f["rho_ratio_min"], f["rho_ratio_max"]
                ),
                "mechanism": "Choked flow at the tip fixes the exit state; vertical momentum (v sin(tilt)) lifts the plume, cold gas heavier than air tends to sink.",
                "implication": "High-momentum cases lift the cloud away from the deck in strong wind; cold dense cases are the ones that stay low.",
                "recommendation": "Replace rated or assumed release rates with the relief-study values, and tip conditions with a real-gas tip calculation where available.",
            }
        elif key.startswith("plan_footprints"):
            n = sum(1 for p in f["flight_path_peaks"] if p >= 20.0)
            d = {
                "observation": "For {} the cloud reaches 20 % LFL on a flight path in {} of {} winds shown (peaks {} % LFL on the paths).".format(
                    f["case"],
                    n,
                    len(f["flight_path_peaks"]),
                    ", ".join(_fmt(p) for p in f["flight_path_peaks"]),
                ),
                "mechanism": "The wind carries the cloud downwind; calm or light stable wind keeps the plume near release height and dense gas slumps, so the footprint reaches the paths.",
                "implication": "Flight paths downwind of the tip are the exposed receptors, not the helideck, in the conditions shown.",
                "recommendation": "Treat low-wind flame-out events as an operational restriction case and run CFD for the worst condition listed in the hand-off.",
            }
        elif key.startswith("vertical"):
            n = sum(1 for p in f["flight_path_peaks"] if p >= 20.0)
            d = {
                "observation": "The cloud reaches 20 % LFL on a flight path in {} of {} sections; helideck peaks are {} % LFL.".format(
                    n,
                    len(f["flight_path_peaks"]),
                    ", ".join(_fmt(p) for p in f["helideck_peaks"]),
                ),
                "mechanism": "Momentum rise lifts the plume above the deck; stable stratification caps the rise so that the cloud stays at flight altitude in light wind.",
                "implication": "Altitude, not only distance, decides exposure: the climb profile crosses the cloud in light wind.",
                "recommendation": "Verify the rise cap against a jet-in-crossflow trajectory model or CFD (vertical scale of the figure is exaggerated {:g} times).".format(
                    f["vertical_exaggeration"]
                ),
            }
        elif key.startswith("flightpath"):
            sectors = f["exposed_sectors"]
            d = {
                "observation": "Cells with 20 % LFL or more occur for {}; the helideck peak over all cells is {:.2f} % LFL.".format(
                    (
                        "wind from {}".format(", ".join(sectors))
                        if sectors
                        else "no wind direction"
                    ),
                    f["helideck_peak_all_cells"],
                ),
                "mechanism": "Only winds that blow across the obstacle-free sector place the plume on the paths, and only light stable winds keep it at flight altitude.",
                "implication": "Operational restrictions can target a small set of direction and speed combinations.",
                "recommendation": "Check the highlighted cells with CFD and against the actual approved paths.",
            }
        elif key.startswith("polar"):
            d = {
                "observation": "Number of sectors reaching 20 % LFL at some speed: {}.".format(
                    ", ".join(f"{k} {v}" for k, v in f["sectors_exposed"].items())
                ),
                "mechanism": "The path set spans the obstacle-free sector, so winds from about the opposite half carry the plume across it.",
                "implication": "Exposure is directional; a wind-direction restriction removes most of it.",
                "recommendation": "Use the direction dependence to define restriction sectors, then confirm with CFD.",
            }
        elif key.startswith("exceedance"):
            d = {
                "observation": "At {} % LFL the largest flight-path exceedance is {:.2f} % of hours ({}); into-wind path {:.2f} %, helideck {:.2f} %.".format(
                    f["thresholds"][-1],
                    f["max_any_path_pct"],
                    f["worst_case"],
                    f["max_into_wind_pct"],
                    f["max_helideck_pct"],
                ),
                "mechanism": "Exceedance is the wind-weighted share of hours with the threshold exceeded somewhere on the receptor, given that a release is ongoing.",
                "implication": "These are conditional shares of wind hours, not annual frequencies; multiply by flame-out frequency and duration for an expected exposure.",
                "recommendation": "Obtain a flame-out frequency before quoting any annual figure.",
            }
        elif key.startswith("benchmark"):
            d = {
                "observation": "Worst benchmark scenario {} gives {:.3f} % LFL at the helideck; scenario peaks: {}.".format(
                    f["worst"],
                    f["worst_pct_lfl"],
                    ", ".join(
                        f"{k}: {_fmt(v)} %" for k, v in f["peaks_pct_lfl"].items()
                    ),
                ),
                "mechanism": "The same screening model is run for the independent study's release and wind conditions.",
                "implication": "Agreement on the helideck is a classification check against the criterion, not a validation of the flight-path values.",
                "recommendation": "Keep the independent study's cases as a standing regression set and report any scenario where the model is above the reference bound.",
            }
        elif key.startswith("tornado"):
            d = {
                "observation": "Flight-path exceedance of 20 % LFL varies between {:.2f} and {:.2f} % of hours over the parameter ranges.".format(
                    f["min_hours20"], f["max_hours20"]
                ),
                "mechanism": "Each parameter changes plume rise or dilution; the axis starts at zero so effect sizes are comparable.",
                "implication": "Conclusions that survive this range are robust to these parameters, not to the missing physics (wake, jet-in-crossflow).",
                "recommendation": "Report the Monte Carlo spread with the base case and extend the ranges if the inputs are poorly known.",
            }
        elif key.startswith("tilt"):
            ex = f["cases_exceeding_at_deg"]
            d = {
                "observation": "Base tip inclination {:.1f} deg; helideck 20 % LFL exceeded for: {}.".format(
                    f["base_tilt_deg"],
                    (
                        ", ".join(
                            "{} at {:.0f} deg or less".format(*kv) for kv in ex.items()
                        )
                        if ex
                        else "no case"
                    ),
                ),
                "mechanism": "A flatter tip sends the jet horizontally, so less momentum lifts the cloud and cold dense gas stays low.",
                "implication": "The helideck result depends on the tip angle for cold dense gas and must be reported with this scan.",
                "recommendation": "Confirm the installed tip inclination and keep the 20-70 deg scan in the report.",
            }
        else:
            d = {
                "observation": rec.title,
                "mechanism": "See the method section.",
                "implication": "See the conclusions.",
                "recommendation": "Review with a qualified engineer.",
            }
        d.update({"figure": rec.name, "title": rec.title})
        out.append(d)
    return out


def build_results(
    study: StudyResult,
    figures: Sequence[Any] = (),
    sensitivity: Mapping[str, Any] | None = None,
    benchmarks: Sequence[BenchmarkScenario] | None = None,
    criteria: Sequence[Mapping[str, Any]] | None = None,
    release_frequency_per_year: float | None = None,
    hours_per_release: float | None = None,
    mode: str = "briggs",
    extra_assumptions: Sequence[str] | None = None,
    extra_data_gaps: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the ``results.json`` fragment from a study.

    Args:
        study: Study result (the 10 and 20 percent thresholds must be present).
        figures: Figure records.
        sensitivity: Sensitivity result.
        benchmarks: Benchmark scenarios against an independent study.
        criteria: Acceptance criteria with their sources (defaults to 10 and 20 percent
            LFL, both reported).
        release_frequency_per_year: Flame-out (unignited release) frequency; without it
            no annual figure is produced.
        hours_per_release: Duration of one release, hours.
        mode: Plume mode of the headline numbers.
        extra_assumptions: Additional assumptions.
        extra_data_gaps: Additional data gaps (mappings with ``gap``, ``source``,
            ``status``, ``assumed``, ``effect``).

    Returns:
        The results fragment.
    """
    _require_thresholds(study)
    criteria = list(criteria or DEFAULT_CRITERIA)
    cases = list(study.releases)
    s = study.summaries
    wind = study.wind
    key_results: dict[str, Any] = {}
    rows = []
    for c in cases:
        m = s[c]["modes"][mode]
        rel = study.releases[c]
        slug = _slug(c)
        key_results[slug + "_peak_helideck_pct_lfl"] = {
            "value": m["peak_pct_lfl_helideck"],
            "unit": "% LFL",
            "label": f"{c}: peak at the helideck",
            "decimals": 2,
            "group": c,
        }
        key_results[slug + "_peak_into_wind_path_pct_lfl"] = {
            "value": m["peak_pct_lfl_into_wind_path"],
            "unit": "% LFL",
            "label": f"{c}: peak on the into-wind path",
            "decimals": 2,
            "group": c,
        }
        key_results[slug + "_peak_any_path_pct_lfl"] = {
            "value": m["peak_pct_lfl_any_path"],
            "unit": "% LFL",
            "label": f"{c}: peak on any flight path",
            "decimals": 1,
            "group": c,
        }
        for thr in ("10", "20"):
            key_results[f"{slug}_hours_ge{thr}_any_path_pct"] = {
                "value": _exc(study, c, mode, thr, "any_path"),
                "unit": "% of wind hours, given a release",
                "label": f"{c}: hours >= {thr} % LFL on any flight path",
                "decimals": 2,
                "group": c,
                "headline": thr == "20",
            }
        rows.append(
            [
                c,
                round(rel.mdot, 1),
                round(rel.tip["v_exit_ms"], 0),
                round(rel.tip["rho_ratio_to_air"], 2),
                round(m["peak_pct_lfl_helideck"], 2),
                round(m["peak_pct_lfl_into_wind_path"], 2),
                round(m["peak_pct_lfl_any_path"], 1),
                round(_exc(study, c, mode, "20", "any_path"), 2),
                round(_exc(study, c, mode, "10", "any_path"), 2),
            ]
        )
    tables: list[dict[str, Any]] = [
        {
            "title": "Summary of release cases (conditional on an unignited release)",
            "headers": [
                "Case",
                "Rate (kg/s)",
                "Tip jet (m/s)",
                "Density / air (-)",
                "Helideck peak (% LFL)",
                "Into-wind peak (% LFL)",
                "Any-path peak (% LFL)",
                "Hours >= 20 % LFL (% of hours)",
                "Hours >= 10 % LFL (% of hours)",
            ],
            "rows": rows,
        }
    ]
    exc_rows = []
    for c in cases:
        for thr in ("10", "20"):
            exc_rows.append(
                [
                    c,
                    float(thr),
                    round(_exc(study, c, mode, thr, "helideck"), 3),
                    round(_exc(study, c, mode, thr, "into_wind_path"), 3),
                    round(_exc(study, c, mode, thr, "any_path"), 3),
                ]
            )
    tables.append(
        {
            "title": "Exceedance by criterion and receptor (percent of wind hours, given a release)",
            "headers": [
                "Case",
                "Criterion (% LFL)",
                "Helideck (% of hours)",
                "Into-wind path (% of hours)",
                "Any path (% of hours)",
            ],
            "rows": exc_rows,
        }
    )
    worst = _worst_case(study, mode)
    bin_rows = []
    for k, label in enumerate(wind.speed_bins):
        bin_rows.append(
            [
                label,
                pasquill_by_speed(
                    float(wind.speed_rep_ms[k]), study.settings.stability_scheme
                ),
                round(
                    s[worst]["modes"][mode]["exceed_any_path_by_speed_bin_pct_hours"][
                        "10"
                    ][label],
                    3,
                ),
                round(
                    s[worst]["modes"][mode]["exceed_any_path_by_speed_bin_pct_hours"][
                        "20"
                    ][label],
                    3,
                ),
            ]
        )
    tables.append(
        {
            "title": f"Flight-path exceedance by speed bin, {worst} (percent of all hours, given a release)",
            "headers": [
                "Speed bin (m/s)",
                "Pasquill class",
                ">= 10 % LFL (% of hours)",
                ">= 20 % LFL (% of hours)",
            ],
            "rows": bin_rows,
        }
    )
    tables.append(
        {
            "title": "Acceptance criteria and their sources",
            "headers": ["Criterion", "Value (% LFL)", "Source"],
            "rows": [[c["name"], c["pct_lfl"], c["source"]] for c in criteria],
        }
    )
    points = benchmark_points(study, benchmarks)
    scan = (sensitivity or {}).get("tilt_scan") or {}
    if scan:
        trows = []
        for case, rr in scan.items():
            for r in rr:
                trows.append(
                    [
                        case,
                        r["tilt_deg"],
                        round(r["helideck_peak"], 2),
                        round(r["peak_any_path"], 1),
                        round(r["hours_ge20"], 2),
                    ]
                )
        tables.append(
            {
                "title": "Tip-inclination scan",
                "headers": [
                    "Case",
                    "Tip inclination (deg)",
                    "Helideck peak (% LFL)",
                    "Any-path peak (% LFL)",
                    "Hours >= 20 % LFL (% of hours)",
                ],
                "rows": trows,
            }
        )

    deck_max = max(s[c]["modes"][mode]["peak_pct_lfl_helideck"] for c in cases)
    deck_case = max(cases, key=lambda c: s[c]["modes"][mode]["peak_pct_lfl_helideck"])
    iw_max = max(s[c]["modes"][mode]["peak_pct_lfl_into_wind_path"] for c in cases)
    ap_case = max(cases, key=lambda c: _exc(study, c, mode, "20", "any_path"))
    ap20 = _exc(study, ap_case, mode, "20", "any_path")
    ap10 = max(_exc(study, c, mode, "10", "any_path") for c in cases)
    pk = s[worst]["modes"][mode]["peak_any_path_condition"]
    active_bins = [
        b
        for b, v in s[worst]["modes"][mode]["exceed_any_path_by_speed_bin_pct_hours"][
            "10"
        ].items()
        if v > 0.0
    ]
    tilt_note = ""
    if scan:
        ex = {
            c: [r["tilt_deg"] for r in rr if r["helideck_peak"] >= 20.0]
            for c, rr in scan.items()
        }
        ex = {c: max(v) for c, v in ex.items() if v}
        tilt_note = (
            " The helideck reaches 20 % LFL at flatter tips: {} (base inclination {:.1f} deg).".format(
                ", ".join("{} at {:.0f} deg or less".format(*kv) for kv in ex.items()),
                study.settings.params.tilt_deg,
            )
            if ex
            else " The helideck stays below 20 % LFL for every tip inclination in the scan."
        )
    conclusions = (
        "Screening result, conditional on an unignited release being ongoing (no annual frequency is implied). "
        "Helideck: peak {} % LFL over all winds ({}); the into-wind path peaks at {} % LFL. "
        "Any flight-path bearing in the obstacle-free sector: 20 % LFL is exceeded in {} % of wind hours ({}) and 10 % LFL in up to {} % of wind hours; "
        "the worst condition is {} at wind from {:03.0f} deg and {:.1f} m/s ({} % LFL on the path).{} "
        "Exposure sits in the speed bins {} m/s. "
        "The result is a screening estimate without platform wake or CFD; the worst conditions are handed to CFD tools.".format(
            _fmt(deck_max),
            deck_case,
            _fmt(iw_max),
            _fmt(ap20),
            ap_case,
            _fmt(ap10),
            worst,
            pk["wind_from_deg"],
            pk["speed_m_s"],
            _fmt(s[worst]["modes"][mode]["peak_pct_lfl_any_path"]),
            tilt_note,
            ", ".join(active_bins) if active_bins else "none",
        )
    )
    conclusions = re.sub(r"\s+", " ", conclusions).strip()
    passive = {
        c: _exc(study, c, "none", "20", "any_path")
        for c in cases
        if "none" in s[c]["modes"]
    }
    flagged = [
        c
        for c in cases
        if any(
            chk["gaussian_shorter_than_free_jet"]
            for chk in s[c]["jet_consistency_20pct_lfl"]
        )
    ]
    ruled_out = []
    if deck_max < 10.0:
        ruled_out.append(
            f"Helideck exposure to 10 % LFL or more: not reached in any case and wind (peak {_fmt(deck_max)} % LFL)."
        )
    if iw_max < 10.0:
        ruled_out.append(
            f"Into-wind approach path exposure to 10 % LFL or more: not reached (peak {_fmt(iw_max)} % LFL)."
        )
    robustness: list[dict[str, Any]] = []
    if scan:
        for case, rr in scan.items():
            lo = min(rr, key=lambda r: r["tilt_deg"])
            robustness.append(
                {
                    "conclusion": f"Helideck below 20 % LFL ({case})",
                    "test": "tip inclination scan {:.0f}-{:.0f} deg".format(
                        lo["tilt_deg"], max(r["tilt_deg"] for r in rr)
                    ),
                    "result": "peak {} % LFL at the flattest tip".format(
                        _fmt(lo["helideck_peak"])
                    ),
                    "status": "robust" if lo["helideck_peak"] < 20.0 else "not robust",
                }
            )
    for case, e in (sensitivity or {}).items():
        if case != "tilt_scan" and "tornado" in e:
            lows = [t["hours20_low"] for t in e["tornado"]] + [
                t["hours20_high"] for t in e["tornado"]
            ]
            robustness.append(
                {
                    "conclusion": f"Flight-path exceedance of 20 % LFL ({case})",
                    "test": "one-at-a-time parameter ranges",
                    "result": "{:.2f} to {:.2f} % of hours (base {:.2f} %)".format(
                        min(lows), max(lows), e["base"]["hours_ge20_pct"]
                    ),
                    "status": (
                        "robust" if min(lows) > 0.0 or max(lows) == 0.0 else "sensitive"
                    ),
                }
            )
    conservatism = [
        (
            f"Stable-biased Pasquill assignment ({study.settings.stability_scheme}): F below 2 m/s, E below 4 m/s keeps a lifted plume near release height."
            if isinstance(study.settings.stability_scheme, str)
            else "User-defined stability scheme."
        ),
        "Only the vertical momentum component of the inclined tip lifts the plume; the horizontal component is ignored.",
        (
            "Passive-release bound (no rise): {} % of hours at 20 % LFL on a flight path.".format(
                ", ".join(f"{c} {_fmt(v)}" for c, v in passive.items())
            )
            if passive
            else "Passive-release bound not run."
        ),
        "Release rate is the rated or peak flow, held constant; depressurisation decay is not credited.",
    ]
    evidence_against = [
        "No platform wake, downwash or mechanical turbulence is modelled; a lifted cloud could be pulled down in the lee of the structure.",
        "A Gaussian plume is not valid much below 1 m/s and meander is ignored; the lowest bin is represented by one speed.",
        "In {} of {} cases the Gaussian distance to 20 % LFL is shorter than the free-jet distance at some low speed (virtual-source over-dilution of a momentum jet): {}.".format(
            len(flagged), len(cases), ", ".join(flagged) if flagged else "none"
        ),
    ]
    discriminating_test = (
        "Run a CFD simulation with the platform geometry for {} at wind from {:03.0f} deg and {:.1f} m/s (the worst flight-path condition) and compare the 20 % LFL envelope along the flight paths with this screening result; "
        "a second run at the flattened tip inclination discriminates the tip-angle sensitivity.".format(
            worst, pk["wind_from_deg"], pk["speed_m_s"]
        )
    )
    handoff = []
    for c in sorted(cases, key=lambda c: -s[c]["modes"][mode]["peak_pct_lfl_any_path"])[
        :3
    ]:
        cond = s[c]["modes"][mode]["peak_any_path_condition"]
        rel = study.releases[c]
        handoff.append(
            {
                "case": c,
                "mass_flow_kg_s": rel.mdot,
                "tip_exit": {
                    k: rel.tip[k]
                    for k in ("v_exit_ms", "d_eff_m", "rho_exp", "t_exp_k", "choked")
                },
                "tip_inclination_deg": study.settings.params.tilt_deg,
                "wind_from_deg": cond["wind_from_deg"],
                "wind_speed_ms": cond["speed_m_s"],
                "peak_pct_lfl_any_path": s[c]["modes"][mode]["peak_pct_lfl_any_path"],
                "path_bearing_deg": cond["path_bearing_deg"],
                "path_distance_m": cond["path_distance_m"],
            }
        )
    assumptions = [
        "Exceedance values are percent of wind hours given an unignited release of the stated rate; they are conditional, not annual frequencies.",
        f"Flight paths are radial paths across the obstacle-free sector every {study.geometry.flight_paths.bearing_step_deg:.0f} deg with a {study.geometry.flight_paths.climb_deg:.0f} deg climb or descent gradient to {study.geometry.flight_paths.length_m:.0f} m; they are assumptions unless the approved paths were supplied.",
        "The wind table is representative ({}); speed bins use representative speeds {} m/s.".format(
            wind.metadata.get("source", "supplied"),
            ", ".join(f"{v:g}" for v in wind.speed_rep_ms),
        ),
        "Pasquill class by speed: %s."
        % (
            study.settings.stability_scheme
            if isinstance(study.settings.stability_scheme, str)
            else "user defined"
        ),
        f"Plume model: choked tip with Birch notional nozzle, Briggs momentum rise with stable-air caps, Gaussian plume with sea reflection and sigma0 = dh / {study.settings.params.sigma0_divisor:g}; tip inclination {study.settings.params.tilt_deg:.1f} deg.",
    ] + list(extra_assumptions or [])
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
            "gap": "Approved approach and departure paths",
            "source": "helideck operations manual",
            "status": "open",
            "assumed": "radial paths across the obstacle-free sector",
            "effect": "exceedance hours depend on which paths are flown",
        },
        {
            "gap": "Platform wake and CFD validation",
            "source": "CFD study",
            "status": "open",
            "assumed": "none; open-terrain Gaussian plume",
            "effect": "non-conservative if the cloud is pulled down in the lee of the structure",
        },
        {
            "gap": "Governing acceptance criterion and its source",
            "source": "project design basis",
            "status": "open",
            "assumed": "10 % and 20 % LFL both reported",
            "effect": "pass or fail depends on the governing value",
        },
    ] + list(extra_data_gaps or [])
    unc: dict[str, Any] = {}
    if sensitivity:
        ucases = [
            c for c in sensitivity if c != "tilt_scan" and "tornado" in sensitivity[c]
        ]
        if ucases:
            uc = max(ucases, key=lambda c: sensitivity[c]["base"]["hours_ge20_pct"])
            e = sensitivity[uc]
            mc = (
                e.get("hours_ge20_pct")
                if isinstance(e.get("hours_ge20_pct"), dict)
                else {}
            )
            unc = {
                "method": "one-at-a-time ranges and uniform Monte Carlo of plume-model parameters (seeded)",
                "case": uc,
                "n_simulations": e.get("monte_carlo_n", 0),
                "seed": e.get("seed"),
                "simulation_engine": "flare_helideck_dispersion screening model",
                "input_parameters": [
                    {
                        "name": t["parameter"],
                        "unit": "-",
                        "low": t["low_input"],
                        "base": None,
                        "high": t["high_input"],
                        "distribution": "uniform",
                    }
                    for t in e["tornado"]
                ],
                "output_parameter": "% of wind hours with >= 20 % LFL on a flight path (conditional on a release)",
                "base": e["base"]["hours_ge20_pct"],
                "p10": mc.get("p10"),
                "p50": mc.get("p50"),
                "p90": mc.get("p90"),
                "tornado": [
                    {
                        "parameter": t["parameter"],
                        "low": t["hours20_low"],
                        "high": t["hours20_high"],
                        "swing": t["swing_hours20"],
                    }
                    for t in e["tornado"]
                ],
                "per_case": {c: sensitivity[c] for c in ucases},
            }
    risk_ap = "Medium" if ap20 > 0.0 else "Low"
    risk_deck = (
        "High" if deck_max >= 20.0 else ("Medium" if deck_max >= 10.0 else "Low")
    )
    risks = [
        {
            "id": "R1",
            "description": "Flight-path exposure to unignited flare gas during a low-wind flame-out",
            "category": "HSE",
            "likelihood": (
                "Not quantified (conditional on release; no flame-out frequency)"
                if release_frequency_per_year is None
                else "Quantified with the supplied flame-out frequency"
            ),
            "consequence": "Major",
            "risk_level": risk_ap,
            "mitigation": "Operational restriction on helicopter movements during flaring upsets; CFD of the worst conditions",
        },
        {
            "id": "R2",
            "description": "Helideck exposure to unignited flare gas",
            "category": "HSE",
            "likelihood": "Not quantified",
            "consequence": "Major",
            "risk_level": risk_deck,
            "mitigation": "Confirm tip inclination and elevation; keep the tilt scan in the report",
        },
        {
            "id": "R3",
            "description": "Screening model under-predicts exposure (no wake, jet over-dilution, low-wind validity)",
            "category": "Model",
            "likelihood": "Possible",
            "consequence": "Moderate",
            "risk_level": "Medium",
            "mitigation": "CFD hand-off for the worst conditions and measured low-wind statistics",
        },
    ]
    levels = {"Low": 0, "Medium": 1, "High": 2}
    risk_eval = {
        "risks": risks,
        "overall_risk_level": max(
            (r["risk_level"] for r in risks), key=lambda v: levels[v]
        ),
        "risk_matrix_used": "screening judgement from computed exceedance (not a calibrated matrix; no release frequency)",
    }
    captions = {r.name: f"{r.title}. {r.sub}." for r in figures}
    result: dict[str, Any] = {
        "key_results": key_results,
        "approach": "Choked tip and Birch notional nozzle, Briggs momentum rise with stable-air limits, Gaussian plume with sea reflection; wind-weighted sweep over direction and speed with helideck points and radial flight paths (conditional on an unignited release).",
        "conclusions": conclusions,
        "validation": {
            "benchmark_points_passed": sum(1 for p in points if p["status"] == "PASS"),
            "benchmark_points_failed": sum(1 for p in points if p["status"] == "FAIL"),
            "acceptance_criteria_met": None,
        },
        "acceptance_criteria": list(criteria),
        "semantics": study.semantics,
        "figure_captions": captions,
        "figure_discussion": figure_discussion(figures, study, mode) if figures else [],
        "equations": EQUATIONS,
        "tables": tables,
        "references": REFERENCES,
        "assumptions": assumptions,
        "data_gaps": data_gaps,
        "uncertainty": unc,
        "risk_evaluation": risk_eval,
        "contributor_ranking": _speed_bin_ranking(study, worst, mode),
        "ruled_out": ruled_out,
        "robustness": robustness,
        "conservatism": conservatism,
        "discriminating_test": discriminating_test,
        "evidence_against": evidence_against,
        "benchmark_validation": {"points": points},
        "cfd_handoff": handoff,
        "warnings": list(study.warnings),
    }
    if release_frequency_per_year is not None and hours_per_release is not None:
        result["annualised_exposure"] = {
            c: annualise_exposure(
                _exc(study, c, mode, "20", "any_path"),
                release_frequency_per_year,
                hours_per_release,
            )
            for c in cases
        }
    if not unc:
        result.pop("uncertainty")
    return result


def validate_fragment(fragment: Mapping[str, Any]) -> list[str]:
    """Check a results fragment against the layout rules of the task ``results.json``.

    Args:
        fragment: Results fragment.

    Returns:
        Problems found; an empty list means the fragment is well formed.
    """
    problems: list[str] = []
    if not isinstance(fragment.get("conclusions"), str):
        problems.append("conclusions must be a string")
    bench = fragment.get("benchmark_validation")
    if not isinstance(bench, dict) or not isinstance(bench.get("points"), list):
        problems.append("benchmark_validation must be {points: [...]}")
    else:
        for i, p in enumerate(bench["points"]):
            for key in ("name", "reference_value", "neqsim_value", "status"):
                if key not in p:
                    problems.append(f"benchmark_validation.points[{i}] lacks {key}")
    for key in ("assumptions", "data_gaps", "key_results", "tables"):
        if not fragment.get(key):
            problems.append(f"{key} is empty")
    for i, item in enumerate(fragment.get("figure_discussion", [])):
        for need in (
            "figure",
            "observation",
            "mechanism",
            "implication",
            "recommendation",
        ):
            if need not in item:
                problems.append(f"figure_discussion[{i}] lacks {need}")
    depth = [
        k
        for k in (
            "contributor_ranking",
            "ruled_out",
            "robustness",
            "conservatism",
            "discriminating_test",
            "evidence_against",
        )
        if fragment.get(k)
    ]
    if len(depth) < 2:
        problems.append("fewer than two analytical-depth keys populated")
    for i, t in enumerate(fragment.get("tables", [])):
        if len(t.get("headers", [])) > 9:
            problems.append(f"tables[{i}] has more than 9 columns")
        for row in t.get("rows", []):
            for cell in row:
                if isinstance(cell, str) and re.match(
                    r"^\s*[-+]?\d+(\.\d+)?\s*(/|;|\|)\s*[-+]?\d", cell
                ):
                    problems.append(f"tables[{i}] has several numbers in one cell")
    return problems


def write_results_json(
    path: str | Path, fragment: Mapping[str, Any], merge: bool = True
) -> Path:
    """Write the fragment, merging into an existing ``results.json`` when requested.

    Dictionaries are updated key by key, lists are extended with items that are not yet
    present, and other values are replaced. ``conclusions`` is always replaced.

    Args:
        path: Target file.
        fragment: Results fragment.
        merge: Merge into an existing file instead of overwriting it.

    Returns:
        The written path.
    """
    p = Path(path)
    data: dict[str, Any] = {}
    if merge and p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
    for key, value in fragment.items():
        if key == "conclusions" or key not in data:
            data[key] = value
        elif isinstance(value, dict) and isinstance(data[key], dict):
            data[key].update(value)
        elif isinstance(value, list) and isinstance(data[key], list):
            data[key] = data[key] + [v for v in value if v not in data[key]]
        else:
            data[key] = value
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=float), encoding="utf-8")
    return p
