"""Choose a finite-element backend, write the case, run it and read it back.

Python has no single finite-element package the way it has one dominant
finite-volume CFD code. The right choice depends on the problem, and picking the
heaviest framework for a one-dimensional conduction question wastes a day, while
picking the lightest for a coupled nonlinear thermo-mechanical problem produces an
answer that cannot be defended. :func:`recommend_backend` makes that choice
explicit and states why, in the same spirit as the multiphase-model screening in
the CFD-coupling skill.

The case itself is written as data plus a fixed solver script: ``inputs.json``
holds the mesh reference, the per-material properties and the boundary conditions;
``case.py`` reads it and solves. Nothing is copied from a tutorial and silently
edited, and the same ``inputs.json`` drives both the scikit-fem and the FEniCSx
script, so a model can be promoted from the light backend to the heavy one without
being rebuilt.

Writing a case never requires a finite-element package to be installed. Running it
does; when the backend is absent the run is reported as not executed rather than
raising, so the generated case can still be inspected, committed or transferred.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

BACKENDS: tuple[str, ...] = (
    "scikit-fem",
    "fenicsx",
    "sfepy",
    "mfem",
    "openseespy",
    "pynite",
)

_IMPORT_NAMES: dict[str, str] = {
    "scikit-fem": "skfem",
    "fenicsx": "dolfinx",
    "sfepy": "sfepy",
    "mfem": "mfem",
    "openseespy": "openseespy",
    "pynite": "PyNite",
}

# Above this many degrees of freedom a pure-Python assembly stops being the
# bottleneck-free choice and a compiled, parallel backend earns its setup cost.
_LARGE_PROBLEM_DOF = 2_000_000

_GENERATED_BACKENDS = ("scikit-fem", "fenicsx")


@dataclass(frozen=True)
class BackendRecommendation:
    """Which finite-element backend fits the problem, and why."""

    backend: str
    rationale: str
    alternatives: tuple[str, ...]
    generated: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MaterialAssignment:
    """Properties of one meshed material group."""

    name: str
    conductivity_w_per_mk: float
    volumetric_heat_capacity_j_per_m3k: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "conductivity_w_per_mk": float(self.conductivity_w_per_mk),
            "volumetric_heat_capacity_j_per_m3k": (
                None
                if self.volumetric_heat_capacity_j_per_m3k is None
                else float(self.volumetric_heat_capacity_j_per_m3k)
            ),
        }


@dataclass(frozen=True)
class BoundaryCondition:
    """One boundary condition on a named mesh face.

    ``kind`` is ``robin`` (a film coefficient and a bulk temperature - the normal
    case, and the one a NeqSim fluid state feeds directly), ``dirichlet`` (a fixed
    surface temperature - only defensible when the surface really is held there),
    ``flux`` (a prescribed heat flux) or ``adiabatic`` (no term, which is what a
    symmetry plane is).
    """

    patch: str
    kind: str = "robin"
    film_coefficient_w_per_m2k: float | None = None
    temperature_c: float | None = None
    flux_w_per_m2: float | None = None

    def __post_init__(self) -> None:
        kind = self.kind.strip().lower()
        if kind not in {"robin", "dirichlet", "flux", "adiabatic"}:
            raise ValueError(
                "kind must be 'robin', 'dirichlet', 'flux' or 'adiabatic'"
            )
        if kind == "robin":
            _require_positive("film_coefficient_w_per_m2k", self.film_coefficient_w_per_m2k)
            if self.temperature_c is None:
                raise ValueError("a robin boundary needs a bulk temperature_c")
        if kind == "dirichlet" and self.temperature_c is None:
            raise ValueError("a dirichlet boundary needs a temperature_c")
        if kind == "flux" and self.flux_w_per_m2 is None:
            raise ValueError("a flux boundary needs a flux_w_per_m2")

    def as_dict(self) -> dict[str, Any]:
        return {
            "patch": self.patch,
            "kind": self.kind.strip().lower(),
            "film_coefficient_w_per_m2k": self.film_coefficient_w_per_m2k,
            "temperature_c": self.temperature_c,
            "flux_w_per_m2": self.flux_w_per_m2,
        }


@dataclass(frozen=True)
class TransientSettings:
    """Time integration settings for a transient conduction solve."""

    initial_temperature_c: float
    duration_s: float
    time_step_s: float
    samples: int = 40

    def __post_init__(self) -> None:
        _require_positive("duration_s", self.duration_s)
        _require_positive("time_step_s", self.time_step_s)
        if self.samples < 2:
            raise ValueError("samples must be at least 2")

    def as_dict(self) -> dict[str, Any]:
        return {
            "initial_temperature_c": float(self.initial_temperature_c),
            "duration_s": float(self.duration_s),
            "time_step_s": float(self.time_step_s),
            "samples": int(self.samples),
        }


@dataclass(frozen=True)
class ConductionProblem:
    """A meshed conduction or species-diffusion problem, ready to be written out.

    The same structure serves heat conduction and species diffusion: replace
    conductivity with diffusivity and volumetric heat capacity with porosity, and
    the operator is identical. ``axisymmetric`` treats the second mesh coordinate
    as a radius, which is what an r-z slice of a pipe, a vessel or a wellbore is.
    """

    name: str
    mesh_file: str
    materials: Sequence[MaterialAssignment]
    boundaries: Sequence[BoundaryCondition]
    axisymmetric: bool = False
    transient: TransientSettings | None = None
    material_tags: Mapping[str, int] | None = None
    boundary_tags: Mapping[str, int] | None = None
    dimension: int = 2

    def __post_init__(self) -> None:
        if not self.materials:
            raise ValueError("at least one material assignment is required")
        if not self.boundaries:
            raise ValueError("at least one boundary condition is required")
        names = [item.name for item in self.materials]
        if len(set(names)) != len(names):
            raise ValueError("material names must be unique")
        patches = [item.patch for item in self.boundaries]
        if len(set(patches)) != len(patches):
            raise ValueError("boundary patches must be unique")
        if self.transient is not None:
            missing = [
                item.name
                for item in self.materials
                if item.volumetric_heat_capacity_j_per_m3k is None
            ]
            if missing:
                raise ValueError(
                    "a transient solve needs a volumetric heat capacity for every "
                    "material; missing for: " + ", ".join(missing)
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "fem-coupling/1.0",
            "name": self.name,
            "mesh_file": self.mesh_file,
            "axisymmetric": bool(self.axisymmetric),
            "materials": {item.name: item.as_dict() for item in self.materials},
            "boundaries": [item.as_dict() for item in self.boundaries],
            "transient": None if self.transient is None else self.transient.as_dict(),
            "material_tags": dict(self.material_tags or {}),
            "boundary_tags": dict(self.boundary_tags or {}),
            "dimension": int(self.dimension),
        }

    @classmethod
    def from_mesh_spec(
        cls,
        spec: Any,
        *,
        name: str,
        mesh_file: str,
        materials: Sequence[MaterialAssignment],
        boundaries: Sequence[BoundaryCondition],
        transient: TransientSettings | None = None,
    ) -> "ConductionProblem":
        """Build a problem from a :class:`fem_coupling.mesh.FemMeshSpec`.

        The physical-group tags are taken straight from the mesh specification, so
        the FEniCSx script (which addresses groups by integer tag) and the
        scikit-fem script (which addresses them by name) see the same partition.
        A swept mesh is already three-dimensional, so the axisymmetric weighting is
        switched off for it - applying it to a revolved model would count the
        circumference twice.
        """
        axisymmetric = getattr(spec, "kind", "") == "axisymmetric_section" and not getattr(
            spec, "is_three_dimensional", False
        )
        return cls(
            name=name,
            mesh_file=mesh_file,
            materials=materials,
            boundaries=boundaries,
            axisymmetric=axisymmetric,
            transient=transient,
            material_tags=spec.material_ids(),
            boundary_tags=spec.boundary_ids(),
            dimension=getattr(spec, "dimension", 2),
        )


@dataclass(frozen=True)
class RunStep:
    """One command in the case workflow and how it ended."""

    command: str
    returncode: int | None
    stdout_tail: str
    stderr_tail: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class RunOutcome:
    """Result of executing the generated case."""

    status: str
    steps: tuple[RunStep, ...]
    backend: str
    message: str

    @property
    def executed(self) -> bool:
        return self.status in {"completed", "failed"}


@dataclass(frozen=True)
class FemResults:
    """Engineering quantities recovered from a solved case."""

    backend: str
    degrees_of_freedom: int | None
    element_count: int | None
    temperature_min_c: float | None
    temperature_max_c: float | None
    temperature_mean_c: float | None
    boundary_heat_flow_w: Mapping[str, float]
    boundary_mean_temperature_c: Mapping[str, float]
    times_s: tuple[float, ...]
    history_min_c: tuple[float, ...]
    history_max_c: tuple[float, ...]
    energy_balance_error_percent: float | None
    findings: tuple[str, ...]


def detect_backends() -> dict[str, bool]:
    """Report which finite-element backends are importable in this environment."""
    return {
        backend: find_spec(_IMPORT_NAMES[backend]) is not None for backend in BACKENDS
    }


def recommend_backend(
    *,
    dimension: int,
    physics: str = "conduction",
    coupled: bool = False,
    nonlinear: bool = False,
    structural_frame: bool = False,
    dynamic: bool = False,
    estimated_dof: int | None = None,
    high_order: bool = False,
) -> BackendRecommendation:
    """Recommend a finite-element backend for the problem at hand.

    ``physics`` is ``conduction``, ``diffusion``, ``elasticity`` or
    ``thermo_mechanical``. ``structural_frame`` marks a beam, frame or truss
    idealisation rather than a continuum. The recommendation states which backends
    this skill can generate a case for and which must be set up by hand.
    """
    if dimension not in (1, 2, 3):
        raise ValueError("dimension must be 1, 2 or 3")
    physics_key = (physics or "").strip().lower()
    if physics_key not in {"conduction", "diffusion", "elasticity", "thermo_mechanical"}:
        raise ValueError(
            "physics must be 'conduction', 'diffusion', 'elasticity' or "
            "'thermo_mechanical'"
        )

    warnings: list[str] = []
    available = detect_backends()

    if structural_frame:
        backend = "openseespy" if (nonlinear or dynamic) else "pynite"
        rationale = (
            "A beam, frame or truss idealisation is a structural-element problem, not "
            "a continuum one. "
            + (
                "Nonlinear or dynamic response puts it in OpenSeesPy territory."
                if (nonlinear or dynamic)
                else "A linear frame is quicker and clearer in PyNite."
            )
        )
        alternatives = ("openseespy", "pynite")
    elif dimension == 1 and physics_key in {"conduction", "diffusion"} and not coupled:
        backend = "scikit-fem"
        rationale = (
            "A one-dimensional linear conduction or diffusion problem does not need a "
            "finite-element framework at all: solve it with "
            "fem_coupling.conduction.RadialConductionModel, which has no dependencies "
            "and cross-checks itself against the closed-form resistance."
        )
        alternatives = ("scikit-fem",)
        warnings.append(
            "Prefer the built-in one-dimensional solver over any external backend "
            "here; it is verifiable against an analytic result and they are not."
        )
    elif coupled or physics_key == "thermo_mechanical" or (nonlinear and dimension == 3):
        backend = "fenicsx"
        rationale = (
            "Coupled or nonlinear multiphysics needs a variational framework that can "
            "express the coupled weak form directly; FEniCSx/DOLFINx is the mature "
            "Python choice."
        )
        alternatives = ("fenicsx", "sfepy", "mfem")
    elif estimated_dof is not None and estimated_dof > _LARGE_PROBLEM_DOF:
        backend = "mfem"
        rationale = (
            f"An estimated {estimated_dof:,} degrees of freedom is past the point where "
            "a pure-Python assembly is comfortable; MFEM (through PyMFEM) is built for "
            "high-order and parallel solves at this size."
        )
        alternatives = ("mfem", "fenicsx")
    elif high_order:
        backend = "fenicsx"
        rationale = (
            "High-order elements are where a framework with a full function-space "
            "abstraction pays for itself."
        )
        alternatives = ("fenicsx", "mfem")
    elif dimension == 2:
        backend = "scikit-fem"
        rationale = (
            "A two-dimensional linear scalar problem is exactly what scikit-fem is "
            "good at: pure NumPy and SciPy, installs with pip anywhere including "
            "Colab, and the assembly is readable enough to review."
        )
        alternatives = ("scikit-fem", "sfepy", "fenicsx")
    else:
        backend = "fenicsx"
        rationale = (
            "A three-dimensional continuum solve is past scikit-fem's comfortable "
            "range; FEniCSx handles the mesh sizes and solvers involved."
        )
        alternatives = ("fenicsx", "mfem", "sfepy")

    if not available.get(backend, False):
        warnings.append(
            f"'{backend}' is not installed in this environment; the case will be "
            "written with the command needed to run it elsewhere."
        )
    if backend not in _GENERATED_BACKENDS:
        warnings.append(
            f"This skill does not generate a '{backend}' case. The recommendation "
            "stands, but the model must be set up in that package by hand."
        )

    return BackendRecommendation(
        backend=backend,
        rationale=rationale,
        alternatives=tuple(alternatives),
        generated=backend in _GENERATED_BACKENDS,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class FemCase:
    """A generated finite-element case: a mesh, an ``inputs.json`` and a solver script."""

    problem: ConductionProblem
    backend: str = "scikit-fem"

    def __post_init__(self) -> None:
        if self.backend not in _GENERATED_BACKENDS:
            raise ValueError(
                "a case can only be generated for "
                + " or ".join(_GENERATED_BACKENDS)
                + f"; '{self.backend}' must be set up by hand"
            )

    def write(self, directory: str | Path) -> Path:
        """Write ``inputs.json`` and ``case.py`` into ``directory``.

        The mesh referenced by the problem is copied into the case directory when
        it lives elsewhere, so the directory is self-contained and can be moved to
        a machine that has the backend installed.
        """
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)

        payload = self.problem.as_dict()
        if self.backend == "fenicsx" and not (payload["material_tags"] and payload["boundary_tags"]):
            raise ValueError(
                "a FEniCSx case needs material_tags and boundary_tags; build the "
                "problem with ConductionProblem.from_mesh_spec so the physical-group "
                "ids travel with it"
            )
        mesh_source = Path(self.problem.mesh_file)
        if mesh_source.exists() and mesh_source.resolve().parent != target.resolve():
            shutil.copy2(mesh_source, target / mesh_source.name)
        payload["mesh_file"] = mesh_source.name

        (target / "inputs.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        script = _SKFEM_SCRIPT if self.backend == "scikit-fem" else _FENICSX_SCRIPT
        (target / "case.py").write_text(script, encoding="utf-8")
        (target / "README.txt").write_text(
            _CASE_README.format(backend=self.backend, name=self.problem.name),
            encoding="utf-8",
        )
        return target

    def command(self) -> str:
        """The command that runs this case."""
        return "python case.py"

    def run(self, directory: str | Path, *, timeout_seconds: int = 1800) -> RunOutcome:
        """Execute the generated case when the backend is importable.

        Returns a not-executed outcome rather than raising when the backend is
        missing, so a case can be built on a laptop and run on a cluster.
        """
        target = Path(directory)
        if find_spec(_IMPORT_NAMES[self.backend]) is None:
            return RunOutcome(
                status="not_executed",
                steps=(),
                backend=self.backend,
                message=(
                    f"{self.backend} is not installed. Run '{self.command()}' in "
                    f"{target} on a machine that has it."
                ),
            )

        try:
            completed = subprocess.run(  # noqa: S603 - fixed command shape
                [sys.executable, "case.py"],
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover
            return RunOutcome(
                status="failed",
                steps=(RunStep(self.command(), None, "", str(error)),),
                backend=self.backend,
                message=str(error),
            )

        step = RunStep(
            command=self.command(),
            returncode=completed.returncode,
            stdout_tail=_tail(completed.stdout),
            stderr_tail=_tail(completed.stderr),
        )
        status = "completed" if completed.returncode == 0 else "failed"
        return RunOutcome(
            status=status,
            steps=(step,),
            backend=self.backend,
            message="solved" if status == "completed" else "the solver script failed",
        )


def read_case_results(directory: str | Path) -> FemResults:
    """Read ``results.json`` written by a solved case into engineering numbers."""
    path = Path(directory) / "results.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no results.json in {directory}; the case has not been run successfully"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))

    flows = {str(k): float(v) for k, v in (payload.get("boundary_heat_flow_w") or {}).items()}
    findings = list(payload.get("findings") or [])

    balance = payload.get("energy_balance_error_percent")
    if balance is None and len(flows) >= 2:
        inflow = sum(value for value in flows.values() if value > 0.0)
        net = sum(flows.values())
        balance = 100.0 * abs(net) / inflow if inflow > 0.0 else None
    if balance is not None and balance > 1.0:
        findings.append(
            f"Boundary energy balance closes to only {balance:.2f} %; refine the mesh "
            "or check that every boundary carries a condition."
        )

    return FemResults(
        backend=str(payload.get("backend", "unknown")),
        degrees_of_freedom=payload.get("degrees_of_freedom"),
        element_count=payload.get("element_count"),
        temperature_min_c=payload.get("temperature_min_c"),
        temperature_max_c=payload.get("temperature_max_c"),
        temperature_mean_c=payload.get("temperature_mean_c"),
        boundary_heat_flow_w=flows,
        boundary_mean_temperature_c={
            str(k): float(v)
            for k, v in (payload.get("boundary_mean_temperature_c") or {}).items()
        },
        times_s=tuple(payload.get("times_s") or ()),
        history_min_c=tuple(payload.get("history_min_c") or ()),
        history_max_c=tuple(payload.get("history_max_c") or ()),
        energy_balance_error_percent=balance,
        findings=tuple(findings),
    )


_CASE_README = """FEM case generated by the NeqSim fem-coupling skill.

  model:   {name}
  backend: {backend}

  inputs.json  the problem: mesh reference, per-material properties, boundary
               conditions and (optionally) the transient settings. Edit this,
               not the script.
  case.py      a fixed solver script. It reads inputs.json and writes
               results.json plus field data. The same inputs.json drives the
               scikit-fem and the FEniCSx script.
  mesh.msh     the Gmsh mesh, with a physical group per material and per face.

