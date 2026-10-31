"""Normalise public regulator-style wellbore tables into the offset evidence tables.

The helpers read the column names of public wellbore tables (``wlbName``, ``wlbCasingDiameter``, ``wlbLotMudDencity``,
``wlbMD``, ``wlbEntryDate`` ...) and return rows for ``offset_casing_lot.csv``, ``offset_mud_weight.csv`` and
``offset_time_depth.csv``. They never fetch data; callers pass rows already read from a file or a service.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .offsets import TABLES

COLUMNS: Dict[str, List[str]] = {
    "casing_lot": ["well", "string", "hole_in", "casing_od_in", "shoe_md_m", "shoe_tvd_m", "tvd_basis", "depth_ref", "rkb_m", "water_depth_m",
                   "lot_fit_type", "lot_emw_sg", "status", "source", "date"],
    "mud": ["well", "md_m", "tvd_m", "mud_weight_sg", "mud_type", "depth_ref", "date", "status", "source"],
    "pressure": ["well", "md_m", "tvd_m", "pore_pressure_bar", "emw_sg", "method", "temperature_c", "depth_ref", "status", "source", "note"],
    "time_depth": ["well", "spud", "td_date", "days_total", "days_per_1000m", "td_md_m", "rig", "max_inc_deg", "status", "source"],
    "problems": ["well", "depth_m", "depth_ref", "event_type", "description", "status", "source", "tier"],
    "documents": ["well", "doc_type", "url_or_path", "access_status"],
}

_FRAC = re.compile(r"^\s*(\d+)?\s*(?:(\d+)\s*/\s*(\d+))?\s*(?:\"|in|inch)?\s*$")


def parse_inches(text: object) -> Optional[float]:
    """Parse a size such as ``13 3/8``, ``9 7/8"``, ``36``, ``17.5`` or ``3/4`` to decimal inches (None if empty or unparsable)."""
    if text is None:
        return None
    s = str(text).strip().replace(",", ".")
    if s == "" or s.lower() in ("nan", "none"):
        return None
    try:
        return float(s.strip('"'))
    except ValueError:
        pass
    m = _FRAC.match(s)
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    whole = float(m.group(1)) if m.group(1) else 0.0
    if m.group(2):
        den = float(m.group(3))
        if den == 0.0:
            return None
        whole += float(m.group(2)) / den
    return whole


def _f(x: object) -> Optional[float]:
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


def parse_date(text: object) -> Optional[date]:
    """Parse an ISO-style date or timestamp (``2014-04-08`` or ``2014-04-08T00:00:00``); None if empty or invalid."""
    if text is None or str(text).strip() == "":
        return None
    try:
        return datetime.fromisoformat(str(text).strip()[:19]).date()
    except ValueError:
        return None


def approx_tvd(md_m: float, td_md_m: Optional[float], td_tvd_m: Optional[float], kickoff_md_m: Optional[float] = None) -> Dict[str, object]:
    """Approximate TVD for a measured depth when no survey is available.

    Above ``kickoff_md_m`` (or for a TD whose TVD is within 0.5 percent of its MD) the well is treated as vertical. Below
    the kick-off the TVD is scaled linearly between the kick-off and TD. The result is DERIVED, never VERIFIED.
    """
    if td_md_m is None or td_tvd_m is None or td_md_m <= 0.0:
        return {"tvd_m": md_m, "basis": "ASSUMED_VERTICAL_NO_SURVEY"}
    if abs(td_md_m - td_tvd_m) / td_md_m < 0.005:
        return {"tvd_m": md_m, "basis": "VERTICAL_TD_MD_EQ_TVD"}
    ko = kickoff_md_m if kickoff_md_m is not None else 0.0
    if md_m <= ko:
        return {"tvd_m": md_m, "basis": "ABOVE_KICKOFF_VERTICAL"}
    frac = (md_m - ko) / max(1e-9, td_md_m - ko)
    return {"tvd_m": ko + frac * (td_tvd_m - ko), "basis": "DERIVED_LINEAR_BELOW_KICKOFF_APPROX"}


