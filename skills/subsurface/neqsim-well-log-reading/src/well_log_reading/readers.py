"""Readers for DLIS, LIS (through dlisio) and LAS 2.0 (built-in) well-log files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import numpy as np

from .model import LogCurve, LogFrame, WellLog

DEFAULT_NULL_VALUES = (-999.25, -999.0, -9999.0, -99999.0)
DLIS_SUFFIXES = (".dlis", ".dls")
LIS_SUFFIXES = (".lis", ".tif", ".lti", ".nti")
LAS_SUFFIXES = (".las",)
LOG_SUFFIXES = DLIS_SUFFIXES + LIS_SUFFIXES + LAS_SUFFIXES
#: Header parameters that describe the depth reference (permanent datum, log and drill
#: measured from, elevations of kelly bushing, drill floor and ground level, depth reference).
DEPTH_REFERENCE_KEYS = ("PDAT", "DREF", "LMF", "DMF", "EKB", "EDF", "EGL", "APD", "EPD")

_DLISIO_MISSING = (
    "reading {fmt} files needs the 'dlisio' package (equinor/dlisio, LGPL-3.0). It is declared "
    "by the neqsim-well-log-reading skill and installed by the plugin; in a source checkout run "
    "'<python> -m pip install dlisio' once. LAS files are read without it."
)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_format(path: Path) -> str:
    """Detect ``dlis``, ``lis`` or ``las`` from the suffix, then from the file content.

    Raises:
        ValueError: if the format cannot be recognised.
    """
    suffix = path.suffix.lower()
    if suffix in DLIS_SUFFIXES:
        return "dlis"
    if suffix in LAS_SUFFIXES:
        return "las"
    if suffix in LIS_SUFFIXES:
        return "lis"
    with open(path, "rb") as handle:
        head = handle.read(200)
    if head.lstrip().startswith(b"~V") or b"~VERSION" in head.upper():
        return "las"
    # A DLIS storage unit label carries "V1.00" and "RECORD" at fixed offsets.
    if head[4:9] == b"V1.00" and head[9:15].strip() == b"RECORD":
        return "dlis"
    raise ValueError(
        f"cannot recognise the well-log format of {path}; expected .dlis, .lis or .las. "
        "Pass fmt='dlis', 'lis' or 'las' if the suffix is non-standard."
    )


def _clean(values: np.ndarray, null_values: Sequence[float]) -> np.ndarray:
    """Return a float copy with absent values replaced by NaN (non-numeric arrays kept)."""
    if values.dtype.kind not in "iuf":
        return values
    out = np.array(values, dtype=float, copy=True)
    for null in null_values:
        out[np.isclose(out, null, rtol=0.0, atol=1e-6)] = np.nan
    return out


def read_well_log(
    path,
    fmt: Optional[str] = None,
    null_values: Sequence[float] = DEFAULT_NULL_VALUES,
    tolerant: bool = True,
) -> WellLog:
    """Read a DLIS, LIS or LAS file into a :class:`WellLog`.

    Args:
        path: file path.
        fmt: ``"dlis"``, ``"lis"`` or ``"las"``; detected when omitted.
        null_values: absent-value codes replaced by NaN in numeric curves.
        tolerant: for DLIS, log recoverable file errors as warnings instead of
            failing (truncated or vendor-quirky files are common).

    Returns:
        The well log with frames, curves, header metadata and provenance.

    Raises:
        FileNotFoundError: if the file does not exist.
        ImportError: if a DLIS/LIS file is read without dlisio installed.
        ValueError: if the format is unknown or the file cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"well-log file not found: {file_path}")
    kind = (fmt or detect_format(file_path)).lower()
    log = WellLog(
        source_path=str(file_path),
        source_format=kind,
        sha256=file_sha256(file_path),
    )
    if kind == "dlis":
        _read_dlis(file_path, log, null_values, tolerant)
    elif kind == "lis":
        _read_lis(file_path, log, null_values)
    elif kind == "las":
        _read_las(file_path, log, null_values)
    else:
        raise ValueError(
            f"unsupported well-log format {fmt!r}; use 'dlis', 'lis' or 'las'"
        )
    if not log.frames:
        log.warnings.append("no curve data found in the file")
    return log


# ---------------------------------------------------------------- DLIS


