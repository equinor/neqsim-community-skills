"""Generate a structured Gmsh mesh for a layered finite-element model.

Meshing is the step where a defensible finite-element study is usually lost. An
unstructured mesh dropped over a layered wall puts two elements across a 12 mm
steel pipe wall and forty across the insulation, so the steel temperature drop -
the one that sets the thermal stress - is represented by a single linear element.

This module builds the mesh the layered geometry actually wants: a structured
tensor grid, one block per (axial segment, through-thickness layer), with the
layer interfaces on element boundaries and a stated number of elements across
every layer. The generated ``.geo`` names each material as a physical surface and
each face as a physical curve, so the solver script can assign properties and
boundary conditions by name instead of by coordinate search.

Gmsh is optional. Without it the ``.geo`` file is still written, together with the
command needed to mesh it elsewhere, exactly as the CFD-coupling skill writes an
OpenFOAM case without OpenFOAM installed.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from importlib.util import find_spec
from math import isfinite, radians
from pathlib import Path
from typing import Mapping, Sequence

# Beyond this in-plane aspect ratio the element gradients degrade noticeably for
# linear elements, which is what a through-thickness temperature profile depends on.
_MAX_ASPECT_RATIO = 20.0

# Fewer elements than this across a layer cannot represent a curved profile, and
# with linear elements two elements cannot represent a gradient change at all.
_MIN_ELEMENTS_PER_LAYER = 3

_KINDS = ("axisymmetric_section", "plane_section", "block")


@dataclass(frozen=True)
class MeshLayer:
    """One through-thickness layer: a material, a thickness and an element count."""

    name: str
    material: str
    thickness_m: float
    cells: int = 4

    def __post_init__(self) -> None:
        _require_positive(f"layer '{self.name}' thickness_m", self.thickness_m)
        if self.cells < 1:
            raise ValueError(f"layer '{self.name}' needs at least one element")


@dataclass(frozen=True)
class MeshSegment:
    """One axial segment: a length, an element count and optional material overrides.

    ``overrides`` maps a layer name to a different material for this segment only.
    That is how a local defect is represented - water ingress into a section of
    wet insulation, a coating holiday, a cement channel - without leaving the
    structured grid. A defect that changes the *thickness* rather than the
    material is outside what a tensor grid can express; import an external mesh
    for that.
    """

    name: str
    length_m: float
    cells: int = 20
    overrides: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_positive(f"segment '{self.name}' length_m", self.length_m)
        if self.cells < 1:
            raise ValueError(f"segment '{self.name}' needs at least one element")


@dataclass(frozen=True)
class FemMeshSpec:
    """A layered, structured mesh definition, two- or three-dimensional.

    ``kind`` is ``axisymmetric_section`` (an r-z slice of a pipe, vessel or
    wellbore, with ``inner_radius_m`` as the bore radius), ``plane_section`` (a
    through-thickness slice of a flat wall) or ``block`` (a rectangular domain such
    as a porous rock sample). ``element_order`` 2 gives quadratic elements, which
    resolve a curved thermal profile with far fewer elements.

    The mesh is two-dimensional unless a third dimension is asked for:

    ``revolve_deg``
        Sweep the section about the axis to produce a three-dimensional pipe or
        vessel wall. 360 gives the full annulus; a smaller angle gives a wedge
        with two symmetry planes, which is what to use when the loading is
        axisymmetric and the mesh only exists to be looked at or to carry a
        circumferential feature.
    ``extrude_m``
        Sweep the section a distance out of plane, for a flat wall or a block.

    Do not reach for three dimensions by default. An axisymmetric problem solved on
    a revolved mesh costs an order of magnitude more and returns the same answer as
    the r-z section; the reasons to revolve are a genuinely circumferential feature
    (a support, a nozzle, a weld that does not run all the way round) and
    presentation.
    """

    kind: str
    layers: Sequence[MeshLayer]
    segments: Sequence[MeshSegment]
    inner_radius_m: float | None = None
    element_order: int = 1
    recombine: bool = True
    name: str = "fem-model"
    revolve_deg: float | None = None
    extrude_m: float | None = None
    circumferential_cells: int = 24

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"kind must be one of {', '.join(_KINDS)}")
        if not self.layers:
            raise ValueError("at least one layer is required")
        if not self.segments:
            raise ValueError("at least one segment is required")
        if self.element_order not in (1, 2):
            raise ValueError("element_order must be 1 or 2")
        if self.kind == "axisymmetric_section":
            _require_positive("inner_radius_m", self.inner_radius_m)
        if self.revolve_deg is not None and self.extrude_m is not None:
            raise ValueError("give revolve_deg or extrude_m, not both")
        if self.revolve_deg is not None:
            if self.kind != "axisymmetric_section":
                raise ValueError(
                    "revolve_deg only applies to an axisymmetric_section; use "
                    "extrude_m for a plane section or a block"
                )
            if not 0.0 < self.revolve_deg <= 360.0:
                raise ValueError("revolve_deg must be greater than 0 and at most 360")
        if self.extrude_m is not None:
            _require_positive("extrude_m", self.extrude_m)
        if self.revolve_deg is not None or self.extrude_m is not None:
            if self.circumferential_cells < 1:
                raise ValueError("circumferential_cells must be at least one")
        names = [layer.name for layer in self.layers]
        if len(set(names)) != len(names):
            raise ValueError("layer names must be unique")
        known = set(names)
        for segment in self.segments:
            unknown = set(segment.overrides) - known
            if unknown:
                raise ValueError(
                    f"segment '{segment.name}' overrides unknown layer(s): "
                    + ", ".join(sorted(unknown))
                )

    @property
    def is_three_dimensional(self) -> bool:
        return self.revolve_deg is not None or self.extrude_m is not None

    @property
    def dimension(self) -> int:
        return 3 if self.is_three_dimensional else 2

    # ------------------------------------------------------------- geometry

    @property
    def axial_stations_m(self) -> tuple[float, ...]:
        """Cumulative axial coordinates, one per segment boundary."""
        stations = [0.0]
        for segment in self.segments:
            stations.append(stations[-1] + segment.length_m)
        return tuple(stations)

    @property
    def radial_stations_m(self) -> tuple[float, ...]:
        """Cumulative through-thickness coordinates, one per layer boundary."""
        start = self.inner_radius_m if self.kind == "axisymmetric_section" else 0.0
        stations = [float(start or 0.0)]
        for layer in self.layers:
            stations.append(stations[-1] + layer.thickness_m)
        return tuple(stations)

    @property
    def total_thickness_m(self) -> float:
        return sum(layer.thickness_m for layer in self.layers)

    @property
    def total_length_m(self) -> float:
        return sum(segment.length_m for segment in self.segments)

    @property
    def element_count(self) -> int:
        planar = sum(segment.cells for segment in self.segments) * sum(
            layer.cells for layer in self.layers
        )
        return planar * self.circumferential_cells if self.is_three_dimensional else planar

    def material_of(self, segment: MeshSegment, layer: MeshLayer) -> str:
        """Material assigned to one grid cell, honouring the segment override."""
        return segment.overrides.get(layer.name, layer.material)

    def materials(self) -> tuple[str, ...]:
        """Every distinct material used by the mesh, in first-appearance order."""
        seen: list[str] = []
        for segment in self.segments:
            for layer in self.layers:
                material = self.material_of(segment, layer)
                if material not in seen:
                    seen.append(material)
        return tuple(seen)

    def boundary_names(self) -> tuple[str, ...]:
        """Physical group names written into the ``.geo``.

        A partial revolve or an extrusion adds the two cut planes, which are
        symmetry planes rather than real boundaries and normally carry an
        adiabatic condition.
        """
        faces = ("inner", "outer", "west", "east")
        if self.is_three_dimensional and self.revolve_deg != 360.0:
            faces += ("symmetry_start", "symmetry_end")
        return faces

    def material_ids(self) -> dict[str, int]:
        """Physical surface id per material, numbered from 1 in appearance order.

        The ids are written explicitly into the ``.geo`` rather than left to Gmsh,
        so a solver that addresses groups by integer tag (dolfinx) and one that
        addresses them by name (meshio, scikit-fem) see the same partition.
        """
        return {material: index + 1 for index, material in enumerate(self.materials())}

    def boundary_ids(self) -> dict[str, int]:
        """Physical curve id per boundary face, numbered from 101."""
        return {name: 101 + index for index, name in enumerate(self.boundary_names())}

    # ------------------------------------------------------------- diagnostics

    def element_sizes_m(self) -> tuple[float, float, float, float]:
        """Smallest and largest element edge in each direction.

        Returns ``(min_axial, max_axial, min_radial, max_radial)`` in metres.
        """
        axial = [segment.length_m / segment.cells for segment in self.segments]
        radial = [layer.thickness_m / layer.cells for layer in self.layers]
        return min(axial), max(axial), min(radial), max(radial)

    def max_aspect_ratio(self) -> float:
        """Worst in-plane element aspect ratio in the grid."""
        worst = 0.0
        for segment in self.segments:
            dx = segment.length_m / segment.cells
            for layer in self.layers:
                dy = layer.thickness_m / layer.cells
                worst = max(worst, dx / dy, dy / dx)
        return worst

    def mesh_warnings(self, *, max_element_size_m: float | None = None) -> tuple[str, ...]:
        """Report the discretisation problems that quietly invalidate a result.

        ``max_element_size_m`` is normally the element-size target returned by
        :func:`fem_coupling.thermal.derive_thermal_conditions`, so the mesh is
        judged against the physics rather than against a habit.
        """
        warnings: list[str] = []

        for layer in self.layers:
            if layer.cells < _MIN_ELEMENTS_PER_LAYER and self.element_order == 1:
                warnings.append(
                    f"Layer '{layer.name}' has {layer.cells} linear element(s) across it; "
                    f"use at least {_MIN_ELEMENTS_PER_LAYER}, or quadratic elements, "
                    "before quoting a temperature drop across this layer."
                )

        aspect = self.max_aspect_ratio()
        if aspect > _MAX_ASPECT_RATIO:
            warnings.append(
                f"Worst element aspect ratio {aspect:.0f} exceeds {_MAX_ASPECT_RATIO:.0f}; "
                "add axial elements or coarsen the through-thickness direction."
            )

        if max_element_size_m is not None:
            _require_positive("max_element_size_m", max_element_size_m)
            _, _, _, max_radial = self.element_sizes_m()
            if max_radial > max_element_size_m:
                warnings.append(
                    f"Largest through-thickness element {max_radial:.4g} m exceeds the "
                    f"target {max_element_size_m:.4g} m set by the thermal penetration "
                    "depth; the transient front will not be resolved."
                )

        if self.kind == "axisymmetric_section":
            radii = self.radial_stations_m
            if radii[-1] / radii[0] > 50.0:
                warnings.append(
                    f"Outer-to-inner radius ratio {radii[-1] / radii[0]:.0f} is large; grade "
                    "the far-field layer so the mesh does not carry uniform elements out "
                    "to a boundary where nothing happens."
                )

        return tuple(warnings)

    # ------------------------------------------------------------- generation

    def geo_script(self) -> str:
        """Return the Gmsh ``.geo`` script for this mesh."""
        xs = self.axial_stations_m
        ys = self.radial_stations_m
        nx = len(self.segments)
        ny = len(self.layers)

        lines: list[str] = [
            "// Generated by the NeqSim fem-coupling skill.",
            "// Structured tensor grid: one block per (axial segment, layer), with every",
            "// layer interface on an element boundary. Physical names carry the material",
            "// assignment and the boundary faces to the solver.",
            f'// model: {self.name}   kind: {self.kind}',
            "SetFactory(\"Built-in\");",
            "",
        ]

        point_id: dict[tuple[int, int], int] = {}
        counter = 1
        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                point_id[(i, j)] = counter
                lines.append(f"Point({counter}) = {{{x:.10g}, {y:.10g}, 0}};")
                counter += 1
        lines.append("")

        line_counter = 1
        horizontal: dict[tuple[int, int], int] = {}
        for i in range(nx):
            for j in range(ny + 1):
                horizontal[(i, j)] = line_counter
                lines.append(
                    f"Line({line_counter}) = {{{point_id[(i, j)]}, {point_id[(i + 1, j)]}}};"
                )
                line_counter += 1

        vertical: dict[tuple[int, int], int] = {}
        for i in range(nx + 1):
            for j in range(ny):
                vertical[(i, j)] = line_counter
                lines.append(
                    f"Line({line_counter}) = {{{point_id[(i, j)]}, {point_id[(i, j + 1)]}}};"
                )
                line_counter += 1
        lines.append("")

        for i, segment in enumerate(self.segments):
            ids = ", ".join(str(horizontal[(i, j)]) for j in range(ny + 1))
            lines.append(f"Transfinite Curve {{{ids}}} = {segment.cells + 1};")
        for j, layer in enumerate(self.layers):
            ids = ", ".join(str(vertical[(i, j)]) for i in range(nx + 1))
            lines.append(f"Transfinite Curve {{{ids}}} = {layer.cells + 1};")
        lines.append("")

        surface_id: dict[tuple[int, int], int] = {}
        loop_counter = line_counter
        for i in range(nx):
            for j in range(ny):
                loop = loop_counter
                lines.append(
                    "Curve Loop({}) = {{{}, {}, -{}, -{}}};".format(
                        loop,
                        horizontal[(i, j)],
                        vertical[(i + 1, j)],
                        horizontal[(i, j + 1)],
                        vertical[(i, j)],
                    )
                )
                lines.append(f"Plane Surface({loop}) = {{{loop}}};")
                lines.append(f"Transfinite Surface {{{loop}}};")
                if self.recombine:
                    lines.append(f"Recombine Surface {{{loop}}};")
                surface_id[(i, j)] = loop
                loop_counter += 1
        lines.append("")

        material_ids = self.material_ids()
        boundary_ids = self.boundary_ids()

        if self.is_three_dimensional:
            lines.extend(
                self._sweep_script(surface_id, nx, ny, material_ids, boundary_ids)
            )
        else:
            for material in self.materials():
                members = [
                    str(surface_id[(i, j)])
                    for i, segment in enumerate(self.segments)
                    for j, layer in enumerate(self.layers)
                    if self.material_of(segment, layer) == material
                ]
                lines.append(
                    'Physical Surface("{}", {}) = {{{}}};'.format(
                        material, material_ids[material], ", ".join(members)
                    )
                )

            faces = {
                "inner": [horizontal[(i, 0)] for i in range(nx)],
                "outer": [horizontal[(i, ny)] for i in range(nx)],
                "west": [vertical[(0, j)] for j in range(ny)],
                "east": [vertical[(nx, j)] for j in range(ny)],
            }
            for face, members in faces.items():
                lines.append(
                    'Physical Curve("{}", {}) = {{{}}};'.format(
                        face, boundary_ids[face], ", ".join(str(m) for m in members)
                    )
                )

        lines.append("")
        lines.append(f"Mesh.ElementOrder = {self.element_order};")
        lines.append("Mesh.MshFileVersion = 2.2;")
        lines.append("")
        return "\n".join(lines)

    def _sweep_script(
        self,
        surface_id: dict[tuple[int, int], int],
        nx: int,
        ny: int,
        material_ids: Mapping[str, int],
        boundary_ids: Mapping[str, int],
    ) -> list[str]:
        """Revolve or extrude the section, and tag the swept volumes and faces.

        Gmsh returns a sweep of a plane surface in a fixed order: the end surface,
        then the volume, then one lateral surface per curve of the loop in loop
        order. The loop is written here as (inner, east, outer, west), so the
        lateral faces come back in that order and can be tagged without any
        geometric search.
        """
        lines: list[str] = []
        if self.revolve_deg is not None:
            angle = radians(self.revolve_deg)
            prefix = f"Extrude {{ {{1, 0, 0}}, {{0, 0, 0}}, {angle:.12g} }}"
            lines.append(
                f"// Revolved {self.revolve_deg:g} deg about the x axis into "
                f"{self.circumferential_cells} circumferential layers."
            )
        else:
            prefix = f"Extrude {{0, 0, {self.extrude_m:.10g}}}"
            lines.append(
                f"// Extruded {self.extrude_m:g} m out of plane into "
                f"{self.circumferential_cells} layers."
            )

        def sweep(surface: int) -> str:
            return (
                f"{prefix} {{ Surface{{{surface}}}; "
                f"Layers{{{self.circumferential_cells}}}; Recombine; }}"
            )

        handles: dict[tuple[int, int], str] = {}
        for i in range(nx):
            for j in range(ny):
                handle = f"sweep_{i}_{j}"
                handles[(i, j)] = handle
                lines.append(f"{handle}[] = {sweep(surface_id[(i, j)])};")
        lines.append("")

        for material in self.materials():
            members = [
                f"{handles[(i, j)]}[1]"
                for i, segment in enumerate(self.segments)
                for j, layer in enumerate(self.layers)
                if self.material_of(segment, layer) == material
            ]
            lines.append(
                'Physical Volume("{}", {}) = {{{}}};'.format(
                    material, material_ids[material], ", ".join(members)
                )
            )

        # Lateral-face indices follow the curve-loop order (inner, east, outer, west).
        faces: dict[str, list[str]] = {
            "inner": [f"{handles[(i, 0)]}[2]" for i in range(nx)],
            "outer": [f"{handles[(i, ny - 1)]}[4]" for i in range(nx)],
            "west": [f"{handles[(0, j)]}[5]" for j in range(ny)],
            "east": [f"{handles[(nx - 1, j)]}[3]" for j in range(ny)],
        }
        if self.revolve_deg != 360.0:
            faces["symmetry_start"] = [
                str(surface_id[(i, j)]) for i in range(nx) for j in range(ny)
            ]
            faces["symmetry_end"] = [
                f"{handles[(i, j)]}[0]" for i in range(nx) for j in range(ny)
            ]
        for face, members in faces.items():
            lines.append(
                'Physical Surface("{}", {}) = {{{}}};'.format(
                    face, boundary_ids[face], ", ".join(members)
                )
            )
        return lines

    def write(self, directory: str | Path) -> Path:
        """Write ``mesh.geo`` into ``directory`` and return its path."""
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        geo_path = target / "mesh.geo"
        geo_path.write_text(self.geo_script(), encoding="utf-8")
        return geo_path

    def generate(self, directory: str | Path, *, timeout_seconds: int = 300) -> "MeshOutcome":
        """Write the ``.geo`` and mesh it with Gmsh when Gmsh is available.

        Returns a :class:`MeshOutcome` describing what happened. When Gmsh is
        absent the geometry is still written and the command needed to mesh it
        elsewhere is returned, so the model can be transferred rather than lost.
        """
        target = Path(directory)
        geo_path = self.write(target)
        msh_path = target / "mesh.msh"
        dimension = self.dimension
        command = (
            f"gmsh -{dimension} -order {self.element_order} {geo_path.name} "
            f"-o {msh_path.name}"
        )

        if find_spec("gmsh") is not None:
            try:
                import gmsh  # noqa: PLC0415 - optional dependency, imported on demand

                gmsh.initialize()
                try:
                    gmsh.option.setNumber("General.Terminal", 0)
                    gmsh.open(str(geo_path))
                    gmsh.model.mesh.generate(dimension)
                    gmsh.write(str(msh_path))
                finally:
                    gmsh.finalize()
            except Exception as error:  # pragma: no cover - depends on the Gmsh build
                return MeshOutcome(
                    status="failed",
                    geo_path=geo_path,
                    mesh_path=None,
                    command=command,
                    message=f"Gmsh Python API failed: {error}",
                )
            return MeshOutcome(
                status="completed",
                geo_path=geo_path,
                mesh_path=msh_path,
                command=command,
                message="meshed with the Gmsh Python API",
            )

        if shutil.which("gmsh"):
            try:
                completed = subprocess.run(  # noqa: S603 - fixed command shape
                    ["gmsh", f"-{dimension}", "-order", str(self.element_order),
                     geo_path.name, "-o", msh_path.name],
                    cwd=str(target),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
            except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover
                return MeshOutcome("failed", geo_path, None, command, str(error))
            if completed.returncode == 0 and msh_path.exists():
                return MeshOutcome(
                    "completed", geo_path, msh_path, command, "meshed with the gmsh executable"
                )
            return MeshOutcome(
                "failed", geo_path, None, command, (completed.stderr or completed.stdout)[-800:]
            )

        return MeshOutcome(
            status="not_executed",
            geo_path=geo_path,
            mesh_path=None,
            command=command,
            message="Gmsh is not installed; the geometry was written and can be meshed "
            "elsewhere with the returned command.",
        )


@dataclass(frozen=True)
class MeshOutcome:
    """Result of writing and (optionally) generating the mesh."""

    status: str
    geo_path: Path
    mesh_path: Path | None
    command: str
    message: str

    @property
    def meshed(self) -> bool:
        return self.status == "completed" and self.mesh_path is not None


def detect_gmsh() -> str | None:
    """Return how Gmsh can be reached (``python``, ``cli``), or ``None``."""
    if find_spec("gmsh") is not None:
        return "python"
    if shutil.which("gmsh"):
        return "cli"
    return None


def _require_positive(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
