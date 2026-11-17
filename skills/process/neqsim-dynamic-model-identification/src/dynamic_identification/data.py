"""Put historian series on one uniform time base and mark bad data, the way TimeSeriesAnalysis expects it."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

BAD_DATA_ID = -9999.0


def load_series(
    path: str | Path,
    value_column: str | None = None,
    time_column: str = "time",
    sentinels: Iterable[float] = (),
) -> pd.Series:
    """Read one tag from a CSV (``time`` plus a value column; ``avg`` or the second column by default).

    Sentinel values (instrument fault codes such as -9999 or -225) become NaN.
    """
    frame = pd.read_csv(path)
    if time_column not in frame.columns:
        raise ValueError(f"{path}: no '{time_column}' column")
    column = value_column or (
        "avg"
        if "avg" in frame.columns
        else next(c for c in frame.columns if c != time_column)
    )
    times = pd.to_datetime(frame[time_column], utc=True, format="mixed")
    values = pd.to_numeric(frame[column], errors="coerce").astype(float)
    for sentinel in sentinels:
        values[np.isclose(values, float(sentinel))] = np.nan
    return pd.Series(values.to_numpy(), index=times, name=Path(path).stem).sort_index()


def frozen_mask(values: np.ndarray, min_run: int) -> np.ndarray:
    """True where a value repeats exactly for at least ``min_run`` samples (hold-last or a dead transmitter)."""
    mask = np.zeros(len(values), dtype=bool)
    if min_run < 2 or len(values) == 0:
        return mask
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start] or np.isnan(values[i]):
            if i - start >= min_run and not np.isnan(values[start]):
                mask[start:i] = True
            start = i
    return mask


def align(
    series: dict[str, pd.Series],
    timebase_s: float | None = None,
    start: str | None = None,
    end: str | None = None,
    max_gap_s: float | None = None,
    frozen_samples: int = 0,
    hold: Iterable[str] = (),
) -> dict[str, object]:
    """Resample all series onto one uniform grid.

    The time base defaults to the largest median sample interval of the inputs. A grid point takes the latest
    sample within ``max_gap_s`` (default one time base); otherwise it is bad. Series named in ``hold`` are
    on-change tags (setpoints, modes): their last value holds until the next change. Returns ``{"times",
    "values", "timebase_s", "bad_fraction"}`` where ``values[name]`` is a float array with NaN for bad points.
    """
    if not series:
        raise ValueError("no series to align")
    hold = set(hold)
    cleaned = {k: s.dropna() for k, s in series.items()}
    if timebase_s is None:
        steps = [
            float(np.median((s.index[1:] - s.index[:-1]).total_seconds()))
            for k, s in cleaned.items()
            if len(s) > 2 and k not in hold
        ]
        if not steps:
            raise ValueError("series are too short to infer a time base")
        timebase_s = max(steps)
    t0 = (
        pd.Timestamp(start, tz="UTC")
        if start
        else max(s.index[0] for s in cleaned.values())
    )
    t1 = (
        pd.Timestamp(end, tz="UTC")
        if end
        else min(s.index[-1] for s in cleaned.values())
    )
    if t1 <= t0:
        raise ValueError("the series do not overlap in time")
    grid = pd.date_range(t0, t1, freq=pd.to_timedelta(timebase_s, unit="s"))
    tolerance = pd.to_timedelta(max_gap_s or timebase_s, unit="s")
    values: dict[str, np.ndarray] = {}
    bad: dict[str, float] = {}
    for name, s in cleaned.items():
        s = s[~s.index.duplicated(keep="last")]
        if name in hold:
            aligned = (
                s.reindex(s.index.union(grid))
                .ffill()
                .reindex(grid)
                .to_numpy(dtype=float)
            )
        else:
            aligned = s.reindex(grid, method="ffill", tolerance=tolerance).to_numpy(
                dtype=float, copy=True
            )
        if frozen_samples and name not in hold:
            aligned[frozen_mask(aligned, frozen_samples)] = np.nan
        values[name] = aligned
        bad[name] = float(np.mean(np.isnan(aligned)))
    return {
        "times": grid,
        "values": values,
        "timebase_s": float(timebase_s),
        "bad_fraction": bad,
    }


def to_tsa(values: Sequence[float]) -> list:
    """Replace NaN with the TimeSeriesAnalysis bad-data marker."""
    return [
        BAD_DATA_ID if (v is None or not np.isfinite(v)) else float(v) for v in values
    ]


def saturation(
    u: np.ndarray, u_min: float, u_max: float, tolerance: float = 0.5
) -> dict[str, float]:
    """Share of valid samples at or near each stop of a controller output (control authority)."""
    valid = u[np.isfinite(u)]
    if len(valid) == 0:
        return {
            "at_min_fraction": float("nan"),
            "at_max_fraction": float("nan"),
            "valid_samples": 0,
        }
    return {
        "at_min_fraction": float(np.mean(valid <= u_min + tolerance)),
        "at_max_fraction": float(np.mean(valid >= u_max - tolerance)),
        "p01": float(np.percentile(valid, 1)),
        "p50": float(np.percentile(valid, 50)),
        "p99": float(np.percentile(valid, 99)),
        "valid_samples": len(valid),
    }