Run with:  python case.py
"""


_SKFEM_SCRIPT = '''"""Solve the conduction / diffusion problem described by inputs.json.

Generated by the NeqSim fem-coupling skill. Backend: scikit-fem.

Everything that describes the physics lives in inputs.json; this script only
assembles and solves. Material groups and boundary faces are addressed by the
physical names carried in the Gmsh mesh, so nothing depends on node numbering.
"""

import json
from pathlib import Path

import numpy as np
import skfem
from skfem import Basis, BilinearForm, FacetBasis, Functional, LinearForm, condense, solve
from skfem.helpers import dot, grad

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
AXISYMMETRIC = bool(CONFIG["axisymmetric"])

_ELEMENTS = {
    "MeshTri1": skfem.ElementTriP1,
    "MeshTri2": skfem.ElementTriP2,
    "MeshQuad1": skfem.ElementQuad1,
    "MeshQuad2": skfem.ElementQuad2,
    "MeshTet1": skfem.ElementTetP1,
    "MeshHex1": skfem.ElementHex1,
}


def weight(w):
    """Axisymmetric volume weight: the second coordinate is the radius."""
    return w.x[1] if AXISYMMETRIC else 1.0


def conduction_form(conductivity):
    @BilinearForm
    def form(u, v, w):
        return conductivity * weight(w) * dot(grad(u), grad(v))

    return form


def capacity_form(capacity):
    @BilinearForm
    def form(u, v, w):
        return capacity * weight(w) * u * v

    return form


def robin_form(film):
    @BilinearForm
    def form(u, v, w):
        return film * weight(w) * u * v

    return form


def source_form(magnitude):
    @LinearForm
    def form(v, w):
        return magnitude * weight(w) * v

    return form


def main():
    mesh = skfem.Mesh.load(str(HERE / CONFIG["mesh_file"]))
    element_class = _ELEMENTS.get(type(mesh).__name__)
    if element_class is None:
        raise SystemExit("unsupported mesh type: " + type(mesh).__name__)
    element = element_class()
    basis = Basis(mesh, element)

    subdomains = mesh.subdomains or {}
    boundaries = mesh.boundaries or {}

    stiffness = None
    mass = None
    transient = CONFIG.get("transient")

    for name, properties in CONFIG["materials"].items():
        if name not in subdomains:
            raise SystemExit(
                "material group '" + name + "' is not in the mesh; groups present: "
                + ", ".join(sorted(subdomains))
            )
        sub = Basis(mesh, element, elements=subdomains[name])
        block = conduction_form(properties["conductivity_w_per_mk"]).assemble(sub)
        stiffness = block if stiffness is None else stiffness + block
        if transient is not None:
            capacity = capacity_form(
                properties["volumetric_heat_capacity_j_per_m3k"]
            ).assemble(sub)
            mass = capacity if mass is None else mass + capacity

    load = basis.zeros()
    dirichlet_dofs = np.array([], dtype=np.int64)
    dirichlet_values = basis.zeros()
    facet_bases = {}

    for condition in CONFIG["boundaries"]:
        patch = condition["patch"]
        kind = condition["kind"]
        if kind == "adiabatic":
            continue
        if patch not in boundaries:
            raise SystemExit(
                "boundary '" + patch + "' is not in the mesh; faces present: "
                + ", ".join(sorted(boundaries))
            )
        facets = FacetBasis(mesh, element, facets=boundaries[patch])
        facet_bases[patch] = facets
        if kind == "robin":
            film = condition["film_coefficient_w_per_m2k"]
            stiffness = stiffness + robin_form(film).assemble(facets)
            load = load + source_form(film * condition["temperature_c"]).assemble(facets)
        elif kind == "flux":
            load = load + source_form(condition["flux_w_per_m2"]).assemble(facets)
        elif kind == "dirichlet":
            dofs = basis.get_dofs(boundaries[patch])
            dirichlet_dofs = np.union1d(dirichlet_dofs, dofs.flatten())
            dirichlet_values[dofs.flatten()] = condition["temperature_c"]

    def constrain(matrix, vector):
        return condense(matrix, vector, x=dirichlet_values, D=dirichlet_dofs)

    times = []
    history_min = []
    history_max = []

    if transient is None:
        if dirichlet_dofs.size == 0:
            temperature = solve(stiffness, load)
        else:
            temperature = solve(*constrain(stiffness, load))
    else:
        steps = max(1, int(round(transient["duration_s"] / transient["time_step_s"])))
        dt = transient["duration_s"] / steps
        system = mass / dt + stiffness
        temperature = basis.zeros() + transient["initial_temperature_c"]
        if dirichlet_dofs.size:
            temperature[dirichlet_dofs] = dirichlet_values[dirichlet_dofs]
        sample_every = max(1, steps // (transient["samples"] - 1))
        times.append(0.0)
        history_min.append(float(temperature.min()))
        history_max.append(float(temperature.max()))
        for step in range(1, steps + 1):
            rhs = mass @ temperature / dt + load
            if dirichlet_dofs.size == 0:
                temperature = solve(system, rhs)
            else:
                temperature = solve(*constrain(system, rhs))
            if step % sample_every == 0 or step == steps:
                times.append(step * dt)
                history_min.append(float(temperature.min()))
                history_max.append(float(temperature.max()))

    heat_flow = {}
    mean_temperature = {}
    scale = 2.0 * np.pi if AXISYMMETRIC else 1.0

    for condition in CONFIG["boundaries"]:
        patch = condition["patch"]
        if patch not in facet_bases:
            continue
        facets = facet_bases[patch]
        field = facets.interpolate(temperature)

        @Functional
        def surface_temperature(w):
            return w["T"] * weight(w)

        @Functional
        def surface_area(w):
            return weight(w) + 0.0 * w["T"]

        area = surface_area.assemble(facets, T=field)
        if area > 0.0:
            mean_temperature[patch] = float(
                surface_temperature.assemble(facets, T=field) / area
            )
        if condition["kind"] == "robin":
            film = condition["film_coefficient_w_per_m2k"]
            bulk = condition["temperature_c"]

            @Functional
            def influx(w):
                return film * (bulk - w["T"]) * weight(w)

            heat_flow[patch] = float(influx.assemble(facets, T=field) * scale)
        elif condition["kind"] == "flux":
            heat_flow[patch] = float(condition["flux_w_per_m2"] * area * scale)

    results = {
        "schema": "fem-coupling/1.0",
        "backend": "scikit-fem",
        "name": CONFIG["name"],
        "axisymmetric": AXISYMMETRIC,
        "degrees_of_freedom": int(basis.N),
        "element_count": int(mesh.t.shape[1]),
        "temperature_min_c": float(temperature.min()),
        "temperature_max_c": float(temperature.max()),
        "temperature_mean_c": float(temperature.mean()),
        "boundary_heat_flow_w": heat_flow,
        "boundary_mean_temperature_c": mean_temperature,
        "times_s": times,
        "history_min_c": history_min,
        "history_max_c": history_max,
        "findings": [],
    }
    if AXISYMMETRIC:
        results["findings"].append(
            "Axisymmetric model: boundary heat flow is per unit axial length of the "
            "modelled section, integrated over 2*pi radians."
        )

    np.savez(HERE / "field.npz", points=mesh.p, temperature=temperature)
    try:
        mesh.save(str(HERE / "field.vtu"), point_data={"temperature": temperature})
        results["field_file"] = "field.vtu"
    except Exception as error:
        results["field_file"] = None
        results["findings"].append("field.vtu could not be written: " + str(error))

    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("solved:", results["name"], "dofs", results["degrees_of_freedom"])


if __name__ == "__main__":
    main()
'''


_FENICSX_SCRIPT = '''"""Solve the conduction / diffusion problem described by inputs.json.

