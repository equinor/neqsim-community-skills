"""Provenance-stamped ``seismic_dataset_evidence.v1`` records and a folder scan."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .geometry import SegyGeometry, inspect_segy

SCHEMA = "seismic_dataset_evidence.v1"
SEGY_SUFFIXES = (".sgy", ".segy", ".sgy3d", ".seg")


def to_evidence(geometry: SegyGeometry) -> dict:
    """Return a JSON-serialisable evidence record for one SEG-Y file (no amplitudes).

    Status is ``unverified``: decoding proves the file is readable, not that
    the CRS, datum, domain (time or depth), polarity or processing are right.
    """
    survey = None
    if geometry.inlines is not None and geometry.crosslines is not None:
        survey = {
            "inline_range": [int(geometry.inlines.min()), int(geometry.inlines.max())],
            "crossline_range": [int(geometry.crosslines.min()), int(geometry.crosslines.max())],
            "inline_count": int(geometry.inlines.size),
            "crossline_count": int(geometry.crosslines.size),
            "sorting": geometry.sorting,
            "offsets": geometry.offsets,
            "header_bytes": list(geometry.header_bytes) if geometry.header_bytes else None,
            "bin_spacing": geometry.bin_spacing,
        }
    samples = geometry.samples
    return {
        "schema": SCHEMA,
        "status": "unverified",
        "source": {
            "path": geometry.path,
            "sha256": geometry.sha256,
            "read_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "reader": "segyio",
        },
        "trace_count": geometry.trace_count,
        "sampling": {
            "sample_count": geometry.sample_count,
            "interval": geometry.sample_interval,
            "first": float(samples[0]) if samples.size else None,
            "last": float(samples[-1]) if samples.size else None,
            "domain": geometry.domain,
            "format": geometry.sample_format,
        },
        "structured": geometry.structured,
        "survey": survey,
        "coordinates": {
            "source": geometry.coordinate_source,
            "unit": geometry.coordinate_unit,
            "scalars": geometry.coordinate_scalars,
            "bbox": geometry.bbox,
            "crs_hints_from_text_header": geometry.crs_hints,
        },
        "amplitude": geometry.amplitude,
        "text_header": geometry.text_header,
        "warnings": list(geometry.warnings),
        "checks_required": [
            "confirm CRS and datum with the data owner; text-header hints are not authoritative",
            "confirm time or depth domain, units and datum (MSL or seismic reference datum)",
            "confirm polarity and processing version before interpreting amplitudes",
        ],
    }


def scan_folder(folder, recursive: bool = True, max_files: int = 200) -> list[dict]:
    """Inspect every SEG-Y file in a folder (read only); failures are reported, not raised."""
    root = Path(folder)
    pattern = "**/*" if recursive else "*"
    files = sorted(p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in SEGY_SUFFIXES)
    records = []
    for path in files[:max_files]:
        try:
            records.append(to_evidence(inspect_segy(path)))
        except Exception as exc:  # noqa: BLE001 - report every failure and continue
            records.append({"schema": SCHEMA, "status": "error", "source": {"path": str(path)},
                            "error": f"{type(exc).__name__}: {exc}"})
    if len(files) > max_files:
        records.append({"schema": SCHEMA, "status": "truncated",
                        "note": f"{len(files) - max_files} more files not read (max_files={max_files})"})
    return records


def write_evidence(records, path) -> Path:
    """Write evidence records as indented JSON and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    return out
