"""Open SEG-Y files with segyio and describe their geometry, coordinates and headers.

Coordinates come from trace headers (CDP_X/CDP_Y by default) with the SEG-Y
coordinate scalar (bytes 71-72) applied. The coordinate reference system is
never guessed: text-header CRS hints are reported as hints only.
"""

from __future__ import annotations

import hashlib
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

_SEGYIO_MISSING = (
    "reading SEG-Y needs the 'segyio' package (equinor/segyio, LGPL-3.0). It is declared by the "
    "neqsim-seismic-segy-reading skill and installed by the plugin; in a source checkout run "
    "'<python> -m pip install segyio' once."
)

#: Inline/crossline header byte pairs tried in order: SEG-Y rev1 standard, then common legacy.
DEFAULT_HEADER_BYTES: Tuple[Tuple[int, int], ...] = (
    (189, 193),
    (9, 21),
    (9, 13),
    (5, 21),
)

COORDINATE_FIELDS = {
    "cdp": ("CDP_X", "CDP_Y"),
    "source": ("SourceX", "SourceY"),
    "group": ("GroupX", "GroupY"),
}

_CRS_PATTERNS = (
    ("epsg", re.compile(r"EPSG\s*[:#]?\s*(\d{4,5})", re.I)),
    ("utm_zone", re.compile(r"UTM\s*(?:ZONE)?\s*(\d{1,2}\s*[NS]?)", re.I)),
    (
        "datum",
        re.compile(r"\b(ED\s?50|ED\s?87|WGS\s?84|ETRS\s?89|NAD\s?27|NAD\s?83)\b", re.I),
    ),
)


def segyio_module():
    """Import segyio or raise an ImportError with the remedy."""
    try:
        import segyio  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(_SEGYIO_MISSING) from exc
    return segyio


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class SegyGeometry:
    """Summary of one SEG-Y file."""

    path: str
    sha256: str
    trace_count: int
    sample_count: int
    sample_interval: float
    samples: np.ndarray
    sample_format: str
    structured: bool
    sorting: str = "unstructured"
    header_bytes: Optional[Tuple[int, int]] = None
    inlines: Optional[np.ndarray] = None
    crosslines: Optional[np.ndarray] = None
    offsets: List[int] = field(default_factory=list)
    coordinate_source: str = "cdp"
    coordinate_scalars: List[int] = field(default_factory=list)
    coordinate_unit: str = "unknown"
    bbox: Optional[Dict[str, float]] = None
    bin_spacing: Optional[Dict[str, float]] = None
    domain: str = "unknown"
    text_header: str = ""
    crs_hints: Dict[str, str] = field(default_factory=dict)
    amplitude: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@contextmanager
def open_segy(
    path, header_bytes: Sequence[Tuple[int, int]] = DEFAULT_HEADER_BYTES
) -> Iterator:
    """Open a SEG-Y file, trying inline/crossline byte pairs, else unstructured.

    Yields ``(segyfile, used_bytes, note)``; ``used_bytes`` is ``None`` for unstructured
    files (2-D lines, pre-stack gathers or irregular surveys) and ``note`` then
    holds the last geometry error.
    """
    segyio = segyio_module()
    last_error = ""
    for iline, xline in header_bytes:
        try:
            handle = segyio.open(str(path), "r", iline=iline, xline=xline)
        except (RuntimeError, ValueError) as exc:
            last_error = str(exc)
            continue
        try:
            yield handle, (iline, xline), ""
        finally:
            handle.close()
        return
    handle = segyio.open(str(path), "r", ignore_geometry=True)
    try:
        yield handle, None, last_error
    finally:
        handle.close()


