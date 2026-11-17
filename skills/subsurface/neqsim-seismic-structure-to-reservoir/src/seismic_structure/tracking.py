"""Seed-based horizon tracking in a post-stack SEG-Y cube (screening only).

From a seed pick, the tracker grows outwards to neighbouring traces, always
expanding the strongest accepted pick first. In each neighbour it looks for an
amplitude extremum of the same polarity within ``max_jump`` samples of the
neighbour's pick and accepts it if it is at least ``min_amplitude_ratio`` of
the seed amplitude. The result is a two-way-time surface on the survey's
inline/crossline grid with world coordinates from the trace headers.

This automates picking one continuous, strong reflector. It does not cross
faults reliably, does not separate interfering events and is not a substitute
for interpretation: the surface is a screening structure map to be checked
against well tops and an interpreter's picks.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from .surface import Surface

MAX_SAMPLES_IN_MEMORY = 400_000_000


@dataclass
class SeismicCube:
    """A post-stack cube in memory with geometry for the inline/crossline grid."""

    data: np.ndarray  # (n_inline, n_crossline, n_samples), NaN for missing traces
    inlines: np.ndarray
    crosslines: np.ndarray
    samples: np.ndarray  # ms (or depth unit for depth cubes)
    x: np.ndarray  # (n_inline, n_crossline)
    y: np.ndarray
    path: str
    geometry_fit_rms: float = 0.0

    @property
    def dt(self) -> float:
        """Sample interval."""
        return (
            float(self.samples[1] - self.samples[0]) if self.samples.size > 1 else 1.0
        )

    def time_at(self, index: float) -> float:
        """Sample value (ms) at a fractional sample index."""
        return float(self.samples[0] + index * self.dt)

    def index_of(self, inline: int, crossline: int) -> tuple[int, int]:
        """Array indices of an inline/crossline pair.

        Raises:
            ValueError: if the line numbers are not in the survey.
        """
        try:
            return int(np.where(self.inlines == inline)[0][0]), int(
                np.where(self.crosslines == crossline)[0][0]
            )
        except IndexError as exc:
            raise ValueError(
                f"inline {inline} / crossline {crossline} is not in the survey"
            ) from exc

    def nearest_trace(self, x: float, y: float) -> tuple[int, int, float]:
        """Indices of the trace nearest a map point and the snap distance."""
        d2 = (self.x - x) ** 2 + (self.y - y) ** 2
        d2 = np.where(np.isfinite(d2), d2, np.inf)
        i, j = np.unravel_index(int(np.argmin(d2)), d2.shape)
        return int(i), int(j), float(math.sqrt(d2[i, j]))

    def grid_geometry(self) -> dict[str, float]:
        """Surface geometry: crosslines along the column axis, inlines along the row axis."""
        ii, jj = np.meshgrid(
            np.arange(self.inlines.size), np.arange(self.crosslines.size), indexing="ij"
        )
        ok = np.isfinite(self.x) & np.isfinite(self.y)
        design = np.column_stack(
            [np.ones(ok.sum()), jj[ok], ii[ok]]
        )  # origin, per crossline, per inline
        cx, *_ = np.linalg.lstsq(design, self.x[ok], rcond=None)
        cy, *_ = np.linalg.lstsq(design, self.y[ok], rcond=None)
        col = np.array([cx[1], cy[1]])
        row = np.array([cx[2], cy[2]])
        cross = col[0] * row[1] - col[1] * row[0]
        residual = np.hypot(design @ cx - self.x[ok], design @ cy - self.y[ok])
        self.geometry_fit_rms = float(np.sqrt(np.mean(residual**2)))
        return {
            "xori": float(cx[0]),
            "yori": float(cy[0]),
            "xinc": float(np.hypot(*col)),
            "yinc": float(np.hypot(*row)),
            "rotation": math.degrees(math.atan2(col[1], col[0])),
            "yflip": 1 if cross > 0 else -1,
        }


def load_cube(
    path, header_bytes=None, max_samples: int = MAX_SAMPLES_IN_MEMORY
) -> SeismicCube:
    """Read a structured post-stack SEG-Y file into memory.

    Raises:
        ValueError: for unstructured or pre-stack files, or cubes larger than ``max_samples``.
    """
    from segy_seismic_reading import (
        DEFAULT_HEADER_BYTES,
        open_segy,
        trace_coordinates,
    )

    with open_segy(path, header_bytes or DEFAULT_HEADER_BYTES) as (handle, used, note):
        if used is None:
            raise ValueError(
                f"{path} has no inline/crossline geometry ({note}); tracking needs a 3-D cube"
            )
        if len(handle.offsets) > 1:
            raise ValueError(
                f"{path} is pre-stack ({len(handle.offsets)} offsets); track on a stacked cube"
            )
        inlines, crosslines = np.asarray(handle.ilines), np.asarray(handle.xlines)
        samples = np.asarray(handle.samples, dtype=float)
        size = inlines.size * crosslines.size * samples.size
        if size > max_samples:
            raise ValueError(
                f"cube has {size} samples (> {max_samples}); cut a sub-volume first"
            )
        il = np.asarray(handle.attributes(used[0])[:])
        xl = np.asarray(handle.attributes(used[1])[:])
        ii = (
            np.searchsorted(inlines, il)
            if inlines[0] <= inlines[-1]
            else np.searchsorted(-inlines, -il)
        )
        jj = (
            np.searchsorted(crosslines, xl)
            if crosslines[0] <= crosslines[-1]
            else np.searchsorted(-crosslines, -xl)
        )
        data = np.full(
            (inlines.size, crosslines.size, samples.size), np.nan, dtype=np.float32
        )
        data[ii, jj] = np.asarray(handle.trace.raw[:], dtype=np.float32)
        tx, ty, _ = trace_coordinates(handle)
        x = np.full((inlines.size, crosslines.size), np.nan)
        y = np.full_like(x, np.nan)
        x[ii, jj], y[ii, jj] = tx, ty
    return SeismicCube(data, inlines, crosslines, samples, x, y, str(path))


def _pick(
    trace: np.ndarray, centre: float, half_window: int, sign: int
) -> tuple[float, float] | None:
    """Best extremum of polarity ``sign`` within ``half_window`` samples of ``centre`` (parabolic refine)."""
    n = trace.size
    lo, hi = max(1, int(math.floor(centre)) - half_window), min(
        n - 2, int(math.ceil(centre)) + half_window
    )
    best = None
    for k in range(lo, hi + 1):
        a, b, c = sign * trace[k - 1], sign * trace[k], sign * trace[k + 1]
        if not np.isfinite(b) or b <= 0 or b < a or b < c:
            continue
        if best is None or b > best[1]:
            denom = a - 2 * b + c
            offset = 0.5 * (a - c) / denom if denom != 0 else 0.0
            best = (k + float(np.clip(offset, -0.5, 0.5)), b)
    return best


def track_horizon(
    cube: SeismicCube,
    seed_inline: int,
    seed_crossline: int,
    seed_time_ms: float,
    polarity: str = "auto",
    seed_window_ms: float = 12.0,
    max_jump_samples: int = 2,
    min_amplitude_ratio: float = 0.3,
    name: str = "tracked_horizon",
) -> Surface:
    """Track one reflector from a seed and return its two-way-time surface.

    Args:
        cube: cube from :func:`load_cube`.
        seed_inline, seed_crossline: seed trace.
        seed_time_ms: approximate seed time; the strongest extremum within ``seed_window_ms`` is used.
        polarity: ``peak``, ``trough`` or ``auto`` (strongest of either at the seed).
        seed_window_ms: half-window for snapping the seed.
        max_jump_samples: largest time shift allowed between neighbouring picks.
        min_amplitude_ratio: picks weaker than this fraction of the seed amplitude stop the growth.
        name: surface name.

    Raises:
        ValueError: if the seed cannot be snapped to an event.
    """
    i0, j0 = cube.index_of(seed_inline, seed_crossline)
    trace = cube.data[i0, j0]
    centre = (seed_time_ms - cube.samples[0]) / cube.dt
    half = max(1, int(round(seed_window_ms / cube.dt)))
    if polarity == "auto":
        candidates = [
            (p, s)
            for s in (1, -1)
            for p in [_pick(trace, centre, half, s)]
            if p is not None
        ]
        if not candidates:
            raise ValueError("no amplitude extremum near the seed time")
        seed_pick, sign = max(candidates, key=lambda c: c[0][1])
    else:
        sign = 1 if polarity == "peak" else -1
        seed_pick = _pick(trace, centre, half, sign)
        if seed_pick is None:
            raise ValueError(f"no {polarity} near the seed time")
    threshold = min_amplitude_ratio * seed_pick[1]
    picks = np.full(cube.data.shape[:2], np.nan)
    picks[i0, j0] = seed_pick[0]
    heap = [(-seed_pick[1], i0, j0)]
    while heap:
        _, i, j = heapq.heappop(heap)
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if not (0 <= a < picks.shape[0] and 0 <= b < picks.shape[1]) or np.isfinite(
                picks[a, b]
            ):
                continue
            neighbour = cube.data[a, b]
            if not np.isfinite(neighbour).any():
                continue
            found = _pick(neighbour, picks[i, j], max_jump_samples, sign)
            if found is None or found[1] < threshold:
                continue
            picks[a, b] = found[0]
            heapq.heappush(heap, (-found[1], a, b))
    times = np.where(np.isfinite(picks), cube.samples[0] + picks * cube.dt, np.nan)
    geometry = cube.grid_geometry()
    surface = Surface(
        values=times.T,
        name=name,
        domain="time",
        unit="ms",
        source=cube.path,
        **geometry,
    )
    coverage = float(np.isfinite(times).mean())
    surface.notes.append(
        f"tracked {'peak' if sign > 0 else 'trough'} from inline {seed_inline} crossline {seed_crossline} "
        f"at {cube.time_at(seed_pick[0]):.1f} ms; coverage {coverage:.0%}; screening pick, not interpretation"
    )
    if cube.geometry_fit_rms > 0.25 * min(geometry["xinc"], geometry["yinc"]):
        surface.notes.append(
            f"trace coordinates deviate {cube.geometry_fit_rms:.1f} m from a regular grid"
        )
    return surface


def seed_from_well(
    cube: SeismicCube, x: float, y: float, depth_m: float, velocity
) -> dict[str, float]:
    """Seed at a well: nearest trace to the well and the time of a known top from a velocity model.

    Returns:
        ``inline``, ``crossline``, ``twt_ms`` and ``snap_distance_m``.
    """
    i, j, snap = cube.nearest_trace(x, y)
    return {
        "inline": int(cube.inlines[i]),
        "crossline": int(cube.crosslines[j]),
        "twt_ms": float(velocity.twt(depth_m)),
        "snap_distance_m": snap,
    }