Generated by the NeqSim fem-coupling skill. Backend: FEniCSx / DOLFINx.

Everything that describes the physics lives in inputs.json; this script only
assembles and solves. Material groups and boundary faces are addressed by the
integer physical tags the fem-coupling mesh generator writes explicitly, so the
partition matches the one the scikit-fem script sees by name.

Targets DOLFINx 0.8 and later. Run in serial or with mpirun.
"""

import json
from pathlib import Path

import numpy as np
import ufl
from dolfinx import fem
from dolfinx.fem.petsc import LinearProblem
from dolfinx.io import XDMFFile, gmshio
from mpi4py import MPI
from petsc4py import PETSc

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
AXISYMMETRIC = bool(CONFIG["axisymmetric"])
MATERIAL_TAGS = CONFIG["material_tags"]
BOUNDARY_TAGS = CONFIG["boundary_tags"]
GEOMETRIC_DIMENSION = int(CONFIG.get("dimension", 2))


def main():
    domain, cell_tags, facet_tags = gmshio.read_from_msh(
        str(HERE / CONFIG["mesh_file"]), MPI.COMM_WORLD, gdim=GEOMETRIC_DIMENSION
    )
    space = fem.functionspace(domain, ("Lagrange", 1))
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    coordinates = ufl.SpatialCoordinate(domain)
    weight = coordinates[1] if AXISYMMETRIC else 1.0

    dx = ufl.Measure("dx", domain=domain, subdomain_data=cell_tags)
    ds = ufl.Measure("ds", domain=domain, subdomain_data=facet_tags)

    transient = CONFIG.get("transient")
    previous = fem.Function(space)
    if transient is not None:
        previous.x.array[:] = transient["initial_temperature_c"]
        steps = max(1, int(round(transient["duration_s"] / transient["time_step_s"])))
        dt = transient["duration_s"] / steps
    else:
        steps, dt = 0, 0.0

    bilinear = None
    linear = None
    for name, properties in CONFIG["materials"].items():
        tag = MATERIAL_TAGS[name]
        conductivity = properties["conductivity_w_per_mk"]
        term = conductivity * weight * ufl.dot(ufl.grad(trial), ufl.grad(test)) * dx(tag)
        bilinear = term if bilinear is None else bilinear + term
        if transient is not None:
            capacity = properties["volumetric_heat_capacity_j_per_m3k"] / dt
            bilinear = bilinear + capacity * weight * trial * test * dx(tag)
            mass = capacity * weight * previous * test * dx(tag)
            linear = mass if linear is None else linear + mass

    if linear is None:
        linear = fem.Constant(domain, PETSc.ScalarType(0.0)) * weight * test * ufl.dx

    dirichlet = []
    for condition in CONFIG["boundaries"]:
        kind = condition["kind"]
        if kind == "adiabatic":
            continue
        tag = BOUNDARY_TAGS[condition["patch"]]
        if kind == "robin":
            film = condition["film_coefficient_w_per_m2k"]
            bulk = condition["temperature_c"]
            bilinear = bilinear + film * weight * trial * test * ds(tag)
            linear = linear + film * bulk * weight * test * ds(tag)
        elif kind == "flux":
            linear = linear + condition["flux_w_per_m2"] * weight * test * ds(tag)
        elif kind == "dirichlet":
            facets = facet_tags.find(tag)
            dofs = fem.locate_dofs_topological(space, domain.topology.dim - 1, facets)
            value = fem.Constant(domain, PETSc.ScalarType(condition["temperature_c"]))
            dirichlet.append(fem.dirichletbc(value, dofs, space))

    options = {"ksp_type": "preonly", "pc_type": "lu"}
    problem = LinearProblem(bilinear, linear, bcs=dirichlet, petsc_options=options)

    times, history_min, history_max = [], [], []
    if transient is None:
        solution = problem.solve()
    else:
        sample_every = max(1, steps // (transient["samples"] - 1))
        times.append(0.0)
        history_min.append(float(previous.x.array.min()))
        history_max.append(float(previous.x.array.max()))
        solution = previous
        for step in range(1, steps + 1):
            solution = problem.solve()
            previous.x.array[:] = solution.x.array
            if step % sample_every == 0 or step == steps:
                times.append(step * dt)
                history_min.append(float(solution.x.array.min()))
                history_max.append(float(solution.x.array.max()))

    scale = 2.0 * np.pi if AXISYMMETRIC else 1.0
    heat_flow, mean_temperature = {}, {}
    for condition in CONFIG["boundaries"]:
        if condition["kind"] == "adiabatic":
            continue
        tag = BOUNDARY_TAGS[condition["patch"]]
        area = fem.assemble_scalar(fem.form(weight * ds(tag)))
        if area > 0.0:
            mean_temperature[condition["patch"]] = float(
                fem.assemble_scalar(fem.form(solution * weight * ds(tag))) / area
            )
        if condition["kind"] == "robin":
            film = condition["film_coefficient_w_per_m2k"]
            bulk = condition["temperature_c"]
            flow = fem.assemble_scalar(
                fem.form(film * (bulk - solution) * weight * ds(tag))
            )
            heat_flow[condition["patch"]] = float(flow * scale)

    results = {
        "schema": "fem-coupling/1.0",
        "backend": "fenicsx",
        "name": CONFIG["name"],
        "axisymmetric": AXISYMMETRIC,
        "degrees_of_freedom": int(space.dofmap.index_map.size_global),
        "element_count": int(domain.topology.index_map(domain.topology.dim).size_global),
        "temperature_min_c": float(solution.x.array.min()),
        "temperature_max_c": float(solution.x.array.max()),
        "temperature_mean_c": float(solution.x.array.mean()),
        "boundary_heat_flow_w": heat_flow,
        "boundary_mean_temperature_c": mean_temperature,
        "times_s": times,
        "history_min_c": history_min,
        "history_max_c": history_max,
        "findings": [],
    }
    if AXISYMMETRIC:
        results["findings"].append(
            "Axisymmetric model: boundary heat flow is per unit axial length of the "
            "modelled section, integrated over 2*pi radians."
        )

    solution.name = "temperature"
    results["field_file"] = None
    try:
        with XDMFFile(domain.comm, str(HERE / "field.xdmf"), "w") as stream:
            stream.write_mesh(domain)
            stream.write_function(solution)
        results["field_file"] = "field.xdmf"
    except Exception as error:
        results["findings"].append("field.xdmf could not be written: " + str(error))

    if domain.comm.rank == 0:
        (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print("solved:", results["name"], "dofs", results["degrees_of_freedom"])


if __name__ == "__main__":
    main()
'''


def _tail(text: str, lines: int = 25) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])


def _require_positive(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