def trace_coordinates(
    handle, source: str = "cdp"
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return trace X, Y with the SEG-Y coordinate scalar applied, and the raw scalars.

    Scalar convention (bytes 71-72): positive multiplies, negative divides, zero means 1.
    """
    segyio = segyio_module()
    try:
        x_field, y_field = COORDINATE_FIELDS[source]
    except KeyError as exc:
        raise ValueError(f"source must be one of {sorted(COORDINATE_FIELDS)}") from exc
    tf = segyio.TraceField
    x = np.asarray(handle.attributes(getattr(tf, x_field))[:], dtype=float)
    y = np.asarray(handle.attributes(getattr(tf, y_field))[:], dtype=float)
    scalar = np.asarray(handle.attributes(tf.SourceGroupScalar)[:], dtype=float)
    factor = np.ones_like(scalar)
    factor[scalar > 0] = scalar[scalar > 0]
    factor[scalar < 0] = 1.0 / np.abs(scalar[scalar < 0])
    return x * factor, y * factor, scalar


def _crs_hints(text: str) -> Dict[str, str]:
    hints = {}
    for key, pattern in _CRS_PATTERNS:
        match = pattern.search(text)
        if match:
            hints[key] = re.sub(r"\s+", "", match.group(1)).upper()
    return hints


def _domain(text: str) -> str:
    upper = text.upper()
    if re.search(r"\bDEPTH\b", upper) and not re.search(r"\bTIME\b", upper):
        return "depth (from text header)"
    if re.search(r"\bTWT\b|\bTIME\b|\bMS\b", upper):
        return "time (from text header)"
    return "time assumed (SEG-Y default); confirm with the data owner"


def _amplitude_stats(handle, max_traces: int = 2000) -> Dict[str, float]:
    count = handle.tracecount
    if count == 0:
        return {}
    picks = np.unique(np.linspace(0, count - 1, min(count, max_traces)).astype(int))
    data = np.stack([np.asarray(handle.trace[int(i)], dtype=float) for i in picks])
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return {"traces_sampled": int(picks.size), "finite_fraction": 0.0}
    p01, p50, p99 = np.percentile(finite, [1, 50, 99])
    return {
        "traces_sampled": int(picks.size),
        "finite_fraction": float(finite.size / data.size),
        "zero_fraction": float(np.mean(finite == 0.0)),
        "min": float(finite.min()),
        "max": float(finite.max()),
        "rms": float(np.sqrt(np.mean(finite**2))),
        "p01": float(p01),
        "p50": float(p50),
        "p99": float(p99),
    }


def inspect_segy(
    path,
    header_bytes: Sequence[Tuple[int, int]] = DEFAULT_HEADER_BYTES,
    coordinate_source: str = "cdp",
) -> SegyGeometry:
    """Describe a SEG-Y file: sizes, sampling, geometry, coordinates, CRS hints, amplitudes.

    Raises:
        FileNotFoundError: if the file does not exist.
        ImportError: if segyio is not installed.
    """
    segyio = segyio_module()
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"SEG-Y file not found: {file_path}")
    with open_segy(file_path, header_bytes) as (handle, used, note):
        text = segyio.tools.wrap(handle.text[0]) if handle.text else ""
        samples = np.asarray(handle.samples, dtype=float)
        interval = float(segyio.tools.dt(handle) / 1000.0) if samples.size > 1 else 0.0
        geometry = SegyGeometry(
            path=str(file_path),
            sha256=file_sha256(file_path),
            trace_count=int(handle.tracecount),
            sample_count=int(samples.size),
            sample_interval=interval,
            samples=samples,
            sample_format=str(handle.format),
            structured=used is not None,
            header_bytes=used,
            coordinate_source=coordinate_source,
            text_header=text,
            crs_hints=_crs_hints(text),
            domain=_domain(text),
        )
        if used is not None:
            geometry.inlines = np.asarray(handle.ilines)
            geometry.crosslines = np.asarray(handle.xlines)
            geometry.offsets = [int(o) for o in handle.offsets]
            geometry.sorting = {1: "crossline", 2: "inline"}.get(
                handle.sorting, str(handle.sorting)
            )
            if len(geometry.offsets) > 1:
                geometry.warnings.append(
                    f"pre-stack data: {len(geometry.offsets)} offsets per bin ({geometry.offsets}); "
                    "sections use the first offset unless offset= is given, slices and amplitude "
                    "statistics mix offsets"
                )
        else:
            geometry.warnings.append(
                "no regular inline/crossline geometry found; treated as unstructured "
                f"({note})"
            )
        unit_code = handle.bin[segyio.BinField.MeasurementSystem]
        geometry.coordinate_unit = {1: "m", 2: "ft"}.get(
            unit_code, "unknown (binary header byte 3255)"
        )
        x, y, scalars = trace_coordinates(handle, coordinate_source)
        geometry.coordinate_scalars = sorted({int(s) for s in np.unique(scalars)})
        if np.allclose(x, 0) and np.allclose(y, 0):
            geometry.warnings.append(
                f"{coordinate_source} coordinates are all zero; try another source"
            )
        else:
            geometry.bbox = {
                "xmin": float(x.min()),
                "xmax": float(x.max()),
                "ymin": float(y.min()),
                "ymax": float(y.max()),
            }
            if used is not None:
                geometry.bin_spacing = _bin_spacing(handle, x, y)
        if not geometry.crs_hints:
            geometry.warnings.append(
                "no CRS found in the text header; obtain it from the data owner"
            )
        geometry.amplitude = _amplitude_stats(handle)
    return geometry


def _bin_spacing(handle, x: np.ndarray, y: np.ndarray) -> Optional[Dict[str, float]]:
    """Inline and crossline bin spacing from the first two lines of the survey."""
    ilines, xlines = np.asarray(handle.ilines), np.asarray(handle.xlines)
    if ilines.size < 2 or xlines.size < 2 or len(handle.offsets) > 1:
        return None
    n_x = xlines.size
    if handle.sorting == 2:  # inline sorted: trace = i * n_xlines + j
        along_xline = np.hypot(x[1] - x[0], y[1] - y[0])
        across = np.hypot(x[n_x] - x[0], y[n_x] - y[0])
    else:
        n_i = ilines.size
        across = np.hypot(x[1] - x[0], y[1] - y[0])
        along_xline = np.hypot(x[n_i] - x[0], y[n_i] - y[0])
    return {
        "crossline_step": float(along_xline / max(abs(xlines[1] - xlines[0]), 1)),
        "inline_step": float(across / max(abs(ilines[1] - ilines[0]), 1)),
    }
