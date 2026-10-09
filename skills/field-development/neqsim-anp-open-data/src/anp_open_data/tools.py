"""Unit, date, CRS and file-reading helpers for ANP open data."""

from __future__ import annotations

import calendar
import csv
import math
from typing import Dict, Iterable, List, Optional

OIL_M3_TO_BBL = 6.28981
SCF_PER_SM3 = 35.3147

_OIL_TO_M3 = {"m3": 1.0, "bbl": 1.0 / OIL_M3_TO_BBL, "mmbbl": 1.0e6 / OIL_M3_TO_BBL}
_GAS_TO_SM3 = {
    "sm3": 1.0,
    "m3": 1.0,
    "thousand_m3": 1.0e3,
    "million_m3": 1.0e6,
    "mmscf": 1.0e6 / SCF_PER_SM3,
}


def oil_volume(value: float, from_unit: str, to_unit: str) -> float:
    """Convert an oil or condensate volume between m3, bbl and mmbbl."""
    try:
        return value * _OIL_TO_M3[from_unit] / _OIL_TO_M3[to_unit]
    except KeyError as exc:
        raise ValueError(f"unknown oil unit {exc}; use one of {sorted(_OIL_TO_M3)}") from None


def gas_volume(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a gas volume between sm3, thousand_m3, million_m3 and mmscf.

    The units are only as exact as the file's stated standard conditions; check the
    dataset documentation before using the result in a fiscal or custody context.
    """
    try:
        return value * _GAS_TO_SM3[from_unit] / _GAS_TO_SM3[to_unit]
    except KeyError as exc:
        raise ValueError(f"unknown gas unit {exc}; use one of {sorted(_GAS_TO_SM3)}") from None


def monthly_to_daily(volume: float, year: int, month: int) -> float:
    """Convert a monthly volume to an average daily rate using the real month length."""
    if not 1 <= month <= 12:
        raise ValueError("month must be 1..12")
    return volume / calendar.monthrange(year, month)[1]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km between two points given as lon/lat in degrees."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def check_crs(declared: Optional[str]) -> Dict[str, object]:
    """Classify a declared CRS before any distance or area is computed.

    Geographic systems (EPSG:4326 and EPSG:4674) hold degrees: use ``haversine_km`` for point
    distances or reproject to a projected CRS before computing lengths and areas.
    """
    if not declared:
        return {"status": "unknown", "action": "find the CRS in the dataset metadata before use"}
    code = declared.strip().upper().replace(" ", "")
    if code in ("EPSG:4326", "EPSG:4674"):
        return {
            "status": "geographic",
            "crs": code,
            "action": "use haversine_km for distances or reproject to a projected CRS first",
        }
    return {"status": "other", "crs": code, "action": "confirm units are metres before computing lengths"}


def load_table(
    path: str,
    mapping: Dict[str, str],
    sep: str = ";",
    decimal: str = ",",
    encoding: str = "utf-8-sig",
    numeric: Iterable[str] = (),
) -> List[Dict[str, object]]:
    """Read a delimited file and rename columns by ``mapping`` {wanted_name: file_header}.

    Raises ``KeyError`` naming every missing header, so a renamed column is a loud failure.
    ``numeric`` lists wanted names to convert to float using ``decimal``. The separator,
    decimal mark and encoding are inputs because they differ between datasets; check the file.
    """
    numeric = set(numeric)
    with open(path, newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle, delimiter=sep)
        headers = reader.fieldnames or []
        missing = [h for h in mapping.values() if h not in headers]
        if missing:
            raise KeyError(f"headers not found in file: {missing}; file has {headers}")
        rows = []
        for raw in reader:
            row: Dict[str, object] = {}
            for name, header in mapping.items():
                value = raw[header]
                if name in numeric:
                    text = (value or "").strip().replace(" ", "")
                    if decimal != ".":
                        text = text.replace(".", "").replace(decimal, ".")
                    row[name] = float(text) if text else float("nan")
                else:
                    row[name] = value
            rows.append(row)
    return rows
