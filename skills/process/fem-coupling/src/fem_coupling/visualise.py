"""Render a solved finite-element field, in two or three dimensions.

A conduction result is a scalar on an unstructured mesh, and a table of minima and
maxima does not show where the gradient concentrates or whether a local feature is
resolved. This module renders the solved field with PyVista, off-screen, into a PNG
that can go straight into a report - and for a three-dimensional mesh it gives the
three views that are actually worth having: the outside surface, a cut plane
through the feature, and a clipped view that exposes the interior.

Rendering never has to succeed for the study to be valid. PyVista is optional; when
it is absent the render is reported as not executed, with the field file path and
the command needed to view it elsewhere, in the same way the mesh and the case are
written without Gmsh or a solver installed.

The renderer is deliberately thin. It shows a field that has already been gated by
:class:`fem_coupling.model.FemCouplingModel`; a picture is not evidence, and a
smooth-looking contour plot on an inadequate mesh is the most persuasive wrong
answer in finite elements.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from pathlib import Path
from typing import Any, Sequence

# Views generated for a three-dimensional mesh when none are named explicitly.
_DEFAULT_3D_VIEWS = ("surface", "slice", "clip")
_VIEWS = ("surface", "slice", "clip", "wireframe")

_DEFAULT_CAMERA = "auto"
_CAMERAS = {
    "auto": None,
    "iso": "isometric",
    "xy": "xy",
    "xz": "xz",
    "yz": "yz",
}


@dataclass(frozen=True)
class RenderOutcome:
    """Result of rendering a solved field."""

    status: str
    images: tuple[Path, ...]
    field_file: Path | None
    field_name: str | None
    field_range: tuple[float, float] | None
    dimension: int | None
    command: str
    message: str

    @property
    def rendered(self) -> bool:
        return self.status == "completed" and bool(self.images)


def detect_pyvista() -> bool:
    """Whether PyVista is importable in this environment."""
    return find_spec("pyvista") is not None


def render_field(
    case_dir: str | Path,
    *,
    field_file: str | None = None,
    field_name: str | None = None,
    views: Sequence[str] | None = None,
    slice_normal: Sequence[float] = (0.0, 0.0, 1.0),
    slice_origin: Sequence[float] | None = None,
    clip_normal: Sequence[float] = (0.0, 1.0, 0.0),
    warp_factor: float | None = None,
    scale: Sequence[float] | None = None,
    show_edges: bool = True,
    colormap: str = "inferno",
    camera: str = _DEFAULT_CAMERA,
    window_size: tuple[int, int] = (1200, 900),
    prefix: str = "field",
) -> RenderOutcome:
    """Render the solved field in ``case_dir`` to PNG files.

    ``field_file`` defaults to whatever the solved case recorded in
    ``results.json`` (``field.vtu`` from scikit-fem, ``field.xdmf`` from FEniCSx),
    falling back to the first readable field file in the directory.

    ``views`` selects which images to produce. A two-dimensional mesh only ever
    gets ``surface``; a three-dimensional mesh defaults to the outside surface, a
    cut plane and a clipped view, because the outside of a solid tells you almost
    nothing about the gradient inside it.

    ``warp_factor`` displaces the mesh by the scalar, which is useful for a thin
    wall where the through-thickness variation is invisible at true scale. It is a
    presentation device and is labelled as such in the returned message. ``scale``
    stretches the view along each axis for the same reason - a 3.5 mm wall on a 1 m
    tube is one pixel wide otherwise.

    ``camera`` defaults to ``auto``, which looks at the plane of the two largest
    extents. An isometric view of a long slender body wastes most of the frame.
    """
    if views is not None:
        for view in views:
            if view not in _VIEWS:
                raise ValueError(f"view must be one of {', '.join(_VIEWS)}")
    if camera not in _CAMERAS:
        raise ValueError(f"camera must be one of {', '.join(_CAMERAS)}")
    if warp_factor is not None:
        _require_finite("warp_factor", warp_factor)
    if scale is not None:
        if len(tuple(scale)) != 3 or any(float(s) <= 0.0 for s in scale):
            raise ValueError("scale must be three positive factors")

    directory = Path(case_dir)
    requested = _resolve_field_file(directory, field_file)
    command = f"python -c \"import pyvista; pyvista.read('{requested.name if requested else 'field.vtu'}').plot()\""

    if requested is None:
        return RenderOutcome(
            status="not_executed",
            images=(),
            field_file=None,
            field_name=None,
            field_range=None,
            dimension=None,
            command=command,
            message=(
                f"no field file in {directory}; the case has not been run, or the "
                "solver could not write one"
            ),
        )

    if not detect_pyvista():
        return RenderOutcome(
            status="not_executed",
            images=(),
            field_file=requested,
            field_name=field_name,
            field_range=None,
            dimension=None,
            command=command,
            message=(
                "PyVista is not installed; the field file was written and can be "
                "opened in ParaView, or rendered elsewhere with the returned command."
            ),
        )

    import pyvista  # noqa: PLC0415 - optional dependency, imported on demand

    pyvista.OFF_SCREEN = True
    try:
        grid = pyvista.read(str(requested))
    except Exception as error:  # pragma: no cover - depends on the file written
        return RenderOutcome(
            status="failed",
            images=(),
            field_file=requested,
            field_name=field_name,
            field_range=None,
            dimension=None,
            command=command,
            message=f"PyVista could not read {requested.name}: {error}",
        )

    if isinstance(grid, pyvista.MultiBlock):
        grid = grid.combine()

    scalar = _resolve_field_name(grid, field_name)
    if scalar is None:
        return RenderOutcome(
            status="failed",
            images=(),
            field_file=requested,
            field_name=None,
            field_range=None,
            dimension=None,
            command=command,
            message=(
                f"{requested.name} carries no point data to plot; arrays present: "
                + (", ".join(grid.array_names) or "none")
            ),
        )

    grid.set_active_scalars(scalar)
    values = grid.point_data[scalar]
    field_range = (float(values.min()), float(values.max()))
    dimension = _dimension_of(grid)

    if views is None:
        views = _DEFAULT_3D_VIEWS if dimension == 3 else ("surface",)

    images: list[Path] = []
    notes: list[str] = []
    for view in views:
        try:
            mesh = _view_mesh(
                pyvista, grid, view, slice_normal, slice_origin, clip_normal
            )
        except Exception as error:  # pragma: no cover - degenerate geometry
            notes.append(f"{view}: {error}")
            continue
        if mesh is None or mesh.n_cells == 0:
            notes.append(f"{view}: the cut produced nothing; check the normal and origin")
            continue
        if warp_factor is not None:
            mesh = mesh.warp_by_scalar(scalar, factor=warp_factor)

        plotter = pyvista.Plotter(off_screen=True, window_size=list(window_size))
        plotter.add_mesh(
            mesh,
            scalars=scalar,
            cmap=colormap,
            clim=field_range,
            show_edges=show_edges and view != "wireframe",
            style="wireframe" if view == "wireframe" else "surface",
            scalar_bar_args={"title": scalar, "n_labels": 5},
        )
        plotter.add_axes()
        _aim_camera(plotter, grid, dimension, camera)
        if scale is not None:
            plotter.set_scale(*[float(s) for s in scale])
            plotter.reset_camera()
        plotter.camera.zoom(1.2)
        target = directory / f"{prefix}_{view}.png"
        plotter.screenshot(str(target))
        plotter.close()
        images.append(target)

    message = f"rendered {len(images)} view(s) of '{scalar}'"
    if warp_factor is not None:
        message += (
            f"; the geometry is warped by the scalar at factor {warp_factor:g} for "
            "visibility and is not to scale"
        )
    if notes:
        message += "; " + "; ".join(notes)

    return RenderOutcome(
        status="completed" if images else "failed",
        images=tuple(images),
        field_file=requested,
        field_name=scalar,
        field_range=field_range,
        dimension=dimension,
        command=command,
        message=message,
    )


def render_mesh(
    mesh_file: str | Path,
    *,
    output: str | Path | None = None,
    show_edges: bool = True,
    window_size: tuple[int, int] = (1200, 900),
) -> RenderOutcome:
    """Render a mesh before it is solved, to check the geometry is what was meant.

    Looking at the mesh is the cheapest way to catch a layer that was assigned the
    wrong material, a defect placed at the wrong station, or a sweep that produced
    a wedge when a full annulus was intended.
    """
    path = Path(mesh_file)
    command = f"gmsh {path.name}"
    if not path.exists():
        return RenderOutcome(
            status="not_executed",
            images=(),
            field_file=None,
            field_name=None,
            field_range=None,
            dimension=None,
            command=command,
            message=f"{path} does not exist; generate the mesh first",
        )
    if not detect_pyvista():
        return RenderOutcome(
            status="not_executed",
            images=(),
            field_file=path,
            field_name=None,
            field_range=None,
            dimension=None,
            command=command,
            message="PyVista is not installed; open the mesh in Gmsh or ParaView instead.",
        )

    import pyvista  # noqa: PLC0415 - optional dependency, imported on demand

    pyvista.OFF_SCREEN = True
    grid = pyvista.read(str(path))
    if isinstance(grid, pyvista.MultiBlock):
        grid = grid.combine()
    target = Path(output) if output is not None else path.with_name("mesh.png")

    plotter = pyvista.Plotter(off_screen=True, window_size=list(window_size))
    plotter.add_mesh(grid, show_edges=show_edges, color="lightsteelblue")
    plotter.add_axes()
    dimension = _dimension_of(grid)
    _aim_camera(plotter, grid, dimension, _DEFAULT_CAMERA)
    plotter.camera.zoom(1.2)
    plotter.screenshot(str(target))
    plotter.close()

    return RenderOutcome(
        status="completed",
        images=(target,),
        field_file=path,
        field_name=None,
        field_range=None,
        dimension=dimension,
        command=command,
        message=f"rendered {grid.n_cells} cells",
    )


def _resolve_field_file(directory: Path, field_file: str | None) -> Path | None:
    if field_file is not None:
        candidate = directory / field_file
        return candidate if candidate.exists() else None

    results = directory / "results.json"
    if results.exists():
        try:
            import json  # noqa: PLC0415 - local, keeps the module import cheap

            recorded = json.loads(results.read_text(encoding="utf-8")).get("field_file")
        except Exception:  # pragma: no cover - malformed results.json
            recorded = None
        if recorded:
            candidate = directory / recorded
            if candidate.exists():
                return candidate

    for pattern in ("*.vtu", "*.xdmf", "*.pvtu", "*.vtk", "*.msh"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def _resolve_field_name(grid: Any, field_name: str | None) -> str | None:
    names = list(grid.point_data.keys())
    if field_name is not None:
        return field_name if field_name in names else None
    for preferred in ("temperature", "T", "u", "concentration"):
        if preferred in names:
            return preferred
    return names[0] if names else None


def _dimension_of(grid: Any) -> int:
    span = _extents(grid)
    largest = max(span) or 1.0
    # A planar mesh has one extent that is a rounding error next to the others.
    return 2 if min(span) / largest < 1.0e-9 else 3


def _extents(grid: Any) -> list[float]:
    bounds = grid.bounds
    return [bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]]


def _aim_camera(plotter: Any, grid: Any, dimension: int, camera: str) -> None:
    """Point the camera at the plane of the two largest extents unless told otherwise."""
    if dimension == 2:
        plotter.view_xy()
        return
    if camera != "auto":
        getattr(plotter, f"view_{_CAMERAS[camera]}", plotter.view_isometric)()
        return
    span = _extents(grid)
    thinnest = span.index(min(span))
    if max(span) / (min(span) or max(span)) < 4.0:
        plotter.view_isometric()
    else:
        (plotter.view_yz, plotter.view_xz, plotter.view_xy)[thinnest]()


def _view_mesh(
    pyvista: Any,
    grid: Any,
    view: str,
    slice_normal: Sequence[float],
    slice_origin: Sequence[float] | None,
    clip_normal: Sequence[float],
) -> Any:
    if view in {"surface", "wireframe"}:
        return grid
    if view == "slice":
        origin = list(slice_origin) if slice_origin is not None else list(grid.center)
        return grid.slice(normal=list(slice_normal), origin=origin)
    return grid.clip(normal=list(clip_normal), origin=list(grid.center))


def _require_finite(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