def normalise_casing_rows(rows: Sequence[Dict[str, str]], well_info: Optional[Dict[str, Dict[str, object]]] = None, source: str = "",
                          status: str = "VERIFIED", date_text: str = "") -> List[Dict[str, object]]:
    """Convert regulator-style casing and leak-off rows to ``offset_casing_lot.csv`` rows.

    Args:
        rows: dict rows with ``wlbName``, ``wlbCasingType``, ``wlbCasingDiameter``, ``wlbCasingDepth``, ``wlbHoleDiameter``,
            ``wlbHoleDepth``, ``wlbLotMudDencity`` and ``wlbFormationTestType``.
        well_info: optional per well dict with ``rkb_m``, ``water_depth_m``, ``td_md_m``, ``td_tvd_m``, ``kickoff_md_m``.
        source: provenance text copied to every row.
        status: status label copied to every row.
        date_text: retrieval date copied to every row.

    Returns:
        Rows with decimal inch sizes, ``lot_fit_type`` of LOT, FIT or none (a density of zero is no test), TVD derived from
        the well info (``tvd_basis`` says how) and the pilot-hole and open-hole rows kept with ``string`` set accordingly.
    """
    info = well_info or {}
    out: List[Dict[str, object]] = []
    for r in rows:
        well = (r.get("wlbName") or "").strip()
        md = _f(r.get("wlbCasingDepth"))
        if not well or md is None:
            continue
        typ = (r.get("wlbFormationTestType") or "").strip().upper()
        dens = _f(r.get("wlbLotMudDencity")) or 0.0
        if dens <= 0.0:
            typ, dens_out = "none", None
        else:
            typ = typ if typ in ("LOT", "FIT") else "FIT"
            dens_out = dens
        wi = info.get(well, {})
        tv = approx_tvd(md, _f(wi.get("td_md_m")), _f(wi.get("td_tvd_m")), _f(wi.get("kickoff_md_m")))
        out.append({
            "well": well, "string": (r.get("wlbCasingType") or "").strip() or "unspecified", "hole_in": parse_inches(r.get("wlbHoleDiameter")),
            "casing_od_in": parse_inches(r.get("wlbCasingDiameter")), "shoe_md_m": md, "shoe_tvd_m": round(float(tv["tvd_m"]), 1),
            "tvd_basis": tv["basis"], "depth_ref": "RKB", "rkb_m": wi.get("rkb_m"), "water_depth_m": wi.get("water_depth_m"),
            "lot_fit_type": typ, "lot_emw_sg": dens_out, "status": status, "source": source, "date": date_text,
        })
    return out


def normalise_mud_rows(rows: Sequence[Dict[str, str]], well_info: Optional[Dict[str, Dict[str, object]]] = None, source: str = "",
                       status: str = "VERIFIED", date_text: str = "") -> List[Dict[str, object]]:
    """Convert regulator-style mud rows (``wlbName``, ``wlbMD``, ``wlbMudWeightAtMD``, ``wlbMudType``) to ``offset_mud_weight.csv`` rows."""
    info = well_info or {}
    out: List[Dict[str, object]] = []
    for r in rows:
        well = (r.get("wlbName") or "").strip()
        md, mw = _f(r.get("wlbMD")), _f(r.get("wlbMudWeightAtMD"))
        if not well or md is None or mw is None or mw <= 0.0:
            continue
        wi = info.get(well, {})
        tv = approx_tvd(md, _f(wi.get("td_md_m")), _f(wi.get("td_tvd_m")), _f(wi.get("kickoff_md_m")))
        out.append({"well": well, "md_m": md, "tvd_m": round(float(tv["tvd_m"]), 1), "mud_weight_sg": mw, "mud_type": (r.get("wlbMudType") or "").strip(),
                    "depth_ref": "RKB", "date": (r.get("wlbMudDateMeasured") or "").strip()[:10] or date_text, "status": status, "source": source})
    return out


