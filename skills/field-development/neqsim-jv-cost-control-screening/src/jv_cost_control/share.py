"""Participating-interest (PI) share checks for partner billing statements."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def infer_interest_ratio(
    gross: pd.Series, share: pd.Series, min_abs: float = 1000.0
) -> pd.Series:
    """Return the implied partner share ratio ``share / gross`` per line.

    Args:
        gross: 100 % amounts.
        share: Partner-share amounts.
        min_abs: Lines with ``|gross|`` below this value return ``NaN`` because
            rounding dominates the ratio.

    Returns:
        Series of implied ratios.
    """
    safe = gross.where(gross.abs() >= min_abs)
    return share / safe


def interest_share_check(
    df: pd.DataFrame,
    gross_col: str,
    share_col: str,
    expected_pis: Sequence[float],
    tol_rel: float = 0.0005,
    tol_abs: float = 0.02,
) -> pd.DataFrame:
    """Flag lines whose share is not ``gross x`` one of the expected PIs.

    A line passes when ``|share - gross * pi| <= max(tol_abs, tol_rel * |gross|)``
    for at least one expected PI. Several PIs are allowed because a statement
    can mix areas where the partner holds different interests (for example a
    cost-pool PI and a carried-party-adjusted PI).

    Args:
        df: Table with gross and share columns.
        gross_col: Name of the 100 % column.
        share_col: Name of the partner-share column.
        expected_pis: Allowed PI fractions, e.g. ``[0.12, 0.13333]``.
        tol_rel: Relative tolerance on the gross amount.
        tol_abs: Absolute tolerance in currency units (rounding).

    Returns:
        Failing lines with ``best_pi``, ``expected_share`` and ``diff`` columns,
        sorted by absolute difference. Empty when every line is consistent.

    Raises:
        ValueError: If ``expected_pis`` is empty.
    """
    if not len(expected_pis):
        raise ValueError("expected_pis must not be empty")
    gross = df[gross_col].astype(float)
    share = df[share_col].astype(float)
    pis = np.array(expected_pis, dtype=float)
    candidates = np.outer(gross.to_numpy(), pis)
    errors = np.abs(candidates - share.to_numpy()[:, None])
    best = errors.argmin(axis=1)
    best_err = errors[np.arange(len(df)), best]
    limit = np.maximum(tol_abs, tol_rel * gross.abs().to_numpy())
    out = df.copy()
    out["best_pi"] = pis[best]
    out["expected_share"] = candidates[np.arange(len(df)), best]
    out["diff"] = share.to_numpy() - out["expected_share"].to_numpy()
    failing = out[best_err > limit].copy()
    failing["abs_diff"] = failing["diff"].abs()
    return failing.sort_values("abs_diff", ascending=False).drop(columns="abs_diff")