def _text(value) -> str:
    """Return a dlisio attribute (string, Longname object, list or None) as text."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(v) for v in value)
    return str(value).strip()


def _read_dlis(path: Path, log: WellLog, null_values, tolerant: bool) -> None:
    try:
        from dlisio import dlis  # noqa: PLC0415
        from dlisio.common import Actions, ErrorHandler  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(_DLISIO_MISSING.format(fmt="DLIS")) from exc

    handler = ErrorHandler(critical=Actions.LOG_ERROR) if tolerant else None
    with dlis.load(str(path), error_handler=handler) as files:
        logical_files = list(files)
        for lf_number, logical_file in enumerate(logical_files):
            for origin in logical_file.origins:
                log.well_name = log.well_name or _text(origin.well_name)
                log.field_name = log.field_name or _text(origin.field_name)
                log.company = log.company or _text(origin.company)
                for attr in (
                    "well_id",
                    "producer_name",
                    "product",
                    "creation_time",
                    "run_nr",
                ):
                    value = _text(getattr(origin, attr, None))
                    if value and attr not in log.metadata:
                        log.metadata[attr] = value
            for parameter in getattr(logical_file, "parameters", []):
                key = parameter.name.strip().upper()
                if key not in DEPTH_REFERENCE_KEYS:
                    continue
                try:
                    values = _text(
                        [
                            v.strip() if isinstance(v, str) else v
                            for v in parameter.values
                        ]
                    )
                    unit = (
                        _text(getattr(parameter.attic["VALUES"], "units", ""))
                        if values
                        else ""
                    )
                except Exception:  # noqa: BLE001 - parameter values may be undecodable
                    continue
                if values:
                    log.metadata.setdefault(f"param.{key}", f"{values} {unit}".strip())
            for frame in logical_file.frames:
                try:
                    data = frame.curves()
                except Exception as exc:  # noqa: BLE001 - dlisio raises many types
                    log.warnings.append(
                        f"frame {frame.name}: curves could not be read ({exc})"
                    )
                    continue
                channels = {ch.name: ch for ch in frame.channels}
                index_name = (
                    frame.index if frame.index in data.dtype.names else "FRAMENO"
                )
                index_channel = channels.get(index_name)
                name = (
                    frame.name
                    if len(logical_files) == 1
                    else f"{frame.name}@LF{lf_number}"
                )
                log_frame = LogFrame(
                    name=name,
                    index_name=index_name,
                    index_unit=_text(index_channel.units) if index_channel else "",
                    index=np.asarray(data[index_name], dtype=float),
                    index_type=_text(frame.index_type),
                )
                for column in data.dtype.names:
                    if column in ("FRAMENO", index_name):
                        continue
                    channel = channels.get(column)
                    log_frame.curves[column] = LogCurve(
                        name=column,
                        unit=_text(channel.units) if channel else "",
                        values=_clean(np.asarray(data[column]), null_values),
                        long_name=_text(channel.long_name) if channel else "",
                    )
                if "TIME" in log_frame.index_type.upper():
                    depth_curve = log_frame.depth_curve()
                    log.warnings.append(
                        f"frame {name} is time indexed; depth taken from channel {depth_curve.name}"
                        if depth_curve is not None
                        else f"frame {name} is time indexed and has no depth channel"
                    )
                log.frames.append(log_frame)


# ---------------------------------------------------------------- LIS

# LIS wellsite (CONS) mnemonics -> WellLog attribute or metadata key.
_LIS_WELLSITE = {"WN": "well_name", "FN": "field_name", "CN": "company"}


def _lis_wellsite(logical_file, log: WellLog) -> None:
    """Copy well, field and company from LIS wellsite-data tables (best effort)."""
    try:
        records = logical_file.wellsite_data()
    except Exception as exc:  # noqa: BLE001 - optional header information
        log.warnings.append(f"LIS wellsite data unreadable ({exc})")
        return
    for record in records:
        try:
            if not record.isstructured():
                continue
            table = record.table(simple=True)
        except Exception:  # noqa: BLE001 - malformed component blocks are common
            continue
        names = table.dtype.names or ()
        if "MNEM" not in names or "VALU" not in names:
            continue
        for row in table:
            mnem = _text(row["MNEM"]).upper()
            value = _text(row["VALU"])
            if not value:
                continue
            attr = _LIS_WELLSITE.get(mnem)
            if attr and not getattr(log, attr):
                setattr(log, attr, value)
            elif attr is None and mnem and mnem.lower() not in log.metadata:
                log.metadata[mnem.lower()] = value


def _read_lis(path: Path, log: WellLog, null_values) -> None:
    try:
        from dlisio import lis  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(_DLISIO_MISSING.format(fmt="LIS")) from exc

    with lis.load(str(path)) as files:
        for lf_number, logical_file in enumerate(files):
            _lis_wellsite(logical_file, log)
            for spec_number, dfsr in enumerate(logical_file.data_format_specs()):
                absent = getattr(dfsr, "absent_value", None)
                nulls = tuple(null_values) + (
                    (absent,) if isinstance(absent, (int, float)) else ()
                )
                units = {sb.mnemonic.strip(): _text(sb.units) for sb in dfsr.specs}
                for rate in sorted(set(dfsr.sample_rates())):
                    try:
                        data = lis.curves(
                            logical_file, dfsr, sample_rate=rate, strict=False
                        )
                    except (ValueError, NotImplementedError) as exc:
                        log.warnings.append(
                            f"LIS file {lf_number} spec {spec_number} rate {rate}: {exc}"
                        )
                        continue
                    names = list(data.dtype.names)
                    index_name = _text(dfsr.index_mnem) or names[0]
                    if index_name not in names:
                        stripped = {n.strip(): n for n in names}
                        index_name = stripped.get(index_name, names[0])
                    log_frame = LogFrame(
                        name=f"LF{lf_number}-DFSR{spec_number}-x{rate}",
                        index_name=index_name.strip(),
                        index_unit=_text(dfsr.index_units)
                        or units.get(index_name.strip(), ""),
                        index=np.asarray(data[index_name], dtype=float),
                        index_type="DEPTH",
                    )
                    for column in names:
                        if column == index_name:
                            continue
                        mnemonic = column.strip()
                        log_frame.curves[mnemonic] = LogCurve(
                            name=mnemonic,
                            unit=units.get(mnemonic, ""),
                            values=_clean(np.asarray(data[column]), nulls),
                        )
                    if log_frame.index.size == 0:
                        log.warnings.append(f"frame {log_frame.name} has no samples")
                    log.frames.append(log_frame)


# ---------------------------------------------------------------- LAS

_LAS_LINE = re.compile(r"^\s*([^.\s]+)\s*\.(\S*)\s*(.*?)\s*:\s*(.*)$")


def _parse_las_header(lines: Iterable[str]) -> List[tuple]:
    """Parse ``MNEM.UNIT  VALUE : DESCRIPTION`` lines into tuples."""
    rows = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _LAS_LINE.match(line)
        if match:
            rows.append(tuple(part.strip() for part in match.groups()))
    return rows


def _read_las(path: Path, log: WellLog, null_values) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = {}
    current = None
    for line in text.splitlines():
        if line.startswith("~"):
            current = line[1:2].upper()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    version = {
        row[0].upper(): row[2] for row in _parse_las_header(sections.get("V", []))
    }
    if version.get("VERS", "").startswith("3"):
        raise ValueError(f"{path} is LAS 3.0; only LAS 1.2 and 2.0 are supported")
    wrapped = version.get("WRAP", "NO").upper().startswith("Y")

    well = {}
    legacy = version.get("VERS", "2.0").startswith("1")
    for mnem, unit, value, description in _parse_las_header(sections.get("W", [])):
        # LAS 1.2 puts the value after the colon; 2.0 before it (description is a label).
        well[mnem.upper()] = (unit, (value or description) if legacy else value)
    log.well_name = well.get("WELL", ("", ""))[1]
    log.field_name = well.get("FLD", ("", ""))[1]
    log.company = well.get("COMP", ("", ""))[1]
    placeholders = [
        k
        for k, v in (
            ("WELL", log.well_name),
            ("FLD", log.field_name),
            ("COMP", log.company),
        )
        if v.strip().upper() in ("WELL", "FIELD", "COMPANY", "UNKNOWN", "N/A", "NA")
    ]
    if placeholders:
        log.warnings.append(
            f"placeholder header values for {placeholders}; confirm the well identity"
        )
    for key in ("UWI", "API", "CTRY", "SRVC", "DATE", "STRT", "STOP", "STEP"):
        if key in well and well[key][1]:
            unit = f" {well[key][0]}" if well[key][0] else ""
            log.metadata[key.lower()] = f"{well[key][1]}{unit}"
    nulls = tuple(null_values)
    if "NULL" in well:
        try:
            nulls = nulls + (float(well["NULL"][1]),)
        except ValueError:
            log.warnings.append(f"unreadable NULL value {well['NULL'][1]!r}")
    for mnem, unit, value, description in _parse_las_header(sections.get("P", [])):
        log.metadata[f"param.{mnem}"] = f"{value} {unit}".strip()

    curves = _parse_las_header(sections.get("C", []))
    if not curves:
        raise ValueError(f"{path} has no ~Curve section")
    tokens = " ".join(sections.get("A", [])).replace(",", " ").split()
    try:
        numbers = np.array([float(t) for t in tokens], dtype=float)
    except ValueError as exc:
        raise ValueError(
            f"{path}: non-numeric value in ~ASCII section ({exc})"
        ) from exc
    n_curves = len(curves)
    if numbers.size % n_curves:
        log.warnings.append(
            f"~ASCII has {numbers.size} values, not a multiple of {n_curves} curves; "
            "the last incomplete row was dropped"
        )
        numbers = numbers[: numbers.size - numbers.size % n_curves]
    data = numbers.reshape(-1, n_curves)
    if wrapped:
        log.metadata["wrap"] = "YES"

    index_mnem, index_unit = curves[0][0], curves[0][1]
    frame = LogFrame(
        name="LAS",
        index_name=index_mnem,
        index_unit=index_unit,
        index=data[:, 0].copy(),
        index_type=(
            "BOREHOLE-DEPTH" if index_unit.lower() not in ("s", "ms", "min") else "TIME"
        ),
    )
    for column, (mnem, unit, _value, description) in enumerate(curves[1:], start=1):
        name = mnem
        suffix = 1
        while name in frame.curves:
            name = f"{mnem}:{suffix}"
            suffix += 1
        frame.curves[name] = LogCurve(
            name=name,
            unit=unit,
            values=_clean(data[:, column], nulls),
            long_name=description,
        )
    log.frames.append(frame)
