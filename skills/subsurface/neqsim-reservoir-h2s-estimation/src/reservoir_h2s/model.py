"""Calibration of the H2S buffer against measured wells: bias and scatter per depositional setting.

The buffer model has no fitted parameter per well. What is calibrated here is how far measured H2S in test gas lies
from the buffer value, per depositional setting, and how much it scatters. That scatter, combined with the uncertainty
of the inputs of a prospect, gives the range of the estimate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .setting import MARINE, UNKNOWN, classify_setting

SCHEMA = "h2s_prospect_calibration.v1"

#: Standard normal quantile of 90 %.
Z90 = 1.2815515655446004

#: Scatter used when a registry holds no value (declared, a factor 2 for one standard deviation).
DEFAULT_SD_LOG10 = 0.30

#: Classes with fewer wells than this use the scatter of all wells, not their own.
MIN_CLASS_SIZE = 3


def lognormal_quantiles(log10_mean: float, log10_sd: float) -> dict[str, float]:
    """Return P10, P50 and P90 of a lognormal quantity.

    Args:
        log10_mean: Mean of log10(value).
        log10_sd: Standard deviation of log10(value).

    Returns:
        ``{"p10", "p50", "p90"}`` with P10 the low value.
    """
    return {
        "p10": 10 ** (log10_mean - Z90 * log10_sd),
        "p50": 10**log10_mean,
        "p90": 10 ** (log10_mean + Z90 * log10_sd),
    }


def _mean(values: Sequence[float]) -> float:
    """Arithmetic mean (0 for an empty list)."""
    return sum(values) / len(values) if values else 0.0


def _sd(values: Sequence[float]) -> float:
    """Sample standard deviation (0 for fewer than two values)."""
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _rmse(values: Sequence[float]) -> float:
    """Root mean square (0 for an empty list)."""
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0


def _share(values: Sequence[float], limit: float) -> float:
    """Share of values with an absolute value below a limit."""
    return sum(1 for v in values if abs(v) <= limit) / len(values) if values else 0.0


def _line(xs: Sequence[float], ys: Sequence[float]) -> dict[str, float] | None:
    """Least-squares line ``y = intercept + slope x`` with its residual scatter; None for fewer than five points."""
    n = len(xs)
    if n < 5:
        return None
    mx, my = _mean(xs), _mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0.0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    res = [y - intercept - slope * x for x, y in zip(xs, ys)]
    return {
        "intercept": intercept,
        "slope": slope,
        "sd": math.sqrt(sum(r * r for r in res) / max(n - 2, 1)),
        "n": n,
    }


def _num(value: Any) -> float | None:
    """Return a finite float, or None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def not_detected(well: Mapping[str, Any]) -> bool:
    """Return True for a well whose readings were all below the detection limit (``detected`` is false)."""
    return str(well.get("detected")).strip().lower() == "false"


def class_statistics(residuals: Sequence[float], pooled_sd: float) -> dict[str, float]:
    """Offset and prediction scatter of one setting.

    Args:
        residuals: log10(measured / buffer) of the wells of the setting.
        pooled_sd: Scatter of all wells about their class means, used for small classes.

    Returns:
        ``n``, ``offset_log10``, ``sd_log10`` and ``sd_prediction_log10``. The prediction scatter includes the
        uncertainty of the class mean, so a class with three wells gives a wider range than one with fifty.
    """
    n = len(residuals)
    sd = _sd(residuals)
    if n < 10:
        sd = max(sd, pooled_sd)
    return {
        "n": n,
        "offset_log10": _mean(residuals),
        "sd_log10": sd,
        "sd_prediction_log10": sd * math.sqrt(1.0 + 1.0 / n) if n else sd,
    }


