"""Trap geometry on a depth surface: crest, spill point, closure, area and gross rock volume.

The closure is found by a priority flood from the crest: nodes are added in
order of depth, and the running maximum depth is the level the trap must fill
to reach them. The first node that lets the fill escape (grid edge, outside a
footprint, or next to an undefined node when those leak) sets the spill depth.
The region above any contact shallower than the spill is exactly the set of
nodes reached below that level, so one flood gives the whole area-depth and
volume-depth curve with no contact stepping.

Undefined nodes are where a horizon was not picked: often faults, sometimes
poor data. They leak by default (conservative). Treating them as barriers
makes the trap fault-bounded, which is an interpretation decision.
"""

from __future__ import annotations

import heapq
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .surface import Surface

_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass
class Closure:
    """Result of a closure analysis on one depth surface."""

    crest_m: float
    crest_index: tuple[int, int]
    crest_xy: tuple[float, float]
    spill_m: float
    spill_index: tuple[int, int] | None
    spill_xy: tuple[float, float] | None
    spill_reason: str
    closed: bool
    order: np.ndarray  # flat node indices in fill order
    levels: np.ndarray  # fill level when each node was reached
    cell_area_m2: float
    undefined_nodes: str
    warnings: list[str] = field(default_factory=list)

    @property
    def relief_m(self) -> float:
        """Maximum column: spill depth minus crest depth."""
        return float(self.spill_m - self.crest_m)

    def region(self, contact_m: float, shape: tuple[int, int]) -> np.ndarray:
        """Boolean ``(ncol, nrow)`` mask of the closure above ``contact_m``."""
        mask = np.zeros(int(np.prod(shape)), dtype=bool)
        mask[self.order[self.levels < contact_m]] = True
        return mask.reshape(shape)


def find_crest(surface: Surface, near_xy: tuple[float, float] | None = None,
               footprint: np.ndarray | None = None) -> tuple[int, int]:
    """Return the crest node: the shallowest node, or the local high reached by climbing from ``near_xy``.

    Raises:
        ValueError: if no defined node is available.
    """
    z = surface.values
    allowed = np.isfinite(z) if footprint is None else (np.isfinite(z) & footprint)
    if not allowed.any():
        raise ValueError("no defined node to take as crest")
    if near_xy is None:
        flat = np.where(allowed, z, np.inf)
        return tuple(int(v) for v in np.unravel_index(int(np.argmin(flat)), z.shape))
    fi, fj = surface.to_index(near_xy[0], near_xy[1])
    i = int(np.clip(round(float(fi)), 0, surface.ncol - 1))
    j = int(np.clip(round(float(fj)), 0, surface.nrow - 1))
    if not allowed[i, j]:
        xs, ys = np.nonzero(allowed)
        k = int(np.argmin((xs - i) ** 2 + (ys - j) ** 2))
        i, j = int(xs[k]), int(ys[k])
    while True:  # steepest climb to a local high (smaller depth)
        best = (z[i, j], i, j)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                a, b = i + di, j + dj
                if 0 <= a < z.shape[0] and 0 <= b < z.shape[1] and allowed[a, b] and z[a, b] < best[0]:
                    best = (z[a, b], a, b)
        if best[1:] == (i, j):
            return i, j
        i, j = best[1], best[2]


def analyse_closure(surface: Surface, crest: tuple[int, int] | None = None,
                    near_xy: tuple[float, float] | None = None,
                    footprint: np.ndarray | None = None,
                    undefined_nodes: str = "leak",
                    min_neighbour_relief_m: float = 1.0) -> Closure:
    """Flood the trap from its crest and locate the spill point.

    Args:
        surface: depth surface (m, positive down).
        crest: crest node index; found with :func:`find_crest` when omitted.
        near_xy: pick the local high nearest this point (for one structure among several).
        footprint: optional boolean mask; leaving it counts as a spill (prospect outline).
        undefined_nodes: ``"leak"`` (default) or ``"barrier"`` (treat gaps as sealing faults).
        min_neighbour_relief_m: a high beyond a saddle must rise at least this much above the
            fill level to count as a separate structure (filters map noise).

    Raises:
        ValueError: for a time surface or an unknown ``undefined_nodes`` option.
    """
    if surface.domain != "depth":
        raise ValueError("closure needs a depth surface; convert time with a velocity model first")
    if undefined_nodes not in ("leak", "barrier"):
        raise ValueError("undefined_nodes must be 'leak' or 'barrier'")
    z = surface.values
    ncol, nrow = z.shape
    defined = np.isfinite(z)
    inside = defined if footprint is None else (defined & footprint)
    ci, cj = crest if crest is not None else find_crest(surface, near_xy, footprint)
    warnings: list[str] = []

    def escapes(i: int, j: int) -> str | None:
        if i in (0, ncol - 1) or j in (0, nrow - 1):
            return "grid edge"
        for di, dj in _NEIGHBOURS:
            a, b = i + di, j + dj
            if footprint is not None and defined[a, b] and not footprint[a, b]:
                return "footprint boundary"
            if not defined[a, b] and undefined_nodes == "leak":
                return "undefined node (possible fault or data gap)"
        return None

    heap = [(float(z[ci, cj]), ci, cj)]
    seen = np.zeros(z.shape, dtype=bool)
    seen[ci, cj] = True
    order: list[int] = []
    levels: list[float] = []
    level = float(z[ci, cj])
    spill_index, reason = None, "flood exhausted the connected surface"
    while heap:
        depth, i, j = heapq.heappop(heap)
        if depth < level - min_neighbour_relief_m:
            # The fill has passed a saddle and is climbing into a neighbouring high.
            spill_index, reason = (i, j), "saddle into a neighbouring high"
            break
        level = max(level, depth)
        why = escapes(i, j)
        if why is not None:
            spill_index, reason = (i, j), why
            break
        order.append(i * nrow + j)
        levels.append(level)
        for di, dj in _NEIGHBOURS:
            a, b = i + di, j + dj
            if inside[a, b] and not seen[a, b]:
                seen[a, b] = True
                heapq.heappush(heap, (float(z[a, b]), a, b))
    if spill_index is None:
        warnings.append("closure bounded only by undefined nodes or the footprint; spill set to the "
                        "deepest node reached")
    crest_m = float(z[ci, cj])
    closed = level > crest_m + 1e-9 and bool(order)
    if not closed:
        warnings.append(f"no closure: the surface leaks at the crest ({reason})")
    xy = surface.node_xy()
    spill_xy = None if spill_index is None else (float(xy[0][spill_index]), float(xy[1][spill_index]))
    return Closure(crest_m=crest_m, crest_index=(int(ci), int(cj)),
                   crest_xy=(float(xy[0][ci, cj]), float(xy[1][ci, cj])),
                   spill_m=float(level), spill_index=spill_index, spill_xy=spill_xy,
                   spill_reason=reason, closed=closed, order=np.asarray(order, dtype=np.int64),
                   levels=np.asarray(levels, dtype=float), cell_area_m2=surface.cell_area_m2,
                   undefined_nodes=undefined_nodes, warnings=warnings)


