"""Read and write surfaces: IRAP classic ASCII, ZMAP+ ASCII and scattered XYZ points.

Binary formats (IRAP binary, CPS-3 binary, Petrel) are read through ``xtgeo``
when it is installed; otherwise convert them to IRAP ASCII first.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from .surface import Surface

IRAP_UNDEF = 9999900.0
SURFACE_SUFFIXES = (
    ".irap",
    ".irapasc",
    ".gri",
    ".grd",
    ".zmap",
    ".zmp",
    ".xyz",
    ".pts",
    ".dat",
    ".txt",
)
_TIME_NAME = re.compile(r"(^|[^a-z])(twt|time|ms)([^a-z]|$)", re.IGNORECASE)


def infer_domain(name: str, values: np.ndarray | None = None) -> str:
    """Guess depth or time from a file name (``twt``, ``time``, ``ms``); default depth.

    The guess is reported as such; a caller who knows the domain passes it explicitly.
    """
    return "time" if _TIME_NAME.search(name or "") else "depth"


def sniff_format(path) -> str | None:
    """Return ``irap``, ``zmap``, ``xyz`` or None from the first lines of a text file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            head = [handle.readline() for _ in range(12)]
    except OSError:
        return None
    first = next((line.strip() for line in head if line.strip()), "")
    if first.split()[:1] == ["-996"]:
        return "irap"
    if any(line.lstrip().startswith("@") for line in head):
        return "zmap"
    numeric = 0
    for line in head:
        parts = re.split(r"[,\s;]+", line.strip())
        try:
            [float(p) for p in parts[:3]]
            numeric += len(parts) >= 3
        except ValueError:
            continue
    return "xyz" if numeric >= 3 else None


def read_surface(
    path,
    fmt: str | None = None,
    domain: str | None = None,
    unit: str | None = None,
    xyz_increment: float | None = None,
) -> Surface:
    """Read a surface file.

    Args:
        path: file path.
        fmt: ``irap``, ``zmap``, ``xyz`` or ``xtgeo``; sniffed when omitted.
        domain: ``depth`` or ``time``; guessed from the file name when omitted (recorded in notes).
        unit: value unit; ``m`` for depth and ``ms`` for time when omitted.
        xyz_increment: node spacing for gridding XYZ points; estimated when omitted.

    Raises:
        ValueError: if the format is unknown or the file is malformed.
    """
    file_path = Path(path)
    kind = (
        fmt
        or sniff_format(file_path)
        or ("xtgeo" if file_path.suffix.lower() in (".gri", ".irapbin") else "")
    ).lower()
    if kind == "irap":
        surface = _read_irap(file_path)
    elif kind == "zmap":
        surface = _read_zmap(file_path)
    elif kind == "xyz":
        surface = _read_xyz(file_path, xyz_increment)
    elif kind == "xtgeo":
        surface = _read_xtgeo(file_path)
    else:
        raise ValueError(
            f"cannot recognise the surface format of {file_path}; pass fmt="
        )
    surface.name = file_path.stem
    surface.source = str(file_path)
    if domain is None:
        surface.domain = infer_domain(file_path.stem)
        surface.notes.append(
            f"domain '{surface.domain}' guessed from the file name; confirm it"
        )
    else:
        surface.domain = domain
    surface.unit = unit or ("ms" if surface.domain == "time" else "m")
    return surface


def _numbers(text: str):
    return np.array(
        [float(t) for t in re.split(r"[,\s]+", text.strip()) if t], dtype=float
    )


def _read_irap(path: Path) -> Surface:
    numbers = _numbers(path.read_text(encoding="utf-8", errors="replace"))
    if numbers.size < 19 or int(numbers[0]) != -996:
        raise ValueError(f"{path} is not an IRAP classic ASCII surface")
    nrow, xinc, yinc = int(numbers[1]), float(numbers[2]), float(numbers[3])
    ncol, rotation, xori, yori = (
        int(numbers[8]),
        float(numbers[9]),
        float(numbers[10]),
        float(numbers[11]),
    )
    values = numbers[19:]
    if values.size != ncol * nrow:
        raise ValueError(f"{path}: {values.size} values for a {ncol} x {nrow} grid")
    grid = values.reshape(
        nrow, ncol
    ).T.copy()  # file order: i fastest within each row j
    grid[grid >= IRAP_UNDEF * 0.999] = np.nan
    yflip = 1 if yinc > 0 else -1
    return Surface(xori, yori, xinc, abs(yinc), grid, rotation=rotation, yflip=yflip)