def calibrate(
    wells: Iterable[Mapping[str, Any]],
    name: str = "H2S buffer calibration",
    created: str | None = None,
    sources: Sequence[str] | None = None,
    within_well_sd_log10: float | None = None,
) -> dict[str, Any]:
    """Build the calibration registry from wells with measured H2S and the buffer value at the same conditions.

    Args:
        wells: One record per well with ``measured_ppm`` (H2S in test gas, well median of the detected readings),
            ``model_ppm`` (buffer value in separator gas), ``res_T_C``, and optionally ``setting`` or ``formation``,
            ``co2_molpct``, ``res_P_bara``, ``haaland_ppm`` and ``detected`` (False for a well with only readings
            below the detection limit, in which case ``detection_limit_ppm`` is used).
        name: Name of the calibration.
        created: Date of the calibration (ISO text).
        sources: Data sources, for the report.
        within_well_sd_log10: Scatter between repeat readings of one well [log10], when known.

    Returns:
        Registry (schema ``h2s_prospect_calibration.v1``) with the offset and scatter per setting, the errors with a
        well left out, the share of wells inside the P10 to P90 range, the comparison with the temperature correlation
        of Håland et al. (1999), and the relations of CO2 and pressure with temperature.

    Raises:
        ValueError: If fewer than five wells have a measured value and a buffer value.
    """
    rows = []
    censored = []
    for w in wells:
        model = _num(w.get("model_ppm"))
        temp = _num(w.get("res_T_C"))
        if model is None or model <= 0.0:
            continue
        setting = classify_setting(w.get("formation"), w.get("setting"))
        if not_detected(w):
            censored.append(
                {
                    "model": model,
                    "limit": _num(w.get("detection_limit_ppm")),
                    "T": temp,
                }
            )
            continue
        measured = _num(w.get("measured_ppm"))
        if measured is None or measured <= 0.0:
            continue
        rows.append(
            {
                "r": math.log10(measured / model),
                "setting": setting,
                "T": temp,
                "co2": _num(w.get("co2_molpct")),
                "P": _num(w.get("res_P_bara")),
                "haaland": _num(w.get("haaland_ppm")),
                "measured": measured,
            }
        )
    if len(rows) < 5:
        raise ValueError(
            "at least five wells with measured H2S and a buffer value are needed"
        )
    by_class: dict[str, list[float]] = {}
    for row in rows:
        by_class.setdefault(row["setting"], []).append(row["r"])
    centred = [r - _mean(v) for v in by_class.values() for r in v]
    dof = max(len(rows) - len(by_class), 1)
    pooled = math.sqrt(sum(c * c for c in centred) / dof)
    classes = {k: class_statistics(v, pooled) for k, v in by_class.items()}
    # ---- every well predicted from the others
    loo, z = [], []
    for i, row in enumerate(rows):
        rest = [x for j, x in enumerate(rows) if j != i]
        same = [x["r"] for x in rest if x["setting"] == row["setting"]]
        use = same if len(same) >= MIN_CLASS_SIZE - 1 else [x["r"] for x in rest]
        rest_by: dict[str, list[float]] = {}
        for x in rest:
            rest_by.setdefault(x["setting"], []).append(x["r"])
        rest_pooled = math.sqrt(
            sum((r - _mean(v)) ** 2 for v in rest_by.values() for r in v)
            / max(len(rest) - len(rest_by), 1)
        )
        stat = class_statistics(use, rest_pooled)
        err = row["r"] - stat["offset_log10"]
        loo.append(err)
        z.append(
            err / stat["sd_prediction_log10"] if stat["sd_prediction_log10"] else 0.0
        )
    raw = [row["r"] for row in rows]
    haal = [
        math.log10(row["measured"] / row["haaland"])
        for row in rows
        if row["haaland"] and row["haaland"] > 0.0
    ]
    bands = []
    for low, high in (
        (-50.0, 70.0),
        (70.0, 100.0),
        (100.0, 130.0),
        (130.0, 160.0),
        (160.0, 400.0),
    ):
        v = [
            row["r"] for row in rows if row["T"] is not None and low <= row["T"] < high
        ]
        if v:
            bands.append(
                {
                    "low_C": low,
                    "high_C": high,
                    "n": len(v),
                    "mean_log10": _mean(v),
                    "sd_log10": _sd(v),
                    "measured_p50_ppm": sorted(
                        row["measured"]
                        for row in rows
                        if row["T"] is not None and low <= row["T"] < high
                    )[len(v) // 2],
                }
            )
    co2_rows = [
        row for row in rows if row["co2"] and row["co2"] > 0 and row["T"] is not None
    ]
    co2_line = _line(
        [r["T"] for r in co2_rows], [math.log10(r["co2"]) for r in co2_rows]
    )
    p_rows = [row for row in rows if row["P"] and row["P"] > 0 and row["T"] is not None]
    p_line = _line([r["T"] for r in p_rows], [r["P"] for r in p_rows])
    temps = [row["T"] for row in rows if row["T"] is not None]
    with_limit = [c for c in censored if c["limit"]]
    return {
        "schema": SCHEMA,
        "name": name,
        "created": created,
        "sources": list(sources or []),
        "n_wells": len(rows),
        "classes": classes,
        "pooled_sd_log10": pooled,
        "within_well_sd_log10": within_well_sd_log10,
        "buffer": {
            "rmse_log10": _rmse(raw),
            "bias_log10": _mean(raw),
            "within_factor_2": _share(raw, math.log10(2.0)),
            "within_factor_3": _share(raw, math.log10(3.0)),
        },
        "haaland": (
            {
                "n": len(haal),
                "rmse_log10": _rmse(haal),
                "bias_log10": _mean(haal),
                "within_factor_2": _share(haal, math.log10(2.0)),
                "within_factor_3": _share(haal, math.log10(3.0)),
            }
            if haal
            else None
        ),
        "well_out": {
            "rmse_log10": _rmse(loo),
            "within_factor_2": _share(loo, math.log10(2.0)),
            "within_factor_3": _share(loo, math.log10(3.0)),
            "inside_p10_p90": sum(1 for v in z if abs(v) <= Z90) / len(z),
            "above_p90": sum(1 for v in z if v > Z90) / len(z),
            "below_p10": sum(1 for v in z if v < -Z90) / len(z),
        },
        "temperature_bands": bands,
        "temperature_range_C": [min(temps), max(temps)] if temps else None,
        "co2_relation": co2_line,
        "pressure_relation": p_line,
        "non_detects": {
            "wells": len(censored),
            "with_detection_limit": len(with_limit),
            "buffer_below_limit": sum(
                1 for c in with_limit if c["model"] <= c["limit"]
            ),
            "buffer_below_1_ppm": sum(1 for c in censored if c["model"] <= 1.0),
            "buffer_below_3_ppm": sum(1 for c in censored if c["model"] <= 3.0),
            "temperature_median_C": (
                sorted(c["T"] for c in censored if c["T"] is not None)[
                    len([c for c in censored if c["T"] is not None]) // 2
                ]
                if any(c["T"] is not None for c in censored)
                else None
            ),
            "buffer_median_ppm": (
                sorted(c["model"] for c in censored)[len(censored) // 2]
                if censored
                else None
            ),
        },
    }


def class_of(registry: Mapping[str, Any], setting: str) -> tuple[dict[str, float], str]:
    """Return the offset and scatter to use for a setting, and a note on what was used.

    Args:
        registry: Calibration registry.
        setting: Depositional setting of the prospect.

    Returns:
        ``(statistics, note)``. A setting without enough wells in the calibration falls back to the unknown class,
        then to marine or paralic with the scatter of all wells.
    """
    classes = registry.get("classes") or {}
    stat = classes.get(setting)
    if stat and stat["n"] >= MIN_CLASS_SIZE:
        return dict(stat), f"{stat['n']} calibration wells of this setting"
    pooled = float(registry.get("pooled_sd_log10") or DEFAULT_SD_LOG10)
    for other in (UNKNOWN, MARINE):
        stat = classes.get(other)
        if stat and stat["n"] >= MIN_CLASS_SIZE and other != setting:
            out = dict(stat)
            out["sd_prediction_log10"] = max(
                out["sd_prediction_log10"], pooled, DEFAULT_SD_LOG10
            )
            return out, (
                f"fewer than {MIN_CLASS_SIZE} calibration wells of this setting: statistics of '{other}' wells used "
                "with a scatter of at least a factor 2"
            )
    sd = max(pooled, DEFAULT_SD_LOG10)
    return (
        {"n": 0, "offset_log10": 0.0, "sd_log10": sd, "sd_prediction_log10": sd},
        f"no calibration wells of this setting: no offset and a scatter of a factor {10 ** sd:.1f}",
    )


def save_registry(registry: Mapping[str, Any], path: str) -> None:
    """Write a registry as JSON.

    Args:
        registry: Calibration registry.
        path: File to write.
    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=1, ensure_ascii=False, default=str)


def load_registry(path: str) -> dict[str, Any]:
    """Read a registry from JSON.

    Args:
        path: File written by :func:`save_registry`.

    Returns:
        Calibration registry.

    Raises:
        ValueError: If the file is not an H2S calibration registry.
    """
    with open(path, "r", encoding="utf-8") as handle:
        registry = json.load(handle)
    if registry.get("schema") != SCHEMA:
        raise ValueError(f"{path} is not an H2S calibration registry ({SCHEMA})")
    return registry
