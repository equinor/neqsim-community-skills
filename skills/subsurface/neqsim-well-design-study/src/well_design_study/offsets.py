"""Offset-well evidence: tables, pressure and strength calibration points, time-depth statistics and time-cost Monte Carlo."""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from .units import BAR_PER_SG_M

TABLES = {
    "casing_lot": "offset_casing_lot.csv",
    "mud": "offset_mud_weight.csv",
    "pressure": "offset_pressure_temp.csv",
    "time_depth": "offset_time_depth.csv",
    "problems": "offset_problems.csv",
    "documents": "offset_documents.csv",
}


def _num(x: object) -> Optional[float]:
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


def read_table(path: Path) -> List[Dict[str, str]]:
    """Read a CSV into dict rows (empty list if the file does not exist)."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def load_evidence(folder: Path) -> Dict[str, List[Dict[str, str]]]:
    """Load every standard offset table found in ``folder``."""
    return {k: read_table(Path(folder) / v) for k, v in TABLES.items()}


@dataclass
class CalibrationPoints:
    """Depth/EMW points extracted from offset wells, with provenance."""

    frac: List[Dict[str, object]] = field(default_factory=list)
    pore: List[Dict[str, object]] = field(default_factory=list)
    mud: List[Dict[str, object]] = field(default_factory=list)


def rebase_tvd(tvd_m: float, well_ref: Optional[Dict[str, float]], target: Optional[Dict[str, float]]) -> float:
    """Move a depth from the offset well's reference to the planned well's reference at equal depth below the mudline.

    ``well_ref`` and ``target`` hold ``rkb_m`` (air gap) and ``water_depth_m``. Without both, the depth is returned unchanged.
    Offsets in deeper or shallower water then compare at the same overburden and effective-stress depth instead of the same
    RKB depth.
    """
    if not well_ref or not target:
        return tvd_m
    try:
        ml_off = float(well_ref["rkb_m"]) + float(well_ref["water_depth_m"])
        ml_tgt = float(target["rkb_m"]) + float(target["water_depth_m"])
    except (KeyError, TypeError, ValueError):
        return tvd_m
    return ml_tgt + (tvd_m - ml_off)


def calibration_points(evidence: Dict[str, List[Dict[str, str]]], well_refs: Optional[Dict[str, Dict[str, float]]] = None,
                       target: Optional[Dict[str, float]] = None) -> CalibrationPoints:
    """Extract strength (LOT, FIT), pressure and mud-weight points.

    LOT points are fracture-pressure estimates; FIT points are lower bounds (formation held the test pressure).
    Pressure rows give pore EMW directly (``emw_sg``) or via ``pore_pressure_bar`` and ``tvd_m``. Mud weights are
    kept separately: a mud weight is an upper bound for pore pressure only when no influx was recorded.

    Args:
        evidence: tables from :func:`load_evidence`.
        well_refs: optional ``{well: {"rkb_m": air gap, "water_depth_m": ...}}``; with ``target`` the depths are rebased to
            equal depth below the mudline of the planned well (see :func:`rebase_tvd`). The original depth stays in ``tvd_orig_m``.
        target: reference of the planned well (``rkb_m``, ``water_depth_m``).

    Returns:
        Calibration points; rows whose ``lot_fit_type`` is ``none`` are skipped.
    """
    cp = CalibrationPoints()
    refs = well_refs or {}

    def shift(well: object, tvd: float) -> float:
        return rebase_tvd(tvd, refs.get(str(well)), target)

    for r in evidence.get("casing_lot", []):
        tvd, emw = _num(r.get("shoe_tvd_m")), _num(r.get("lot_emw_sg"))
        kind = (r.get("lot_fit_type") or "LOT").upper()
        if tvd and emw and kind != "NONE":
            cp.frac.append({"well": r.get("well"), "tvd_m": shift(r.get("well"), tvd), "tvd_orig_m": tvd, "emw_sg": emw, "kind": kind,
                            "source": r.get("source"), "tvd_basis": r.get("tvd_basis")})
    for r in evidence.get("pressure", []):
        tvd = _num(r.get("tvd_m"))
        emw = _num(r.get("emw_sg"))
        p = _num(r.get("pore_pressure_bar"))
        if tvd and emw is None and p:
            emw = p / (BAR_PER_SG_M * tvd)
        if tvd and emw:
            cp.pore.append({"well": r.get("well"), "tvd_m": shift(r.get("well"), tvd), "tvd_orig_m": tvd, "emw_sg": emw, "method": r.get("method"), "source": r.get("source")})
    for r in evidence.get("mud", []):
        tvd, mw = _num(r.get("tvd_m")), _num(r.get("mud_weight_sg"))
        if tvd and mw:
            cp.mud.append({"well": r.get("well"), "tvd_m": shift(r.get("well"), tvd), "tvd_orig_m": tvd, "mw_sg": mw, "source": r.get("source")})
    return cp


def envelope(points: Sequence[Dict[str, object]], key: str, bin_m: float = 250.0) -> List[Dict[str, float]]:
    """Min / median / max of ``key`` in depth bins (for low, base, high curves). Sparse bins are returned as they are."""
    bins: Dict[int, List[tuple]] = {}
    for p in points:
        z = float(p["tvd_m"])
        bins.setdefault(int(z // bin_m), []).append((z, float(p[key])))
    out = []
    for b in sorted(bins):
        v = [x[1] for x in bins[b]]
        z = [x[0] for x in bins[b]]
        out.append({"tvd_m": float(np.mean(z)), "min": min(v), "median": float(np.median(v)), "max": max(v), "n": len(v)})
    return out


def time_depth_stats(rows: Sequence[Dict[str, str]]) -> Dict[str, object]:
    """Days per 1000 m and total days across offset wells (empirical P10, P50, P90 with the n used)."""
    d1000, total = [], []
    for r in rows:
        v = _num(r.get("days_per_1000m"))
        t = _num(r.get("days_total"))
        if v:
            d1000.append(v)
        if t:
            total.append(t)

    def pct(a: List[float], p: float) -> Optional[float]:
        return float(np.percentile(a, p)) if a else None

    return {"n_days_per_1000m": len(d1000), "days_per_1000m_p10": pct(d1000, 10), "days_per_1000m_p50": pct(d1000, 50), "days_per_1000m_p90": pct(d1000, 90),
            "n_total": len(total), "days_total_p10": pct(total, 10), "days_total_p50": pct(total, 50), "days_total_p90": pct(total, 90)}


def problem_frequency(rows: Sequence[Dict[str, str]], wells: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, object]]:
    """Count recorded events by type, and the share of wells with at least one such event."""
    by: Dict[str, set] = {}
    count: Dict[str, int] = {}
    all_wells = set(wells or [r.get("well") for r in rows])
    for r in rows:
        t = (r.get("event type") or r.get("event_type") or "other").strip().lower()
        count[t] = count.get(t, 0) + 1
        by.setdefault(t, set()).add(r.get("well"))
    return {t: {"events": count[t], "wells_with_event": len(by[t]), "share_of_wells": len(by[t]) / max(1, len(all_wells))} for t in count}


@dataclass
class SectionTime:
    """Planned drilling time of a section in days at (P10, P50, P90) of the productive (no-NPT) time."""

    name: str
    p10: float
    p50: float
    p90: float


@dataclass
class NptEvent:
    """Non-productive-time event: occurrence probability and duration (days) at P10/P50/P90 when it occurs."""

    name: str
    probability: float
    p10: float
    p50: float
    p90: float


@dataclass
class CostBasis:
    """Cost inputs (MNOK). All are assumptions unless sourced; keep their provenance in the assumption register."""

    spread_mnok_per_day: float
    materials_mnok: float
    services_mnok: float
    fixed_mnok: float = 0.0
    materials_sigma: float = 0.10
    services_sigma: float = 0.15
    rate_sigma: float = 0.10


def _tri(rng: np.random.Generator, p10: float, p50: float, p90: float, n: int) -> np.ndarray:
    """Sample a lognormal-like skewed distribution fitted to P10, P50 and P90 (two-sided lognormal)."""
    p10, p50, p90 = max(1e-6, p10), max(1e-6, p50), max(1e-6, p90)
    z90 = 1.2815515655446004
    s_lo = (math.log(p50) - math.log(p10)) / z90
    s_hi = (math.log(p90) - math.log(p50)) / z90
    z = rng.standard_normal(n)
    return np.where(z < 0, p50 * np.exp(z * s_lo), p50 * np.exp(z * s_hi))


def monte_carlo(sections: Sequence[SectionTime], npt: Sequence[NptEvent], cost: CostBasis, n: int = 20000, seed: int = 20261031,
                common_sigma: float = 0.0) -> Dict[str, object]:
    """Monte Carlo of well days and cost: section times, NPT events, day-rate, materials and services uncertainty.

    ``common_sigma`` is the log-standard deviation of one performance factor that scales every section time of a sample
    together (same rig, crew and campaign). Independent sections alone make the total too narrow; calibrate ``common_sigma``
    so that the productive-time P10-P90 spread matches the offset wells.
    """
    rng = np.random.default_rng(seed)
    days_sec = {s.name: _tri(rng, s.p10, s.p50, s.p90, n) for s in sections}
    if common_sigma > 0.0:
        common = rng.lognormal(0.0, common_sigma, n)
        days_sec = {k: v * common for k, v in days_sec.items()}
    prod = sum(days_sec.values())
    npt_days = np.zeros(n)
    npt_by: Dict[str, np.ndarray] = {}
    for e in npt:
        occurs = rng.random(n) < e.probability
        dur = _tri(rng, e.p10, e.p50, e.p90, n) * occurs
        npt_by[e.name] = dur
        npt_days += dur
    days = prod + npt_days
    rate = cost.spread_mnok_per_day * rng.lognormal(0.0, cost.rate_sigma, n)
    mat = cost.materials_mnok * rng.lognormal(0.0, cost.materials_sigma, n)
    svc = cost.services_mnok * rng.lognormal(0.0, cost.services_sigma, n)
    total = days * rate + mat + svc + cost.fixed_mnok

    def pc(a: np.ndarray) -> Dict[str, float]:
        return {"p10": float(np.percentile(a, 10)), "p50": float(np.percentile(a, 50)), "p90": float(np.percentile(a, 90)), "mean": float(a.mean())}

    contrib = {k: float(np.corrcoef(v, total)[0, 1]) if v.std() > 0 else 0.0 for k, v in {**days_sec, **npt_by}.items()}
    return {"n": n, "seed": seed, "days_productive": pc(prod), "days_npt": pc(npt_days), "days_total": pc(days), "cost_mnok": pc(total),
            "section_days": {k: pc(v) for k, v in days_sec.items()}, "npt_days": {k: pc(v) for k, v in npt_by.items()},
            "correlation_with_cost": contrib, "samples_days": days, "samples_cost": total}
