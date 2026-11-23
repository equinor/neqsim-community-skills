"""Gas-explosion and gas-dispersion CFD workflow on top of OpenFOAM PDRFoam (porosity / distributed resistance + Xi flame wrinkling).

This is the explosion companion of :mod:`cfd_coupling.openfoam`. It writes, runs and reads back a complete PDRFoam case for a
congested module with a stoichiometric cloud (explosion) or for a steady leak (dispersion with a modified ``PDRFoam`` that carries an
``fvOptions`` source in the mixture-fraction equation), computes the cloud metrics that FLACS-type studies report (flammable volume,
equivalent stoichiometric cloud Q9-type, fuel mass), the mesh convergence index and a verification suite with known answers.

Evidence status. Everything produced here is SCREENING. A result may be quoted only after :func:`assess_explosion_readiness` returns
``ready`` (geometry, congestion, source, ignition, confinement/vents and gas detection all present) AND :func:`assess_explosion_quality`
is not ``not_usable`` (verification run, three grids, grid-convergence index). Validation against experiments of congested geometry is a
separate step that this module does NOT perform; the verification suite tests only the combustion thermodynamics, the laminar flame speed
and the pressure-wave machinery. Human review by a qualified explosion engineer is required before any value is used for design.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "pdr_templates"
IMAGE_DEFAULT = "opencfd/openfoam-default:latest"

#: stoichiometric air/fuel mass ratio and unburnt molar mass of the two PDRFoam fuel packages shipped in ``pdr_templates``
FUELS = {
    "methane": {
        "fuel_name": "Methane",
        "afr_st": 17.1667,
        "mw": 16.043,
        "thermo": "thermo_methane",
        "scope": "fuel_methane",
    },
    "propane": {
        "fuel_name": "Propane",
        "afr_st": 15.5776,
        "mw": 44.0962,
        "thermo": "thermo_propane",
        "scope": "fuel_propane",
    },
}

_HEADER = "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class %s;\n    object %s;\n}\n\n"


# ----------------------------------------------------------------------------------------------------------------- readiness gate
REQUIRED_INPUTS = (
    "geometry",
    "congestion",
    "source",
    "ignition_location",
    "vents_confinement",
    "gas_detection",
)


@dataclass
class ExplosionReadiness:
    verdict: str
    missing: list[str]
    findings: list[str]

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "missing": self.missing,
            "findings": self.findings,
        }


def assess_explosion_readiness(inputs: dict[str, object]) -> ExplosionReadiness:
    """Fail closed: an explosion result is not claimed unless every required input is present.

    ``inputs`` maps each name in :data:`REQUIRED_INPUTS` to a truthy evidence object (a dict with at least ``source`` or a non-empty list).
    A value that carries ``{"status": "assumed"}`` is accepted but reported, so the result is labelled screening.
    """
    missing, findings = [], []
    for k in REQUIRED_INPUTS:
        v = inputs.get(k)
        if not v:
            missing.append(k)
        elif isinstance(v, dict) and v.get("status") == "assumed":
            findings.append("%s is an assumption: result is screening only" % k)
    verdict = "not_ready" if missing else ("ready_screening" if findings else "ready")
    if missing:
        findings.append(
            "do not report explosion results: missing " + ", ".join(missing)
        )
    return ExplosionReadiness(verdict, missing, findings)


# -------------------------------------------------------------------------------------------------------------------- grid helper
def stretched_segment(
    length: float, h0: float, growth: float = 1.12
) -> tuple[int, float]:
    """Number of cells and last/first size ratio of a geometric segment of ``length`` starting with cell size ``h0``."""
    if length <= h0 * 1.0001:
        return 1, 1.0
    n = max(
        2, math.ceil(math.log(1.0 + length * (growth - 1.0) / h0) / math.log(growth))
    )
    lo, hi = (
        1.0 + 1e-6,
        4.0,
    )  # solve g so that h0 (g^n - 1)/(g - 1) = length for the integer n
    for _ in range(100):
        g = 0.5 * (lo + hi)
        if h0 * (g**n - 1.0) / (g - 1.0) > length:
            hi = g
        else:
            lo = g
    return n, g ** (n - 1)


def axis_spec(
    far_lo: float | None,
    fine_lo: float,
    fine_hi: float,
    far_hi: float | None,
    h: float,
    growth: float = 1.12,
):
    """PDRblockMesh axis: optional stretched segment, uniform core of cell size ``h``, optional stretched segment."""
    pts, nc, rt = [], [], []
    if far_lo is not None and far_lo < fine_lo - 1e-9:
        n, r = stretched_segment(fine_lo - far_lo, h, growth)
        pts += [far_lo]
        nc += [n]
        rt += [1.0 / r]
    pts += [fine_lo]
    nc += [max(1, round((fine_hi - fine_lo) / h))]
    rt += [1.0]
    pts += [fine_hi]
    if far_hi is not None and far_hi > fine_hi + 1e-9:
        n, r = stretched_segment(far_hi - fine_hi, h, growth)
        pts += [far_hi]
        nc += [n]
        rt += [r]
    return pts, nc, rt


@dataclass
class Domain:
    """Computational domain (m, case frame). The core ``fine`` box is meshed uniformly with cell size ``h`` (scalar or per-axis tuple)."""

    fine: tuple[float, float, float, float, float, float]  # x0 x1 y0 y1 z0 z1
    far: tuple[float, float, float, float, float, float]
    h: object = 1.0
    growth: float = 1.12
    west_wall: bool = True  # x = far x0 is a rigid wall (the explosion barrier)

    def hxyz(self) -> tuple[float, float, float]:
        return (
            tuple(self.h) if isinstance(self.h, (tuple, list)) else (float(self.h),) * 3
        )

    def axes(self):
        fx0, fx1, fy0, fy1, fz0, fz1 = self.fine
        gx0, gx1, gy0, gy1, gz0, gz1 = self.far
        hx, hy, hz = self.hxyz()
        return {
            "x": axis_spec(
                None if self.west_wall else gx0, fx0, fx1, gx1, hx, self.growth
            ),
            "y": axis_spec(gy0, fy0, fy1, gy1, hy, self.growth),
            "z": axis_spec(gz0, fz0, fz1, gz1, hz, self.growth),
        }

    def n_cells(self) -> int:
        n = 1
        for ax in self.axes().values():
            n *= sum(ax[1])
        return n

    @classmethod
    def for_module(
        cls,
        size: tuple[float, float, float],
        h: float,
        margin_cells: int = 3,
        far: tuple[float, ...] | None = None,
        growth: float = 1.25,
        west_wall: bool = True,
    ) -> Domain:
        """Domain whose uniform core is aligned to a module ``size`` = (LX, LY, LZ) with its west wall at x = 0 and floor at z = 0.

        The cell size is adapted per axis so that the module is an integer number of cells (n = round(L / h)). One extra cell below the floor and one
        above the roof is the slab layer, so deck and roof are fully blocked cells (solid) and no gas leaks through a sub-grid plate.
        """
        lx, ly, lz = size
        n = [max(1, round(v / h)) for v in size]
        hx, hy, hz = lx / n[0], ly / n[1], lz / n[2]
        fine = (
            0.0,
            lx + margin_cells * hx,
            -margin_cells * hy,
            ly + margin_cells * hy,
            -hz * max(margin_cells - 1, 1),
            lz + margin_cells * hz,
        )
        far = far or (0.0, lx + 30.0, -25.0, ly + 25.0, -12.0, lz + 14.0)
        return cls(
            fine=fine, far=far, h=(hx, hy, hz), growth=growth, west_wall=west_wall
        )

    def slab_thickness(self) -> float:
        """Thickness of the deck/roof slab layer (one cell in z)."""
        return self.hxyz()[2]


# --------------------------------------------------------------------------------------------------------------- case description
@dataclass
class Cloud:
    """Stoichiometric cuboid cloud (Z-013 F.2.3). ``k0`` / ``eps0``: initial turbulence in the cloud (jet-induced, Z-013 F.4.3)."""

    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    k0: float = 0.5
    length_scale: float = 0.3


@dataclass
class Ignition:
    location: tuple[float, float, float]
    diameter: float = 1.0
    strength: float = 10.0
    start: float = 1e-5
    duration: float = 0.05
    thickness: float = 0.05  # ignitionThickness of the sphere shell (m)


@dataclass
class LeakSource:
    """Momentum-conserving pseudo-source (Birch type): fuel mass rate, thrust, direction, location, cell box."""

    location: tuple[float, float, float]
    direction: tuple[float, float, float]
    fuel_rate_kg_s: float
    thrust_N: float
    box_half_width: float = 0.5
    ramp_s: float = (
        0.0  # linear ramp of the source over this time (avoids a start-up shock in the compressible solver)
    )


@dataclass
class Wind:
    speed: float = 0.0
    face: str = (
        "xmax"  # xmax / ymin / ymax (windward patch); the wind blows into the domain through that face
    )
    intensity: float = 0.1
    length_scale: float = 5.0


@dataclass
class PdrCaseSpec:
    name: str
    domain: Domain
    obstacles_dict: str
    fuel: str = "propane"
    cloud: Cloud | None = None
    ignition: Ignition | None = None
    leak: LeakSource | None = None
    wind: Wind = field(default_factory=Wind)
    end_time: float = 0.3
    write_interval: float = 0.02
    max_co: float = 0.3
    max_dt: float = 1e-3
    monitor_points: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    wall_panel_points: dict[str, list[tuple[float, float, float]]] = field(
        default_factory=dict
    )
    cell_width_sub: float | None = None
    n_outer: int = 10
    solver: str = "PDRFoam"
    betav_min: float = (
        0.2  # cells with volume porosity below this are removed (treated as solid) before the run
    )
    xi_model: str = (
        "transport"  # "fixed" gives Xi = 1 (laminar flame), used by the verification cases
    )
    patches_wall_faces: tuple[int, ...] = (0,)  # 0 = xmin
    extra_functions: str = (
        ""  # additional function-object blocks appended inside controlDict functions {}
    )
    notes: str = ""

    def ft_stoich(self) -> float:
        return 1.0 / (1.0 + FUELS[self.fuel]["afr_st"])


def _janaf_h(fuel: str, block: str, temperature_k: float, mw: float) -> float:
    txt = (TEMPLATES / FUELS[fuel]["thermo"]).read_text(encoding="utf-8")
    start = txt.index("\n%s\n" % block)
    seg = txt[start : start + 900]
    key = "highCpCoeffs" if temperature_k >= 1000.0 else "lowCpCoeffs"
    coeffs = [
        float(x) for x in re.search(key + r"\s*\(([^)]*)\)", seg).group(1).split()
    ]
    a0, a1, a2, a3, a4, a5 = coeffs[:6]
    t = temperature_k
    return (
        8.314462618
        * (a0 * t + a1 * t**2 / 2 + a2 * t**3 / 3 + a3 * t**4 / 4 + a4 * t**5 / 5 + a5)
        / (mw * 1e-3)
    )


def fuel_absolute_enthalpy(fuel: str, temperature_k: float = 288.15) -> float:
    """Absolute (formation-inclusive) specific enthalpy of the fuel [J/kg] from the JANAF template at ``temperature_k``."""
    return _janaf_h(fuel, "fuel", temperature_k, FUELS[fuel]["mw"])


def oxidant_absolute_enthalpy(fuel: str, temperature_k: float = 288.15) -> float:
    """Absolute specific enthalpy of the oxidant (air) [J/kg] from the same template."""
    txt = (TEMPLATES / FUELS[fuel]["thermo"]).read_text(encoding="utf-8")
    mw = float(
        re.search(r"oxidant\s*\{.*?molWeight\s+([0-9.]+)", txt, re.DOTALL).group(1)
    )
    return _janaf_h(fuel, "oxidant", temperature_k, mw)


def leak_enthalpy_source(
    fuel: str, fuel_rate_kg_s: float, temperature_k: float = 288.15
) -> float:
    """Value to give the ``ha`` entry of the leak fvOptions [W].

    The fuel is injected as a passive mass-fraction source (ft) without a density source (PDRFoam's rhoEqn has no fvOptions), i.e. it REPLACES
    local air: the mixture enthalpy changes by m_dot*(h_fuel - h_air). PDRFoam's EaEqn carries the fvOptions term on the left-hand side, so the sign
    of the value given here is the opposite of the physical source. Without this term the injected fuel is heated by its heat of formation.
    """
    return -fuel_rate_kg_s * (
        fuel_absolute_enthalpy(fuel, temperature_k)
        - oxidant_absolute_enthalpy(fuel, temperature_k)
    )


def _fmt(v: Iterable[float]) -> str:
    return "(" + " ".join("%.6g" % x for x in v) + ")"


def _field(
    name: str, dims: str, internal: str, boundary: str, cls: str = "volScalarField"
) -> str:
    return (
        _HEADER % (cls, name)
    ) + "dimensions %s;\ninternalField %s;\nboundaryField\n{\n%s}\n" % (
        dims,
        internal,
        boundary,
    )


def _bc(patch: str, body: str) -> str:
    return "    %s\n    {\n%s    }\n" % (
        patch,
        "".join("        %s\n" % l for l in body.strip().splitlines()),
    )


def write_case(spec: PdrCaseSpec, case_dir: Path) -> Path:
    """Write the complete PDRFoam case tree (constant, system, 0.orig, geometry)."""
    case_dir = Path(case_dir)
    for d in ("constant", "system", "0.orig", "geometry", "fuels"):
        (case_dir / d).mkdir(parents=True, exist_ok=True)
    fuel = FUELS[spec.fuel]
    # --- constant
    for tpl, dst in (
        ("PDRProperties", "constant/PDRProperties"),
        ("turbulenceProperties", "constant/turbulenceProperties"),
        ("g", "constant/g"),
        (fuel["thermo"], "constant/thermophysicalProperties"),
        (fuel["scope"], "fuels/" + spec.fuel),
    ):
        shutil.copyfile(TEMPLATES / tpl, case_dir / dst)
    for tpl in ("fvSchemes", "fvSolution"):
        txt = (TEMPLATES / tpl).read_text(encoding="utf-8")
        if tpl == "fvSolution":
            txt = txt.replace(
                "nOuterCorrectors    10;", "nOuterCorrectors    %d;" % spec.n_outer
            )
        (case_dir / "system" / tpl).write_text(txt, encoding="utf-8")
    if spec.xi_model != "transport":
        pdr = (case_dir / "constant" / "PDRProperties").read_text(encoding="utf-8")
        pdr = re.sub(
            r"^XiModel\s+transport;",
            "XiModel         %s;" % spec.xi_model,
            pdr,
            count=1,
            flags=re.MULTILINE,
        )
        (case_dir / "constant" / "PDRProperties").write_text(pdr, encoding="utf-8")
    ig = spec.ignition
    ign_block = "ignite no;\nignitionSites ();\n"
    if ig is not None:
        ign_block = (
            "ignite yes;\nignitionSites\n(\n    {\n        location %s;\n        diameter %.4g;\n        start %.3g;\n"
            "        duration %.4g;\n        strength %.4g;\n    }\n);\n"
            % (_fmt(ig.location), ig.diameter, ig.start, ig.duration, ig.strength)
        )
    comb = (_HEADER % ("dictionary", "combustionProperties")) + (
        'laminarFlameSpeedCorrelation SCOPE;\nfuel %s;\nfuelFile "fuels/%s";\n'
        % (fuel["fuel_name"], spec.fuel)
        + ign_block
        + "ignitionSphereFraction 1.0;\nignitionThickness %.4g;\nignitionCircleFraction 0.5;\n"
        % (ig.thickness if ig is not None else 0.05)
    )
    (case_dir / "constant" / "combustionProperties").write_text(comb, encoding="utf-8")
    # --- geometry and mesh
    (case_dir / "geometry" / "obstaclesDict").write_text(
        spec.obstacles_dict, encoding="utf-8"
    )
    axes = spec.domain.axes()
    mesh = _HEADER % ("dictionary", "PDRblockMeshDict") + "scale 1.0;\n"
    for ax in "xyz":
        pts, nc, rt = axes[ax]
        mesh += "%s\n{\n    points (%s);\n    nCells (%s);\n    ratios (%s);\n}\n" % (
            ax,
            " ".join("%.6g" % p for p in pts),
            " ".join(str(n) for n in nc),
            " ".join("%.8g" % r for r in rt),
        )
    wind_faces = (
        {"xmax": 1, "ymin": 2, "ymax": 3}[spec.wind.face]
        if spec.wind.speed > 0
        else None
    )
    open_faces = [
        i
        for i in (0, 1, 2, 3, 4, 5)
        if i not in spec.patches_wall_faces and i != wind_faces
    ]
    mesh += (
        "defaultPatch { name defaultFaces; type wall; }\nboundary\n(\n    outer { type patch; faces (%s); }\n"
        % " ".join(map(str, open_faces))
    )
    if wind_faces is not None:
        mesh += "    inlet { type patch; faces (%d); }\n" % wind_faces
    mesh += (
        "    mergingFaces { type wall; faces (); }\n    blockedFaces { type wall; faces (); }\n    wallFaces { type wall; faces (%s); }\n);\n"
        % (" ".join(map(str, spec.patches_wall_faces)))
    )
    (case_dir / "system" / "PDRblockMeshDict").write_text(mesh, encoding="utf-8")
    cw = spec.cell_width_sub or max(spec.domain.hxyz())
    (case_dir / "system" / "PDRsetFieldsDict").write_text(
        _HEADER % ("dictionary", "PDRsetFieldsDict")
        + 'obsFileDir "<case>/geometry";\nobsFileNames (obstaclesDict);\ncellWidth %.4g;\ncellWidthFactor 1.0;\n'
        % cw,
        encoding="utf-8",
    )
    # --- initial cloud
    ft = spec.ft_stoich()
    regions = ""
    if spec.cloud:
        c = spec.cloud
        eps0 = 0.09**0.75 * c.k0**1.5 / max(c.length_scale, 1e-3)
        regions = (
            "    boxToCell\n    {\n        box %s %s;\n        fieldValues\n        (\n            volScalarFieldValue ft %.6g\n"
            "            volScalarFieldValue k %.6g\n            volScalarFieldValue epsilon %.6g\n        );\n    }\n"
            % (_fmt(c.lo), _fmt(c.hi), ft, c.k0, eps0)
        )
    (case_dir / "system" / "setFieldsDict").write_text(
        _HEADER % ("dictionary", "setFieldsDict")
        + "defaultFieldValues\n(\n    volScalarFieldValue p 101325\n    volScalarFieldValue T 288.15\n"
        "    volScalarFieldValue Tu 288.15\n    volScalarFieldValue ft 0\n);\nregions\n(\n"
        + regions
        + ");\n",
        encoding="utf-8",
    )
    # --- fvOptions for the leak
    if spec.leak is not None:
        lk = spec.leak
        lo = [lk.location[i] - lk.box_half_width for i in range(3)]
        hi = [lk.location[i] + lk.box_half_width for i in range(3)]
        d = lk.direction
        nrm = math.sqrt(sum(x * x for x in d)) or 1.0
        fx, fy, fz = [lk.thrust_N * x / nrm for x in d]
        fvo = _HEADER % ("dictionary", "fvOptions")
        r = max(lk.ramp_s, 0.0)

        def ramp(v):
            return (
                "{ explicit table ((0 0) (%.4g %.6g)); implicit none; }" % (r, v)
                if r > 0
                else "(%.6g 0)" % v
            )

        def ramp_vec(vx, vy, vz):
            return (
                "{ explicit table ((0 (0 0 0)) (%.4g (%.6g %.6g %.6g))); implicit none; }"
                % (r, vx, vy, vz)
                if r > 0
                else "((%.6g %.6g %.6g) 0)" % (vx, vy, vz)
            )

        fvo += (
            "leakScalar\n{\n    type scalarSemiImplicitSource;\n    active true;\n    selectionMode cellZone;\n    cellZone leakZone;\n"
            "    volumeMode absolute;\n    sources\n    {\n        ft %s;\n        ha %s;\n    }\n}\n"
            % (
                ramp(lk.fuel_rate_kg_s),
                ramp(leak_enthalpy_source(spec.fuel, lk.fuel_rate_kg_s)),
            )
        )
        fvo += (
            "leakMomentum\n{\n    type vectorSemiImplicitSource;\n    active true;\n    selectionMode cellZone;\n    cellZone leakZone;\n"
            "    volumeMode absolute;\n    sources\n    {\n        U %s;\n    }\n}\n"
            % ramp_vec(fx, fy, fz)
        )
        (case_dir / "constant" / "fvOptions").write_text(fvo, encoding="utf-8")
        leak_actions = (
            "    {\n        name leakCells;\n        type cellSet;\n        action new;\n        source boxToCell;\n        box %s %s;\n    }\n"
            "    {\n        name leakZone;\n        type cellZoneSet;\n        action new;\n        source setToCellZone;\n        set leakCells;\n    }\n"
            % (_fmt(lo), _fmt(hi))
        )
    else:
        leak_actions = ""
    # fully blocked cells (betav ~ 0 from PDRsetFields) are removed with subsetMesh; their faces become the 'blockedFaces' wall patch
    (case_dir / "system" / "topoSetDict").write_text(
        _HEADER % ("dictionary", "topoSetDict")
        + "actions\n(\n    {\n        name fluidCells;\n        type cellSet;\n        action new;\n        source fieldToCell;\n"
        "        field betav;\n        min %.3g;\n        max 1.5;\n    }\n"
        % spec.betav_min
        + leak_actions
        + ");\n",
        encoding="utf-8",
    )
    # --- fields
    w = spec.wind
    u_in = (
        {"xmax": (-w.speed, 0, 0), "ymin": (0, w.speed, 0), "ymax": (0, -w.speed, 0)}[
            w.face
        ]
        if w.speed > 0
        else (0, 0, 0)
    )
    k_in = 1.5 * (w.intensity * w.speed) ** 2 if w.speed > 0 else 1e-4
    eps_in = 0.09**0.75 * k_in**1.5 / w.length_scale if w.speed > 0 else 1e-5
    inlet = w.speed > 0
    io = "type inletOutlet;\ninletValue $internalField;\nvalue $internalField;"

    inlet_cmds: list[tuple[str, str]] = []

    def build(
        name,
        dims,
        internal,
        outer,
        wall,
        inlet_bc,
        block="type zeroGradient;",
        cls="volScalarField",
    ):
        b = (
            _bc("outer", outer)
            + _bc("wallFaces", wall)
            + _bc("blockedFaces", block)
            + _bc("mergingFaces", wall)
        )
        if inlet:
            b += _bc("inlet", inlet_bc)
            inlet_cmds.append((name, " ".join(inlet_bc.split())))
        (case_dir / "0.orig" / name).write_text(
            _field(name, dims, internal, b, cls), encoding="utf-8"
        )

    zg = "type zeroGradient;"
    build(
        "p",
        "[1 -1 -2 0 0 0 0]",
        "uniform 101325",
        "type waveTransmissive;\ngamma 1.3;\nfieldInf 101325;\nlInf 5;\nvalue $internalField;",
        zg,
        zg,
    )
    build(
        "U",
        "[0 1 -1 0 0 0 0]",
        "uniform (0 0 0)",
        io,
        "type fixedValue;\nvalue uniform (0 0 0);",
        "type fixedValue;\nvalue uniform %s;" % _fmt(u_in),
        "type fixedValue;\nvalue uniform (0 0 0);",
        "volVectorField",
    )
    for n in ("T", "Tu"):
        build(
            n,
            "[0 0 0 1 0 0 0]",
            "uniform 288.15",
            io,
            zg,
            "type fixedValue;\nvalue uniform 288.15;",
        )
    build(
        "k",
        "[0 2 -2 0 0 0 0]",
        "uniform %.6g" % k_in,
        io,
        "type kqRWallFunction;\nvalue $internalField;",
        "type fixedValue;\nvalue uniform %.6g;" % k_in,
    )
    build(
        "epsilon",
        "[0 2 -3 0 0 0 0]",
        "uniform %.6g" % eps_in,
        io,
        "type epsilonWallFunction;\nvalue $internalField;",
        "type fixedValue;\nvalue uniform %.6g;" % eps_in,
    )
    build(
        "nut",
        "[0 2 -1 0 0 0 0]",
        "uniform 0",
        io,
        "type nutkWallFunction;\nvalue $internalField;",
        zg,
    )
    for n, v in (
        ("ft", "0"),
        ("GRep", "0"),
        ("GRxp", "0"),
        ("RPers", "0"),
        ("b", "1"),
        ("Xi", "1"),
        ("Xp", "1"),
        ("Su", "0.5"),
    ):
        build(
            n,
            "[0 0 0 0 0 0 0]",
            "uniform " + v,
            io,
            zg,
            "type fixedValue;\nvalue uniform %s;" % v,
        )
    # --- controlDict with probes
    # PDRsetFields rewrites the 0/ fields WITHOUT the user patch "inlet"; the run re-applies the wind boundary conditions with this script
    (case_dir / "system" / "inletPatch.sh").write_text(
        "".join(
            'foamDictionary -entry boundaryField.inlet -set "{%s}" 0/%s > /dev/null\n'
            % (bc, n)
            for n, bc in inlet_cmds
        ),
        encoding="utf-8",
    )
    pts = dict(spec.monitor_points)
    for nm, pl in spec.wall_panel_points.items():
        for i, p in enumerate(pl):
            pts["%s_%02d" % (nm, i)] = p
    names = list(pts)
    (case_dir / "system" / "monitorPoints.json").write_text(
        json.dumps({n: list(pts[n]) for n in names}, indent=1), encoding="utf-8"
    )
    probes = (
        (
            "    probes\n    {\n        type probes;\n        libs (sampling);\n        name probes;\n        writeControl timeStep;\n        writeInterval 1;\n"
            "        fields (p T b ft U);\n        probeLocations\n        (\n"
            + "".join("            %s\n" % _fmt(pts[n]) for n in names)
            + "        );\n    }\n"
        )
        if names
        else ""
    )
    probes += spec.extra_functions
    cd = (
        _HEADER % ("dictionary", "controlDict")
        + "application %s;\nstartFrom startTime;\nstartTime 0;\nstopAt endTime;\nendTime %.6g;\ndeltaT 1e-5;\n"
        "writeControl runTime;\nwriteInterval %.6g;\npurgeWrite 0;\nwriteFormat ascii;\nwritePrecision 8;\nwriteCompression off;\n"
        "timeFormat general;\ntimePrecision 6;\nrunTimeModifiable yes;\nadjustTimeStep yes;\nmaxCo %.3g;\nmaxDeltaT %.3g;\nfunctions\n{\n%s}\n"
        % (
            spec.solver,
            spec.end_time,
            spec.write_interval,
            spec.max_co,
            spec.max_dt,
            probes,
        )
    )
    (case_dir / "system" / "controlDict").write_text(cd, encoding="utf-8")
    return case_dir


# -------------------------------------------------------------------------------------------------------------------- run helpers
def docker_run(
    case_dir: Path,
    commands: Sequence[str],
    bin_dir: Path | None = None,
    cpus: int = 4,
    image: str = IMAGE_DEFAULT,
    timeout: int | None = None,
    trap_fpe: bool = False,
) -> subprocess.CompletedProcess:
    """Run shell commands inside the OpenFOAM image with the case bind-mounted (never ``--rm`` without a mount: the case survives).

    ``trap_fpe=False`` disables floating-point trapping (``FOAM_SIGFPE=false``): PDRFoam raises harmless invalid operations inside the
    Xi / drag sub-models for cells next to removed (fully blocked) cells. The probes are checked for finite values afterwards instead.
    """
    mounts = ["-v", "%s:/case" % case_dir]
    path = "" if trap_fpe else "export FOAM_SIGFPE=false; "
    if bin_dir:
        mounts += ["-v", "%s:/r5bin:ro" % bin_dir]
        path += "export PATH=/r5bin:$PATH; "
    script = "cd /case && %sset -o pipefail; " % path + " && ".join(commands)
    cmd = (
        ["docker", "run", "--rm", "--cpus", str(cpus)]
        + mounts
        + [image, "bash", "-lc", script]
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        creationflags=flags,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def explosion_commands(
    np_procs: int = 1,
    solver: str = "PDRFoam",
    dispersion: bool = False,
    inlet_patch: bool = False,
) -> list[str]:
    """Mesh, PDR fields, solid-cell removal, initial cloud, run (optionally parallel); dispersion adds cell volumes/centres for the cloud metrics."""
    cmds = [
        "rm -rf 0 processor* postProcessing log.*",
        "cp -r 0.orig 0",
        "PDRblockMesh > log.PDRblockMesh 2>&1",
        "PDRsetFields > log.PDRsetFields 2>&1",
        # PDRFoam reads the PDR fields from mesh.facesInstance(): put the mesh in time 0 (the tutorials get this from refineHexMesh)
        "mkdir -p 0/polyMesh && cp -r constant/polyMesh/* 0/polyMesh/",
        "topoSet > log.topoSet 2>&1",
    ]
    if (
        inlet_patch
    ):  # PDRsetFields writes its fields without the user patch "inlet": add zero-gradient, then re-apply the wind BCs
        cmds += [
            'for f in 0/*; do [ -f $f ] && ! grep -qE "^[[:space:]]*inlet[[:space:]]*$" $f && foamDictionary -entry boundaryField.inlet -set "{type zeroGradient;}" $f > /dev/null; done; true',
            "sh system/inletPatch.sh",
        ]
    cmds += [
        "subsetMesh -overwrite -patch blockedFaces fluidCells > log.subsetMesh 2>&1"
    ]
    cmds += ["setFields > log.setFields 2>&1"]
    if np_procs > 1:
        cmds += [
            "printf 'FoamFile{version 2.0;format ascii;class dictionary;object decomposeParDict;}\\nnumberOfSubdomains %d;\\nmethod scotch;\\n' %d > system/decomposeParDict"
            % (np_procs, np_procs),
            "decomposePar -force > log.decomposePar 2>&1",
            "mpirun --allow-run-as-root --oversubscribe -np %d %s -parallel > log.%s 2>&1"
            % (np_procs, solver, solver),
            "reconstructPar %s > log.reconstructPar 2>&1 || true"
            % ("" if dispersion else "-latestTime"),
        ]
    else:
        cmds += ["%s > log.%s 2>&1" % (solver, solver)]
    if dispersion:
        cmds += [
            "postProcess -func writeCellVolumes -latestTime > log.pp1 2>&1",
            "postProcess -func writeCellCentres -latestTime > log.pp2 2>&1",
        ]
    return cmds


# ---------------------------------------------------------------------------------------------------------------- result readers
def read_probes(case_dir: Path, field_name: str = "p"):
    """Return (times, {probe_index: values}) from postProcessing/probes/*/<field>. Scalars only."""
    import numpy as np

    files = sorted(
        (Path(case_dir) / "postProcessing" / "probes").glob("*/" + field_name)
    )
    rows = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                continue
            parts = line.split()
            if parts:
                rows.append([float(x) for x in parts])
    arr = np.array(rows)
    return arr[:, 0], arr[:, 1:]


