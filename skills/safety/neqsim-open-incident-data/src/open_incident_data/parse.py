"""Parse the BSEE investigation and structure CSV files."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional, Tuple

from .sources import SOURCES


@dataclass(frozen=True)
class Investigation:
    """One BSEE accident investigation."""

    occurred: date
    lease: str
    area: str
    block: str
    labels: Tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Structure:
    """One platform structure with its installed period."""

    number: str
    area: str
    kind: str
    major: bool
    manned_24h: bool
    installed: date
    removed: Optional[date]
    water_depth_ft: Optional[float]


def parse_date(text: str) -> Optional[date]:
    """Parse ``M/D/YYYY`` (as BSEE writes it); returns ``None`` for blank or malformed text."""
    value = (text or "").strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def split_labels(accident_type: str) -> Tuple[str, ...]:
    """Split a composite label such as ``"- Fire - Required Muster "`` into ``("Fire", "Required Muster")``."""
    text = (accident_type or "").strip()
    if text.startswith("-"):
        text = text[1:]
    return tuple(part.strip() for part in re.split(r"\s+-\s+", text.strip()) if part.strip())


def _rows(text: str, source: str) -> List[dict]:
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in SOURCES[source]["columns"] if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"{source} file lacks expected columns {missing}; BSEE may have changed the format")
    return list(reader)


def parse_investigations(text: str) -> List[Investigation]:
    """Parse ``mv_acc_investigations.txt``; rows with an unreadable date are dropped."""
    out: List[Investigation] = []
    for row in _rows(text, "investigations"):
        occurred = parse_date(row["DATE_OCCURRED"])
        if occurred is None:
            continue
        area, _, block = (row["AREA_BLOCK"] or "").strip().partition(" ")
        out.append(Investigation(occurred, row["LEASE_NUMBER"].strip(), area, block.strip(),
                                 split_labels(row["ACCIDENT_TYPE"]), row["STATUS"].strip()))
    return out


def parse_structures(text: str) -> List[Structure]:
    """Parse ``mv_platstruc_structures.txt``; structures without an install date are dropped."""
    out: List[Structure] = []
    for row in _rows(text, "structures"):
        installed = parse_date(row["INSTALL_DATE"])
        if installed is None:
            continue
        try:
            depth: Optional[float] = float(row["WATER_DEPTH"])
        except ValueError:
            depth = None
        out.append(Structure(row["STRUCTURE_NUMBER"].strip(), row["AREA_CODE"].strip(), row["STRUC_TYPE_CODE"].strip(),
                             row["MAJ_STRUC_FLAG"].strip().upper() == "Y", row["MANNED_24_HR_FL"].strip().upper() == "Y",
                             installed, parse_date(row["REMOVAL_DATE"]), depth))
    return out