def write_irap(surface: Surface, path) -> Path:
    """Write IRAP classic ASCII (``yflip`` normalised to 1, NaN as 9999900)."""
    s = surface.normalized()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    xmax = s.xori + (s.ncol - 1) * s.xinc
    ymax = s.yori + (s.nrow - 1) * s.yinc
    lines = [
        f"-996 {s.nrow} {s.xinc:.6f} {s.yinc:.6f}",
        f"{s.xori:.6f} {xmax:.6f} {s.yori:.6f} {ymax:.6f}",
        f"{s.ncol} {s.rotation:.6f} {s.xori:.6f} {s.yori:.6f}",
        "0 0 0 0 0 0 0",
    ]
    flat = np.where(np.isfinite(s.values), s.values, IRAP_UNDEF).T.ravel()
    for k in range(0, flat.size, 6):
        lines.append(" ".join(f"{v:.4f}" for v in flat[k : k + 6]))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _read_zmap(path: Path) -> Surface:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("!")]
    at = [k for k, ln in enumerate(header) if ln.lstrip().startswith("@")]
    if len(at) < 2:
        raise ValueError(f"{path} is not a ZMAP+ grid (missing @ header lines)")
    head = header[at[0] + 1 : at[1]]
    first = [t.strip() for t in head[0].split(",")]
    null = float(first[1]) if first[1] else 1e30
    shape = _numbers(head[1])
    nrow, ncol, xmin, xmax, ymin, ymax = (
        int(shape[0]),
        int(shape[1]),
        *map(float, shape[2:6]),
    )
    values = _numbers(" ".join(header[at[1] + 1 :]))
    if values.size != ncol * nrow:
        raise ValueError(f"{path}: {values.size} values for a {ncol} x {nrow} grid")
    grid = values.reshape(ncol, nrow)[
        :, ::-1
    ].copy()  # file: per column, top (ymax) down
    grid[np.isclose(grid, null)] = np.nan
    return Surface(
        xmin, ymin, (xmax - xmin) / (ncol - 1), (ymax - ymin) / (nrow - 1), grid
    )


def write_zmap(surface: Surface, path, null: float = 1e30) -> Path:
    """Write ZMAP+ ASCII. ZMAP cannot store rotation, so rotated surfaces are refused."""
    s = surface.normalized()
    if abs(s.rotation) > 1e-9:
        raise ValueError("ZMAP+ cannot hold a rotated grid; write IRAP instead")
    xmax, ymax = s.xori + (s.ncol - 1) * s.xinc, s.yori + (s.nrow - 1) * s.yinc
    lines = [
        "! written by seismic_structure",
        f"@{s.name} HEADER, GRID, 5",
        f"15, {null:.0E}, , 4, 1",
        f"{s.nrow}, {s.ncol}, {s.xori:.4f}, {xmax:.4f}, {s.yori:.4f}, {ymax:.4f}",
        "0.0, 0.0, 0.0",
        "@",
    ]
    flat = np.where(np.isfinite(s.values), s.values, null)[:, ::-1].ravel()
    for k in range(0, flat.size, 5):
        lines.append(
            "".join(
                f"{v:15.4f}" if abs(v) < 1e20 else f"{v:15.4E}" for v in flat[k : k + 5]
            )
        )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _read_xyz(path: Path, increment: float | None) -> Surface:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [p for p in re.split(r"[,\s;]+", line.strip()) if p]
        try:
            rows.append([float(p) for p in parts[:3]])
        except ValueError:
            continue
    points = np.array([r for r in rows if len(r) == 3], dtype=float)
    if points.shape[0] < 4:
        raise ValueError(f"{path}: fewer than 4 x y z points")
    return grid_points(points[:, 0], points[:, 1], points[:, 2], increment)


def grid_points(
    x, y, z, increment: float | None = None, max_gap: float | None = None
) -> Surface:
    """Grid scattered points (linear triangulation; nodes far from any point stay undefined).

    Args:
        x, y, z: point coordinates and values.
        increment: node spacing; estimated from point density when omitted.
        max_gap: nodes further than this from any point are undefined (default 2 x increment).
    """
    from scipy.interpolate import griddata
    from scipy.spatial import cKDTree

    x, y, z = (np.asarray(a, dtype=float) for a in (x, y, z))
    area = max((x.max() - x.min()) * (y.max() - y.min()), 1.0)
    inc = float(increment) if increment else max(math.sqrt(area / x.size), 1e-6)
    ncol = int(round((x.max() - x.min()) / inc)) + 1
    nrow = int(round((y.max() - y.min()) / inc)) + 1
    gi, gj = np.meshgrid(
        x.min() + np.arange(ncol) * inc, y.min() + np.arange(nrow) * inc, indexing="ij"
    )
    values = griddata((x, y), z, (gi, gj), method="linear")
    distance, _ = cKDTree(np.column_stack([x, y])).query(
        np.column_stack([gi.ravel(), gj.ravel()])
    )
    values[(distance > (max_gap or 2.0 * inc)).reshape(values.shape)] = np.nan
    surface = Surface(float(x.min()), float(y.min()), inc, inc, values)
    surface.notes.append(f"gridded from {x.size} points at {inc:g} spacing (linear)")
    return surface


def _read_xtgeo(path: Path) -> Surface:
    try:
        import xtgeo
    except ImportError as exc:
        raise ValueError(
            f"{path}: binary surface formats need xtgeo; export IRAP ASCII instead"
        ) from exc
    surf = xtgeo.surface_from_file(str(path))
    values = np.ma.filled(surf.values.astype(float), np.nan)
    return Surface(
        surf.xori,
        surf.yori,
        surf.xinc,
        surf.yinc,
        values,
        rotation=surf.rotation,
        yflip=int(surf.yflip),
    )
