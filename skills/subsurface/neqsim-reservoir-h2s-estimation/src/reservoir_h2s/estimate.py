"""Best estimate of H2S in the gas of a prospect or discovery, with an explicit uncertainty.

Three lines of evidence are combined:

1. the mineral buffer from NeqSim at the reservoir temperature, pressure and CO2 content (pyrite and Fe-carbonate),
   flashed to test-separator gas;
2. the calibration of that buffer against measured wells: offset and scatter per depositional setting;
3. H2S readings from the discovery itself, when they exist.

The range of the estimate adds the scatter of measured wells about the buffer to the effect of what is not yet known
about the prospect (temperature, CO2, pressure). The estimate is for the virgin reservoir: souring by injected
seawater is a separate effect and is not included.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .buffer import MG_PER_NM3_PER_PPM, SOUR_SERVICE_KPA, buffered_h2s, haaland_ppm
from .formatting import fmt
from .model import Z90, class_of, lognormal_quantiles, not_detected
from .setting import CARBONATE, CONTINENTAL, UNKNOWN, classify_setting, formation_key

SCHEMA = "h2s_prospect_estimate.v1"

#: One standard deviation of the reservoir temperature of a prospect that has not been drilled [C].
PROSPECT_T_SD_C = 10.0
#: One standard deviation of a measured reservoir temperature [C].
MEASURED_T_SD_C = 3.0
#: Scatter of a CO2 content taken from analogues [log10] (a factor 1.4).
GIVEN_CO2_SD_LOG10 = 0.15
#: Scatter of a measured CO2 content [log10].
MEASURED_CO2_SD_LOG10 = 0.04
#: Scatter of the reservoir pressure of a prospect [log10] (about 12 %).
PROSPECT_P_SD_LOG10 = 0.05
#: Smallest scatter used for a measured H2S value [log10] (a factor 1.4).
MIN_MEASURED_SD_LOG10 = 0.15
#: Default H2S limit of sales gas [mg/Nm3], a common limit of European gas transport systems.
GAS_SPEC_MG_NM3 = 5.0

Buffer = Callable[..., Mapping[str, Any]]


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


def nice_value(value: float, direction: int = 0) -> float:
    """Round a positive value to a step of the series 1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8 times a power of ten.

    Args:
        value: Positive value.
        direction: ``-1`` rounds down, ``1`` rounds up, ``0`` takes the nearest step on a log scale.

    Returns:
        The rounded value.
    """
    exp = math.floor(math.log10(value))
    mant = value / 10**exp
    steps = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
    if direction < 0:
        pick = [s for s in steps if s <= mant + 1e-9][-1]
    elif direction > 0:
        pick = next(s for s in steps if s >= mant - 1e-9)
    else:
        pick = min(steps, key=lambda s: abs(math.log10(s) - math.log10(mant)))
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


def ordinal(value: float) -> str:
    """Return a whole number with its ordinal ending: 1st, 2nd, 3rd, 63rd, 11th.

    Args:
        value: Number; rounded to the nearest whole number.

    Returns:
        Text such as ``"63rd"``.
    """
    n = round(value)
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _median(values: Sequence[float]) -> float:
    """Median of a non-empty list."""
    v = sorted(values)
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else 0.5 * (v[mid - 1] + v[mid])


def find_analogues(
    prospect: Mapping[str, Any],
    wells: Iterable[Mapping[str, Any]],
    count: int = 10,
) -> list[dict[str, Any]]:
    """Rank measured wells as analogues: wells of the same setting first, then by distance, then by temperature.

    Args:
        prospect: Prospect with ``lat``, ``lon``, ``formation``, ``setting`` and ``res_T_C``.
        wells: Calibration wells with ``measured_ppm``, ``model_ppm``, ``lat``, ``lon``, ``formation``, ``setting``.
        count: Number of analogues returned.

    Returns:
        Analogue records with distance, match (same formation or same setting), measured H2S, buffer value and
        their ratio, nearest first.
    """
    have_pos = not _missing(prospect.get("lat")) and not _missing(prospect.get("lon"))
    fm_p = formation_key(prospect.get("formation"))
    out = []
    for w in wells:
        if _missing(w.get("measured_ppm")) or not_detected(w):
            continue
        setting = classify_setting(w.get("formation"), w.get("setting"))
        level, label = 0, "other setting"
        if setting == prospect.get("setting") and setting != UNKNOWN:
            level, label = 1, "same setting"
        if fm_p and fm_p == formation_key(w.get("formation")):
            level, label = 2, "same formation"
        km = None
        if have_pos and not _missing(w.get("lat")) and not _missing(w.get("lon")):
            km = distance_km(
                float(prospect["lat"]),
                float(prospect["lon"]),
                float(w["lat"]),
                float(w["lon"]),
            )
        dt = (
            abs(float(w["res_T_C"]) - float(prospect["res_T_C"]))
            if not _missing(w.get("res_T_C")) and not _missing(prospect.get("res_T_C"))
            else None
        )
        model = None if _missing(w.get("model_ppm")) else float(w["model_ppm"])
        out.append(
            {
                "well": w.get("wellbore") or w.get("well"),
                "field": None if _missing(w.get("field")) else w.get("field"),
                "formation": (
                    None
                    if _missing(w.get("formation"))
                    else str(w["formation"]).split(";")[0].strip()
                ),
                "setting": setting,
                "match": label,
                "match_level": level,
                "distance_km": km,
                "reservoir_T_C": (
                    None if _missing(w.get("res_T_C")) else float(w["res_T_C"])
                ),
                "co2_molpct": (
                    None if _missing(w.get("co2_molpct")) else float(w["co2_molpct"])
                ),
                "measured_ppm": float(w["measured_ppm"]),
                "buffer_ppm": model,
                "ratio": float(w["measured_ppm"]) / model if model else None,
                "_dt": dt,
            }
        )
    # nearest first when the position is known, else closest in temperature
    out.sort(
        key=lambda a: (
            -min(a["match_level"], 1),
            a["distance_km"] if a["distance_km"] is not None else 1e9,
            a["_dt"] if a["_dt"] is not None else 1e9,
        )
    )
    for a in out:
        a.pop("_dt")
    return out[:count]


def estimate_prospect(
    prospect: Mapping[str, Any],
    registry: Mapping[str, Any],
    wells: Sequence[Mapping[str, Any]] | None = None,
    buffer: Buffer | None = None,
    measurements: Sequence[float] | None = None,
    thresholds: Sequence[float] = (1.0, 3.0, 10.0, 30.0),
    gas_spec_mg_nm3: float = GAS_SPEC_MG_NM3,
    curve: bool = True,
) -> dict[str, Any]:
    """Estimate H2S in the test gas of a prospect or discovery with an explicit uncertainty.

    Args:
        prospect: ``name`` and what is known of ``res_T_C`` (needed), ``res_P_bara``, ``co2_molpct``, ``formation``,
            ``setting``, ``fluid_type``, ``lat``, ``lon``. The scatter of the inputs can be given as ``res_T_sd_C``,
            ``co2_sd_log10`` and ``res_P_sd_log10``; ``measured_conditions`` set to True marks temperature, pressure
            and CO2 as measured in a well. ``sulfate_minerals`` set to True marks anhydrite in the reservoir.
        registry: Calibration registry of :func:`reservoir_h2s.model.calibrate`.
        wells: Calibration wells, for the analogue table and the figures.
        buffer: Function ``(temperature_c, pressure_bara, co2_molpct, fluid_type)`` returning the record of
            :func:`reservoir_h2s.buffer.buffered_h2s`; default calls NeqSim.
        measurements: H2S readings in test gas from the discovery itself [ppm], if any.
        thresholds: H2S levels [ppm] for which the probability of exceedance is reported.
        gas_spec_mg_nm3: H2S limit of the sales gas [mg/Nm3] for the screening against a gas specification.
        curve: Calculate the buffer over temperature for the figure (eight more buffer calls).

    Returns:
        Result record (schema ``h2s_prospect_estimate.v1``) with the best estimate, P10/P50/P90, exceedance
        probabilities, the range for design, the sour-service and gas-specification screening, the uncertainty
        budget, analogues, reasoning, accuracy statements, assumptions and data gaps.

    Raises:
        ValueError: If the reservoir temperature is not given.
    """
    p = dict(prospect)
    gaps: list[str] = []
    assumptions: list[str] = []
    reasoning: list[str] = []
    run = buffer or buffered_h2s
    if _missing(p.get("res_T_C")):
        raise ValueError(
            "reservoir temperature (res_T_C) is needed: H2S in the reservoir is controlled by temperature first"
        )
    temp = float(p["res_T_C"])
    measured_cond = bool(p.get("measured_conditions"))
    fluid_type = (
        "oil" if str(p.get("fluid_type") or "gas").lower().startswith("oil") else "gas"
    )
    if _missing(p.get("fluid_type")):
        assumptions.append("Fluid type not given: gas assumed")
    p["fluid_type"] = fluid_type
    p["setting"] = classify_setting(p.get("formation"), p.get("setting"))
    # ---- inputs and their scatter
    sd_t = float(
        p.get("res_T_sd_C") or (MEASURED_T_SD_C if measured_cond else PROSPECT_T_SD_C)
    )
    if _missing(p.get("res_T_sd_C")):
        assumptions.append(
            f"Reservoir temperature taken as {'measured' if measured_cond else 'predicted'}: "
            f"one standard deviation of {sd_t:.0f} °C"
        )
    co2_rel = registry.get("co2_relation")
    if not _missing(p.get("co2_molpct")):
        co2 = float(p["co2_molpct"])
        sd_co2 = float(
            p.get("co2_sd_log10")
            or (MEASURED_CO2_SD_LOG10 if measured_cond else GIVEN_CO2_SD_LOG10)
        )
        co2_basis = (
            "measured"
            if measured_cond
            else "given, from analogues or the prospect evaluation"
        )
    elif co2_rel:
        co2 = 10 ** (co2_rel["intercept"] + co2_rel["slope"] * temp)
        sd_co2 = float(co2_rel["sd"])
        co2_basis = "from the CO2 against temperature trend of the calibration wells"
        gaps.append(
            f"CO2 content not given: {fmt(co2)} mol % taken from the trend of CO2 with temperature in the calibration "
            f"wells (a factor {10 ** sd_co2:.1f} either way)"
        )
    else:
        co2, sd_co2 = 2.0, 0.35
        co2_basis = "declared default"
        gaps.append(
            "CO2 content not given and no CO2 trend in the calibration: 2 mol % assumed (a factor 2.2 either way)"
        )
    co2 = max(co2, 0.01)
    p_rel = registry.get("pressure_relation")
    if not _missing(p.get("res_P_bara")):
        pres = float(p["res_P_bara"])
        sd_p = float(
            p.get("res_P_sd_log10") or (0.01 if measured_cond else PROSPECT_P_SD_LOG10)
        )
        p_basis = "measured" if measured_cond else "given"
    elif p_rel:
        pres = max(p_rel["intercept"] + p_rel["slope"] * temp, 50.0)
        sd_p = math.log10(1.0 + min(float(p_rel["sd"]) / pres, 1.0))
        p_basis = "from the pressure against temperature trend of the calibration wells"
        gaps.append(
            f"Reservoir pressure not given: {fmt(pres, 3)} bara taken from the trend with temperature in the calibration wells"
        )
    else:
        pres, sd_p = max(3.0 * temp, 50.0), 0.12
        p_basis = "declared default (3 bar per °C)"
        gaps.append(f"Reservoir pressure not given: {fmt(pres, 3)} bara assumed")
    p.update(
        {
            "co2_used_molpct": co2,
            "co2_basis": co2_basis,
            "res_P_used_bara": pres,
            "pressure_basis": p_basis,
        }
    )
    # ---- buffer and its sensitivity to the inputs
    base = dict(run(temp, pres, co2, fluid_type))
    sep0, res0 = float(base["separator_gas_ppm"]), float(base["reservoir_fluid_ppm"])

    def log_sep(t: float, pr: float, c: float) -> float:
        return math.log10(float(run(t, pr, c, fluid_type)["separator_gas_ppm"]))

    l0 = math.log10(sep0)
    s_t = (log_sep(temp + 10.0, pres, co2) - l0) / 10.0
    s_c = (log_sep(temp, pres, co2 * 1.5) - l0) / math.log10(1.5)
    s_p = (log_sep(temp, pres * 1.2, co2) - l0) / math.log10(1.2)
    stat, class_note = class_of(registry, p["setting"])
    offset = float(stat["offset_log10"])
    sd_model = float(stat["sd_prediction_log10"])
    parts = [
        ("Scatter of measured wells about the buffer", "-", sd_model),
        ("Reservoir temperature", f"± {sd_t:.0f} °C", abs(s_t) * sd_t),
        ("CO2 content", f"factor {10 ** sd_co2:.2f}", abs(s_c) * sd_co2),
        ("Reservoir pressure", f"factor {10 ** sd_p:.2f}", abs(s_p) * sd_p),
    ]
    var = sum(v * v for _, _, v in parts)
    sd_total = math.sqrt(var)
    budget = [
        {
            "source": name,
            "input_scatter": scatter,
            "factor": 10**v,
            "share_of_variance": v * v / var if var else 0.0,
        }
        for name, scatter, v in parts
    ]
    mu_model = l0 + offset
    q_model = lognormal_quantiles(mu_model, sd_total)
    cal_range = registry.get("temperature_range_C")
    reasoning.append(
        f"The pyrite and Fe-carbonate buffer gives {fmt(res0)} ppm H2S in the reservoir fluid at {fmt(temp, 3)} °C, {fmt(pres, 3)} bara and {fmt(co2)} mol % CO2, "
        f"and {fmt(sep0)} ppm in test-separator gas. The temperature correlation of Håland et al. (1999) gives {fmt(haaland_ppm(temp))} ppm."
    )
    if abs(offset) >= 0.02:
        reasoning.append(
            "Measured wells of the setting '{}' lie a factor {:.2f} {} the buffer on average ({}); the estimate is "
            "moved accordingly.".format(
                p["setting"],
                10 ** abs(offset),
                "above" if offset > 0 else "below",
                class_note,
            )
        )
    else:
        reasoning.append(
            f"Measured wells of the setting '{p['setting']}' show no offset from the buffer ({class_note})."
        )
    reasoning.append(
        f"A reservoir {10.0:.0f} °C hotter holds a factor {10 ** (10.0 * s_t):.1f} more H2S; twice the CO2 gives a factor {2.0**s_c:.2f} more."
    )
    lead = max(budget, key=lambda b: b["share_of_variance"])
    reasoning.append(
        "The largest contribution to the range is '{}' ({:.0f} % of the variance).".format(
            lead["source"].lower(), 100 * lead["share_of_variance"]
        )
    )
    # ---- validity of the buffer for this reservoir
    notes = []
    if p["setting"] == CONTINENTAL:
        notes.append(
            "Continental red beds are oxidised and hold little pyrite: measured H2S lies below the buffer, and few "
            "wells constrain by how much. The range is wide for that reason."
        )
    if p["setting"] == CARBONATE:
        notes.append(
            "Carbonate and evaporite reservoirs are outside the calibration. Where anhydrite is present above about "
            "120 °C, thermochemical sulfate reduction can raise H2S far above the buffer; treat the estimate as a "
            "lower bound and obtain a sample."
        )
        gaps.append(
            "Carbonate or evaporite reservoir: the buffer calibration does not cover this setting"
        )
    if p.get("sulfate_minerals") and temp > 120.0 and p["setting"] != CARBONATE:
        notes.append(
            "Sulfate minerals are reported above 120 °C: thermochemical sulfate reduction can raise H2S above the "
            "buffer until reactive iron is used up. The estimate may be low."
        )
    if temp < 70.0:
        notes.append(
            "Below about 70 °C the mineral reactions are slow and the buffer value is small; measured H2S is then often "
            "below the detection limit, and bacterial sulfate reduction can add H2S where sulfate and nutrients exist."
        )
    if cal_range and not (cal_range[0] <= temp <= cal_range[1]):
        gaps.append(
            f"Reservoir temperature {temp:.0f} °C is outside the calibration ({cal_range[0]:.0f} to {cal_range[1]:.0f} °C)"
        )
    if float(base.get("siderite_margin_log10", 1.0)) < 0.0:
        notes.append(
            "The CO2 fugacity is below the siderite and magnetite boundary: siderite is not stable and the buffer does not apply."
        )
    if float(base.get("pyrite_margin_log10", 1.0)) < 0.0:
        notes.append(
            "The buffered H2S is below the pyrite and pyrrhotite boundary: pyrite is not stable."
        )
    reasoning += notes
    if p["setting"] == UNKNOWN:
        gaps.append(
            "Reservoir formation not given: depositional setting unknown, statistics of wells without a setting used"
        )
    # ---- analogues
    analogues = find_analogues(p, wells) if wells else []
    near = [
        a
        for a in analogues
        if a["match_level"] >= 1
        and a["distance_km"] is not None
        and a["distance_km"] <= 100.0
    ]
    if near:
        vals = [a["measured_ppm"] for a in near]
        reasoning.append(
            "Within 100 km {} of the same setting: {} to {} ppm at {} to {} °C.".format(
                (
                    "there is one measured well"
                    if len(near) == 1
                    else f"there are {len(near)} measured wells"
                ),
                fmt(min(vals)),
                fmt(max(vals)),
                (
                    fmt(
                        min(
                            a["reservoir_T_C"]
                            for a in near
                            if a["reservoir_T_C"] is not None
                        ),
                        3,
                    )
                    if any(a["reservoir_T_C"] is not None for a in near)
                    else "-"
                ),
                (
                    fmt(
                        max(
                            a["reservoir_T_C"]
                            for a in near
                            if a["reservoir_T_C"] is not None
                        ),
                        3,
                    )
                    if any(a["reservoir_T_C"] is not None for a in near)
                    else "-"
                ),
            )
        )
    # ---- measurements in the discovery
    measured = [
        float(v) for v in (measurements or []) if v is not None and float(v) > 0.0
    ]
    basis = (
        "mineral buffer calibrated on measured wells (no measurement in this reservoir)"
    )
    high_floor = None
    if measured:
        med = _median(measured)
        sd_use = max(
            float(registry.get("within_well_sd_log10") or 0.0), MIN_MEASURED_SD_LOG10
        )
        mu_use = math.log10(med)
        basis = (
            "H2S measured in the test gas of this discovery (median of the readings)"
        )
        pct = 100.0 * (1.0 - exceedance(mu_model, sd_total, med))
        reasoning.append(
            "{}; the median, {} ppm, is the best estimate. It lies at the {} percentile of the buffer estimate "
            "({} to {} ppm, P10 to P90).".format(
                (
                    f"The discovery has one reading in test gas, {fmt(med)} ppm"
                    if len(measured) == 1
                    else f"The discovery has {len(measured)} readings in test gas, {fmt(min(measured))} to {fmt(max(measured))} ppm"
                ),
                fmt(med),
                ordinal(pct),
                fmt(q_model["p10"]),
                fmt(q_model["p90"]),
            )
        )
        if med < q_model["p10"]:
            high_floor = q_model["p50"]
            reasoning.append(
                "The readings lie below the P10 of the buffer estimate. H2S is lost to steel, to scavengers in the "
                "mud and to water during a short test, so a low reading is weaker evidence than a high one: the "
                "upper value of the range for design is kept at the buffer estimate."
            )
        elif med > q_model["p90"]:
            reasoning.append(
                "The readings lie above the P90 of the buffer estimate. The reading stands; check for sulfate "
                "minerals, a hotter source of the gas and the CO2 content."
            )
    else:
        mu_use, sd_use = mu_model, sd_total
    q = lognormal_quantiles(mu_use, sd_use)
    low = nice_value(q["p50"], -1)
    high = nice_value(max(q["p90"], high_floor or 0.0), 1)
    if high <= low:
        high = nice_value(low * 1.01, 1)
    # ---- sour service and gas specification
    to_res = res0 / sep0 if sep0 > 0 else 1.0
    if fluid_type == "gas":
        kpa50 = q["p50"] * to_res * 1e-6 * pres * 100.0
        sour_basis = (
            "H2S mole fraction of the reservoir gas times the reservoir pressure"
        )
    else:
        kpa50 = float(base.get("h2s_fugacity_bar", 0.0)) * 100.0 * q["p50"] / sep0
        sour_basis = "H2S fugacity in the reservoir oil (equal to the partial pressure in a gas in equilibrium with it)"
    sour = {
        "limit_kpa": SOUR_SERVICE_KPA,
        "partial_pressure_kpa_p50": kpa50,
        "partial_pressure_kpa_p90": kpa50 * 10 ** (Z90 * sd_use),
        "probability_sour": (
            exceedance(math.log10(kpa50), sd_use, SOUR_SERVICE_KPA)
            if kpa50 > 0
            else 0.0
        ),
        "pressure_bara": pres,
        "basis": sour_basis,
    }
    spec_ppm = gas_spec_mg_nm3 / MG_PER_NM3_PER_PPM
    spec = {
        "limit_mg_nm3": gas_spec_mg_nm3,
        "limit_ppm": spec_ppm,
        "p50_mg_nm3": q["p50"] * MG_PER_NM3_PER_PPM,
        "p90_mg_nm3": q["p90"] * MG_PER_NM3_PER_PPM,
        "probability_above": exceedance(mu_use, sd_use, spec_ppm),
    }
    factor = 10 ** (Z90 * sd_use)
    accuracy = [
        f"The P10 to P90 range spans a factor {factor**2:.1f} (a factor {factor:.1f} either side of the median)."
    ]
    buf = registry.get("buffer") or {}
    out = registry.get("well_out") or {}
    haal = registry.get("haaland")
    if buf:
        text = (
            "Calibration: {} wells with H2S measured in test gas. The buffer reproduces {:.0f} % of them within a "
            "factor 2 and {:.0f} % within a factor 3 (root mean square error {:.2f} in log10, a factor {:.1f})".format(
                registry.get("n_wells"),
                100 * buf["within_factor_2"],
                100 * buf["within_factor_3"],
                buf["rmse_log10"],
                10 ** buf["rmse_log10"],
            )
        )
        if haal:
            text += "; the temperature correlation alone gives {:.0f} % within a factor 2 (error {:.2f})".format(
                100 * haal["within_factor_2"], haal["rmse_log10"]
            )
        accuracy.append(text + ".")
    if out:
        accuracy.append(
            "Check of the stated range: with each well left out in turn, {:.0f} % of the wells fell inside the P10 to "
            "P90 range, {:.0f} % above and {:.0f} % below (80, 10 and 10 expected).".format(
                100 * out["inside_p10_p90"],
                100 * out["above_p90"],
                100 * out["below_p10"],
            )
        )
    accuracy.append(
        "That check uses the measured temperature and CO2 of each well. For a prospect these are predictions, and "
        "their uncertainty is added in the range above."
    )
    nd = registry.get("non_detects") or {}
    if nd.get("wells"):
        accuracy.append(
            "{} further wells had no detectable H2S in the test gas. The buffer gives less than 1 ppm for {} of them "
            "and less than 3 ppm for {}; detector tubes read down to between 0.2 and 1 ppm, depending on the tube. In "
            "the other {} the buffer gives more than 3 ppm: either H2S was lost during the test or the reservoir holds "
            "less than the buffer. A result far below the estimate is therefore possible and is not covered by the "
            "stated range.".format(
                nd["wells"],
                nd.get("buffer_below_1_ppm", 0),
                nd.get("buffer_below_3_ppm", 0),
                nd["wells"] - nd.get("buffer_below_3_ppm", 0),
            )
        )
    nb = registry.get("neighbours")
    if nb:
        accuracy.append(
            "Neighbouring wells add no information beyond their temperature and CO2: the deviations from the buffer of "
            "wells within {:.0f} km of each other are not correlated (correlation {:.2f}, {} wells). The analogue "
            "wells are shown for context and are not used to adjust the estimate.".format(
                nb["radius_km"], nb["correlation"], nb["n"]
            )
        )
    if not measured:
        accuracy.append(
            "Readings in the test gas of a well narrow the range to about a factor {:.1f} either side.".format(
                10
                ** (
                    Z90
                    * max(
                        float(registry.get("within_well_sd_log10") or 0.0),
                        MIN_MEASURED_SD_LOG10,
                    )
                )
            )
        )
    curve_points = []
    if curve:
        for t in (60.0, 80.0, 100.0, 120.0, 140.0, 160.0, 180.0, 200.0):
            try:
                curve_points.append(
                    {
                        "T_C": t,
                        "buffer_ppm": float(
                            run(t, pres, co2, fluid_type)["separator_gas_ppm"]
                        ),
                    }
                )
            except Exception:  # noqa: BLE001, S112
                continue
    return {
        "schema": SCHEMA,
        "prospect": p,
        "unit": "ppm by mole in separator or test gas",
        "basis": basis,
        "best_estimate": q["p50"],
        "p10": q["p10"],
        "p50": q["p50"],
        "p90": q["p90"],
        "log10_sd": sd_use,
        "recommended_range": {"low": low, "high": high},
        "probability_above": {
            f"{x:g}": exceedance(mu_use, sd_use, x) for x in thresholds
        },
        "sour_service": sour,
        "gas_specification": spec,
        "buffer": {
            **{k: v for k, v in base.items() if k != "warnings"},
            "sensitivity": {
                "log10_per_C": s_t,
                "log10_per_log10_co2": s_c,
                "log10_per_log10_pressure": s_p,
            },
        },
        "statistical": {
            "setting": p["setting"],
            "offset_log10": offset,
            "sd_wells_log10": sd_model,
            "sd_total_log10": sd_total,
            "class_note": class_note,
            "buffer_estimate": q_model,
        },
        "uncertainty_budget": budget,
        "measurements": {
            "gas_readings": measured,
            "median": _median(measured) if measured else None,
            "highest": max(measured) if measured else None,
        },
        "analogues": analogues,
        "curve": curve_points,
        "reasoning": reasoning,
        "accuracy": accuracy,
        "assumptions": assumptions,
        "data_gaps": gaps,
        "calibration": {
            "name": registry.get("name"),
            "created": registry.get("created"),
            "wells": registry.get("n_wells"),
            "sources": registry.get("sources"),
        },
    }
