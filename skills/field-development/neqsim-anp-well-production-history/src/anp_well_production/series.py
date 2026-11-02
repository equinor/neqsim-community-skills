"""Well, field and installation production series from ANP records.

All functions work on the record layout produced by ``parse.normalize`` and use
rates in m3/d (liquids, water) and thousand m3/d (gas). Nothing here adds
information: aggregation, ratios, completeness and consistency checks only.
"""

from __future__ import annotations

import datetime as _dt
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .parse import RATE_FIELDS

_PRESALT_LABELS = {"presal", "pre sal", "pre-sal", "pre_sal", "presalt", "pre-salt"}
_OFFSHORE_LABELS = {"mar", "offshore", "sea"}


def expected_latest_period(today: Optional[_dt.date] = None) -> Tuple[int, int]:
    """Return the newest production month ANP can have published.

    ANP publishes a month's well data in the second month after it: January in
    March. On any date in month M the newest month that can be public is M-2, and
    it may appear only later in M.

    Args:
        today: Reference date; the current date when omitted.

    Returns:
        ``(year, month)``.
    """
    today = today or _dt.date.today()
    index = today.year * 12 + (today.month - 1) - 2
    return index // 12, index % 12 + 1


def _row_key(rec: Mapping[str, Any]) -> Tuple:
    """Identity of one production row: a well can be split over several fields."""
    return (rec.get("well"), rec.get("period"), rec.get("field"), rec.get("zone"), rec.get("installation"))


