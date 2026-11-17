"""Anti-collision scan with the ISCWSA separation-factor rule (Sawaryn et al., SPE-194090, 2019).

SF = (D - Rr - Ro - Sm) / (k * sqrt(sigma_S^2 + sigma_pa^2)), sigma_S^2 = n^T (Cr + Co) n, where D is the
centre-to-centre distance and n its unit vector. Default k = 3.5, Sm = 0.3 m, sigma_pa = 0.5 m.
Operator rules (k, thresholds, hole/casing radii, minimum separation) override these defaults.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass

import numpy as np

from .trajectory import Wellpath
from .uncertainty import ErrorModel


@dataclass
class SFRule:
    """Separation-factor rule and classification thresholds."""

    k_sigma: float = 3.5
    surface_margin_m: float = 0.3
    sigma_pa_m: float = 0.5
    stop_below: float = 1.0
    caution_below: float = 1.5
    ref_radius_m: float = 0.156
    offset_radius_m: float = 0.156

    def classify(self, sf: float) -> str:
        """STOP, CAUTION or OK."""
        if sf < self.stop_below:
            return "STOP"
        if sf < self.caution_below:
            return "CAUTION"
        return "OK"


def separation_factor(d: float, sigma_s2: float, rule: SFRule = SFRule()) -> float:
    """ISCWSA SF for a centre-to-centre distance ``d`` (m) and combined variance along n (m^2)."""
    return (d - rule.ref_radius_m - rule.offset_radius_m - rule.surface_margin_m) / (
        rule.k_sigma * math.sqrt(max(sigma_s2, 0.0) + rule.sigma_pa_m ** 2))


def _segments(offsets: Iterable[Wellpath], parents: Sequence[str], tie_md: float | None,
              model: ErrorModel, warnings: list[str]):
    names, A, B, CA, CB, MA, MB = [], [], [], [], [], [], []
    for w in offsets:
        if len(w.md) < 2:
            continue
        cov = w.cov
        if cov is None:
            cov = model.covariance(w.md, w.inc, w.az)
            warnings.append(f"{w.name}: no survey covariance, modelled with {model.name}")
        keep = np.ones(len(w.md) - 1, bool)
        if w.name in parents and tie_md is not None:
            keep &= w.md[1:] > tie_md + 1e-6
        for j in np.where(keep)[0]:
            names.append(w.name)
            A.append(w.xyz[j]); B.append(w.xyz[j + 1])
            CA.append(cov[j]); CB.append(cov[j + 1])
            MA.append(w.md[j]); MB.append(w.md[j + 1])
    return (np.array(names), np.array(A), np.array(B), np.array(CA), np.array(CB), np.array(MA), np.array(MB))


def scan(reference: Wellpath, offsets: Iterable[Wellpath], rule: SFRule = SFRule(),
         parents: Sequence[str] | None = None, from_md: float | None = None,
         model: ErrorModel | None = None) -> dict:
    """Closest-approach scan: every reference station from ``from_md`` against every offset segment.

    ``parents`` names the bores the reference shares hole with (sidetrack parent and its other
    sidetracks); their segments above the tie-in MD are skipped and their exit depth is reported.
    Default ``from_md`` is the tie-in for sidetracks, else the first station.
    Returns ``{"offsets": [...], "profile": [...], "warnings": [...], "rule": {...}}`` with offsets sorted by SF.
    """
    if reference.cov is None:
        raise ValueError("reference has no covariance: call add_model_covariance first")
    model = model or ErrorModel()
    parents = tuple(parents or ((reference.parent,) if reference.parent else ()))
    tie = reference.tie_md
    start_md = from_md if from_md is not None else (tie if tie is not None else float(reference.md[0]))
    warnings: list[str] = []
    names, A, B, CA, CB, MA, MB = _segments(offsets, parents, tie, model, warnings)
    result = {"offsets": [], "profile": [], "warnings": warnings, "rule": asdict(rule)}
    if len(names) == 0:
        warnings.append("no offset segments to scan")
        return result
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    uniq, inv = np.unique(names, return_inverse=True)
    best = {str(u): {"sf": math.inf} for u in uniq}
    track: dict[str, list] = {}
    r_sum = rule.ref_radius_m + rule.offset_radius_m + rule.surface_margin_m
    for i in np.where(reference.md > start_md + 1e-6)[0]:
        p, cr = reference.xyz[i], reference.cov[i]
        u = np.clip(((p - A) * AB).sum(1) / L2, 0, 1)
        q = A + u[:, None] * AB
        dvec = p - q
        D = np.sqrt((dvec ** 2).sum(1))
        n = dvec / np.maximum(D, 1e-9)[:, None]
        co = CA + u[:, None, None] * (CB - CA)
        sig2 = np.einsum("ki,kij,kj->k", n, co + cr[None], n)
        ell = rule.k_sigma * np.sqrt(np.maximum(sig2, 0) + rule.sigma_pa_m ** 2)
        sf = (D - r_sum) / ell
        order = np.lexsort((sf, inv))
        first = np.r_[0, np.where(np.diff(inv[order]) != 0)[0] + 1]
        kmin = int(np.argmin(sf))
        result["profile"].append({"md": float(reference.md[i]), "v": float(p[2]), "min_sf": float(sf[kmin]),
                                  "min_sf_offset": str(names[kmin]), "cc_m": float(D[kmin])})
        for f in first:
            k = order[f]
            w = str(names[k])
            if w in parents:
                track.setdefault(w, []).append((float(reference.md[i]), float(sf[k])))
            if sf[k] < best[w]["sf"]:
                best[w] = {"sf": float(sf[k]), "cc_m": float(D[k]), "ref_md": float(reference.md[i]),
                           "ref_v": float(p[2]), "offset_md": float(MA[k] + u[k] * (MB[k] - MA[k])),
                           "ellipse_sum_m": float(ell[k])}
    table = []
    for w, v in best.items():
        if not math.isfinite(v["sf"]):
            continue
        row = {"wellbore": w, **v, "status": rule.classify(v["sf"]), "parent_bore": w in parents}
        if row["parent_bore"]:
            row.update(parent_exit(track.get(w, []), rule))
        table.append(row)
    result["offsets"] = sorted(table, key=lambda x: x["sf"])
    return result


def parent_exit(track: Sequence, rule: SFRule = SFRule()) -> dict:
    """Exit depths from a parent bore: last MD with SF below STOP and CAUTION, and min SF after exit."""
    below_stop = [m for m, s in track if s < rule.stop_below]
    below_caution = [m for m, s in track if s < rule.caution_below]
    exit_md = max(below_caution) if below_caution else None
    after = [s for m, s in track if exit_md is None or m > exit_md]
    return {"last_md_below_stop": max(below_stop) if below_stop else None,
            "last_md_below_caution": exit_md,
            "min_sf_after_exit": round(min(after), 2) if after else None}


def governing(result: dict, include_parents: bool = False) -> dict | None:
    """Lowest-SF offset (non-parent by default)."""
    rows = [r for r in result["offsets"] if include_parents or not r["parent_bore"]]
    return rows[0] if rows else None


def pull_back_search(plan_fn: Callable[[np.ndarray], Wellpath], target, origin_en, offsets: Iterable[Wellpath],
                     rule: SFRule = SFRule(), distances: Sequence[float] = (0, 25, 50, 75, 100, 125, 150, 200, 250),
                     required_sf: float | None = None, **scan_kwargs) -> dict:
    """Move the target back towards ``origin_en`` along the approach azimuth until the governing
    non-parent SF reaches ``required_sf`` (default the CAUTION threshold).

    ``plan_fn(target_xyz) -> Wellpath`` must return a planned path *with covariance*.
    Returns the sweep table and the first acceptable pull-back (or None).
    """
    offsets = list(offsets)
    target = np.asarray(target, float)
    required = rule.caution_below if required_sf is None else required_sf
    approach = target[:2] - np.asarray(origin_en, float)
    approach = approach / np.linalg.norm(approach)
    rows, chosen = [], None
    for back in distances:
        tgt = target.copy()
        tgt[:2] -= back * approach
        try:
            wp = plan_fn(tgt)
        except ValueError as exc:
            rows.append({"pull_back_m": back, "error": str(exc)})
            continue
        res = scan(wp, offsets, rule, **scan_kwargs)
        g = governing(res)
        sf = g["sf"] if g else math.inf
        rows.append({"pull_back_m": back, "target": [round(float(x), 2) for x in tgt],
                     "governing_offset": g["wellbore"] if g else None, "governing_sf": round(sf, 2),
                     "td_md_m": round(float(wp.md[-1]), 1)})
        if chosen is None and sf >= required:
            chosen = {"pull_back_m": back, "target": [float(x) for x in tgt], "governing_sf": sf}
    return {"required_sf": required, "sweep": rows, "chosen": chosen}