def pressure_metrics(t, p_pa, p0=101325.0, window_s: float = 0.0):
    """Peak overpressure (Pa), time of peak, positive-phase impulse (Pa s) and duration above 10 % of the peak."""
    import numpy as np

    dp = np.asarray(p_pa) - p0
    i = int(np.argmax(dp))
    peak = float(dp[i])
    pos = np.clip(dp, 0, None)
    imp = float(
        getattr(np, "trapezoid", None)(pos, t)
        if hasattr(np, "trapezoid")
        else np.trapz(pos, t)
    )
    above = t[dp > 0.1 * peak]
    dur = float(above[-1] - above[0]) if len(above) > 1 else 0.0
    return {
        "peak_pa": peak,
        "t_peak_s": float(t[i]),
        "impulse_pa_s": imp,
        "duration_s": dur,
    }


def gci(f1: float, f2: float, f3: float, r: float, fs: float = 1.25):
    """Roache grid-convergence index. f1 finest, f3 coarsest, constant refinement ratio r. Returns dict with p, f_ext, gci_fine (fraction)."""
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0 or e32 == 0 or e32 / e21 <= 0:
        # oscillatory or converged: report the fine-medium difference as the uncertainty band
        return {
            "order": None,
            "f_extrapolated": None,
            "gci_fine": abs(e21) / abs(f1) * fs if f1 else None,
            "monotonic": False,
        }
    p = math.log(abs(e32 / e21)) / math.log(r)
    f_ext = f1 - e21 / (r**p - 1.0)
    g = fs * abs(e21 / f1) / (r**p - 1.0)
    return {"order": p, "f_extrapolated": f_ext, "gci_fine": g, "monotonic": True}


