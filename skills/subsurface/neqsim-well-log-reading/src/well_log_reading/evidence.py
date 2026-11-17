"""Provenance-stamped hand-off records and folder scans for well-log files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .model import WellLog
from .readers import DEPTH_REFERENCE_KEYS, LOG_SUFFIXES, read_well_log

SCHEMA = "well_log_evidence.v1"


def to_evidence(log: WellLog) -> dict:
    """Return a JSON-serialisable ``well_log_evidence.v1`` record for one file.

    The record holds provenance (path, format, SHA-256, read time), header
    metadata and a curve inventory per frame. It carries no curve values; write
    those with :func:`write_frame_csv` when a downstream step needs them.
    Status is always ``unverified``: the reader proves the file was decoded, not
    that depth references, units or calibrations are correct.
    """
    frames = []
    for frame in log.frames:
        depth_indexed = frame.is_depth_indexed
        depth_curve = frame.depth_curve()
        index_range = None
        depth_range = None
        if frame.index.size:
            index_range = [float(np.nanmin(frame.index)), float(np.nanmax(frame.index))]
            if frame.has_depth:
                depth = frame.depth_m()
                depth_range = [float(np.nanmin(depth)), float(np.nanmax(depth))]
        frames.append(
            {
                "name": frame.name,
                "index_name": frame.index_name,
                "index_unit": frame.index_unit,
                "index_type": frame.index_type,
                "depth_indexed": depth_indexed,
                "depth_from_channel": depth_curve.name if depth_curve is not None else None,
                "index_range": index_range,
                "depth_range_m": depth_range,
                "samples": int(frame.index.size),
                "curves": frame.inventory(),
            }
        )
    return {
        "schema": SCHEMA,
        "status": "unverified",
        "depth_reference_hints": {
            key: value for key, value in log.metadata.items()
            if key.startswith("param.") and key[6:].upper() in DEPTH_REFERENCE_KEYS
        },
        "source": {
            "path": log.source_path,
            "format": log.source_format,
            "sha256": log.sha256,
            "read_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "reader": "dlisio" if log.source_format in ("dlis", "lis") else "built-in LAS 2.0",
        },
        "well_name": log.well_name,
        "field_name": log.field_name,
        "company": log.company,
        "metadata": dict(log.metadata),
        "frames": frames,
        "warnings": list(log.warnings),
        "checks_required": [
            "confirm depth reference (RKB/DF/MSL) and whether the index is MD or TVD",
            "confirm the well identity against the header, not the file name",
            "check units and environmental corrections before quantitative use",
        ],
    }


def write_frame_csv(log: WellLog, out_dir, frame_name: str | None = None) -> Path:
    """Write one frame's scalar curves as CSV (depth in metres when depth indexed)."""
    frame = log.frame(frame_name)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(log.source_path).stem
    path = out / f"{stem}__{frame.name.replace('/', '_').replace('@', '_')}.csv"
    frame.to_dataframe().to_csv(path)
    return path


def scan_folder(folder, recursive: bool = True, max_files: int = 500) -> list[dict]:
    """Read every DLIS/LIS/LAS file in a folder and return one evidence record each.

    The folder is only read. Files that fail are reported with an ``error``
    entry instead of stopping the scan, so one corrupt file never hides the rest.
    """
    root = Path(folder)
    pattern = "**/*" if recursive else "*"
    files = sorted(p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in LOG_SUFFIXES)
    records = []
    for path in files[:max_files]:
        try:
            records.append(to_evidence(read_well_log(path)))
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
