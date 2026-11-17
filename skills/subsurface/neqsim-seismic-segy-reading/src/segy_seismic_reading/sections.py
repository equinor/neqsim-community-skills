"""Read sections, slices, nearest traces and fences along a map polyline; write small cubes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np

from .geometry import DEFAULT_HEADER_BYTES, open_segy, segyio_module, trace_coordinates


@dataclass
class Section:
    """A 2-D amplitude section (traces x samples) with trace positions."""

    data: np.ndarray
    samples: np.ndarray
    x: np.ndarray
    y: np.ndarray
    trace_index: np.ndarray
    label: str
    distance: Optional[np.ndarray] = None
    snap_distance: Optional[np.ndarray] = None


def _nearest(tx: np.ndarray, ty: np.ndarray, px: np.ndarray, py: np.ndarray):
    """Index of and distance to the nearest trace for every point."""
    try:
        from scipy.spatial import cKDTree  # noqa: PLC0415  (optional speed-up)

        distance, index = cKDTree(np.column_stack([tx, ty])).query(
            np.column_stack([px, py])
        )
        return np.asarray(index), np.asarray(distance)
    except ImportError:
        index = np.empty(px.size, dtype=int)
        distance = np.empty(px.size)
        for k in range(px.size):
            d2 = (tx - px[k]) ** 2 + (ty - py[k]) ** 2
            index[k] = int(np.argmin(d2))
            distance[k] = float(np.sqrt(d2[index[k]]))
        return index, distance


def _section(handle, traces: np.ndarray, label: str, source: str) -> Section:
    tx, ty, _ = trace_coordinates(handle, source)
    data = np.stack([np.asarray(handle.trace[int(i)], dtype=float) for i in traces])
    return Section(
        data,
        np.asarray(handle.samples, dtype=float),
        tx[traces],
        ty[traces],
        np.asarray(traces),
        label,
    )


def _line_traces(
    handle,
    used,
    inline: Optional[int] = None,
    crossline: Optional[int] = None,
    offset: Optional[int] = None,
) -> np.ndarray:
    """Trace indices on one inline or crossline, ordered along the line, one offset only."""
    segyio = segyio_module()
    il = np.asarray(handle.attributes(used[0])[:])
    xl = np.asarray(handle.attributes(used[1])[:])
    offsets = np.asarray(handle.attributes(segyio.TraceField.offset)[:])
    wanted_offset = int(handle.offsets[0]) if offset is None else int(offset)
    mask = (
        offsets == wanted_offset
        if len(handle.offsets) > 1
        else np.ones(il.size, dtype=bool)
    )
    if inline is not None:
        mask &= il == inline
        order_key = xl
    else:
        mask &= xl == crossline
        order_key = il
    traces = np.flatnonzero(mask)
    return traces[np.argsort(order_key[traces], kind="stable")]


def read_inline(
    path,
    inline: int,
    header_bytes=DEFAULT_HEADER_BYTES,
    source: str = "cdp",
    offset: Optional[int] = None,
) -> Section:
    """Return one inline as a section (crosslines x samples).

    For pre-stack files the first offset is used unless ``offset`` is given.

    Raises:
        ValueError: for unstructured files or an inline that is not in the survey.
    """
    with open_segy(path, header_bytes) as (handle, used, note):
        if used is None:
            raise ValueError(
                f"{path} has no inline geometry ({note}); use extract_fence"
            )
        ilines = list(handle.ilines)
        if inline not in ilines:
            raise ValueError(
                f"inline {inline} not in survey range {ilines[0]}-{ilines[-1]}"
            )
        return _section(
            handle,
            _line_traces(handle, used, inline=inline, offset=offset),
            f"inline {inline}",
            source,
        )


def read_crossline(
    path,
    crossline: int,
    header_bytes=DEFAULT_HEADER_BYTES,
    source: str = "cdp",
    offset: Optional[int] = None,
) -> Section:
    """Return one crossline as a section (inlines x samples).

    For pre-stack files the first offset is used unless ``offset`` is given.

    Raises:
        ValueError: for unstructured files or a crossline that is not in the survey.
    """
    with open_segy(path, header_bytes) as (handle, used, note):
        if used is None:
            raise ValueError(
                f"{path} has no crossline geometry ({note}); use extract_fence"
            )
        xlines = list(handle.xlines)
        if crossline not in xlines:
            raise ValueError(
                f"crossline {crossline} not in survey range {xlines[0]}-{xlines[-1]}"
            )
        return _section(
            handle,
            _line_traces(handle, used, crossline=crossline, offset=offset),
            f"crossline {crossline}",
            source,
        )


def read_slice(path, sample_value: float, header_bytes=DEFAULT_HEADER_BYTES):
    """Return the horizontal slice nearest to a sample value (ms or depth unit).

    Returns:
        ``(slice, used_sample)`` where ``slice`` is (inlines x crosslines) for
        structured files, or one value per trace otherwise.
    """
    with open_segy(path, header_bytes) as (handle, used, _note):
        samples = np.asarray(handle.samples, dtype=float)
        k = int(np.argmin(np.abs(samples - sample_value)))
        if used is not None:
            return np.asarray(handle.depth_slice[k], dtype=float), float(samples[k])
        values = np.array(
            [handle.trace[i][k] for i in range(handle.tracecount)], dtype=float
        )
        return values, float(samples[k])


def trace_at_xy(
    path, x: float, y: float, header_bytes=DEFAULT_HEADER_BYTES, source: str = "cdp"
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Return the trace nearest to a map point (for example a well location).

    Returns:
        ``(trace, samples, info)`` where ``info`` holds the trace index, its
        coordinates, inline/crossline when known and the snap distance.
    """
    with open_segy(path, header_bytes) as (handle, used, _note):
        tx, ty, _ = trace_coordinates(handle, source)
        index, distance = _nearest(tx, ty, np.array([x]), np.array([y]))
        i = int(index[0])
        info = {
            "trace_index": i,
            "x": float(tx[i]),
            "y": float(ty[i]),
            "snap_distance": float(distance[0]),
        }
        if used is not None:
            header = handle.header[i]
            info["inline"] = int(header[used[0]])
            info["crossline"] = int(header[used[1]])
        trace = np.asarray(handle.trace[i], dtype=float)
        return trace, np.asarray(handle.samples, dtype=float), info


