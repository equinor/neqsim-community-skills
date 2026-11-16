"""Raw test-separator series: test-window means and quality flags."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd


def window_mean(series: pd.Series, start, end, drop_first: float = 0.10, min_points: int = 5) -> Optional[Dict[str, float]]:
    """Mean, standard deviation and point count of ``series`` over a test window.

    The first ``drop_first`` share of the window is dropped: the separator level and the line are still settling after
    the well is routed to the test separator. Returns None when fewer than ``min_points`` values remain.
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if series.index.tz is not None and start.tz is None:
        start, end = start.tz_localize(series.index.tz), end.tz_localize(series.index.tz)
    start = start + (end - start) * drop_first
    s = pd.to_numeric(series[(series.index >= start) & (series.index < end)], errors="coerce").dropna()
    if len(s) < min_points:
        return None
    return {"mean": float(s.mean()), "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0, "n": int(len(s))}


def quality_flags(duration_h: float, water_raw_m3d: Optional[float], water_reported_m3d: Optional[float],
                       oil_cv: Optional[float] = None, min_duration_h: float = 0.5, water_tolerance: float = 0.15,
                       max_oil_cv: float = 0.30) -> Dict[str, bool]:
    """Flags that make a test unusable for calibration.

    ``water_mismatch``: raw water differs from the reported test water by more than ``water_tolerance`` - usually a
    deduction test, a second well on the header or a meter problem, so the raw window is not a single-well test.
    ``unstable``: coefficient of variation of the oil rate above ``max_oil_cv`` (slugging, start-up).
    """
    flags = {"too_short": not (duration_h and duration_h >= min_duration_h), "water_mismatch": False, "unstable": False}
    if water_raw_m3d is not None and water_reported_m3d:
        flags["water_mismatch"] = abs(water_raw_m3d / water_reported_m3d - 1.0) > water_tolerance
    if oil_cv is not None:
        flags["unstable"] = oil_cv > max_oil_cv
    return flags