# -------------------------------------------------------------------------------------------------------------- cloud metrics
def laminar_speed_scope(fuel: str, phi: float) -> float:
    """Laminar burning speed (m/s) of the shipped fuel at equivalence ratio ``phi`` (ambient T, p), for cloud-metric weighting.

    Gaussian fit ``S_L = S_max exp(-xi (phi - phi_m)^2)`` inside the flammability limits of the SCOPE file, anchored to the SCOPE stoichiometric
    value (methane 0.35 m/s, propane 0.45 m/s). The SCOPE polynomials of the fuel file are used by PDRFoam itself, but the upper polynomial is
    not a simple function of ``phi - 1`` and cannot be re-evaluated here reliably, so this fit (about +-20 % over 0.6 < phi < 1.5) is used only
    for the equivalent-stoichiometric-cloud weighting.
    """
    txt = (TEMPLATES / FUELS[fuel]["scope"]).read_text(encoding="utf-8")
    lfl = float(re.search(r"lowerFlammabilityLimit\s+([\d.eE+-]+);", txt).group(1))
    ufl = float(re.search(r"upperFlammabilityLimit\s+([\d.eE+-]+);", txt).group(1))
    if phi < lfl or phi > ufl:
        return 0.0
    smax, phim, xi = {"methane": (0.36, 1.07, 6.5), "propane": (0.475, 1.10, 6.0)}[fuel]
    return smax * math.exp(-xi * (phi - phim) ** 2)


