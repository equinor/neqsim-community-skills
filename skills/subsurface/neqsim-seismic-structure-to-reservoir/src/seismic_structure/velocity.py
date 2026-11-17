"""Time-to-depth conversion with a linear velocity function calibrated on well ties.

Interval velocity increases linearly with depth below the seismic reference
datum, ``V(z) = v0 + k z``. With one-way time ``t`` this gives

    z = (v0 / k) (exp(k t) - 1)      (k > 0)
    z = v0 t                         (k = 0, constant velocity)

and depth below MSL is ``datum_m + z``. One tie fixes ``v0`` for a given ``k``;
two or more ties also let ``k`` be fitted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from .surface import Surface


@dataclass
class VelocityModel:
    """Linear-in-depth velocity function and its calibration record."""

    v0: float
    k: float = 0.0
    datum_m: float = 0.0
    ties: list[tuple[float, float]] = field(default_factory=list)
    rms_error_m: float | None = None
    note: str = ""

    def depth(self, twt_ms) -> np.ndarray:
        """Depth (m below MSL, positive down) for two-way time in ms."""
        t = np.asarray(twt_ms, dtype=float) / 2000.0
        if abs(self.k) < 1e-9:
            z = self.v0 * t
        else:
            z = self.v0 / self.k * np.expm1(self.k * t)
        return self.datum_m + z

    def twt(self, depth_m) -> np.ndarray:
        """Two-way time in ms for depth below MSL (inverse of :meth:`depth`)."""
        z = np.asarray(depth_m, dtype=float) - self.datum_m
        if abs(self.k) < 1e-9:
            t = z / self.v0
        else:
            t = np.log1p(self.k * z / self.v0) / self.k
        return 2000.0 * t

    def as_dict(self) -> dict:
        """JSON-serialisable record."""
        return {"v0_m_per_s": self.v0, "k_per_s": self.k, "datum_m": self.datum_m,
                "ties": [list(t) for t in self.ties], "rms_error_m": self.rms_error_m,
                "note": self.note}


def _g(t: np.ndarray, k: float) -> np.ndarray:
    return t if abs(k) < 1e-9 else np.expm1(k * t) / k


def calibrate_velocity(ties: Sequence[tuple[float, float]], k: float | None = None,
                       datum_m: float = 0.0, k_range: tuple[float, float] = (0.0, 1.5)) -> VelocityModel:
    """Fit ``v0`` (and ``k`` when not given and there are two or more ties) to well ties.

    Args:
        ties: ``(twt_ms, depth_m_below_msl)`` pairs at the horizon or along a checkshot.
        k: fixed velocity gradient (1/s); fitted when None and ties allow, else 0.
        datum_m: seismic reference datum depth below MSL (0 for an MSL datum).
        k_range: search interval for ``k``.

    Raises:
        ValueError: with no ties, or with ties above the datum.
    """
    pairs = np.asarray(ties, dtype=float).reshape(-1, 2)
    if pairs.shape[0] == 0:
        raise ValueError("at least one (twt_ms, depth_m) tie is needed")
    t = pairs[:, 0] / 2000.0
    z = pairs[:, 1] - datum_m
    if (z <= 0).any() or (t <= 0).any():
        raise ValueError("ties must lie below the datum with positive time")

    def fit(gradient: float) -> tuple[float, float]:
        g = _g(t, gradient)
        v0 = float(np.dot(z, g) / np.dot(g, g))
        return v0, float(np.sqrt(np.mean((v0 * g - z) ** 2)))

    if k is None and pairs.shape[0] >= 2 and np.ptp(t) > 0:
        grid = np.linspace(k_range[0], k_range[1], 301)
        errors = [fit(value)[1] for value in grid]
        k_fit = float(grid[int(np.argmin(errors))])
        note = f"v0 and k fitted to {pairs.shape[0]} ties"
    else:
        k_fit = 0.0 if k is None else float(k)
        note = (f"v0 fitted to {pairs.shape[0]} tie(s) with k fixed at {k_fit:g}"
                + ("" if k is not None else " (one tie cannot resolve k)"))
    v0, rms = fit(k_fit)
    return VelocityModel(v0=v0, k=k_fit, datum_m=datum_m, ties=[tuple(p) for p in pairs.tolist()],
                         rms_error_m=rms, note=note)


def time_to_depth(surface: Surface, model: VelocityModel) -> Surface:
    """Convert a two-way-time surface (ms) to depth below MSL (m).

    Raises:
        ValueError: if the surface is already in depth.
    """
    if surface.domain != "time":
        raise ValueError(f"surface {surface.name!r} is in {surface.domain}, not time")
    depth = replace(surface, values=model.depth(surface.values), domain="depth", unit="m",
                    name=f"{surface.name}_depth", notes=list(surface.notes))
    depth.notes.append(
        f"depth-converted with V(z) = {model.v0:.0f} + {model.k:.3f} z m/s, datum {model.datum_m:g} m"
        + (f", tie RMS {model.rms_error_m:.1f} m" if model.rms_error_m is not None else ""))
    return depth
