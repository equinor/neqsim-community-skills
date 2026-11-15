"""Config-driven CRS check with an evidence record.

Example config::

    {
      "points": [{"name": "template", "x": 500123.0, "y": 6680456.0}],
      "crs": "EPSG:23031",
      "target_crs": "EPSG:4326", "operation": "EPSG:1612",
      "datum_candidates": ["EPSG:23031", "EPSG:32631", "EPSG:25831"],
      "route": {"crs": "EPSG:32631", "points": [[500000, 6680000], [512000, 6690000]]},
      "geojson": ["<task>/references/maps/layout.geojson"],
      "shift_tolerance_m": 5.0,
      "out_dir": "<task>/step2_analysis/crs"
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .checks import area_of_use_check, axis_check, datum_sensitivity, geojson_check, projection_factors, \
    route_lengths, to_geographic
from .transform import CrsError, engine_name, transform

SCHEMA = "crs_check_evidence.v1"


def run_crs_check(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the configured checks. Status is ``ok``, ``attention`` (findings to resolve) or ``blocked``."""
    evidence: Dict[str, Any] = {"schema": SCHEMA, "status": "ok", "verification": "unverified",
                                "engine": engine_name(), "findings": [], "missing": [], "results": {},
                                "outputs": {}}
    points = [(float(p["x"]), float(p["y"])) for p in config.get("points", [])]
    names = [p.get("name", f"p{i}") for i, p in enumerate(config.get("points", []))]
    crs = config.get("crs")
    if points and not crs:
        evidence["missing"].append("crs: the CRS of the points is not stated; use datum_candidates to see what "
                                   "the ambiguity costs, and ask the data owner")
    if points and crs:
        try:
            area = area_of_use_check(points, crs)
            evidence["results"]["area_of_use"] = area
            for i in area["outside"]:
                evidence["findings"].append(f"{names[i]} is outside the area of use of {crs} ({area['area']})")
            for finding in axis_check(points, crs):
                evidence["findings"].append(f"{crs}: {finding}")
            if config.get("target_crs"):
                result = transform(points, crs, config["target_crs"], config.get("operation"))
                evidence["results"]["transform"] = {
                    "target_crs": config["target_crs"],
                    "points": [{"name": n, "x": c[0], "y": c[1]} for n, c in zip(names, result.coordinates)],
                    **result.provenance()}
                evidence["findings"] += result.warnings
            from pyproj import CRS

            if CRS.from_user_input(crs).is_projected:
                lon, lat = to_geographic(points[:1], crs)[0]
                evidence["results"]["projection_factors"] = dict(projection_factors(crs, lon, lat), at=names[0])
        except CrsError as exc:
            evidence["missing"].append(str(exc))
    if config.get("datum_candidates") and points:
        sens = datum_sensitivity(points, config["datum_candidates"], config.get("operations"))
        evidence["results"]["datum_sensitivity"] = sens
        tolerance = float(config.get("shift_tolerance_m", 5.0))
        if sens["max_shift_m"] > tolerance:
            evidence["findings"].append(
                f"the candidate datums place the points up to {sens['max_shift_m']:.0f} m apart (tolerance "
                f"{tolerance:g} m): the datum must be confirmed before positions, distances or clearances are used")
    if config.get("route"):
        route = config["route"]
        lengths = route_lengths([tuple(p) for p in route["points"]], route["crs"])
        evidence["results"]["route_lengths"] = lengths
        if abs(lengths["difference_ppm"]) > 100:
            evidence["findings"].append(f"grid and geodesic route lengths differ by {lengths['difference_m']:.1f} m "
                                        f"({lengths['difference_ppm']:.0f} ppm): state which length is used")
    for path in config.get("geojson", []):
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            for finding in geojson_check(document):
                evidence["findings"].append(f"{Path(path).name}: {finding}")
        except Exception as exc:  # noqa: BLE001 - reported
            evidence["missing"].append(f"geojson {path}: {exc}")
    if evidence["missing"]:
        evidence["status"] = "blocked"
    elif evidence["findings"]:
        evidence["status"] = "attention"
    if config.get("out_dir"):
        out_dir = Path(config["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "crs_check_evidence.json"
        path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        evidence["outputs"]["evidence"] = str(path)
    return evidence