def equivalent_stoich_cloud(
    ft_field, cell_volumes, fuel: str = "propane", ref_expansion: float | None = None
) -> dict:
    """Q9-type equivalent stoichiometric cloud volume and flammable volume from a mixture-fraction field.

    ``V_ESC = sum_i V_i * [Su(phi_i) (E(phi_i) - 1)] / [Su(1) (E(1) - 1)]`` (Z-013 F.4.2: weighted by the concentration dependence of the
    burning speed and expansion ratio). The expansion ratio is approximated as ``E(phi) = 1 + (E_st - 1) * min(phi, 1/phi)`` - a stated
    approximation; replace by a flame-temperature table for design use.
    """
    import numpy as np

    ft = np.asarray(ft_field, dtype=float)
    v = np.asarray(cell_volumes, dtype=float)
    afr = FUELS[fuel]["afr_st"]
    phi = np.where(ft > 0, (ft / np.maximum(1 - ft, 1e-12)) * afr, 0.0)
    e_st = ref_expansion or 8.0
    su = np.array([laminar_speed_scope(fuel, float(x)) for x in phi])
    e = 1.0 + (e_st - 1.0) * np.minimum(phi, 1.0 / np.maximum(phi, 1e-9))
    su1 = laminar_speed_scope(fuel, 1.0)
    w = np.where(su > 0, su * (e - 1.0) / max(su1 * (e_st - 1.0), 1e-12), 0.0)
    flam = su > 0
    return {
        "flammable_volume_m3": float(v[flam].sum()),
        "esc_volume_m3": float((w * v).sum()),
        "volume_above_UEL_m3": (
            float(v[phi > 1.0][su[phi > 1.0] == 0].sum()) if (phi > 1.0).any() else 0.0
        ),
        "fuel_mass_fraction_weighted_ft_max": float(ft.max()) if ft.size else 0.0,
    }


