"""Best estimate of mercury in the gas of a prospect or discovery.

Combines four lines of evidence into one result with an explicit uncertainty:

1. a statistical model calibrated on tested wells (reservoir age class, structural province, temperature),
2. the analogue tests nearest to the prospect in the same reservoir age class,
3. measurements in the discovery itself, when they exist (the highest gas reading is trusted),
4. the mineral-equilibrium limits from NeqSim (trace-sulfide worst case and liquid mercury).

The result is an order-of-magnitude statement. Nothing here replaces a gas sample from the reservoir.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .formatting import fmt
from .model import Z90, ShrinkageModel, lognormal_quantiles
from .stratigraphy import classify_formation, source_class_of_epoch

SCHEMA = "mercury_prospect_estimate.v1"

#: Smallest log10 standard deviation used for a measured value (a factor 2).
MIN_MEASURED_SD_LOG10 = 0.3


def _missing(value: Any) -> bool:
    """Return True for None, NaN and empty strings."""
    return (
        value is None
        or (isinstance(value, float) and math.isnan(value))
        or (isinstance(value, str) and not value.strip())
    )


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points.

    Args:
        lat1: Latitude of the first point [degrees north].
        lon1: Longitude of the first point [degrees east].
        lat2: Latitude of the second point [degrees north].
        lon2: Longitude of the second point [degrees east].

    Returns:
        Distance [km].
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def nice_range(low: float, high: float) -> tuple[float, float]:
    """Round a range outwards to one significant figure from the series 1, 2, 3, 5.

    Args:
        low: Lower value (positive).
        high: Upper value (positive).

    Returns:
        ``(low rounded down, high rounded up)``.
    """

    def snap(value: float, up: bool) -> float:
        exp = math.floor(math.log10(value))
        mant = value / 10**exp
        steps = [1.0, 2.0, 3.0, 5.0, 10.0]
        pick = (
            next(s for s in steps if s >= mant - 1e-9)
            if up
            else [s for s in steps if s <= mant + 1e-9][-1]
        )
        return pick * 10**exp

    return snap(low, False), snap(high, True)


def nice_value(value: float) -> float:
    """Round a positive value to the nearest of 1, 2, 3, 5 times a power of ten (nearest on a log scale).

    Args:
        value: Positive value.

    Returns:
        The rounded value.
    """
    exp = math.floor(math.log10(value))
    mant = value / 10**exp
    pick = min(
        (1.0, 2.0, 3.0, 5.0, 10.0),
        key=lambda step: abs(math.log10(step) - math.log10(mant)),
    )
    return pick * 10**exp


def exceedance(log10_mean: float, log10_sd: float, threshold: float) -> float:
    """Probability that a lognormal quantity exceeds a threshold.

    Args:
        log10_mean: Mean of log10(value).
        log10_sd: Standard deviation of log10(value).
        threshold: Threshold in the unit of the value.

    Returns:
        Probability between 0 and 1.
    """
    if log10_sd <= 0.0:
        return 1.0 if log10_mean > math.log10(threshold) else 0.0
    z = (math.log10(threshold) - log10_mean) / log10_sd
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def find_analogues(
    prospect: Mapping[str, Any],
    tests: Iterable[Mapping[str, Any]],
    count: int = 12,
    max_km: float = 400.0,
) -> list[dict[str, Any]]:
    """Rank tested intervals as analogues: same formation, then same group, then same age class, then distance.

    Args:
        prospect: Prospect with ``lat``, ``lon`` and the stratigraphy filled by :func:`estimate_prospect`.
        tests: Tested intervals with ``lat``, ``lon``, ``formation``, ``group``, ``source_class``, ``hg``.
        count: Number of analogues returned.
        max_km: Tests farther away are used only when fewer than ``count`` are found inside.

    Returns:
        Analogue records with distance, match level and mercury value, best match first.
    """
    out = []
    have_pos = not _missing(prospect.get("lat")) and not _missing(prospect.get("lon"))
    for t in tests:
        if _missing(t.get("hg")):
            continue
        level, label = 0, "other reservoir age"
        if not _missing(prospect.get("source_class")) and t.get(
            "source_class"
        ) == prospect.get("source_class"):
            level, label = 1, "same reservoir age class"
        if not _missing(prospect.get("group")) and t.get("group") == prospect.get(
            "group"
        ):
            level, label = 2, "same group"
        fm_p, fm_t = (
            classify_formation(prospect.get("formation"))["formation_key"],
            classify_formation(t.get("formation"))["formation_key"],
        )
        if fm_p and fm_p == fm_t:
            level, label = 3, "same formation"
        km = None
        if have_pos and not _missing(t.get("lat")) and not _missing(t.get("lon")):
            km = distance_km(
                float(prospect["lat"]),
                float(prospect["lon"]),
                float(t["lat"]),
                float(t["lon"]),
            )
        out.append(
            {
                "well": t.get("wellbore") or t.get("well"),
                "field": None if _missing(t.get("field")) else t.get("field"),
                "formation": (
                    None if _missing(t.get("formation")) else t.get("formation")
                ),
                "group": None if _missing(t.get("group")) else t.get("group"),
                "match": label,
                "match_level": level,
                "distance_km": km,
                "mercury": float(t["hg"]),
                "reservoir_T_C": (
                    None if _missing(t.get("res_T_C")) else float(t["res_T_C"])
                ),
                "production_gas": (
                    bool(t.get("operation"))
                    if not _missing(t.get("operation"))
                    else False
                ),
            }
        )
    near = [
        a
        for a in out
        if a["match_level"] >= 1
        and (a["distance_km"] is None or a["distance_km"] <= max_km)
    ]
    pool = (
        near
        if len(near) >= min(count, 4)
        else [a for a in out if a["match_level"] >= 1] or out
    )
    pool.sort(
        key=lambda a: (
            -min(a["match_level"], 2),
            a["distance_km"] if a["distance_km"] is not None else 1e9,
        )
    )
    return pool[:count]


def estimate_prospect(
    prospect: Mapping[str, Any],
    registry: Mapping[str, Any],
    tests: Sequence[Mapping[str, Any]] | None = None,
    limits: Mapping[str, Any] | None = None,
    measurements: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Estimate mercury in the gas of a prospect or discovery with an explicit uncertainty.

    Args:
        prospect: ``name`` and what is known of ``lat``, ``lon``, ``formation``, ``epoch``, ``source_class``,
            ``province``, ``res_T_C``, ``res_P_bara``, ``fluid_type``, ``co2_molpct``.
        registry: Calibration registry (``model``, ``cv_sd_log10``, ``discovery_level``, ``within_well_sd_log10``,
            ``distribution``, ``trace_limit_exceedance``).
        tests: Tested intervals of the calibration set, for analogues and the province of the nearest test.
        limits: Output of :func:`reservoir_mercury.limits.mercury_limits`, or ``None`` when not calculated.
        measurements: Mercury readings in gas from the discovery itself [microgram per Sm3], if any.

    Returns:
        Result record (schema ``mercury_prospect_estimate.v1``) with the best estimate, P10/P50/P90, exceedance
        probabilities, recommended range for design, analogues, limits, reasoning, accuracy statements and data gaps.
    """
    p = dict(prospect)
    gaps: list[str] = []
    reasoning: list[str] = []
    # ---- stratigraphy
    cls = classify_formation(p.get("formation"))
    if _missing(p.get("epoch")) and cls["epoch"]:
        p["epoch"] = cls["epoch"]
    if _missing(p.get("group")) and cls["group"]:
        p["group"] = cls["group"]
    if _missing(p.get("source_class")):
        p["source_class"] = source_class_of_epoch(p.get("epoch")) or cls["source_class"]
    if _missing(p.get("source_class")):
        gaps.append(
            "Reservoir age (formation or epoch) not given or not recognised: the estimate uses no "
            "stratigraphic information"
        )
    # ---- province from the nearest tested well
    tests = list(tests or [])
    if (
        _missing(p.get("province"))
        and tests
        and not _missing(p.get("lat"))
        and not _missing(p.get("lon"))
    ):
        best = None
        for t in tests:
            if (
                _missing(t.get("province"))
                or _missing(t.get("lat"))
                or _missing(t.get("lon"))
            ):
                continue
            km = distance_km(
                float(p["lat"]), float(p["lon"]), float(t["lat"]), float(t["lon"])
            )
            if best is None or km < best[0]:
                best = (km, t["province"])
        if best and best[0] <= 60.0:
            p["province"] = best[1]
            p["province_source"] = (
                f"province of the nearest tested well ({best[0]:.0f} km)"
            )
    if _missing(p.get("res_T_C")):
        gaps.append(
            "Reservoir temperature not given: the estimate uses the average temperature of the tested wells"
        )

    # ---- statistical model
    model = ShrinkageModel.from_dict(registry["model"])
    pred = model.predict(p)
    sd_test = float(registry["cv_sd_log10"])
    disc = registry["discovery_level"]
    mu_disc = pred["log10"] + float(disc["offset_log10_over_test_prediction"])
    sd_disc = float(disc["sd_log10_about_prediction"])
    q_test = lognormal_quantiles(pred["log10"], sd_test)
    q_disc = lognormal_quantiles(mu_disc, sd_disc)
    for name in pred["unseen"]:
        gaps.append(
            f"No tested well with {name} in the calibration set: that predictor is not used"
        )
    ncs = registry["distribution"]
    reasoning.append(
        "Tests on the shelf span {} to {} µg/Sm³ (P10 to P90) with a median of {} µg/Sm³; the "
        "starting point for any reservoir is this distribution.".format(
            fmt(ncs["p10"]), fmt(ncs["p90"]), fmt(ncs["p50"])
        )
    )
    contrib = pred["contributions"]
    if not _missing(p.get("source_class")):
        reasoning.append(
            "Reservoir age class '{}' moves the estimate by a factor {:.1f}.".format(
                p["source_class"], 10 ** contrib.get("source_class", 0.0)
            )
        )
    if (
        not _missing(p.get("province"))
        and "province" in contrib
        and not any("province" in u for u in pred["unseen"])
    ):
        reasoning.append(
            "Structural province '{}' moves it by a factor {:.1f}.".format(
                p["province"], 10 ** contrib["province"]
            )
        )
    if not _missing(p.get("res_T_C")) and "res_T_C" in contrib:
        reasoning.append(
            "Reservoir temperature {:.0f} °C moves it by a factor {:.1f} (higher temperature, more "
            "mercury on average).".format(float(p["res_T_C"]), 10 ** contrib["res_T_C"])
        )

    # ---- analogues
    analogues = find_analogues(p, tests) if tests else []
    strong = [
        a
        for a in analogues
        if a["match_level"] >= 1 and (a["distance_km"] or 1e9) <= 100.0
    ]
    analogue_summary = None
    if strong:
        vals = [a["mercury"] for a in strong]
        analogue_summary = {
            "count": len(vals),
            "highest": max(vals),
            "lowest": min(vals),
            "geometric_mean": 10 ** (sum(math.log10(v) for v in vals) / len(vals)),
            "basis": "tests of the same reservoir age class within 100 km",
        }
        reasoning.append(
            f"{len(vals)} tested intervals of the same reservoir age class lie within 100 km: "
            f"{fmt(min(vals))} to {fmt(max(vals))} µg/Sm³. "
            "Neighbouring wells differ by a factor of about ten on average, so they indicate the level, not "
            "the value."
        )
    elif tests:
        gaps.append("No tested interval of the same reservoir age class within 100 km")

    # ---- measurements in the discovery
    measured = [
        float(v) for v in (measurements or []) if v is not None and float(v) > 0.0
    ]
    basis = "statistical model and analogues (no measurement in this reservoir)"
    if measured:
        best = max(measured)
        # scatter between tests of one well, never taken below a factor 2 (one standard deviation)
        sd_own = max(
            float(registry.get("within_well_sd_log10", 0.55)), MIN_MEASURED_SD_LOG10
        )
        q_best = lognormal_quantiles(math.log10(best), sd_own)
        low, high = nice_range(best / 3.0, best / 3.0)[0], nice_value(best * 3.0)
        best_estimate, mu_use, sd_use = best, math.log10(best), sd_own
        basis = "highest gas reading measured in this discovery"
        reasoning.append(
            f"The discovery has {len(measured)} gas reading(s); the highest, {fmt(best)} µg/Sm³, is the best "
            "estimate. Gas readings can be too low (adsorption, short flow period, chemicals) but are unlikely "
            "to be too high."
        )
        if best < q_disc["p10"]:
            reasoning.append(
                "The reading lies below the P10 of the statistical estimate ({} µg/Sm³): check "
                "flow duration, sampling point and hydrate-inhibitor use before relying on it.".format(
                    fmt(q_disc["p10"])
                )
            )
    else:
        q_best = q_disc
        best_estimate, mu_use, sd_use = q_disc["p50"], mu_disc, sd_disc
        # from the median (rounded down) to the P90 (rounded to the nearest step: its own error is larger)
        low, high = nice_range(q_disc["p50"], q_disc["p50"])[0], nice_value(
            q_disc["p90"]
        )
        reasoning.append(
            "Production gas has followed the highest reading of a discovery, not the typical test. The estimate "
            "is therefore stated for the highest reading expected in the discovery, a factor %.1f above the "
            "typical test." % (10 ** float(disc["offset_log10_over_test_prediction"]))
        )

    # ---- mineral limits
    lim = dict(limits) if limits else None
    if lim:
        reasoning.append(
            "Mineral equilibrium (NeqSim) gives upper limits: {} µg/Sm³ for mercury held as a trace in sulfide "
            "(a(HgS) = {:g}) and {} µg/Sm³ for liquid mercury. {:.0f} % of the tests exceed the trace-sulfide "
            "limit, so it is a practical worst case and not a hard cap.".format(
                fmt(lim["trace_sulfide_limit"]),
                lim.get("trace_activity", 0.003),
                fmt(lim["liquid_limit"]),
                100 * float(registry.get("trace_limit_exceedance", 0.07)),
            )
        )
        if measured and max(measured) > lim["trace_sulfide_limit"]:
            reasoning.append(
                "The highest reading is above the trace-sulfide limit. Such readings occur and are among the "
                "highest on the shelf; the reading stands, and the limit is not used to reduce it."
            )
        if high > lim["liquid_limit"]:
            high = nice_range(low, lim["liquid_limit"])[1]
    else:
        gaps.append(
            "Mineral-equilibrium limits not calculated (reservoir temperature and pressure needed)"
        )

    factor = 10 ** (Z90 * sd_use)
    scores = registry["cross_validation"]
    within_model = scores[registry["model_name"]]["well_out"]["within_factor_10"]
    within_base = next(v for k, v in scores.items() if k.startswith("M0"))["well_out"][
        "within_factor_10"
    ]
    accuracy = [
        f"The P10 to P90 range spans a factor {factor**2:.0f} (a factor {factor:.0f} either side of the median).",
        (
            f"Calibration: {registry['n_tests']} tests in {registry['n_wells']} wells. With a well left out, "
            f"{100 * within_model:.0f} % of the tests are predicted within a factor 10 "
            f"({100 * within_base:.0f} % without any predictor)."
        ),
        "Tests in one well differ by a factor {:.1f} (one standard deviation); wells in one field by a factor {:.0f}.".format(
            10 ** float(registry["within_well_sd_log10"]),
            10 ** float(registry["within_field_sd_log10"]),
        ),
    ]
    cover = registry.get("interval_coverage")
    if cover and not measured:
        accuracy.append(
            "Check of the stated range: with a well left out, {:.0f} % of the tests fell inside the P10 to P90 "
            "range of the model, {:.0f} % above and {:.0f} % below (80, 10 and 10 expected). For the highest "
            "reading per discovery the figures are {:.0f}, {:.0f} and {:.0f} %.".format(
                100 * cover["test_inside_p10_p90"],
                100 * cover["test_above_p90"],
                100 * cover["test_below_p10"],
                100 * cover["discovery_inside_p10_p90"],
                100 * cover["discovery_above_p90"],
                100 * cover["discovery_below_p10"],
            )
        )
    if not measured:
        accuracy.append(
            "Only a gas sample from this reservoir, taken late in a flow period and analysed at the rig, "
            "narrows the range to about a factor 3 to 5."
        )
    return {
        "schema": SCHEMA,
        "prospect": p,
        "unit": "microgram per Sm3 of separator or test gas",
        "basis": basis,
        "best_estimate": best_estimate,
        "p10": q_best["p10"],
        "p50": q_best["p50"],
        "p90": q_best["p90"],
        "recommended_range": {"low": low, "high": high},
        "probability_above": {
            str(x): exceedance(mu_use, sd_use, x) for x in (1, 10, 100, 1000)
        },
        "statistical": {
            "typical_test": q_test,
            "highest_reading_in_discovery": q_disc,
            "log10_sd_test": sd_test,
            "log10_sd_discovery": sd_disc,
            "contributions_log10": contrib,
            "model": registry.get("model_name"),
            "unseen": pred["unseen"],
        },
        "measurements": {
            "gas_readings": measured,
            "highest": max(measured) if measured else None,
        },
        "analogues": analogues,
        "analogue_summary": analogue_summary,
        "limits": lim,
        "reasoning": reasoning,
        "accuracy": accuracy,
        "data_gaps": gaps,
        "calibration": {
            "name": registry.get("name"),
            "created": registry.get("created"),
            "tests": registry["n_tests"],
            "wells": registry["n_wells"],
        },
    }
