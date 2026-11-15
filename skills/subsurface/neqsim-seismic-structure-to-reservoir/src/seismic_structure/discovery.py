"""Find the structural data that exists in task folders and say which ladder rung it can serve.

Files are only read. Each candidate is classified by suffix and content:

* ``published_grid``     - Eclipse/OPM grids (``.EGRID``, ``.GRDECL``)
* ``depth_surface`` / ``time_surface`` - IRAP, ZMAP+ or XYZ horizons
* ``fault_data``         - files named as faults or fault sticks
* ``seismic``            - SEG-Y volumes (``.sgy``, ``.segy``)
* ``well_logs``          - DLIS, LIS, LAS
* ``well_ties``          - CSV/JSON with time and depth columns (checkshots, tops with TWT)
* ``well_tops``          - CSV with well, X, Y, formation and depth columns (no time)

:func:`geometry_attempts` turns the inventory into ``data_first_gate`` records
for the ``geometry`` ingredient of the reservoir-model-builder skill.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Union

from .io import infer_domain, sniff_format

SEISMIC_SUFFIXES = (".sgy", ".segy")
LOG_SUFFIXES = (".dlis", ".dls", ".lis", ".las")
GRID_SUFFIXES = (".egrid", ".grdecl", ".grid")
SURFACE_HINT_SUFFIXES = (".irap", ".irapasc", ".gri", ".zmap", ".zmp", ".xyz", ".pts", ".dat", ".txt", ".asc")
_FAULT_NAME = re.compile(r"fault|fsticks?|polygon", re.I)
_TIE_HEADERS = re.compile(r"twt|time", re.I)
_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
OWN_OUTPUT_MARKER = "structure_evidence.json"


def _is_own_output(item: Path, exclude: Sequence[Path]) -> bool:
    """True for files written by this workflow, which must never be read back as input."""
    parent = item.parent.resolve()
    if any(parent == ex or ex in parent.parents for ex in exclude):
        return True
    return (item.parent / OWN_OUTPUT_MARKER).exists()


def _iter_files(paths: Iterable[Union[str, Path]], max_files: int,
                exclude: Sequence[Path] = ()) -> List[Path]:
    found: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            for item in path.rglob("*"):
                if item.is_file() and not (_SKIP_DIRS & set(item.parts)) and not _is_own_output(item, exclude):
                    found.append(item)
                if len(found) >= max_files:
                    break
    return sorted(set(found))[:max_files]


def _csv_header(path: Path) -> List[str]:
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as handle:
            return next(csv.reader(handle), [])
    except OSError:
        return []


def _tie_file(path: Path) -> bool:
    if path.suffix.lower() == ".csv":
        joined = " ".join(_csv_header(path))
        return bool(_TIE_HEADERS.search(joined)) and "depth" in joined.lower()
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and "ties" in data
    return False


def _column(header: Sequence[str], pattern: str) -> Optional[str]:
    for name in header:
        if re.fullmatch(pattern, name.strip(), re.I):
            return name
    return None


def _tops_columns(header: Sequence[str]) -> Optional[Dict[str, str]]:
    columns = {
        "x": _column(header, r"x|x_?(utm|coord|m)?|easting"),
        "y": _column(header, r"y|y_?(utm|coord|m)?|northing"),
        "depth": _column(header, r"(tvd(ss|msl)?|depth|z)(_?m)?|tvdss_m|depth_m"),
        "formation": _column(header, r"formation|horizon|surface|top|pick|name"),
        "well": _column(header, r"well(bore)?(_?name)?|uwi"),
    }
    return columns if all(columns[k] for k in ("x", "y", "depth", "formation")) else None


def read_well_tops(path) -> List[dict]:
    """Read well tops (``well``, ``x``, ``y``, ``formation``, ``depth_m``) from a CSV with those columns.

    Depth is taken as given (TVDSS/MSL, positive down, is expected); the column name is kept for the record.
    """
    file_path = Path(path)
    with open(file_path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        columns = _tops_columns(reader.fieldnames or [])
        if columns is None:
            raise ValueError(f"{file_path} needs X, Y, depth and formation columns")
        tops = []
        for row in reader:
            try:
                tops.append({"well": (row.get(columns["well"]) or file_path.stem) if columns["well"] else file_path.stem,
                             "x": float(row[columns["x"]]), "y": float(row[columns["y"]]),
                             "formation": row[columns["formation"]].strip(), "depth_m": float(row[columns["depth"]]),
                             "depth_column": columns["depth"], "source": str(file_path)})
            except (TypeError, ValueError):
                continue
    return tops


def discover(paths: Sequence[Union[str, Path]], max_files: int = 2000,
             exclude: Sequence[Union[str, Path]] = ()) -> Dict[str, List[dict]]:
    """Inventory structural data under the given files or folders (read only).

    Folders holding this workflow's own output (``structure_evidence.json``) and the ``exclude``
    folders are skipped, so a tracked top written by an earlier run is never re-read as an input.

    Returns:
        A mapping from category to ``{"path", "kind", ...}`` records.
    """
    inventory: Dict[str, List[dict]] = {k: [] for k in (
        "published_grid", "depth_surface", "time_surface", "fault_data", "seismic", "well_logs", "well_ties",
        "well_tops")}
    excluded = [Path(p).resolve() for p in exclude]
    for path in _iter_files(paths, max_files, excluded):
        suffix = path.suffix.lower()
        record = {"path": str(path), "name": path.stem}
        if suffix in SEISMIC_SUFFIXES:
            inventory["seismic"].append(record)
        elif suffix in LOG_SUFFIXES:
            inventory["well_logs"].append(record)
        elif suffix in GRID_SUFFIXES:
            inventory["published_grid"].append(record)
        elif suffix in (".csv", ".json") and _tie_file(path):
            inventory["well_ties"].append(record)
        elif suffix == ".csv" and _tops_columns(_csv_header(path)):
            inventory["well_tops"].append(record)
        elif suffix in SURFACE_HINT_SUFFIXES:
            fmt = sniff_format(path)
            if fmt is None:
                continue
            if _FAULT_NAME.search(path.stem):
                inventory["fault_data"].append(dict(record, format=fmt))
                continue
            domain = infer_domain(path.stem)
            inventory[f"{domain}_surface"].append(dict(record, format=fmt, domain_guessed=True))
    return inventory


def choose_top_surface(inventory: Dict[str, List[dict]]) -> Optional[dict]:
    """Pick the most likely reservoir-top surface: a name with 'top', else the only candidate."""
    for key in ("depth_surface", "time_surface"):
        items = inventory.get(key, [])
        tops = [s for s in items if re.search(r"top", s["name"], re.I)]
        if len(tops) == 1:
            return dict(tops[0], domain=key.split("_")[0])
        if len(items) == 1:
            return dict(items[0], domain=key.split("_")[0])
    return None


def geometry_candidates(inventory: Dict[str, List[dict]]) -> Dict[str, bool]:
    """Which geometry ladder rungs have data in the inventory (availability, not an outcome)."""
    surfaces = inventory["depth_surface"] + inventory["time_surface"]
    return {
        "published_grid": bool(inventory["published_grid"]),
        "horizons_and_faults": len(surfaces) >= 2 and bool(inventory["fault_data"]),
        "structure_map": bool(surfaces) or bool(inventory["seismic"]),
        "well_tops": bool(inventory.get("well_tops")) or bool(inventory["well_ties"]),
        "assumed_block": True,
    }


def geometry_attempts(inventory: Dict[str, List[dict]], used: Optional[str] = None,
                      detail: str = "") -> List[dict]:
    """``data_first_gate`` records for the geometry ladder, down to the rung that was used.

    Rungs above ``used`` with no data found are ``absent``. Rungs above it whose data
    *was* found are deliberately left without a record: the gate then blocks with
    "never attempted" until the caller tries them (for example loads the published
    grid) and records ``used``, ``blocked`` (access or read failure) or a reason.
    Without ``used`` only the ``absent`` records are returned.

    Args:
        inventory: result of :func:`discover`.
        used: the rung actually used (``structure_map``, ``horizons_and_faults``, ...).
        detail: text for the used rung (for example "top tracked from seismic, screening").
    """
    available = geometry_candidates(inventory)
    attempts = []
    for source in ("published_grid", "horizons_and_faults", "structure_map", "well_tops", "assumed_block"):
        if source == used:
            attempts.append({"source": source, "outcome": "used", "detail": detail})
            break
        if not available[source]:
            attempts.append({"source": source, "outcome": "absent", "detail": "none found in the searched folders"})
    return attempts