def read_internal_field(path: Path):
    """Read an ASCII OpenFOAM volScalarField internalField (uniform or nonuniform List<scalar>) into a numpy array (None if uniform)."""
    import numpy as np

    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(", txt)
    if not m:
        u = re.search(r"internalField\s+uniform\s+([\d.eE+-]+);", txt)
        return float(u.group(1)) if u else None
    n = int(m.group(1))
    start = m.end()
    body = txt[start : txt.index(")", start)]
    return np.array(body.split(), dtype=float)[:n]


def read_cell_centres(path: Path):
    """Read a ``C`` (cell centres) volVectorField written by ``postProcess -func writeCellCentres``."""
    import numpy as np

    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\(", txt)
    n = int(m.group(1))
    body = txt[m.end() : txt.index("\n)\n", m.end())]
    vals = re.findall(r"\(([^()]+)\)", body)
    return np.array([[float(x) for x in v.split()] for v in vals[:n]])


def cloud_metrics_from_case(
    case_dir: Path,
    time_name: str,
    box: tuple[float, float, float, float, float, float],
    fuel: str,
    geom_time: str | None = None,
    rho_fuel_vol: float = 1.0,
    lfl_vol: float = 0.037,
    ufl_vol: float = 0.13,
    stoich_vol: float = 0.07,
) -> dict:
    """Flammable cloud metrics from the mixture fraction ``ft`` of a dispersion run inside ``box`` (x0 x1 y0 y1 z0 z1).

    ``ft`` is the fuel mass fraction. Volume fraction is derived with the fuel/air molar masses of the shipped fuel (stoichiometric mass ratio).
    Returns flammable volume (LFL..UFL), volume above UEL, the Q9-type equivalent stoichiometric volume and fuel mass in the box.
    """
    import numpy as np

    case_dir = Path(case_dir)
    ft = read_internal_field(case_dir / time_name / "ft")
    gt = geom_time or time_name
    vol = read_internal_field(case_dir / gt / "V")
    cc = read_cell_centres(case_dir / gt / "C")
    x0, x1, y0, y1, z0, z1 = box
    sel = (
        (cc[:, 0] >= x0)
        & (cc[:, 0] <= x1)
        & (cc[:, 1] >= y0)
        & (cc[:, 1] <= y1)
        & (cc[:, 2] >= z0)
        & (cc[:, 2] <= z1)
    )
    mw_f, mw_a = FUELS[fuel]["mw"], 28.85
    ftc = np.clip(ft[sel], 0.0, 1.0)
    vv = vol[sel]
    phi_vol = (ftc / mw_f) / (ftc / mw_f + (1 - ftc) / mw_a)
    flam = (phi_vol >= lfl_vol) & (phi_vol <= ufl_vol)
    out = equivalent_stoich_cloud(
        np.where(flam, ftc, 0.0), vv, fuel
    )  # only cells inside the real-mixture LFL..UFL contribute
    out.update(
        {
            "V_flammable_m3": float(vv[flam].sum()),
            "V_above_UFL_m3": float(vv[phi_vol > ufl_vol].sum()),
            "V_ge_50pct_LFL_m3": float(vv[phi_vol >= 0.5 * lfl_vol].sum()),
            "fuel_mass_in_box_kg": None,
            "max_vol_fraction": float(phi_vol.max()) if phi_vol.size else 0.0,
            "n_cells_box": int(sel.sum()),
        }
    )
    return out


# ----------------------------------------------------------------------------------------------------------------- verification
def closed_vessel_case(
    name: str = "closed_vessel",
    h: float = 0.05,
    side: float = 1.0,
    fuel: str = "methane",
) -> PdrCaseSpec:
    """1 m3 closed cube, stoichiometric premixed gas, central ignition: peak pressure ratio vs the adiabatic isochoric limit."""
    dom = Domain(
        fine=(0, side, 0, side, 0, side),
        far=(0, side, 0, side, 0, side),
        h=h,
        west_wall=False,
    )
    obst = _HEADER % ("dictionary", "obstaclesDict") + (
        "scale 1.0;\nverbose 0;\ncorner_stub\n{\n    enabled true;\n    obstacles\n    (\n"
        "        cyl { point (%.3f %.3f %.3f); direction z; length 0.06; diameter 0.02; }\n    );\n}\n"
        % (side - 0.04, side - 0.04, 0.0)
    )
    # PDRFoam needs the PDR fields (constant/betav...): a negligible 2 cm stub in a corner makes PDRsetFields write them
    spec = PdrCaseSpec(
        name=name,
        domain=dom,
        obstacles_dict=obst,
        fuel=fuel,
        cloud=Cloud(
            (-1, -1, -1), (side + 1, side + 1, side + 1), k0=0.1, length_scale=0.1
        ),
        ignition=Ignition(
            (side / 2,) * 3, diameter=3 * h, strength=10.0, duration=0.01
        ),
        end_time=0.6,
        write_interval=0.05,
        max_co=0.3,
        max_dt=1e-3,
        monitor_points={
            "centre": (side / 2,) * 3,
            "wall": (side - h / 2, side / 2, side / 2),
        },
        patches_wall_faces=(0, 1, 2, 3, 4, 5),
    )
    return spec


def open_flame_case(
    name: str = "open_flame",
    h: float = 0.05,
    half: float = 1.6,
    fuel: str = "methane",
    xi_model: str = "fixed",
) -> PdrCaseSpec:
    """Quiescent stoichiometric cube cloud in open air, central ignition: laminar flame-front speed vs sigma * S_L (known answer)."""
    dom = Domain(
        fine=(-half, half, -half, half, -half, half),
        far=(-half, half, -half, half, -half, half),
        h=h,
        west_wall=False,
    )
    obst = _HEADER % ("dictionary", "obstaclesDict") + (
        "scale 1.0;\nverbose 0;\ncorner_stub\n{\n    enabled true;\n    obstacles\n    (\n"
        "        cyl { point (%.3f %.3f %.3f); direction z; length 0.06; diameter 0.02; }\n    );\n}\n"
        % (half - 0.05, half - 0.05, -half + 0.01)
    )
    probes = {
        "r%03d" % int(100 * r): (r, 0.0, 0.0) for r in (0.4, 0.55, 0.7, 0.85, 1.0, 1.15)
    }
    return PdrCaseSpec(
        name=name,
        domain=dom,
        obstacles_dict=obst,
        fuel=fuel,
        xi_model=xi_model,
        cloud=Cloud((-half - 1,) * 3, (half + 1,) * 3, k0=0.01, length_scale=0.1),
        ignition=Ignition(
            (0.0, 0.0, 0.0), diameter=2.5 * h, strength=10.0, duration=0.02
        ),
        end_time=0.9,
        write_interval=0.1,
        n_outer=3,
        max_co=0.3,
        max_dt=2e-3,
        monitor_points=probes,
        patches_wall_faces=(),
    )
