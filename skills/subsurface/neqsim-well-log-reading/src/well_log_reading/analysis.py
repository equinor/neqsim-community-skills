"""Screening analyses on a depth-indexed log frame.

All depths are metres along the log index (normally measured depth from the
log's depth reference, for example RKB). Formation tops, loss events or fault
picks must use the same reference; convert TVD picks to MD with the well's
survey first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from .model import LogCurve, LogFrame


def _scalar_curves(frame: LogFrame, curves: Iterable[str] | None):
    if curves is None:
        return [c for c in frame.curves.values() if not c.is_array]
    return [frame.curve(name) for name in curves]


def _stats(values: np.ndarray) -> dict[str, float | None]:
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        return {"n": 0, "mean": None, "p10": None, "p50": None, "p90": None}
    p10, p50, p90 = np.percentile(valid, [10, 50, 90])
    return {
        "n": int(valid.size),
        "mean": float(valid.mean()),
        "p10": float(p10),
        "p50": float(p50),
        "p90": float(p90),
    }


def zone_statistics(
    frame: LogFrame,
    zones: Sequence[Mapping],
    curves: Iterable[str] | None = None,
) -> list[dict]:
    """Summarise curves inside depth zones (formations, reservoir zones, intervals).

    Args:
        frame: a depth-indexed frame.
        zones: sequence of mappings with ``name``, ``top_m`` and ``base_m``.
        curves: curve names or canonical mnemonics; all scalar curves when omitted.

    Returns:
        One row per zone and curve with sample count, valid fraction, mean and
        P10/P50/P90 (P10 is the 10th percentile, low value). A zone includes its
        top and excludes its base (``top <= depth < base``), so adjacent zones
        never count the boundary sample twice; a base at or below the deepest
        sample includes that sample, so the end of the log is never dropped.

    Raises:
        ValueError: if a zone has base above top.
    """
    depth = frame.depth_m()
    deepest = float(np.nanmax(depth)) if depth.size else 0.0
    selected = _scalar_curves(frame, curves)
    rows = []
    for zone in zones:
        top, base = float(zone["top_m"]), float(zone["base_m"])
        if base < top:
            raise ValueError(f"zone {zone.get('name')!r}: base {base} is above top {top}")
        below_top = depth >= top
        inside = below_top & ((depth < base) | ((depth <= base) & (base >= deepest)))
        for curve in selected:
            values = np.asarray(curve.values, dtype=float)[inside]
            row = {
                "zone": zone.get("name", f"{top:.1f}-{base:.1f}"),
                "top_m": top,
                "base_m": base,
                "curve": curve.name,
                "canonical": curve.canonical,
                "unit": curve.unit,
                "samples_in_zone": int(inside.sum()),
                "valid_fraction": float(np.isfinite(values).mean()) if values.size else 0.0,
            }
            row.update(_stats(values))
            rows.append(row)
    return rows


def depth_window_contrast(
    frame: LogFrame,
    depth_m: float,
    half_width_m: float = 5.0,
    background_m: float = 20.0,
    curves: Iterable[str] | None = None,
) -> list[dict]:
    """Compare curves in a window around an event depth with the rock above and below.

    Use it for loss events, fault or fracture picks and influx depths: a log
    signature (low density, high caliper, resistivity drop) that differs from
    both shoulders supports the pick; no contrast means the logs neither
    confirm nor reject it.

    Args:
        frame: a depth-indexed frame.
        depth_m: event depth on the log index.
        half_width_m: half-width of the event window.
        background_m: thickness of each shoulder interval above and below the window.
        curves: curves to compare; all scalar curves when omitted.

    Returns:
        One row per curve with window, above and below means and the contrast
        ``window - mean(above, below)`` in curve units and in shoulder standard deviations.
    """
    depth = frame.depth_m()
    window = (depth >= depth_m - half_width_m) & (depth <= depth_m + half_width_m)
    above = (depth >= depth_m - half_width_m - background_m) & (depth < depth_m - half_width_m)
    below = (depth > depth_m + half_width_m) & (depth <= depth_m + half_width_m + background_m)
    rows = []
    for curve in _scalar_curves(frame, curves):
        values = np.asarray(curve.values, dtype=float)
        w, a, b = values[window], values[above], values[below]
        w, a, b = w[np.isfinite(w)], a[np.isfinite(a)], b[np.isfinite(b)]
        row = {
            "event_depth_m": float(depth_m),
            "curve": curve.name,
            "canonical": curve.canonical,
            "unit": curve.unit,
            "window_mean": float(w.mean()) if w.size else None,
            "above_mean": float(a.mean()) if a.size else None,
            "below_mean": float(b.mean()) if b.size else None,
            "contrast": None,
            "contrast_sigma": None,
            "data_coverage": "ok" if (w.size and a.size and b.size) else "insufficient",
        }
        if w.size and a.size and b.size:
            shoulders = np.concatenate([a, b])
            reference = 0.5 * (a.mean() + b.mean())
            row["contrast"] = float(w.mean() - reference)
            spread = float(shoulders.std(ddof=1)) if shoulders.size > 1 else 0.0
            row["contrast_sigma"] = row["contrast"] / spread if spread > 0 else None
        rows.append(row)
    return rows


def resample(frame: LogFrame, step_m: float, curves: Iterable[str] | None = None) -> LogFrame:
    """Return a new frame on a regular depth grid in metres (linear interpolation).

    NaN gaps are not bridged: an output sample is NaN when either neighbour is NaN.

    Raises:
        ValueError: if ``step_m`` is not positive.
    """
    if step_m <= 0:
        raise ValueError("step_m must be positive")
    depth = frame.depth_m()
    order = np.argsort(depth)
    depth_sorted = depth[order]
    grid = np.arange(np.nanmin(depth), np.nanmax(depth) + 0.5 * step_m, step_m)
    out = LogFrame(
        name=f"{frame.name}-resampled-{step_m:g}m",
        index_name="DEPTH",
        index_unit="m",
        index=grid,
        index_type=frame.index_type,
    )
    for curve in _scalar_curves(frame, curves):
        values = np.asarray(curve.values, dtype=float)[order]
        interpolated = np.interp(grid, depth_sorted, np.nan_to_num(values, nan=0.0))
        gap = np.interp(grid, depth_sorted, np.isnan(values).astype(float)) > 0
        interpolated[gap] = np.nan
        out.curves[curve.name] = LogCurve(curve.name, curve.unit, interpolated, curve.long_name)
    return out
