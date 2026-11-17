"""End-to-end: find structural data, build a depth top, analyse the trap and hand off to the reservoir model.

Driven by a plain dict (or JSON file) so an agent can run it unattended:

```json
{
  "field_name": "Example", "fluid_type": "oil",
  "search_paths": ["<task>/step1_scope_and_research/references"],
  "top_surface": null, "surface_domain": null,
  "base_surface": null, "thickness_m": 60,
  "seismic": {"path": null, "seed": {"inline": 120, "crossline": 880, "twt_ms": 160},
              "well": {"x": 0, "y": 0, "top_depth_m": 2000}, "polarity": "auto"},
  "velocity": {"v0": 1800, "k": 0.4, "datum_m": 0} ,
  "contact_m": null, "target_grv_mm3": null, "crest_near": null,
  "undefined_nodes": "leak",
  "grid": {"nz": 10, "coarsen": 1, "porosity": 0.22, "net_to_gross": 0.8,
           "permeability_mD": 150, "kv_kh": 0.1},
  "out_dir": "<task>/step2_analysis/structure"
}
```

Every unknown is reported, never filled silently: a time surface without a
velocity model stops with ``status = "blocked"`` and the missing item, and a
contact that was not given is placed at the spill point with a warning.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .closure import (
    analyse_closure,
    contact_for_volume,
    contact_sweep,
    volumes_at_contact,
)
from .discovery import (
    choose_top_surface,
    discover,
    geometry_attempts,
    geometry_candidates,
    read_well_tops,
)
from .grid import build_layered_grid
from .io import read_surface, write_irap
from .surface import Surface
from .velocity import VelocityModel, calibrate_velocity, time_to_depth

SCHEMA = "structure_evidence.v1"
MAX_NODES = 2_000_000


def surface_roughness(surface: Surface) -> float | None:
    """Median absolute second difference along both axes (m): noise that dip does not explain."""
    z = surface.values
    parts = [
        np.abs(z[2:, :] - 2 * z[1:-1, :] + z[:-2, :]),
        np.abs(z[:, 2:] - 2 * z[:, 1:-1] + z[:, :-2]),
    ]
    finite = np.concatenate([p[np.isfinite(p)] for p in parts])
    return float(np.median(finite)) if finite.size else None


def read_ties(path) -> list[tuple[float, float]]:
    """Read ``(twt_ms, depth_m)`` pairs from CSV (columns with 'twt'/'time' and 'depth') or JSON ``{"ties": [...]}``."""
    file_path = Path(path)
    if file_path.suffix.lower() == ".json":
        return [
            tuple(map(float, pair))
            for pair in json.loads(file_path.read_text(encoding="utf-8"))["ties"]
        ]
    with open(file_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return []
    time_key = next(k for k in rows[0] if re.search(r"twt|time", k, re.IGNORECASE))
    depth_key = next(k for k in rows[0] if re.search(r"depth", k, re.IGNORECASE))
    return [
        (float(r[time_key]), float(r[depth_key]))
        for r in rows
        if r[time_key] and r[depth_key]
    ]


def _velocity(
    config: Mapping[str, Any], inventory: dict[str, list[dict]]
) -> VelocityModel | None:
    spec = config.get("velocity") or {}
    datum = float(spec.get("datum_m", 0.0))
    ties = list(spec.get("ties") or [])
    if spec.get("ties_file"):
        ties += read_ties(spec["ties_file"])
    if not ties and not spec.get("v0") and len(inventory.get("well_ties", [])) == 1:
        ties = read_ties(inventory["well_ties"][0]["path"])
    if ties:
        return calibrate_velocity(ties, k=spec.get("k"), datum_m=datum)
    if spec.get("v0"):
        return VelocityModel(
            v0=float(spec["v0"]),
            k=float(spec.get("k", 0.0)),
            datum_m=datum,
            note="velocity given by the user, not calibrated to ties",
        )
    return None


def _top_pick(tops: list[dict]) -> dict | None:
    """The reservoir-top pick to seed from: a formation name containing 'top', first well."""
    candidates = [t for t in tops if re.search(r"top", t["formation"], re.IGNORECASE)]
    return candidates[0] if candidates else None


def _track_from_seismic(config, inventory, velocity, evidence) -> Surface | None:
    from .tracking import load_cube, seed_from_well, track_horizon

    spec = dict(config.get("seismic") or {})
    path = spec.get("path") or (
        inventory["seismic"][0]["path"]
        if len(inventory.get("seismic", [])) == 1
        else None
    )
    if not path:
        evidence["missing"].append(
            "a depth or time top surface, or one SEG-Y cube to track"
        )
        return None
    seed = spec.get("seed")
    well = spec.get("well")
    if not seed and not well and evidence.get("well_tops"):
        pick = _top_pick(evidence["well_tops"])
        if pick is not None:
            well = {
                "x": pick["x"],
                "y": pick["y"],
                "top_depth_m": pick["depth_m"],
                "name": pick["well"],
                "formation": pick["formation"],
                "source": pick["source"],
            }
            evidence["warnings"].append(
                f"seed taken from discovered top '{pick['formation']}' in {pick['well']} "
                f"({pick['depth_column']} {pick['depth_m']:g}); confirm it is the reservoir top"
            )
    cube = load_cube(path)
    if not seed and well:
        if velocity is None:
            evidence["missing"].append(
                "a velocity model to place the well top in time for the seed"
            )
            return None
        seed = seed_from_well(
            cube,
            float(well["x"]),
            float(well["y"]),
            float(well["top_depth_m"]),
            velocity,
        )
        evidence["seed"] = dict(seed, from_well=well)
        if seed["snap_distance_m"] > 2 * max(cube.grid_geometry()["xinc"], 1.0):
            evidence["warnings"].append(
                f"well is {seed['snap_distance_m']:.0f} m from the nearest trace"
            )
    if not seed:
        evidence["missing"].append(
            "a seed (inline, crossline, twt_ms), a well with a known top depth, or a "
            "tops CSV (well, X, Y, formation, TVDSS) in the searched folders"
        )
        return None
    evidence.setdefault("seed", dict(seed))
    surface = track_horizon(
        cube,
        int(seed["inline"]),
        int(seed["crossline"]),
        float(seed.get("twt_ms", 0.0)),
        polarity=spec.get("polarity", "auto"),
        max_jump_samples=int(spec.get("max_jump_samples", 2)),
        min_amplitude_ratio=float(spec.get("min_amplitude_ratio", 0.3)),
    )
    evidence["sources"].append(
        {"role": "top (tracked)", "path": str(path), "method": "seed-based tracking"}
    )
    return surface


def _plot(top: Surface, closure, contact: float, path: Path) -> str | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    x, y = top.node_xy()
    fig, ax = plt.subplots(figsize=(8, 6.5))
    mesh = ax.pcolormesh(
        x, y, np.ma.masked_invalid(top.values), shading="auto", cmap="viridis_r"
    )
    fig.colorbar(mesh, ax=ax, label="depth (m)")
    if closure is not None and closure.closed:
        region = closure.region(contact, top.values.shape).astype(float)
        ax.contour(x, y, region, levels=[0.5], colors="red", linewidths=1.5)
        ax.plot(*closure.crest_xy, "w^", ms=9, label=f"crest {closure.crest_m:.0f} m")
        if closure.spill_xy:
            ax.plot(
                *closure.spill_xy, "rx", ms=9, label=f"spill {closure.spill_m:.0f} m"
            )
        ax.legend(loc="best", fontsize=8)
    ax.set_title(
        f"{top.name}: closure at contact {contact:.0f} m" if closure else top.name
    )
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_aspect("equal")
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _well_tie_check(
    top: Surface, tops: list[dict], tolerance_m: float, evidence
) -> list[dict]:
    """Depth of the mapped top at each well 'top' pick against the pick (surface minus pick, m)."""
    rows = []
    for pick in tops:
        if not re.search(r"top", pick["formation"], re.IGNORECASE):
            continue
        mapped = float(top.sample(pick["x"], pick["y"])[0])
        misfit = mapped - pick["depth_m"] if np.isfinite(mapped) else None
        rows.append(
            {
                "well": pick["well"],
                "formation": pick["formation"],
                "pick_m": pick["depth_m"],
                "surface_m": mapped if np.isfinite(mapped) else None,
                "misfit_m": misfit,
            }
        )
        if misfit is None:
            evidence["warnings"].append(
                f"{pick['well']} {pick['formation']} lies outside the mapped surface"
            )
        elif abs(misfit) > tolerance_m:
            evidence["warnings"].append(
                f"{pick['well']} {pick['formation']}: mapped top {mapped:.1f} m vs pick {pick['depth_m']:.1f} m "
                f"({misfit:+.1f} m): wrong horizon, wrong velocity or a datum difference"
            )
    return rows


def run_structure_workflow(config: Mapping[str, Any]) -> dict[str, Any]:
    """Run discovery, depth conversion, closure, volumes, builder hand-off and optional grid.

    Returns:
        A ``structure_evidence.v1`` record (also written to ``out_dir`` when given).
    """
    out_dir = Path(config["out_dir"]) if config.get("out_dir") else None
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "ok",
        "verification": "unverified",
        "sources": [],
        "warnings": [],
        "missing": [],
        "outputs": {},
    }
    inventory = (
        discover(
            config.get("search_paths") or [],
            exclude=[out_dir] if out_dir is not None else (),
        )
        if config.get("search_paths")
        else {
            k: []
            for k in (
                "published_grid",
                "depth_surface",
                "time_surface",
                "fault_data",
                "seismic",
                "well_logs",
                "well_ties",
                "well_tops",
            )
        }
    )
    evidence["inventory"] = {k: [r["path"] for r in v] for k, v in inventory.items()}
    evidence["geometry_candidates"] = geometry_candidates(inventory)
    tops: list[dict] = []
    for record in inventory["well_tops"]:
        try:
            tops += read_well_tops(record["path"])
        except ValueError as exc:
            evidence["warnings"].append(str(exc))
    evidence["well_tops"] = tops
    velocity = _velocity(config, inventory)

    top: Surface | None = None
    tracked = False
    rung, rung_detail = "structure_map", ""
    if config.get("top_surface"):
        top = read_surface(config["top_surface"], domain=config.get("surface_domain"))
        evidence["sources"].append({"role": "top", "path": str(config["top_surface"])})
        rung_detail = "top surface supplied"
    else:
        candidate = choose_top_surface(inventory)
        if candidate is not None:
            top = read_surface(candidate["path"], domain=config.get("surface_domain"))
            evidence["sources"].append(
                {"role": "top (discovered)", "path": candidate["path"]}
            )
            rung_detail = f"top surface found: {Path(candidate['path']).name}"
        else:
            top = _track_from_seismic(config, inventory, velocity, evidence)
            rung_detail = (
                "top tracked from seismic (screening pick, not interpretation)"
            )
            tracked = True
    if top is None:
        evidence["status"] = "blocked"
        evidence["gate_attempts"] = {"geometry": geometry_attempts(inventory)}
        return _finish(evidence, out_dir)
    smooth_cells = int(config.get("smooth_cells", 1 if tracked else 0))
    if smooth_cells:
        top = top.smooth(smooth_cells)
    evidence["warnings"] += [n for n in top.notes if "guessed" in n or "deviate" in n]
    evidence["top_surface_input"] = top.describe()

    if top.domain == "time":
        if velocity is None:
            evidence["status"] = "blocked"
            evidence["missing"].append(
                "velocity model or well ties (twt_ms, depth_m) for time-to-depth"
            )
            evidence["gate_attempts"] = {"geometry": geometry_attempts(inventory)}
            return _finish(evidence, out_dir)
        top = time_to_depth(top, velocity)
        evidence["velocity"] = velocity.as_dict()
        if velocity.note.startswith("velocity given"):
            evidence["warnings"].append(
                "velocity not calibrated to well ties; depths carry its full uncertainty"
            )
    if top.values.size > MAX_NODES:
        factor = int(np.ceil(np.sqrt(top.values.size / MAX_NODES)))
        top = top.coarsen(factor)
        evidence["warnings"].append(
            f"surface coarsened by {factor} for the closure analysis"
        )
    evidence["well_tie_check"] = _well_tie_check(
        top, tops, float(config.get("tie_tolerance_m", 10.0)), evidence
    )

    base = (
        read_surface(config["base_surface"], domain="depth")
        if config.get("base_surface")
        else None
    )
    thickness = config.get("thickness_m")
    if base is None and thickness is None:
        evidence["warnings"].append(
            "no base surface or thickness: reservoir assumed as thick as the column "
            "(gross rock volume is an upper bound)"
        )
    closure = analyse_closure(
        top,
        near_xy=tuple(config["crest_near"]) if config.get("crest_near") else None,
        undefined_nodes=config.get("undefined_nodes", "leak"),
    )
    evidence["warnings"] += closure.warnings
    min_nodes = int(config.get("min_closure_nodes", 9))
    closure_nodes = (
        int((closure.levels < closure.spill_m).sum()) if closure.closed else 0
    )
    roughness = surface_roughness(top)
    evidence["surface_roughness_m"] = roughness
    if closure.closed and closure_nodes < min_nodes:
        evidence["warnings"].append(
            f"closure covers only {closure_nodes} node(s) (< {min_nodes}) with {closure.relief_m:.1f} m relief: "
            "treated as map noise, not a trap"
        )
        closure.closed = False
    elif (
        closure.closed and roughness is not None and closure.relief_m < 3.0 * roughness
    ):
        evidence["warnings"].append(
            f"closure relief {closure.relief_m:.1f} m is less than 3 x the map roughness ({roughness:.1f} m): "
            "the trap may be picking noise; check the horizon before using the volumes"
        )
    evidence["closure"] = {
        "closed": closure.closed,
        "crest_m": closure.crest_m,
        "crest_xy": closure.crest_xy,
        "spill_m": closure.spill_m,
        "spill_xy": closure.spill_xy,
        "spill_reason": closure.spill_reason,
        "relief_m": closure.relief_m,
        "undefined_nodes": closure.undefined_nodes,
    }
    if closure.closed and closure.spill_reason == "grid edge":
        evidence["warnings"].append(
            "the spill is at the edge of the mapped area: the closure is limited by data coverage, so the spill "
            "depth, area and volume are minimums; extend the surface or seismic before trusting them"
        )
    sweep = (
        contact_sweep(
            top,
            closure,
            step_m=float(config.get("sweep_step_m", 5.0)),
            base=base,
            thickness_m=thickness,
        )
        if closure.closed
        else []
    )
    evidence["contact_sweep"] = sweep

    contact = config.get("contact_m")
    if config.get("target_grv_mm3") is not None and closure.closed:
        fit = contact_for_volume(sweep, float(config["target_grv_mm3"]))
        if fit is None:
            evidence["warnings"].append(
                "the closure cannot hold the target gross rock volume"
            )
        else:
            contact = fit["contact_m"]
            evidence["contact_from_target_volume"] = fit
    if contact is None:
        contact = closure.spill_m
        evidence["warnings"].append(
            "no contact given: placed at the spill point (maximum closure, not a contact)"
        )
    elif contact > closure.spill_m:
        evidence["warnings"].append(
            f"contact {contact:g} m is below the spill {closure.spill_m:.1f} m; "
            "the trap cannot hold it, contact set to spill"
        )
        contact = closure.spill_m
    evidence["contact_m"] = float(contact)

    if not closure.closed:
        evidence["status"] = "no_closure"
    else:
        volumes = volumes_at_contact(top, closure, contact, base, thickness)
        evidence["volumes"] = volumes
        label = "derived" if tracked else "interpreted"
        evidence["builder_inputs"] = {
            "field_name": config.get("field_name", top.name),
            "fluid_type": config.get("fluid_type", "oil"),
            "area_km2": round(volumes["area_km2"], 4),
            "gross_thickness_m": round(volumes["equivalent_thickness_m"], 2),
            "datum_depth_m_tvdmsl": round(volumes["hc_column_mean_depth_m"], 1),
            "field_provenance": {
                "area_km2": label,
                "gross_thickness_m": label,
                "datum_depth_m_tvdmsl": label,
            },
        }
        evidence["builder_note"] = (
            "gross_thickness_m is the closure-equivalent thickness (gross rock volume / area), so area x thickness "
            "reproduces the mapped gross rock volume. Provenance is 'interpreted' for an interpreted surface and "
            "'derived' for a top tracked here, which the builder does not count as data-backed. Merge your own "
            "field_provenance for rock and fluid inputs (for example 'default' for user assumptions)."
        )
    evidence["gate_attempts"] = {
        "geometry": geometry_attempts(inventory, used=rung, detail=rung_detail)
    }
    skipped = [
        s
        for s, found in evidence["geometry_candidates"].items()
        if found and s in ("published_grid", "horizons_and_faults")
    ]
    if skipped:
        evidence["warnings"].append(
            f"higher geometry rungs have data that this workflow did not use ({', '.join(skipped)}): they have no "
            "gate record, so data_first_gate blocks until you try them and record the outcome"
        )

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        evidence["outputs"]["top_depth_irap"] = str(
            write_irap(top, out_dir / f"{top.name}.irap")
        )
        png = _plot(
            top,
            closure if closure.closed else None,
            contact,
            out_dir / "closure_map.png",
        )
        if png:
            evidence["outputs"]["closure_map_png"] = png
    grid_spec = config.get("grid")
    if grid_spec and closure.closed and (base is not None or thickness is not None):
        grid = build_layered_grid(
            top,
            nz=int(grid_spec.get("nz", 10)),
            base=base,
            thickness_m=thickness,
            coarsen=int(grid_spec.get("coarsen", 1)),
            porosity=float(grid_spec.get("porosity", 0.2)),
            net_to_gross=float(grid_spec.get("net_to_gross", 1.0)),
            permeability_mD=float(grid_spec.get("permeability_mD", 100.0)),
            kv_kh=float(grid_spec.get("kv_kh", 0.1)),
            contact_m=contact,
            closure=closure,
            water_saturation=grid_spec.get("water_saturation"),
        )
        evidence["grid"] = {
            "dimensions": [grid.nx, grid.ny, grid.nz],
            "summary": grid.summary,
            "builder_validation": grid.validation,
            "notes": grid.notes,
        }
        if out_dir is not None:
            evidence["outputs"]["grid_grdecl"] = str(
                grid.write(out_dir / "grid.grdecl")
            )
    elif grid_spec:
        evidence["warnings"].append(
            "grid not built: it needs a closure and a base surface or thickness"
        )
    return _finish(evidence, out_dir)


def _finish(evidence: dict[str, Any], out_dir: Path | None) -> dict[str, Any]:
    evidence["checks_required"] = [
        "confirm the horizon is the reservoir top (tie to well tops in the same datum)",
        "confirm depth datum and sign, CRS and the velocity model with the data owner",
        "decide whether undefined nodes are faults (barrier) or data gaps (leak)",
        "replace the spill-point contact with a pressure- or log-based contact when available",
    ]
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "structure_evidence.json"
        evidence["outputs"]["evidence_json"] = str(path)
        path.write_text(
            json.dumps(evidence, indent=2, default=_json_default), encoding="utf-8"
        )
    return evidence


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)
