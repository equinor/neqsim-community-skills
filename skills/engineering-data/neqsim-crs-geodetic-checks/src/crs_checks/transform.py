"""Coordinate transforms with explicit operations and recorded provenance.

The engine is equinor/geodetic-engine when it is installed (PROJ 9.9 with its pinned pyproj), otherwise pyproj
under the same rules: a datum change must name its operation when the candidates disagree, ballpark
transformations are refused, a missing grid is reported, and the PROJ pipeline that ran is recorded.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

Point = tuple[float, float]
AMBIGUITY_TOLERANCE_M = 0.01


class CrsError(ValueError):
    """A transformation that cannot be done exactly as asked."""


class AmbiguousOperationError(CrsError):
    """Several operations exist and they disagree; one must be named."""


@dataclass
class TransformResult:
    coordinates: list[Point]
    operation: str
    accuracy_m: float | None
    pipeline: str
    engine: str
    candidates: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def provenance(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "accuracy_m": self.accuracy_m,
            "pipeline": self.pipeline,
            "engine": self.engine,
            "candidates": self.candidates,
            "warnings": self.warnings,
        }


def engine_name() -> str:
    try:
        import geodetic_engine  # type: ignore[import-not-found]  # noqa: F401

        return "geodetic-engine"
    except Exception:  # noqa: BLE001 - also fails when its PROJ pin does not match
        import pyproj

        return f"pyproj {pyproj.__version__} (PROJ {pyproj.proj_version_str})"


def _crs(code: str):
    from pyproj import CRS

    return CRS.from_user_input(code)


def operation_codes(transformer) -> list[str]:
    """Authority codes of the operation and of every step (for matching a named operation)."""
    text = json.dumps(transformer.to_json_dict())
    import re

    return [
        f"{a}:{c}"
        for a, c in re.findall(
            r'"authority":\s*"([A-Z]+)",\s*"code":\s*"?(\d+)"?', text
        )
    ]


def _metres_apart(dst_crs, a: Point, b: Point) -> float:
    from pyproj import Geod

    crs = _crs(dst_crs)
    if crs.is_geographic:
        geod = Geod(ellps="WGS84")
        return float(geod.inv(a[0], a[1], b[0], b[1])[2])
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _check_operation_area(operation: str, points: list[Point], src: str) -> None:
    """Refuse a named operation whose area of use does not contain the points (both engines)."""
    from pyproj.crs import CoordinateOperation

    try:
        authority, code = operation.split(":", 1)
        op = CoordinateOperation.from_authority(authority.strip().upper(), code.strip())
    except Exception:  # noqa: BLE001 - unknown codes are reported by the engine itself
        return
    area = op.area_of_use
    if area is None:
        return
    from .checks import to_geographic

    lonlat = to_geographic(points, src)
    outside = [
        p
        for p in lonlat
        if not (
            area.west - 0.01 <= p[0] <= area.east + 0.01
            and area.south - 0.01 <= p[1] <= area.north + 0.01
        )
    ]
    if outside:
        raise CrsError(
            f"operation {operation} ({op.name}) is valid for {area.name}; {len(outside)} point(s) lie "
            f"outside it, for example lon/lat {tuple(round(v, 4) for v in outside[0])}"
        )


def transform(
    points: Sequence[Point], src: str, dst: str, operation: str | None = None
) -> TransformResult:
    """Transform x/y (lon/lat for geographic CRSs, always in that order) from ``src`` to ``dst``.

    ``operation`` names the datum transformation (for example ``EPSG:1612``), or ``"best"`` for the most accurate
    available one (recorded as such). Without it the call succeeds only when every available operation gives the
    same result within 1 cm. A named operation must cover the points (its EPSG area of use).
    """
    points = [(float(x), float(y)) for x, y in points]
    best = bool(operation) and operation.lower() == "best"
    if operation and not best:
        _check_operation_area(operation, points, src)
    if engine_name() == "geodetic-engine" and not best:
        return _transform_geodetic_engine(points, src, dst, operation)
    import pyproj

    pyproj_engine = f"pyproj {pyproj.__version__} (PROJ {pyproj.proj_version_str})"
    from pyproj.transformer import AreaOfInterest, TransformerGroup

    aoi = None
    try:
        from .checks import to_geographic

        lonlat = to_geographic(points, src)
        lons, lats = [p[0] for p in lonlat], [p[1] for p in lonlat]
        if all(-180 <= v <= 180 for v in lons) and all(-90 <= v <= 90 for v in lats):
            aoi = AreaOfInterest(min(lons), min(lats), max(lons), max(lats))
    except Exception:
        aoi = None
    group = TransformerGroup(
        src, dst, always_xy=True, allow_ballpark=False, area_of_interest=aoi
    )
    if not group.transformers:
        raise CrsError(
            f"no exact operation from {src} to {dst} is available (ballpark refused); missing grids: "
            f"{[op.name for op in group.unavailable_operations]}"
        )
    warnings = []
    if not group.best_available:
        warnings.append(
            "the most accurate operation needs a grid that is not installed: "
            + ", ".join(op.name for op in group.unavailable_operations[:3])
        )
    candidates = []
    for t in group.transformers:
        out = [t.transform(x, y) for x, y in points]
        candidates.append(
            {
                "name": t.description or t.name,
                "accuracy_m": t.accuracy if t.accuracy >= 0 else None,
                "codes": operation_codes(t),
                "transformer": t,
                "result": out,
            }
        )
    if operation and operation.lower() == "best":
        pick = min(
            candidates,
            key=lambda c: c["accuracy_m"] if c["accuracy_m"] is not None else 1e9,
        )
        warnings.append(
            "operation chosen as the most accurate available, not named by the user"
        )
    elif operation:
        chosen = [c for c in candidates if operation.upper() in c["codes"]]
        if not chosen:
            raise CrsError(
                f"operation {operation} is not available for these points (outside its area of use, or "
                f"its grid is missing); available here: "
                + "; ".join(f"{c['name']} {c['codes'][:3]}" for c in candidates)
            )
        pick = chosen[0]
    else:
        spread = max(
            (
                _metres_apart(dst, a, b)
                for c in candidates[1:]
                for a, b in zip(candidates[0]["result"], c["result"])
            ),
            default=0.0,
        )
        if spread > AMBIGUITY_TOLERANCE_M:
            raise AmbiguousOperationError(
                f"{len(candidates)} operations from {src} to {dst} disagree by up to {spread:.2f} m; name one: "
                + "; ".join(
                    f"{c['name']} (accuracy {c['accuracy_m']} m)"
                    for c in candidates[:6]
                )
            )
        pick = candidates[0]
    public = [
        {k: v for k, v in c.items() if k not in ("transformer", "result")}
        for c in candidates
    ]
    return TransformResult(
        coordinates=[tuple(p) for p in pick["result"]],
        operation=pick["name"],
        accuracy_m=pick["accuracy_m"],
        pipeline=pick["transformer"].definition,
        engine=pyproj_engine,
        candidates=public,
        warnings=warnings,
    )


def _transform_geodetic_engine(
    points: list[Point], src: str, dst: str, operation: str | None
) -> TransformResult:
    from geodetic_engine import geodesy  # type: ignore[import-not-found]

    try:
        result = (
            geodesy.transform(src, dst, points, operation=operation)
            if operation
            else geodesy.transform(src, dst, points)
        )
    except Exception as exc:
        if type(exc).__name__ == "AmbiguousOperationError":
            raise AmbiguousOperationError(str(exc)) from exc
        raise CrsError(str(exc)) from exc
    op = result.operation
    return TransformResult(
        coordinates=[tuple(c) for c in result.coordinates],
        operation=str(op.name),
        accuracy_m=getattr(op, "accuracy", None),
        pipeline=str(result.pipeline),
        engine="geodetic-engine",
    )
