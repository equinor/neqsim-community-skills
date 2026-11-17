"""Regular 2-D surfaces (depth or two-way time) on a possibly rotated grid.

Geometry follows the common geomodelling convention (also used by xtgeo and by
surface-grid services): node ``(i, j)`` with ``i`` along the column axis and
``j`` along the row axis sits at

    x = xori + i*xinc*cos(r) - j*yinc*yflip*sin(r)
    y = yori + i*xinc*sin(r) + j*yinc*yflip*cos(r)

with ``r`` the rotation in degrees anticlockwise from east. Values have shape
``(ncol, nrow)``; undefined nodes are NaN. Depth is positive down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np


@dataclass
class Surface:
    """A regular surface grid with its geometry, domain and provenance."""

    xori: float
    yori: float
    xinc: float
    yinc: float
    values: np.ndarray
    rotation: float = 0.0
    yflip: int = 1
    name: str = "surface"
    domain: str = "depth"  # "depth" (m, positive down) or "time" (two-way time, ms)
    unit: str = "m"
    source: str = ""
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values, dtype=float)
        if self.values.ndim != 2:
            raise ValueError("surface values must be a 2-D (ncol, nrow) array")
        if self.xinc <= 0 or self.yinc <= 0:
            raise ValueError("xinc and yinc must be positive")
        if self.yflip not in (1, -1):
            raise ValueError("yflip must be 1 or -1")
        if self.domain not in ("depth", "time"):
            raise ValueError("domain must be 'depth' or 'time'")

    @property
    def ncol(self) -> int:
        """Number of nodes along the column (i) axis."""
        return int(self.values.shape[0])

    @property
    def nrow(self) -> int:
        """Number of nodes along the row (j) axis."""
        return int(self.values.shape[1])

    @property
    def cell_area_m2(self) -> float:
        """Plan area represented by one node, m2 (rotation does not change it)."""
        return float(self.xinc * self.yinc)

    @property
    def defined(self) -> np.ndarray:
        """Boolean mask of defined nodes."""
        return np.isfinite(self.values)

    def node_xy(self) -> tuple[np.ndarray, np.ndarray]:
        """Return x and y of every node, each of shape ``(ncol, nrow)``."""
        i, j = np.meshgrid(np.arange(self.ncol), np.arange(self.nrow), indexing="ij")
        return self._to_world(i.astype(float), j.astype(float))

    def _to_world(self, i, j):
        r = math.radians(self.rotation)
        u = np.asarray(i) * self.xinc
        v = np.asarray(j) * self.yinc * self.yflip
        return (self.xori + u * math.cos(r) - v * math.sin(r),
                self.yori + u * math.sin(r) + v * math.cos(r))

    def to_index(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """Return fractional node indices ``(i, j)`` of world coordinates."""
        r = math.radians(self.rotation)
        dx = np.asarray(x, dtype=float) - self.xori
        dy = np.asarray(y, dtype=float) - self.yori
        u = dx * math.cos(r) + dy * math.sin(r)
        v = -dx * math.sin(r) + dy * math.cos(r)
        return u / self.xinc, v / (self.yinc * self.yflip)

    def sample(self, x, y) -> np.ndarray:
        """Bilinear value at world coordinates; NaN outside the grid or next to undefined nodes."""
        fi, fj = self.to_index(x, y)
        fi, fj = np.atleast_1d(fi), np.atleast_1d(fj)
        out = np.full(fi.shape, np.nan)
        inside = (fi >= 0) & (fj >= 0) & (fi <= self.ncol - 1) & (fj <= self.nrow - 1)
        i0 = np.clip(np.floor(fi).astype(int), 0, max(self.ncol - 2, 0))
        j0 = np.clip(np.floor(fj).astype(int), 0, max(self.nrow - 2, 0))
        i1 = np.minimum(i0 + 1, self.ncol - 1)
        j1 = np.minimum(j0 + 1, self.nrow - 1)
        ti, tj = fi - i0, fj - j0
        v = self.values
        value = (v[i0, j0] * (1 - ti) * (1 - tj) + v[i1, j0] * ti * (1 - tj)
                 + v[i0, j1] * (1 - ti) * tj + v[i1, j1] * ti * tj)
        out[inside] = value[inside]
        return out

    def resample_to(self, target: Surface) -> Surface:
        """Return this surface sampled on the nodes of ``target`` (bilinear)."""
        x, y = target.node_xy()
        values = self.sample(x.ravel(), y.ravel()).reshape(target.values.shape)
        return replace(target, values=values, name=self.name, domain=self.domain,
                       unit=self.unit, source=self.source, notes=list(self.notes))

    def same_geometry(self, other: Surface, tol: float = 1e-6) -> bool:
        """True when both surfaces share nodes (origin, increments, rotation, size)."""
        return (self.values.shape == other.values.shape and self.yflip == other.yflip
                and all(abs(a - b) <= tol * max(1.0, abs(a)) for a, b in (
                    (self.xori, other.xori), (self.yori, other.yori), (self.xinc, other.xinc),
                    (self.yinc, other.yinc), (self.rotation, other.rotation))))

    def normalized(self) -> Surface:
        """Return an equivalent surface with ``yflip = 1`` (rows reversed, origin moved)."""
        if self.yflip == 1:
            return self
        x, y = self._to_world(0.0, float(self.nrow - 1))
        return replace(self, xori=float(x), yori=float(y), yflip=1,
                       values=self.values[:, ::-1].copy(), notes=list(self.notes))

    def coarsen(self, factor: int) -> Surface:
        """Average blocks of ``factor x factor`` nodes (NaN-aware); use for very large grids."""
        if factor <= 1:
            return self
        nc, nr = self.ncol // factor, self.nrow // factor
        if nc < 2 or nr < 2:
            raise ValueError(f"factor {factor} leaves fewer than 2 x 2 nodes")
        block = self.values[: nc * factor, : nr * factor].reshape(nc, factor, nr, factor)
        with np.errstate(all="ignore"):
            count = np.isfinite(block).sum(axis=(1, 3))
            total = np.nansum(block, axis=(1, 3))
            mean = np.where(count > 0, total / np.maximum(count, 1), np.nan)
        # Block centre: half a block minus half a node from the original origin.
        shift = 0.5 * (factor - 1)
        x, y = self._to_world(shift, shift)
        return replace(self, xori=float(x), yori=float(y), xinc=self.xinc * factor,
                       yinc=self.yinc * factor, values=mean,
                       notes=list(self.notes) + [f"coarsened by {factor}"])

    def smooth(self, cells: int = 1) -> Surface:
        """NaN-aware moving average over ``(2 cells + 1)`` squared nodes; undefined nodes stay undefined."""
        if cells <= 0:
            return self
        from scipy.ndimage import uniform_filter

        size = 2 * int(cells) + 1
        defined = np.isfinite(self.values)
        weight = uniform_filter(defined.astype(float), size=size, mode="nearest")
        total = uniform_filter(np.where(defined, self.values, 0.0), size=size, mode="nearest")
        with np.errstate(all="ignore"):
            values = np.where(defined & (weight > 0), total / weight, np.nan)
        return replace(self, values=values, notes=list(self.notes) + [f"smoothed {size} x {size} nodes"])

    def stats(self) -> dict[str, float | None]:
        """Min, max, mean and defined fraction of the values."""
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return {"min": None, "max": None, "mean": None, "defined_fraction": 0.0}
        return {"min": float(finite.min()), "max": float(finite.max()),
                "mean": float(finite.mean()),
                "defined_fraction": float(finite.size / self.values.size)}

    def describe(self) -> dict:
        """JSON-serialisable summary (geometry, domain, statistics, provenance)."""
        x, y = self.node_xy()
        defined = self.defined
        bbox = None
        if defined.any():
            bbox = {"xmin": float(x[defined].min()), "xmax": float(x[defined].max()),
                    "ymin": float(y[defined].min()), "ymax": float(y[defined].max())}
        return {"name": self.name, "domain": self.domain, "unit": self.unit,
                "ncol": self.ncol, "nrow": self.nrow, "xori": self.xori, "yori": self.yori,
                "xinc": self.xinc, "yinc": self.yinc, "rotation": self.rotation,
                "yflip": self.yflip, "bbox": bbox, "stats": self.stats(),
                "source": self.source, "notes": list(self.notes)}


def surface_from_function(func, xori: float, yori: float, xinc: float, yinc: float,
                          ncol: int, nrow: int, **kwargs) -> Surface:
    """Build a surface from ``func(x, y)`` evaluated on the nodes (tests and synthetic cases)."""
    base = Surface(xori, yori, xinc, yinc, np.zeros((ncol, nrow)), **kwargs)
    x, y = base.node_xy()
    base.values = np.asarray(func(x, y), dtype=float)
    return base
