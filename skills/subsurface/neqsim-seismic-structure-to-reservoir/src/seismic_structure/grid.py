"""Simple layered OPM Flow grid between a top and a base surface (DX/DY/DZ/TOPS geometry).

The grid is a local Cartesian box per surface node: map rotation is dropped
(DX and DY are the node spacings) and layers split each column evenly between
top and base. That keeps structure, thickness and volumes, and is enough for
screening depletion and injection; faults and lateral property trends are not
represented. Property arrays go through the reservoir-model-builder checks
(``build_static_model_deck_input``) when that skill is installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .closure import Closure, _base_values
from .surface import Surface


@dataclass
class LayeredGrid:
    """Keyword arrays in Eclipse order (i fastest, then j, then k)."""

    nx: int
    ny: int
    nz: int
    keywords: dict[str, np.ndarray]
    contact_m: float | None
    summary: dict[str, float] = field(default_factory=dict)
    validation: dict | None = None
    notes: list[str] = field(default_factory=list)

    def write(self, path) -> Path:
        """Write a GRID-section include with DX, DY, DZ, TOPS, ACTNUM and properties.

        RUNSPEC must carry ``DIMENS nx ny nz /``; the header states it.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"-- Layered grid from seismic_structure: DIMENS {self.nx} {self.ny} {self.nz} /",
                 "-- Local Cartesian geometry; map rotation not represented. Screening only."]
        lines += [f"-- {note}" for note in self.notes]
        for key, values in self.keywords.items():
            integer = key == "ACTNUM"
            lines.append(key)
            flat = np.asarray(values).ravel()
            for k in range(0, flat.size, 8):
                chunk = flat[k:k + 8]
                lines.append(" ".join(str(int(v)) if integer else f"{v:.6g}" for v in chunk))
            lines.append("/")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out


def build_layered_grid(top: Surface, nz: int = 10, base: Surface | None = None,
                       thickness_m: float | None = None, coarsen: int = 1,
                       porosity: float = 0.2, net_to_gross: float = 1.0, permeability_mD: float = 100.0,
                       kv_kh: float = 0.1, contact_m: float | None = None,
                       closure: Closure | None = None,
                       water_saturation: float | None = None) -> LayeredGrid:
    """Build DX/DY/DZ/TOPS/ACTNUM/PORO/NTG/PERM arrays between top and base.

    Args:
        top: depth surface of the reservoir top.
        nz: number of layers (proportional split of each column).
        base: base surface; else ``thickness_m`` below the top.
        thickness_m: constant gross thickness when there is no base surface.
        coarsen: average ``coarsen x coarsen`` surface nodes per cell.
        porosity, net_to_gross, permeability_mD, kv_kh: constant properties (screening).
        contact_m: hydrocarbon contact for the volume check.
        closure: closure from :func:`analyse_closure`; restricts the volume check to the trap.
        water_saturation: when given, ``hcpv_mm3`` is reported; otherwise only the net pore volume.

    Raises:
        ValueError: without a base or thickness, or for a time surface.
    """
    if top.domain != "depth":
        raise ValueError("grid needs a depth top surface")
    if base is None and thickness_m is None:
        raise ValueError("give a base surface or thickness_m")
    base_values = _base_values(top, base, thickness_m)
    trap = None
    if closure is not None and contact_m is not None:
        trap = closure.region(contact_m, top.values.shape)
    top_s, base_s = top, Surface(top.xori, top.yori, top.xinc, top.yinc, base_values, top.rotation, top.yflip)
    if coarsen > 1:
        top_s, base_s = top.coarsen(coarsen), base_s.coarsen(coarsen)
        if trap is not None:
            nc, nr = top_s.values.shape
            block = trap[: nc * coarsen, : nr * coarsen].reshape(nc, coarsen, nr, coarsen)
            trap = block.mean(axis=(1, 3)) >= 0.5
    t, b = top_s.values, base_s.values
    nx, ny = t.shape
    h = b - t
    active_col = np.isfinite(t) & np.isfinite(h) & (h > 0)
    tt, hh = np.where(active_col, t, 0.0), np.where(active_col, h, 0.0)
    k = np.arange(nz)[:, None, None]
    dz = np.broadcast_to(hh / nz, (nz, nx, ny))
    tops = tt[None] + k * dz
    actnum = np.broadcast_to(active_col, (nz, nx, ny)).astype(int)

    def eclipse(a: np.ndarray) -> np.ndarray:  # (nz, nx, ny) -> i fastest, then j, then k
        return np.ascontiguousarray(np.transpose(a, (0, 2, 1))).ravel()

    ones = np.ones((nz, nx, ny))
    keywords = {
        "DX": eclipse(ones * top_s.xinc), "DY": eclipse(ones * top_s.yinc), "DZ": eclipse(np.where(actnum, dz, 1.0)),
        "TOPS": eclipse(tops), "ACTNUM": eclipse(actnum), "PORO": eclipse(ones * porosity),
        "NTG": eclipse(ones * net_to_gross), "PERMX": eclipse(ones * permeability_mD),
        "PERMY": eclipse(ones * permeability_mD), "PERMZ": eclipse(ones * permeability_mD * kv_kh),
    }
    grid = LayeredGrid(nx, ny, nz, keywords, contact_m)
    cell = top_s.xinc * top_s.yinc
    grid.summary = {"active_cells": int(actnum.sum()), "bulk_volume_mm3": float((hh * cell).sum() / 1e6),
                    "pore_volume_mm3": float((hh * cell).sum() * porosity * net_to_gross / 1e6)}
    if contact_m is not None:
        above = np.clip(np.minimum(b, contact_m) - t, 0.0, None)
        above = np.where(active_col if trap is None else (active_col & trap), above, 0.0)
        grid.summary["grv_above_contact_mm3"] = float(above.sum() * cell / 1e6)
        grid.summary["net_pore_volume_above_contact_mm3"] = (
            grid.summary["grv_above_contact_mm3"] * porosity * net_to_gross)
        if water_saturation is not None:
            grid.summary["hcpv_mm3"] = grid.summary["net_pore_volume_above_contact_mm3"] * (1.0 - float(water_saturation))
    grid.notes.append(f"{nx} x {ny} x {nz}; cell {top_s.xinc:g} x {top_s.yinc:g} m; constant properties")
    grid.validation = _validate_with_builder(grid)
    return grid


def _validate_with_builder(grid: LayeredGrid) -> dict | None:
    try:
        from reservoir_model_builder import (
            GridDimensions,
            StaticModelArrays,
            build_static_model_deck_input,
        )
    except ImportError:
        return None
    model = StaticModelArrays(GridDimensions(grid.nx, grid.ny, grid.nz, source="seismic_structure"))
    for key in ("PORO", "NTG", "PERMX", "PERMY", "PERMZ", "ACTNUM"):
        model.add(key, grid.keywords[key].tolist(), source="seismic_structure constant screening value")
    result = build_static_model_deck_input(model)
    return {"deck_writable": result.get("deck_writable"),
            "blocked_because": result.get("blocked_because"),
            "unusable": [v.get("keyword") for v in result.get("validations", []) if not v.get("usable")]}
