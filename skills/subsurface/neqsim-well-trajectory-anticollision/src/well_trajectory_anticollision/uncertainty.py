"""Illustrative position-uncertainty model for screening anti-collision.

This is a REDUCED, systematic-only MWD model in the spirit of the ISCWSA error model (Williamson 2000;
ISCWSA OWSG set). It is not a certified tool code. Each term is propagated as fully correlated along the
new hole: e_k(md) = sum over stations of (dP/d term) * sigma_k, and Cov = sum_k e_k e_k^T (E, N, V).
Prefer the operator's definitive-survey covariances for offsets and use this model only for planned hole
or offsets without covariances, after checking it against a reference covariance (see
:func:`compare_growth`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .trajectory import Wellpath, tangent


def _default_terms(b_total_nt: float, dip_deg: float) -> dict[str, tuple[str, float]]:
    bh = b_total_nt * math.cos(math.radians(dip_deg))
    return {
        "DSF depth scale": ("md", 5.6e-4),
        "DREF depth reference": ("md0", 0.35),
        "XYM misalignment": ("inc", math.radians(0.1)),
        "SAG": ("inc_sin", math.radians(0.2)),
        "DEC declination": ("az", math.radians(0.36)),
        "DBH crustal/BH": ("az", 5000.0 / bh * math.pi / 180.0),
        "AMIL axial interference": ("az_amil", 220.0 / bh),
    }


@dataclass
class ErrorModel:
    """Reduced systematic MWD error model (1 sigma). ``terms`` maps name -> (kind, sigma).

    Kinds: ``md`` (depth scale), ``md0`` (constant depth reference), ``inc``, ``inc_sin`` (sag),
    ``az`` (declination/crustal), ``az_amil`` (axial interference, scales with sin I |sin A|).
    Defaults: total field 52000 nT and dip 76 deg (high-latitude North Sea order of magnitude);
    replace with site geomagnetic values.
    """

    b_total_nt: float = 52000.0
    dip_deg: float = 76.0
    terms: dict[str, tuple[str, float]] | None = None
    name: str = "reduced-MWD (illustrative)"
    _resolved: dict[str, tuple[str, float]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self._resolved = dict(self.terms) if self.terms else _default_terms(self.b_total_nt, self.dip_deg)

    def covariance(self, md, inc_rad, az_rad) -> np.ndarray:
        """Covariance growth (n, 3, 3) from the first station (zero at station 0)."""
        md = np.asarray(md, float)
        inc = np.asarray(inc_rad, float)
        az = np.asarray(az_rad, float)
        n = len(md)
        cov = np.zeros((n, 3, 3))
        acc = {k: np.zeros(3) for k in self._resolved}
        t = tangent(inc, az)
        for i in range(1, n):
            dmd = md[i] - md[i - 1]
            for j in (i - 1, i):
                ci, si, ca, sa = math.cos(inc[j]), math.sin(inc[j]), math.cos(az[j]), math.sin(az[j])
                d_inc = np.array([ci * sa, ci * ca, -si])
                d_az = np.array([si * ca, -si * sa, 0.0])
                for k, (kind, sig) in self._resolved.items():
                    if kind == "md":
                        acc[k] += 0.5 * dmd * t[j] * sig
                    elif kind == "inc":
                        acc[k] += 0.5 * dmd * d_inc * sig
                    elif kind == "inc_sin":
                        acc[k] += 0.5 * dmd * d_inc * sig * si
                    elif kind == "az":
                        acc[k] += 0.5 * dmd * d_az * sig
                    elif kind == "az_amil":
                        acc[k] += 0.5 * dmd * d_az * sig * si * abs(sa)
            c = np.zeros((3, 3))
            for k, (kind, sig) in self._resolved.items():
                e = t[i] * sig if kind == "md0" else acc[k]
                c += np.outer(e, e)
            cov[i] = c
        return cov


def add_model_covariance(wp: Wellpath, model: ErrorModel | None = None, from_md: float | None = None) -> Wellpath:
    """Add model covariance growth from ``from_md`` (default: the tie-in, else the first station).

    Existing covariance at ``from_md`` is carried forward as a constant base, so the tie-in uncertainty
    of a sidetrack is inherited from the parent definitive survey.
    """
    model = model or ErrorModel()
    if from_md is None:
        from_md = wp.tie_md if wp.tie_md is not None else float(wp.md[0])
    i0 = wp.station_index(from_md)
    base = np.zeros((len(wp.md), 3, 3)) if wp.cov is None else wp.cov.copy()
    if wp.cov is not None:
        base[i0:] = wp.cov[i0]
    base[i0:] += model.covariance(wp.md[i0:], wp.inc[i0:], wp.az[i0:])
    wp.cov = base
    return wp


def compare_growth(reference: Wellpath, model: ErrorModel | None = None, from_md: float | None = None,
                   samples: int = 6) -> list:
    """Compare model sqrt(trace) growth with the reference wellbore's own covariance growth below ``from_md``.

    Ratio > 1 means the model is more conservative than the reference survey program.
    """
    if reference.cov is None:
        raise ValueError("reference wellbore has no covariance")
    model = model or ErrorModel()
    i0 = reference.station_index(from_md if from_md is not None else float(reference.md[0]))
    mc = model.covariance(reference.md[i0:], reference.inc[i0:], reference.az[i0:])
    rows = []
    step = max(1, len(mc) // samples)
    for k in range(step, len(mc), step):
        ref = math.sqrt(max(float(np.trace(reference.cov[i0 + k] - reference.cov[i0])), 0.0))
        mod = math.sqrt(float(np.trace(mc[k])))
        rows.append({"md": float(reference.md[i0 + k]), "reference_sqrt_trace_m": round(ref, 2),
                     "model_sqrt_trace_m": round(mod, 2), "ratio": round(mod / ref, 2) if ref > 0 else None})
    return rows


def horizontal_major_sigma(cov: np.ndarray) -> float:
    """1-sigma horizontal major semi-axis (m) of a 3x3 E-N-V covariance."""
    return float(math.sqrt(max(np.linalg.eigvalsh(np.asarray(cov)[:2, :2]))))