def densify_polyline(points: Sequence[Tuple[float, float]], spacing: float):
    """Return x, y and along-line distance at a regular spacing along a polyline.

    Raises:
        ValueError: for fewer than two points or a non-positive spacing.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        raise ValueError("a fence needs at least two (x, y) points")
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    segment = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
    chainage = np.concatenate([[0.0], np.cumsum(segment)])
    distance = np.arange(0.0, chainage[-1] + 0.5 * spacing, spacing)
    distance[-1] = min(distance[-1], chainage[-1])
    x = np.interp(distance, chainage, pts[:, 0])
    y = np.interp(distance, chainage, pts[:, 1])
    return x, y, distance


def extract_fence(
    path,
    points: Sequence[Tuple[float, float]],
    spacing: float = 25.0,
    max_snap: Optional[float] = None,
    header_bytes=DEFAULT_HEADER_BYTES,
    source: str = "cdp",
) -> Section:
    """Extract an arbitrary fence (section) along a map polyline by nearest-trace snapping.

    Args:
        path: SEG-Y file.
        points: polyline vertices in the survey CRS and units.
        spacing: along-line sample spacing in survey units (use about the bin size).
        max_snap: points further than this from any trace become NaN columns
            (outside the survey). Defaults to 1.5 x ``spacing``.
        header_bytes: inline/crossline byte pairs to try.
        source: coordinate source ``cdp``, ``source`` or ``group``.

    Returns:
        A :class:`Section` with along-line ``distance`` and ``snap_distance``.
    """
    px, py, distance = densify_polyline(points, spacing)
    limit = 1.5 * spacing if max_snap is None else max_snap
    with open_segy(path, header_bytes) as (handle, _used, _note):
        tx, ty, _ = trace_coordinates(handle, source)
        index, snap = _nearest(tx, ty, px, py)
        samples = np.asarray(handle.samples, dtype=float)
        data = np.full((px.size, samples.size), np.nan)
        cache = {}
        for k, i in enumerate(index):
            if snap[k] > limit:
                continue
            if i not in cache:
                cache[i] = np.asarray(handle.trace[int(i)], dtype=float)
            data[k] = cache[i]
    return Section(data, samples, px, py, index, "fence", distance, snap)


def write_cube(
    path,
    data: np.ndarray,
    inlines: Sequence[int],
    crosslines: Sequence[int],
    sample_interval_ms: float,
    origin: Tuple[float, float] = (0.0, 0.0),
    bin_size: Tuple[float, float] = (25.0, 25.0),
    rotation_deg: float = 0.0,
    text: str = "",
    coordinate_scalar: int = -100,
) -> Path:
    """Write a regular 3-D cube (inlines x crosslines x samples) as inline-sorted SEG-Y.

    Crosslines run along local x and inlines along local y; ``rotation_deg``
    rotates the grid anticlockwise about ``origin``. Coordinates are stored as
    integers with ``coordinate_scalar`` (negative divides, SEG-Y convention).
    Use it for synthetic test volumes and for exporting model results.
    """
    segyio = segyio_module()
    cube = np.asarray(data, dtype=np.float32)
    ilines, xlines = np.asarray(inlines, dtype=int), np.asarray(crosslines, dtype=int)
    if cube.shape[:2] != (ilines.size, xlines.size):
        raise ValueError(
            f"data shape {cube.shape} does not match {ilines.size} x {xlines.size}"
        )
    spec = segyio.spec()
    spec.ilines, spec.xlines = ilines, xlines
    spec.samples = np.arange(cube.shape[2]) * float(sample_interval_ms)
    spec.format = 5  # 4-byte IEEE float
    spec.sorting = 2  # inline sorted
    scale = (
        abs(coordinate_scalar)
        if coordinate_scalar < 0
        else 1.0 / max(coordinate_scalar, 1)
    )
    cos_r, sin_r = np.cos(np.radians(rotation_deg)), np.sin(np.radians(rotation_deg))
    tf = segyio.TraceField
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with segyio.create(str(out), spec) as handle:
        trace = 0
        for i, il in enumerate(ilines):
            for j, xl in enumerate(xlines):
                lx, ly = j * bin_size[0], i * bin_size[1]
                x = origin[0] + lx * cos_r - ly * sin_r
                y = origin[1] + lx * sin_r + ly * cos_r
                handle.header[trace] = {
                    tf.INLINE_3D: int(il),
                    tf.CROSSLINE_3D: int(xl),
                    tf.CDP_X: int(round(x * scale)),
                    tf.CDP_Y: int(round(y * scale)),
                    tf.SourceGroupScalar: int(coordinate_scalar),
                    tf.TRACE_SAMPLE_INTERVAL: int(round(sample_interval_ms * 1000)),
                    tf.TRACE_SAMPLE_COUNT: int(cube.shape[2]),
                }
                handle.trace[trace] = cube[i, j]
                trace += 1
        handle.bin.update(
            hdt=int(round(sample_interval_ms * 1000)),
            hns=int(cube.shape[2]),
            format=5,
            mfeet=1,
        )
        lines = {n + 1: line for n, line in enumerate(text.splitlines()[:40]) if line}
        handle.text[0] = segyio.tools.create_text_header(
            lines or {1: "written by segy_seismic_reading"}
        )
    return out


def save_section_png(
    section: Section,
    out_path,
    title: str = "",
    clip_percentile: float = 99.0,
    sample_label: str = "TWT (ms)",
) -> Path:
    """Plot a section with a symmetric grey-scale clip and save it as PNG."""
    import matplotlib  # noqa: PLC0415  (optional dependency)

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    data = section.data
    finite = np.abs(data[np.isfinite(data)])
    clip = float(np.percentile(finite, clip_percentile)) if finite.size else 1.0
    clip = clip or 1.0
    horizontal = (
        section.distance if section.distance is not None else np.arange(data.shape[0])
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(
        data.T,
        cmap="gray_r",
        vmin=-clip,
        vmax=clip,
        aspect="auto",
        extent=[horizontal[0], horizontal[-1], section.samples[-1], section.samples[0]],
    )
    ax.set_xlabel("distance along line" if section.distance is not None else "trace")
    ax.set_ylabel(sample_label)
    ax.set_title(title or section.label)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out