def merge_environments(
    by_environment: Mapping[str, Sequence[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Combine onshore, offshore and pre-salt files without double counting.

    The ANP pre-salt file is a subset of the offshore file. Rows of the pre-salt
    file are therefore dropped when the same row (well, month, field,
    installation) is in the offshore file, and the offshore row is marked
    ``presalt=True``. Rows get the file label as ``environment`` when they have
    none (the by-well rate files have no such column).

    Args:
        by_environment: Records per label; labels are matched case-insensitively
            (``mar``/``offshore``, ``terra``/``onshore``, ``presal``/``pre-salt``).

    Returns:
        ``(records, report)``. The report has ``n_offshore``, ``n_presalt``,
        ``n_overlap``, ``presalt_only`` (well and month of rows found only in
        the pre-salt file), ``presalt_is_subset`` and ``warnings``.
    """
    presalt: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    offshore_keys = set()
    n_offshore = 0
    for label, recs in by_environment.items():
        norm = label.strip().lower()
        labelled = [r if r.get("environment") else dict(r, environment=label.upper()) for r in recs]
        if norm in _PRESALT_LABELS:
            presalt.extend(labelled)
            continue
        rest.extend(labelled)
        if norm in _OFFSHORE_LABELS:
            n_offshore += len(recs)
            offshore_keys.update(_row_key(r) for r in recs)
    warnings: List[str] = []
    merged = list(rest)
    overlap = 0
    only: List[Tuple[str, str]] = []
    presalt_keys = set()
    for rec in presalt:
        key = _row_key(rec)
        presalt_keys.add(key)
        if key in offshore_keys:
            overlap += 1
        else:
            only.append((rec["well"], rec["period"]))
            merged.append(dict(rec, presalt=True))
    for rec in merged:
        if _row_key(rec) in presalt_keys:
            rec["presalt"] = True
    if presalt and not n_offshore:
        warnings.append(
            "No offshore file given: pre-salt rows used alone cover only the pre-salt polygon, not all offshore wells."
        )
    if only and n_offshore:
        warnings.append(
            "%d pre-salt well-months are absent from the offshore file; check that both files are from the same release."
            % len(only)
        )
    report = {
        "n_offshore": n_offshore,
        "n_presalt": len(presalt),
        "n_overlap": overlap,
        "presalt_only": only,
        "presalt_is_subset": not only,
        "warnings": warnings,
    }
    return merged, report


def _sum(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


def ratios(rec: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Return gas-liquid ratio and water cut of one record or aggregate.

    Args:
        rec: Record with ``liquid_m3d``, ``gas_total_km3d`` and ``water_m3d``.

    Returns:
        ``gor_sm3_sm3`` (gas per liquid, thousand m3 gas times 1000 over m3
        liquid), ``gor_scf_bbl``, ``water_cut`` (water over water plus liquid)
        and ``wor``. Each is ``None`` when its denominator is not positive.
    """
    liquid = rec.get("liquid_m3d")
    gas = rec.get("gas_total_km3d")
    water = rec.get("water_m3d")
    gor = gas * 1000.0 / liquid if (liquid and liquid > 0 and gas is not None) else None
    wc = water / (water + liquid) if (water is not None and liquid is not None and water + liquid > 0) else None
    wor = water / liquid if (water is not None and liquid and liquid > 0) else None
    return {
        "gor_sm3_sm3": gor,
        "gor_scf_bbl": None if gor is None else gor * 5.614583,
        "water_cut": wc,
        "wor": wor,
    }


def aggregate(
    records: Iterable[Mapping[str, Any]],
    by: Sequence[str] = ("field",),
    allow_duplicates: bool = False,
) -> List[Dict[str, Any]]:
    """Sum rates per period and group (field, installation, basin, well, ...).

    Args:
        records: Normalised production records.
        by: Record keys that define a group, for example ``("field",)`` or
            ``("installation",)``; use ``()`` for a national total.
        allow_duplicates: When False, a repeated well/period/zone/installation
            key raises, which catches onshore, offshore and pre-salt files added
            together by mistake.

    Returns:
        One dict per group and period, sorted by group then period, with the
        group keys, ``period``, ``n_wells`` (wells with positive liquid or gas),
        every field of ``RATE_FIELDS`` summed, and :func:`ratios`.

    Raises:
        ValueError: Duplicate keys while ``allow_duplicates`` is False.
    """
    seen = set()
    groups: Dict[Tuple, Dict[str, Any]] = {}
    for r in records:
        if not allow_duplicates:
            dup = _row_key(r)
            if dup in seen:
                raise ValueError(
                    "Duplicate row for %s in %s (field %s, installation %s): do not add the pre-salt file "
                    "to the offshore file; use merge_environments" % (dup[0], dup[1], dup[2], dup[4])
                )
            seen.add(dup)
        key = tuple(r.get(k) for k in by) + (r["period"],)
        g = groups.setdefault(
            key,
            {**{k: r.get(k) for k in by}, "period": r["period"], "year": r["year"], "month": r["month"],
             "days": r["days"], "_wells": set(), "_vals": {f: [] for f in RATE_FIELDS}},
        )
        for f in RATE_FIELDS:
            g["_vals"][f].append(r.get(f))
        if (r.get("liquid_m3d") or 0) > 0 or (r.get("gas_total_km3d") or 0) > 0:
            g["_wells"].add(r.get("well"))
    out: List[Dict[str, Any]] = []
    for key in sorted(groups, key=lambda k: tuple("" if v is None else str(v) for v in k)):
        g = groups[key]
        row = {k: v for k, v in g.items() if not k.startswith("_")}
        for f in RATE_FIELDS:
            row[f] = _sum(g["_vals"][f])
        row["n_wells"] = len(g["_wells"])
        row.update(ratios(row))
        out.append(row)
    return out


def well_history(records: Iterable[Mapping[str, Any]], well: str) -> List[Dict[str, Any]]:
    """Return one well's monthly series sorted by period.

    ANP allocates a well that drains several fields as one row per field. Rows of
    the same month are summed so that the history is the whole well; ``field``
    then lists the fields joined by ``+`` and ``hours_on`` is the longest value.

    Args:
        records: Normalised production records.
        well: ANP well name (exact match after trimming).

    Returns:
        One dict per month with the summed rates, :func:`ratios`, the first
        available ``api``, ``gas_composition_pct`` and ``gcv_kj_m3``, and
        ``n_rows``; oldest first.
    """
    by_period: Dict[str, List[Mapping[str, Any]]] = {}
    for r in records:
        if (r.get("well") or "").strip() == well.strip():
            by_period.setdefault(r["period"], []).append(r)
    out: List[Dict[str, Any]] = []
    for period in sorted(by_period):
        rows = by_period[period]
        first = rows[0]
        rec = {k: first.get(k) for k in ("well", "installation", "year", "month", "period", "days", "family")}
        rec["field"] = "+".join(sorted({r.get("field") or "" for r in rows}))
        for f in RATE_FIELDS:
            rec[f] = _sum(r.get(f) for r in rows)
        hours = [r["hours_on"] for r in rows if r.get("hours_on") is not None]
        rec["hours_on"] = max(hours) if hours else None
        for k in ("api", "gas_composition_pct", "gcv_kj_m3", "analysis_period"):
            rec[k] = next((r.get(k) for r in rows if r.get(k) is not None), None)
        rec["n_rows"] = len(rows)
        rec.update(ratios(rec))
        out.append(rec)
    return out


def producing_rate(rec: Mapping[str, Any], key: str = "liquid_m3d") -> Optional[float]:
    """Rate over the hours the well was on stream.

    ANP rates are monthly volume divided by calendar days, so a well on stream
    for part of the month looks weaker than it was. With ``hours_on`` the rate
    over producing time is the calendar rate times month hours over hours on
    stream.

    Args:
        rec: Record with ``hours_on`` (by-well rate files only) and ``days``.
        key: Rate field to convert.

    Returns:
        The producing-time rate, or ``None`` when hours are missing or zero.
    """
    hours = rec.get("hours_on")
    value = rec.get(key)
    if hours is None or hours <= 0 or value is None:
        return None
    return value * rec["days"] * 24.0 / min(hours, rec["days"] * 24.0)


def cumulative(history: Iterable[Mapping[str, Any]], key: str = "liquid_m3d") -> List[Tuple[str, float]]:
    """Cumulative production from a monthly rate series.

    Args:
        history: Records of one well, field or group, sorted by period.
        key: Rate field; liquid and water give m3, gas gives thousand m3.

    Returns:
        ``(period, cumulative volume)`` pairs; missing rates add nothing.
    """
    total = 0.0
    out = []
    for r in history:
        v = r.get(key)
        if v is not None:
            total += v * r["days"]
        out.append((r["period"], total))
    return out


def completeness(
    records: Iterable[Mapping[str, Any]],
    today: Optional[_dt.date] = None,
) -> Dict[str, Any]:
    """Check which months a record set covers.

    Args:
        records: Records of any group.
        today: Reference date for the publication lag.

    Returns:
        ``first``, ``last``, ``n_periods``, ``missing`` (months absent between
        first and last), ``expected_latest`` and ``behind_expected_months``
        (positive when the data end before the newest month ANP can have
        published).
    """
    periods = sorted({r["period"] for r in records})
    if not periods:
        return {"first": None, "last": None, "n_periods": 0, "missing": [],
                "expected_latest": "%04d-%02d" % expected_latest_period(today), "behind_expected_months": None}

    def idx(p: str) -> int:
        y, m = p.split("-")
        return int(y) * 12 + int(m) - 1

    have = {idx(p) for p in periods}
    missing = []
    for i in range(idx(periods[0]), idx(periods[-1]) + 1):
        if i not in have:
            missing.append("%04d-%02d" % (i // 12, i % 12 + 1))
    ey, em = expected_latest_period(today)
    return {
        "first": periods[0],
        "last": periods[-1],
        "n_periods": len(periods),
        "missing": missing,
        "expected_latest": "%04d-%02d" % (ey, em),
        "behind_expected_months": ey * 12 + em - 1 - idx(periods[-1]),
    }


def well_flags(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Flag data features that bias a well analysis.

    Args:
        history: One well's records sorted by period.

    Returns:
        ``shut_in`` (periods with no liquid and no gas), ``partial`` (periods on
        stream for under half the month), ``hours_conflict`` (rate above zero
        with zero hours on stream), ``gaps`` (missing months between first and
        last) and ``gor_outliers`` (periods whose gas-liquid ratio is over five
        times the well median).
    """
    shut_in, partial, conflict = [], [], []
    for r in history:
        liq, gas = r.get("liquid_m3d"), r.get("gas_total_km3d")
        if (liq or 0) <= 0 and (gas or 0) <= 0:
            shut_in.append(r["period"])
        hours = r.get("hours_on")
        if hours is not None:
            if hours <= 0 and ((liq or 0) > 0 or (gas or 0) > 0):
                conflict.append(r["period"])
            elif 0 < hours < 0.5 * r["days"] * 24:
                partial.append(r["period"])
    gors = [(r["period"], ratios(r)["gor_sm3_sm3"]) for r in history]
    vals = [g for _, g in gors if g]
    outliers = []
    if len(vals) >= 5:
        med = statistics.median(vals)
        outliers = [p for p, g in gors if g and med > 0 and g > 5.0 * med]
    return {
        "shut_in": shut_in,
        "partial": partial,
        "hours_conflict": conflict,
        "gaps": completeness(history)["missing"],
        "gor_outliers": outliers,
    }


def decline_series(
    history: Iterable[Mapping[str, Any]],
    key: str = "liquid_m3d",
    on_stream: bool = False,
) -> List[Tuple[float, float]]:
    """Build the ``(year, rate)`` input of an Arps decline fit.

    Months with a zero or missing rate are dropped, because a shut-in month is an
    operating event and not reservoir decline. Time is the mid-month in decimal
    years. The result feeds ``fit_arps_decline`` of the skill
    ``neqsim-norwegian-continental-shelf-data``.

    Args:
        history: Records of one well or group, sorted by period.
        key: Rate field to fit.
        on_stream: Use :func:`producing_rate` instead of the calendar rate.

    Returns:
        List of ``(decimal year, rate)``.
    """
    out = []
    for r in history:
        v = producing_rate(r, key) if on_stream else r.get(key)
        if v is None or v <= 0:
            continue
        out.append((r["year"] + (r["month"] - 0.5) / 12.0, v))
    return out


def reconcile(
    rate_records: Iterable[Mapping[str, Any]],
    volume_records: Iterable[Mapping[str, Any]],
    rel_tol: float = 0.005,
) -> List[Dict[str, Any]]:
    """Compare by-well rate files with by-well volume files for the same months.

    Both families describe the same wells; the rate is the volume over calendar
    days. Differences point to a unit error, a stale download or a revised
    month.

    Args:
        rate_records: Records of the ``well_monthly_rates`` family.
        volume_records: Records of the ``well_monthly_volumes`` family.
        rel_tol: Allowed relative difference (rate files round to four decimals).

    Returns:
        List of mismatches ``{well, period, field, rate_file, volume_file,
        rel_diff}`` for liquid, gas and water; empty when the files agree.
    """
    fields = ("liquid_m3d", "gas_total_km3d", "water_m3d")

    def totals(records: Iterable[Mapping[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Optional[float]]]:
        acc: Dict[Tuple[str, str], Dict[str, Optional[float]]] = {}
        for r in records:
            slot = acc.setdefault((r["well"], r["period"]), {f: None for f in fields})
            for f in fields:
                if r.get(f) is not None:
                    slot[f] = (slot[f] or 0.0) + r[f]
        return acc

    rates, vols = totals(rate_records), totals(volume_records)
    out = []
    for key, rate in rates.items():
        vol = vols.get(key)
        if vol is None:
            continue
        for fld in fields:
            a, b = rate[fld], vol[fld]
            if a is None or b is None:
                continue
            scale = max(abs(a), abs(b))
            if scale < 1e-6:
                continue
            rel = abs(a - b) / scale
            if rel > rel_tol and abs(a - b) > 1e-3:
                out.append({"well": key[0], "period": key[1], "field": fld,
                            "rate_file": a, "volume_file": b, "rel_diff": rel})
    return out
