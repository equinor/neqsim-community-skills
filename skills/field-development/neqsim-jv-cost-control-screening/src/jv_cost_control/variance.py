"""Variance analysis helpers: budget/forecast variances, unit-cost split, outliers."""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


def variance_table(
    df: pd.DataFrame,
    actual: str,
    reference: str,
    keys: Sequence[str],
    abs_threshold: float,
    pct_threshold: float = 0.10,
) -> pd.DataFrame:
    """Compute actual-minus-reference variances and flag material ones.

    Args:
        df: Detail table.
        actual: Column with actual cost.
        reference: Column with budget, forecast or plan cost.
        keys: Columns to aggregate by (for example account and development area).
        abs_threshold: Minimum absolute variance to be material.
        pct_threshold: Minimum relative variance to be material. A line with
            zero reference and an absolute variance above ``abs_threshold`` is
            always material (unbudgeted spend).

    Returns:
        Table sorted by absolute variance with ``variance``, ``variance_pct``,
        ``direction`` (``over`` or ``under`` for costs), ``material`` and
        ``unbudgeted`` columns.
    """
    grouped = df.groupby(list(keys), dropna=False)[[actual, reference]].sum().reset_index()
    grouped["variance"] = grouped[actual] - grouped[reference]
    ref_abs = grouped[reference].abs()
    grouped["variance_pct"] = np.where(ref_abs > 0, grouped["variance"] / ref_abs.where(ref_abs > 0), np.nan)
    grouped["unbudgeted"] = (ref_abs == 0) & (grouped[actual].abs() >= abs_threshold)
    pct_ok = grouped["variance_pct"].abs() >= pct_threshold
    grouped["material"] = (grouped["variance"].abs() >= abs_threshold) & (pct_ok | grouped["unbudgeted"])
    grouped["direction"] = np.where(grouped["variance"] >= 0, "over", "under")
    order = grouped["variance"].abs().sort_values(ascending=False).index
    return grouped.loc[order].reset_index(drop=True)


def variance_commentary(
    table: pd.DataFrame,
    name_cols: Sequence[str],
    actual: str,
    reference: str,
    unit: str = "MUSD",
    top_n: int = 10,
) -> List[Dict[str, str]]:
    """Draft fact-only commentary lines for the largest material variances.

    The sentence states only numbers taken from the table. The cause is left as
    a ``reason`` placeholder that the controller must confirm with the operator;
    nothing is invented.

    Args:
        table: Output of :func:`variance_table`.
        name_cols: Columns that identify the line in the sentence.
        actual: Actual column name.
        reference: Reference column name.
        unit: Unit label used in the text.
        top_n: Number of material lines to describe.

    Returns:
        List of dicts with ``line``, ``fact`` and ``reason`` keys.
    """
    material = table[table["material"]].head(top_n)
    items = []
    for _, row in material.iterrows():
        name = " / ".join(str(row[c]) for c in name_cols)
        pct = row["variance_pct"]
        pct_text = "unbudgeted" if pd.isna(pct) else f"{pct:+.0%}"
        fact = (
            f"{name}: actual {row[actual]:,.1f} {unit} vs reference "
            f"{row[reference]:,.1f} {unit} ({row['variance']:+,.1f} {unit}, {pct_text}, "
            f"{row['direction']})."
        )
        items.append({"line": name, "fact": fact, "reason": "TO BE CONFIRMED WITH OPERATOR"})
    return items


def price_volume_split(
    cost_actual: float, volume_actual: float, cost_ref: float, volume_ref: float
) -> Dict[str, float]:
    """Split a cost variance into volume and unit-rate effects.

    ``volume_effect = (V_act - V_ref) * unit_ref`` and
    ``rate_effect = (unit_act - unit_ref) * V_act`` so that the two add up to
    the total variance exactly.

    Args:
        cost_actual: Actual cost.
        volume_actual: Actual activity volume (barrels, days, well count).
        cost_ref: Reference cost.
        volume_ref: Reference activity volume.

    Returns:
        Dict with ``total``, ``volume_effect``, ``rate_effect``, ``unit_actual``
        and ``unit_ref``.

    Raises:
        ValueError: If a volume is not positive.
    """
    if volume_actual <= 0 or volume_ref <= 0:
        raise ValueError("volumes must be positive")
    unit_act = cost_actual / volume_actual
    unit_ref = cost_ref / volume_ref
    volume_effect = (volume_actual - volume_ref) * unit_ref
    rate_effect = (unit_act - unit_ref) * volume_actual
    return {
        "total": cost_actual - cost_ref,
        "volume_effect": volume_effect,
        "rate_effect": rate_effect,
        "unit_actual": unit_act,
        "unit_ref": unit_ref,
    }


def run_rate_outlook(
    ytd: float, months_elapsed: int, full_year_ref: float | None = None, months_in_year: int = 12
) -> Dict[str, float]:
    """Linear run-rate full-year outlook compared with a full-year reference.

    Args:
        ytd: Year-to-date cost.
        months_elapsed: Number of closed months in ``ytd``.
        full_year_ref: Optional full-year budget or forecast.
        months_in_year: Months per year.

    Returns:
        Dict with ``run_rate_full_year`` and, if a reference is given,
        ``vs_reference`` and ``vs_reference_pct``.

    Raises:
        ValueError: If ``months_elapsed`` is not in ``1..months_in_year``.
    """
    if not 1 <= months_elapsed <= months_in_year:
        raise ValueError("months_elapsed must be between 1 and months_in_year")
    run_rate = ytd / months_elapsed * months_in_year
    result = {"run_rate_full_year": run_rate}
    if full_year_ref is not None:
        result["vs_reference"] = run_rate - full_year_ref
        result["vs_reference_pct"] = (run_rate - full_year_ref) / abs(full_year_ref) if full_year_ref else float("nan")
    return result


def outlier_months(series: pd.Series, z_threshold: float = 3.5) -> pd.Series:
    """Flag outliers with the robust modified z-score (median/MAD).

    Args:
        series: Monthly values.
        z_threshold: Modified z-score above which a value is flagged.

    Returns:
        Boolean series, ``True`` for outliers. All ``False`` when MAD is zero.
    """
    values = series.astype(float)
    median = values.median()
    mad = (values - median).abs().median()
    if mad == 0:
        return pd.Series(False, index=series.index)
    modified_z = 0.6745 * (values - median) / mad
    return modified_z.abs() > z_threshold