def _base_values(top: Surface, base: Surface | None, thickness_m: float | None) -> np.ndarray:
    if base is not None:
        if base.domain != "depth":
            raise ValueError("base surface must be in depth")
        b = base if base.same_geometry(top) else base.resample_to(top)
        return b.values
    if thickness_m is not None:
        if thickness_m <= 0:
            raise ValueError("thickness_m must be positive")
        return top.values + float(thickness_m)
    return np.full(top.values.shape, np.inf)  # reservoir as thick as the column


def volumes_at_contact(top: Surface, closure: Closure, contact_m: float,
                       base: Surface | None = None, thickness_m: float | None = None) -> dict[str, float]:
    """Area, gross rock volume and mean column depth above one contact.

    Gross rock volume is ``sum(max(0, min(base, contact) - top)) x cell area`` over the closure.
    Without a base or thickness the reservoir is as thick as the column (an upper bound).
    """
    flat_top = top.values.ravel()
    base_flat = _base_values(top, base, thickness_m).ravel()
    nodes = closure.order[closure.levels < contact_m]
    column = np.clip(np.minimum(base_flat[nodes], contact_m) - flat_top[nodes], 0.0, None)
    column = np.where(np.isfinite(column), column, 0.0)
    grv = float(column.sum() * closure.cell_area_m2)
    mid = flat_top[nodes] + 0.5 * column
    mean_depth = float((mid * column).sum() / column.sum()) if column.sum() > 0 else float("nan")
    return {"contact_m": float(contact_m), "area_km2": nodes.size * closure.cell_area_m2 / 1e6,
            "grv_mm3": grv / 1e6, "mean_column_m": float(column.mean()) if nodes.size else 0.0,
            "equivalent_thickness_m": grv / (nodes.size * closure.cell_area_m2) if nodes.size else 0.0,
            "hc_column_mean_depth_m": mean_depth, "nodes": int(nodes.size)}


def contact_sweep(top: Surface, closure: Closure, step_m: float = 5.0,
                  base: Surface | None = None, thickness_m: float | None = None) -> list[dict[str, float]]:
    """Area and gross rock volume for contacts from the crest down to the spill."""
    if step_m <= 0:
        raise ValueError("step_m must be positive")
    contacts = np.arange(closure.crest_m + step_m, closure.spill_m, step_m).tolist() + [closure.spill_m]
    rows = [{"contact_m": closure.crest_m, "area_km2": 0.0, "grv_mm3": 0.0, "mean_column_m": 0.0,
             "equivalent_thickness_m": 0.0, "hc_column_mean_depth_m": closure.crest_m, "nodes": 0}]
    return rows + [volumes_at_contact(top, closure, c, base, thickness_m)
                   for c in contacts if c > closure.crest_m]


def contact_for_volume(rows: Sequence[dict[str, float]], target_grv_mm3: float) -> dict[str, float] | None:
    """Interpolate the contact and area that give a target gross rock volume; None if it does not fit.

    ``rows`` come from :func:`contact_sweep` (first row is the crest with zero volume).
    """
    if not rows or target_grv_mm3 > rows[-1]["grv_mm3"] or target_grv_mm3 < rows[0]["grv_mm3"]:
        return None
    for previous, row in zip(rows, rows[1:]):
        if previous["grv_mm3"] <= target_grv_mm3 <= row["grv_mm3"]:
            span = row["grv_mm3"] - previous["grv_mm3"]
            t = 0.0 if span == 0 else (target_grv_mm3 - previous["grv_mm3"]) / span
            return {"contact_m": previous["contact_m"] + t * (row["contact_m"] - previous["contact_m"]),
                    "area_km2": previous["area_km2"] + t * (row["area_km2"] - previous["area_km2"])}
    return {"contact_m": rows[0]["contact_m"], "area_km2": rows[0]["area_km2"]}