def normalise_wellbore_rows(rows: Sequence[Dict[str, str]], wells: Optional[Iterable[str]] = None, source: str = "",
                            status: str = "VERIFIED") -> List[Dict[str, object]]:
    """Convert regulator-style wellbore attribute rows to ``offset_time_depth.csv`` rows.

    ``days_total`` is completion date minus entry date (days from spud to rig release or abandonment, including every sidetrack
    reported on the same row); ``days_per_1000m`` divides by the total depth in km. A sidetrack row covers only the days after
    kick-off, so it is flagged in ``max_inc_deg`` and should not be mixed with a parent well without care.
    """
    keep = set(wells) if wells else None
    out: List[Dict[str, object]] = []
    for r in rows:
        well = (r.get("wlbWellboreName") or r.get("wlbName") or "").strip()
        if not well or (keep is not None and well not in keep):
            continue
        d0, d1 = parse_date(r.get("wlbEntryDate")), parse_date(r.get("wlbCompletionDate"))
        td = _f(r.get("wlbTotalDepth"))
        days = float((d1 - d0).days) if d0 and d1 else None
        stated = _f(r.get("wlbDrillingDays"))
        out.append({"well": well, "spud": d0.isoformat() if d0 else "", "td_date": d1.isoformat() if d1 else "",
                    "days_total": stated if stated else days, "days_per_1000m": (stated or days) / (td / 1000.0) if (stated or days) and td else None,
                    "td_md_m": td, "rig": (r.get("wlbDrillingFacility") or "").strip(), "max_inc_deg": _f(r.get("wlbMaxInclation")),
                    "status": status, "source": source})
    return out


EVENT_PATTERNS = [
    ("shallow_gas", re.compile(r"shallow gas", re.I)),
    ("kick", re.compile(r"\bkick(?!ed off)|well control|influx|water kick", re.I)),
    ("loss", re.compile(r"\bloss(?:es)?\b|lost circulation|mud losses|losses", re.I)),
    ("stuck", re.compile(r"\bstuck\b|got stuck|pack[- ]?off|tight hole|overpull", re.I)),
    ("instability", re.compile(r"instabil|collaps|cavings|washout|wellbore stability", re.I)),
    ("HPHT", re.compile(r"high pore pressure|overpress|high pressure|HPHT|high temperature", re.I)),
    ("sidetrack", re.compile(r"technical side-?track|side-?track(?:ed)? due|junked", re.I)),
    ("other", re.compile(r"lost time|delayed|weather|logging problem|equipment failure|tool failure", re.I)),
]


def tag_problem_sentences(well: str, text: str) -> List[Dict[str, str]]:
    """Split a wellbore-history text into sentences and tag the ones that describe operational problems.

    Negative statements ("no shallow gas was observed", "without significant problems") are returned with ``negated`` set to
    ``True`` so that a reviewer can drop them. Tags are keyword based and need human review.
    """
    clean = re.sub(r"<[^>]+>", " ", text or "")
    out: List[Dict[str, str]] = []
    for sent in re.split(r"(?<=[.!?])\s+", clean):
        s = sent.strip()
        if not s:
            continue
        neg = bool(re.search(r"\bno (?:significant |major |shallow )?(?:gas|problem|loss|kick|hole problems?)|without significant|not (?:observed|encountered|recorded)", s, re.I))
        for name, pat in EVENT_PATTERNS:
            if pat.search(s):
                out.append({"well": well, "event_type": name, "sentence": s, "negated": str(neg)})
                break
    return out


def write_table(rows: Sequence[Dict[str, object]], table: str, folder: Path) -> Path:
    """Write rows to the standard CSV for ``table`` (a key of :data:`COLUMNS`) in ``folder``; missing columns are blank."""
    cols = COLUMNS[table]
    path = Path(folder) / TABLES[table]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    return path
